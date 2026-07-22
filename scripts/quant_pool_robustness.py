#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETF Pool Robustness Study — REQ-363
====================================
回答三个问题：
  1. 策略是靠少数 ETF 撑起来还是普适于全池？（随机子集分布）
  2. 哪些扇区正向/负向贡献？（leave-one-sector-out）
  3. 池子大小是否有最优区间？（k-Sharpe 曲线）

用法：
  python scripts/quant_pool_robustness.py --phase 1    # leave-one-sector-out
  python scripts/quant_pool_robustness.py --phase 2    # random subsets
  python scripts/quant_pool_robustness.py --phase 3    # stratified vs random
  python scripts/quant_pool_robustness.py --phase all  # 全跑

不改引擎，不改参数，不改 universe config。纯研究脚本。
"""
import argparse
import csv
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime

# ensure project root on path
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)

import yaml
from scripts.quant_backtest import run_backtest

OUT_DIR = os.path.join(PROJ, "research", "pool_robustness")
UNIVERSE_PATH = os.path.join(PROJ, "config", "quant_universe.yaml")
PRESET = "gam-0"

# ── helpers ──────────────────────────────────────────────

def load_universe():
    """Return list of {code, name, sector} from config."""
    with open(UNIVERSE_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["universe"]


def sector_groups(etfs):
    """Group ETF codes by sector. Returns {sector: [code, ...]}."""
    g = defaultdict(list)
    for e in etfs:
        g[e["sector"]].append(e["code"])
    return dict(g)


def all_codes(etfs):
    return [e["code"] for e in etfs]


def run_one(label, codes):
    """Run a single gam-0 backtest with the given universe subset.  Returns dict of key metrics."""
    t0 = time.time()
    nav_df, signals, extra = run_backtest(
        preset=PRESET, universe_filter=codes, verbose=False
    )
    elapsed = time.time() - t0
    # extra values are already in % (e.g., annual_return=239.36 = 239.36%)
    m = {
        "label": label,
        "n_etfs": len(codes),
        "annual_return": extra.get("annual_return"),
        "sharpe": extra.get("sharpe"),
        "sortino": extra.get("sortino"),
        "max_drawdown": extra.get("max_drawdown"),
        "elapsed_s": round(elapsed, 1),
    }
    return m


def ensure_out_dir():
    os.makedirs(OUT_DIR, exist_ok=True)


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  -> saved {len(rows)} rows to {path}")


# ── Phase 1: leave-one-sector-out ────────────────────────

def phase1():
    print("=" * 60)
    print("Phase 1: leave-one-sector-out")
    print("=" * 60)

    etfs = load_universe()
    codes_all = all_codes(etfs)
    sectors = sector_groups(etfs)
    results = []

    # baseline — full pool
    print(f"\n[ 1/12] BASELINE  (n={len(codes_all)})")
    r = run_one("BASELINE", codes_all)
    r["sector_removed"] = "(none)"
    results.append(r)
    _print_metrics(r)

    # remove each sector
    for i, (sector, sector_codes) in enumerate(sorted(sectors.items()), start=2):
        subset = [c for c in codes_all if c not in sector_codes]
        label = f"-{sector}"
        print(f"\n[{i:2d}/12] {label}  (remove {len(sector_codes)}, keep {len(subset)})")
        r = run_one(label, subset)
        r["sector_removed"] = sector
        results.append(r)
        _print_metrics(r)

    # compute delta vs baseline
    bl = results[0]
    for r in results[1:]:
        if bl["sharpe"] is not None and r["sharpe"] is not None:
            r["delta_sharpe"] = round(r["sharpe"] - bl["sharpe"], 4)
        else:
            r["delta_sharpe"] = None
        r["delta_ar"] = (
            round(r["annual_return"] - bl["annual_return"], 1)
            if bl["annual_return"] is not None and r["annual_return"] is not None
            else None
        )

    ensure_out_dir()
    fields = [
        "sector_removed", "label", "n_etfs",
        "annual_return", "sharpe", "sortino",
        "max_drawdown", "delta_sharpe", "delta_ar", "elapsed_s",
    ]
    path = os.path.join(OUT_DIR, "leave_one_out.csv")
    write_csv(path, results, fields)

    # summary
    print("\n--- Phase 1 Summary (sorted by delta_sharpe) ---")
    sorted_results = sorted(
        [r for r in results if r.get("delta_sharpe") is not None],
        key=lambda r: r["delta_sharpe"],
    )
    for r in sorted_results:
        direction = (
            "拖后腿" if r["delta_sharpe"] > 0.05
            else "正向贡献" if r["delta_sharpe"] < -0.05
            else "影响不大"
        )
        print(f"  {r['sector_removed']:12s}  ΔSharpe={r['delta_sharpe']:+.4f}  ΔAR={r.get('delta_ar',0):+.1f}pp  [{direction}]")

    return results


# ── Phase 2: random subsets ──────────────────────────────

def phase2(k_values=None, n_per_k=20):
    if k_values is None:
        k_values = [10, 15, 20, 27, 35, 54]

    print("=" * 60)
    print(f"Phase 2: random subsets  k={k_values}  n={n_per_k}")
    print("=" * 60)

    etfs = load_universe()
    codes_all = all_codes(etfs)
    results = []
    total_runs = len(k_values) * n_per_k

    run_idx = 0
    for k in k_values:
        actual_k = min(k, len(codes_all))
        for i in range(n_per_k):
            run_idx += 1
            subset = random.sample(codes_all, actual_k)
            label = f"k={k}_run={i+1}"
            print(f"\n[{run_idx}/{total_runs}] {label}  (n={actual_k})")
            r = run_one(label, subset)
            r["k"] = k
            r["run_id"] = i + 1
            results.append(r)
            _print_metrics(r)

    ensure_out_dir()
    fields = [
        "k", "run_id", "label", "n_etfs",
        "annual_return", "sharpe", "sortino",
        "max_drawdown", "elapsed_s",
    ]
    path = os.path.join(OUT_DIR, "random_subsets.csv")
    write_csv(path, results, fields)

    # summary by k
    print("\n--- Phase 2 Summary (mean Sharpe by k) ---")
    by_k = defaultdict(list)
    for r in results:
        if r["sharpe"] is not None:
            by_k[r["k"]].append(r["sharpe"])
    for k in sorted(by_k):
        vals = by_k[k]
        mean_s = sum(vals) / len(vals)
        std_s = (sum((v - mean_s) ** 2 for v in vals) / len(vals)) ** 0.5
        print(f"  k={k:2d}  mean_Sharpe={mean_s:.4f}  std={std_s:.4f}  n={len(vals)}")

    return results


# ── Phase 3: stratified vs random ────────────────────────

def phase3(k=27, n=20):
    print("=" * 60)
    print(f"Phase 3: stratified vs random  k={k}  n={n}")
    print("=" * 60)

    etfs = load_universe()
    codes_all = all_codes(etfs)
    sectors = sector_groups(etfs)
    sector_names = sorted(sectors)
    results = []

    # random
    print("\n-- Random --")
    for i in range(n):
        subset = random.sample(codes_all, k)
        label = f"random_run={i+1}"
        print(f"\n[{i+1}/{n}] {label}")
        r = run_one(label, subset)
        r["method"] = "random"
        r["run_id"] = i + 1
        results.append(r)
        _print_metrics(r)

    # stratified: at least 1 from each sector, rest random
    print("\n-- Stratified --")
    for i in range(n):
        subset = []
        for sn in sector_names:
            subset.append(random.choice(sectors[sn]))
        # fill remaining from pool not yet picked
        remaining = [c for c in codes_all if c not in subset]
        extra_needed = k - len(subset)
        if extra_needed > 0:
            subset.extend(random.sample(remaining, extra_needed))
        label = f"stratified_run={i+1}"
        print(f"\n[{i+1}/{n}] {label}  (n={len(subset)})")
        r = run_one(label, subset)
        r["method"] = "stratified"
        r["run_id"] = i + 1
        results.append(r)
        _print_metrics(r)

    ensure_out_dir()
    fields = [
        "method", "run_id", "label", "n_etfs",
        "annual_return", "sharpe", "sortino",
        "max_drawdown", "elapsed_s",
    ]
    path = os.path.join(OUT_DIR, "stratified_vs_random.csv")
    write_csv(path, results, fields)

    # summary
    rand_sharpes = [r["sharpe"] for r in results if r["method"] == "random" and r["sharpe"] is not None]
    strat_sharpes = [r["sharpe"] for r in results if r["method"] == "stratified" and r["sharpe"] is not None]
    print("\n--- Phase 3 Summary ---")
    if rand_sharpes:
        print(f"  random:     mean_Sharpe={sum(rand_sharpes)/len(rand_sharpes):.4f}")
    if strat_sharpes:
        print(f"  stratified: mean_Sharpe={sum(strat_sharpes)/len(strat_sharpes):.4f}")

    return results


# ── output helpers ───────────────────────────────────────

def _print_metrics(r):
    # extra values: annual_return / max_drawdown already in %; sharpe/sortino are decimals
    ar = f"{r['annual_return']:.1f}%" if r.get("annual_return") is not None else "?"
    md = f"{r['max_drawdown']:.1f}%" if r.get("max_drawdown") is not None else "?"
    sh = f"{r['sharpe']:.2f}" if r.get("sharpe") is not None else "?"
    print(f"    AR={ar}  Sharpe={sh}  MDD={md}  ({r['elapsed_s']}s)")


def _pct(v):
    """Format a value already in percent (e.g., 239.36 -> '239.4%')."""
    return f"{v:.1f}%" if v is not None else "?"


def _fmt(v):
    return f"{v:.2f}" if v is not None else "?"


# ── CLI ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ETF Pool Robustness Study (REQ-363)")
    parser.add_argument("--phase", choices=["1", "2", "3", "all"], default="all",
                        help="Which phase to run (default: all)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    random.seed(args.seed)
    ensure_out_dir()
    t_start = time.time()

    if args.phase in ("1", "all"):
        phase1()

    if args.phase in ("2", "all"):
        phase2()

    if args.phase in ("3", "all"):
        phase3()

    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"Done. Total elapsed: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
