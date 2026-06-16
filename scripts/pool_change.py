#!/usr/bin/env python3
"""Single-ETF pool change tool. Enforces docs/ops/pool-change.md SOP.
Usage:
  python scripts/pool_change.py --remove CODE
  python scripts/pool_change.py --add CODE --name "短名" --sector "扇区" --market sh|sz [--qdii]
  python scripts/pool_change.py --replace OLD NEW --name "短名" --sector "扇区" --market sh|sz [--qdii]

One ETF per invocation. Refuses to batch.
"""
import sys, os, json, time, argparse, subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "quant_universe.yaml"
TRACKING_DIR = PROJECT_ROOT / "research" / "pool" / "rounds"
BACKTEST_CMD = [sys.executable, str(PROJECT_ROOT / "scripts" / "quant_backtest.py"),
                "--preset", "gam-1", "--start", "2020-05-22", "--end", "2026-06-12"]
FETCH_CMD = [sys.executable, str(PROJECT_ROOT / "scripts" / "quant_data_fetcher.py")]

parser = argparse.ArgumentParser(description="Single-ETF pool change (SOP enforced)")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--remove", type=str, help="ETF code to remove")
group.add_argument("--add", type=str, help="ETF code to add")
group.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), help="Old → New ETF codes")
parser.add_argument("--name", type=str, help="Short display name (required for --add/--replace)")
parser.add_argument("--sector", type=str, help="Sector (required for --add/--replace)")
parser.add_argument("--market", type=str, choices=["sh", "sz"], help="Market (required for --add/--replace)")
parser.add_argument("--qdii", action="store_true", help="Mark as QDII ETF")
parser.add_argument("--round", type=str, help="Round date key (e.g. 2026-06-16)")
args = parser.parse_args()

# ── Safety: one ETF only ──
if args.add and args.remove:
    print("ERROR: Cannot --add and --remove in one invocation.")
    sys.exit(1)

import yaml, pandas as pd, numpy as np


def read_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def run_backtest():
    """Return (TR, MDD, Sharpe) from 6y gam-1 backtest."""
    r = subprocess.run(BACKTEST_CMD, capture_output=True, timeout=180,
                       encoding="utf-8", errors="replace")
    for line in r.stdout.split("\n"):
        if "总收益率" in line:
            tr = float(line.strip().split(":")[1].strip().replace("+", "").replace("%", ""))
        if "最大回撤" in line:
            mdd = float(line.strip().split(":")[1].strip().replace("%", ""))
        if "夏普比率" in line:
            sharpe = float(line.strip().split(":")[1].strip())
    return tr, mdd, sharpe


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


# ═══════════════════════════════════════════════════
# REMOVE
# ═══════════════════════════════════════════════════
if args.remove:
    code = args.remove
    cfg = read_config()
    entry = next((e for e in cfg["universe"] if e["code"] == code), None)
    if not entry:
        log(f"ERROR: {code} not in pool")
        sys.exit(1)

    log(f"Remove: {code} {entry['name']}")
    log("Step 1: baseline backtest...")
    tr0, mdd0, sh0 = run_backtest()
    log(f"  Baseline: TR={tr0:+.2f}% MDD={mdd0:.2f}% Sharpe={sh0:.2f}")

    log("Step 2: updating config...")
    cfg["universe"] = [e for e in cfg["universe"] if e["code"] != code]
    write_config(cfg)

    log("Step 3: verification backtest...")
    tr1, mdd1, sh1 = run_backtest()
    log(f"  After:    TR={tr1:+.2f}% MDD={mdd1:.2f}% Sharpe={sh1:.2f}")
    log(f"  Δ: TR={tr1-tr0:+.2f}pp MDD={mdd1-mdd0:+.2f}pp Sharpe={sh1-sh0:+.2f}")

    if abs(tr1 - tr0) / max(abs(tr0), 1) > 0.05:
        log(f"WARNING: TR change >5% — review before proceeding")
    log(f"DONE: {code} removed. Pool: {len(cfg['universe'])} ETFs")

