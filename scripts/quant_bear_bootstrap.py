#!/usr/bin/env python3
"""
REQ-250 方向1: Bear Market Bootstrap.
Extract daily returns from bear market period (2022 high to 2024 low),
bootstrap to see which (C, CS) loses least in a purely hostile environment.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_backtest import run_backtest
from quant_data_utils import load_etf_data as _load_etf_data
from benchmark_data import load_hs300_daily_cached, build_hs300_weekly, build_ma_trend_cache

RESULTS_DIR = SKILL_DIR / "research" / "strategy" / "kelly"

# Bear market period: Jan 2022 (China tech peak) → Feb 2024 (pre-AI rally low)
BEAR_START = "2022-01-04"
BEAR_END = "2024-02-05"

# Test key (C, CS) combos: presets + extreme variants
TEST_COMBOS = [
    (0.5, 0, "Static C"),         # preset2 baseline
    (0.5, 3, "C=.5 CS=3"),
    (0.5, 10, "Preset1"),         # current
    (1.0, 0, "C=1.0 CS=0"),
    (1.0, 3, "C=1.0 CS=3"),
    (1.0, 4.8, "集中趋势4.8"),
    (1.4, 4.8, "Kelly 1.4/4.8"),  # REQ-250 found
    (0.2, 0.5, "Low CS 0.5"),
    (0.1, 0, "最低风险"),
    (1.5, 5, "最高风险"),
]

N_BOOTSTRAP = 1000


def preload_data(preset):
    cfg = _load_config(preset)
    universe = cfg["universe"]
    data_dir = str(SKILL_DIR / "data" / "quant")
    all_daily, all_weekly = {}, {}
    for etf in universe:
        code = etf["code"]
        daily, weekly = _load_etf_data(code, data_dir)
        if daily is not None:
            all_daily[code] = daily
        if weekly is not None:
            all_weekly[code] = weekly
    hs300_daily = load_hs300_daily_cached()
    hs300_weekly = build_hs300_weekly(hs300_daily) if hs300_daily is not None else None
    hs300_above_ma = build_ma_trend_cache(hs300_daily, hs300_weekly, period=26)
    return {"all_daily": all_daily, "all_weekly": all_weekly, "hs300_above_ma": hs300_above_ma}


def _load_config(preset):
    import yaml
    config_path = SKILL_DIR / "config" / "quant_universe.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_override(c_val, cs_val):
    return {"position": {"concentration": c_val, "c_sensitivity": cs_val}}


def main():
    parser = argparse.ArgumentParser(description="Bear Market Bootstrap")
    parser.add_argument("--preset", default="preset1")
    parser.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    args = parser.parse_args()

    print(f"Bear Market Bootstrap — {args.preset}")
    print(f"  Period: {BEAR_START} → {BEAR_END}")
    print(f"  Combos: {len(TEST_COMBOS)}, Bootstrap: {args.bootstrap}/combo")

    print("  Preloading data...")
    preloaded = preload_data(args.preset)
    print(f"    Loaded {len(preloaded['all_daily'])} ETFs")

    results = []

    for c_val, cs_val, label in TEST_COMBOS:
        print(f"\n  [{label}] C={c_val} CS={cs_val}...", flush=True)

        # Run full 6Y backtest to get dated daily returns
        override = make_override(c_val, cs_val)
        nav_df, _signal, _extra = run_backtest(
            start_date="2020-05-27", end_date="2026-05-26",
            preset=args.preset, preloaded=preloaded,
            config_override=override,
            return_details=False, return_debug=False,
        )

        # Filter to bear market period
        dates = nav_df["date"]
        daily_all = nav_df["nav"].pct_change().values
        bear_mask = (dates >= BEAR_START) & (dates <= BEAR_END)
        bear_returns = daily_all[bear_mask]
        bear_returns = bear_returns[~np.isnan(bear_returns)]

        if len(bear_returns) < 50:
            print(f"    SKIP: only {len(bear_returns)} bear days")
            continue

        n_bear_days = len(bear_returns)
        bear_years = n_bear_days / 252

        # Full-period metrics for reference
        nav = nav_df["nav"].values
        total_return = (nav[-1] / nav[0] - 1.0) * 100.0
        drawdown = (nav - np.maximum.accumulate(nav)) / np.maximum.accumulate(nav) * 100.0
        mdd = float(drawdown.min())

        # Bear-period-only metrics (single path)
        bear_cum = np.prod(1.0 + bear_returns)
        bear_return = (bear_cum - 1.0) * 100.0
        bear_mean = float(np.mean(bear_returns)) * 252
        bear_std = float(np.std(bear_returns)) * np.sqrt(252)

        # Sortino on bear returns
        bear_down = bear_returns[bear_returns < 0]
        bear_down_std = float(np.std(bear_down)) * np.sqrt(252) if len(bear_down) > 0 else bear_std
        bear_sortino = (bear_mean - 0.02) / bear_down_std if bear_down_std > 0 else 0

        # Bootstrap: resample bear-market returns only
        finals = np.empty(args.bootstrap)
        for i in range(args.bootstrap):
            idx = np.random.randint(0, n_bear_days, size=n_bear_days)
            finals[i] = np.prod(1.0 + bear_returns[idx])

        median_final = float(np.median(finals))
        p5_final = float(np.percentile(finals, 5))
        p1_final = float(np.percentile(finals, 1))
        ruin_prob = float(np.mean(finals < 1.0)) * 100.0
        geom_growth = float(np.log(median_final)) / bear_years if median_final > 0 else -999

        entry = {
            "label": label, "C": c_val, "CS": cs_val,
            "bear_days": n_bear_days,
            "bear_return_actual": round(bear_return, 2),
            "bear_annual_mean": round(bear_mean * 100, 2),
            "bear_annual_std": round(bear_std * 100, 2),
            "bear_sortino": round(bear_sortino, 2),
            "full_total_return": round(total_return, 2),
            "full_mdd": round(mdd, 2),
            "bootstrap_median": round(median_final, 4),
            "bootstrap_p5": round(p5_final, 4),
            "bootstrap_p1": round(p1_final, 4),
            "bootstrap_ruin_pct": round(ruin_prob, 2),
            "bootstrap_geom": round(geom_growth, 4),
        }
        results.append(entry)

        print(f"    Bear actual: {bear_return:+.1f}%  |  Bootstrap median: {median_final:.4f}x  "
              f"P5: {p5_final:.4f}x  ruin: {ruin_prob:.1f}%  geom: {geom_growth:.4f}")

    if not results:
        print("ERROR: No results")
        return 1

    # Print summary
    print(f"\n{'='*95}")
    print(f"  Bear Market Bootstrap — {args.preset}")
    print(f"  Period: {BEAR_START} → {BEAR_END}")
    print(f"{'='*95}")

    # Sort by bootstrap median (best = least loss / highest median during bear)
    sorted_by_median = sorted(results, key=lambda r: r["bootstrap_median"], reverse=True)
    print(f"\n  Ranked by Bootstrap Median (bear-only returns resampled {args.bootstrap}×):")
    print(f"  {'Rank':<5} {'Label':<16} {'C':<6} {'CS':<6} {'ActBear%':>8} {'B-Median':>9} {'B-P5':>9} {'B-Ruin%':>7} {'B-Geom':>7} {'Full%':>8}")
    print(f"  {'─'*5} {'─'*16} {'─'*6} {'─'*6} {'─'*8} {'─'*9} {'─'*9} {'─'*7} {'─'*7} {'─'*8}")
    for i, r in enumerate(sorted_by_median):
        marker = " <-- BEST" if i == 0 else ""
        print(f"  {i+1:<5} {r['label']:<16} {r['C']:<6} {r['CS']:<6} "
              f"{r['bear_return_actual']:>+7.1f}% {r['bootstrap_median']:>8.4f}x "
              f"{r['bootstrap_p5']:>8.4f}x {r['bootstrap_ruin_pct']:>5.1f}% "
              f"{r['bootstrap_geom']:>6.4f} {r['full_total_return']:>+7.1f}%{marker}")

    # Sort by bootstrap P5 (worst-case scenario)
    sorted_by_p5 = sorted(results, key=lambda r: r["bootstrap_p5"], reverse=True)
    print(f"\n  Ranked by Bootstrap P5 (worst 5% scenario):")
    print(f"  {'Rank':<5} {'Label':<16} {'C':<6} {'CS':<6} {'B-P5':>9} {'B-Median':>9} {'ActBear%':>8}")
    print(f"  {'─'*5} {'─'*16} {'─'*6} {'─'*6} {'─'*9} {'─'*9} {'─'*8}")
    for i, r in enumerate(sorted_by_p5[:10]):
        marker = " <-- BEST" if i == 0 else ""
        print(f"  {i+1:<5} {r['label']:<16} {r['C']:<6} {r['CS']:<6} "
              f"{r['bootstrap_p5']:>8.4f}x {r['bootstrap_median']:>8.4f}x "
              f"{r['bear_return_actual']:>+7.1f}%{marker}")

    # Analysis: do high-CS combos suffer more in bear?
    print(f"\n  Analysis:")
    print(f"  {'Label':<16} {'CS':<6} {'BearActual':>10} {'B-Med':>8} {'σ_bear/yr':>10}")
    print(f"  {'─'*16} {'─'*6} {'─'*10} {'─'*8} {'─'*10}")
    for r in sorted(results, key=lambda r: r["CS"]):
        print(f"  {r['label']:<16} {r['CS']:<6} {r['bear_return_actual']:>+9.1f}% "
              f"{r['bootstrap_median']:>7.4f}x {r['bear_annual_std']:>9.1f}%")

    # Save
    output_path = RESULTS_DIR / "bear_bootstrap.json"
    output = {
        "preset": args.preset,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bear_period": {"start": BEAR_START, "end": BEAR_END},
        "n_bootstrap": args.bootstrap,
        "results": sorted_by_median,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")
    print(f"{'='*95}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