# ═══════════════════════════════════════════════════
# ADD
# ═══════════════════════════════════════════════════
elif args.add:
    code = args.add
    if not args.name or not args.sector or not args.market:
        log("ERROR: --name, --sector, --market required for --add")
        sys.exit(1)

    cfg = read_config()
    if any(e["code"] == code for e in cfg["universe"]):
        log(f"ERROR: {code} already in pool")
        sys.exit(1)

    log(f"Add: {code} {args.name} ({args.sector}/{args.market})")

    log("Step 1: fetching K-line data...")
    r = subprocess.run(FETCH_CMD + ["--full", "--code", code], capture_output=True, timeout=180,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or "FAIL" in (r.stdout or ""):
        log(f"ERROR: data fetch failed\n{r.stdout}\n{r.stderr}")
        sys.exit(1)
    rows_line = [l for l in r.stdout.split("\n") if "daily+" in l]
    if rows_line:
        import re
        m = re.search(r"daily\+(\d+)", rows_line[0])
        daily_rows = int(m.group(1)) if m else 0
        log(f"  K-line fetched: {daily_rows} daily rows")
        if daily_rows < 250:
            log(f"WARNING: only {daily_rows} daily rows (<250). Proceed with caution.")

    log("Step 2: baseline backtest...")
    tr0, mdd0, sh0 = run_backtest()
    log(f"  Baseline: TR={tr0:+.2f}% MDD={mdd0:.2f}% Sharpe={sh0:.2f}")

    log("Step 3: updating config...")
    entry = {"code": code, "name": args.name, "market": args.market, "sector": args.sector}
    if args.qdii:
        entry["qdii"] = True
    cfg["universe"].append(entry)
    write_config(cfg)

    log("Step 4: verification backtest...")
    tr1, mdd1, sh1 = run_backtest()
    log(f"  After:    TR={tr1:+.2f}% MDD={mdd1:.2f}% Sharpe={sh1:.2f}")
    log(f"  Δ: TR={tr1-tr0:+.2f}pp MDD={mdd1-mdd0:+.2f}pp Sharpe={sh1-sh0:+.2f}")

    if tr1 < tr0 * 0.9:
        log(f"WARNING: TR dropped >10%. Review before continuing.")
    log(f"DONE: {code} added. Pool: {len(cfg['universe'])} ETFs")

# ═══════════════════════════════════════════════════
# REPLACE
# ═══════════════════════════════════════════════════
elif args.replace:
    old, new = args.replace
    if not args.name or not args.sector or not args.market:
        log("ERROR: --name, --sector, --market required for --replace")
        sys.exit(1)

    cfg = read_config()
    old_entry = next((e for e in cfg["universe"] if e["code"] == old), None)
    if not old_entry:
        log(f"ERROR: {old} not in pool")
        sys.exit(1)

    log(f"Replace: {old} {old_entry['name']} → {new} {args.name}")

    log("Step 1: fetching new ETF K-line...")
    r = subprocess.run(FETCH_CMD + ["--full", "--code", new], capture_output=True, timeout=180,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or "FAIL" in (r.stdout or ""):
        log(f"ERROR: data fetch failed")
        sys.exit(1)

    log("Step 2: baseline backtest...")
    tr0, mdd0, sh0 = run_backtest()
    log(f"  Baseline: TR={tr0:+.2f}% MDD={mdd0:.2f}% Sharpe={sh0:.2f}")

    log("Step 3: updating config (remove old + add new)...")
    cfg["universe"] = [e for e in cfg["universe"] if e["code"] != old]
    entry = {"code": new, "name": args.name, "market": args.market, "sector": args.sector}
    if args.qdii:
        entry["qdii"] = True
    cfg["universe"].append(entry)
    write_config(cfg)

    log("Step 4: verification backtest...")
    tr1, mdd1, sh1 = run_backtest()
    log(f"  After:    TR={tr1:+.2f}% MDD={mdd1:.2f}% Sharpe={sh1:.2f}")
    log(f"  Δ: TR={tr1-tr0:+.2f}pp MDD={mdd1-mdd0:+.2f}pp Sharpe={sh1-sh0:+.2f}")

    if tr1 < tr0 * 0.9:
        log(f"WARNING: TR dropped >10%.")
    log(f"DONE: {old}→{new}. Pool: {len(cfg['universe'])} ETFs")
