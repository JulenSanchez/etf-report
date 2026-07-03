#!/usr/bin/env python3
"""Standalone optimization pipeline — runs multiple schools sequentially.

Replaces ad-hoc temp scripts and Desktop .bat files. Features:
  - Pre-flight validation (Python + optuna + data)
  - Sequential school execution with per-school frontier generation
  - Auto-skip schools whose pool was already updated today
  - Timestamped logging
  - Resilient: one school failure doesn't block the rest

Usage:
  python scripts/run_optimization.py
  python scripts/run_optimization.py --schools gambler,zen
  python scripts/run_optimization.py --trials 50 --max-rounds 5
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT / "research" / "params" / "runs"
POOL_DIR = PROJECT / "research" / "params"

# ── Defaults (matching production run parameters) ──
DEFAULTS = {
    "trials_per_round": 100,
    "max_rounds": 8,
    "start_date": "2020-07-03",
    "schools": ["gambler", "zen", "actuary"],
}

# Per-school metric (matches iterative_optimizer.py _DF)
SCHOOL_METRICS = {
    "gambler": "6y_ar",
    "zen": "6y_sortino",
    "actuary": "6y_calmar",
}


def log(msg: str, log_path: Path = None):
    """Print + append to log file."""
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def preflight(python: str) -> bool:
    """Validate environment before starting long-running work."""
    ok = True

    # 1. Python exists
    py = Path(python)
    if not py.exists():
        log(f"  FAIL: Python not found: {python}")
        return False

    # 2. optuna importable
    r = subprocess.run(
        [python, "-c", "import optuna"],
        capture_output=True, text=True, cwd=PROJECT,
    )
    if r.returncode != 0:
        log(f"  FAIL: optuna not installed in {python}")
        log(f"    stderr: {r.stderr.strip()[:200]}")
        ok = False

    # 3. Core modules importable
    r = subprocess.run(
        [python, "-c",
         "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'scripts'); "
         "from etf_report.core.quant_contract import load_pool, save_pool, build_frontier_output"],
        capture_output=True, text=True, cwd=PROJECT,
    )
    if r.returncode != 0:
        log(f"  FAIL: core modules not importable")
        log(f"    stderr: {r.stderr.strip()[:200]}")
        ok = False

    # 4. quant_backtest importable (needed for frontier re-validation)
    r = subprocess.run(
        [python, "-c",
         "import sys; sys.path.insert(0,'scripts'); "
         "from quant_backtest import run_backtest"],
        capture_output=True, text=True, cwd=PROJECT,
    )
    if r.returncode != 0:
        log(f"  FAIL: quant_backtest not importable")
        log(f"    stderr: {r.stderr.strip()[:200]}")
        ok = False

    return ok


def pool_updated_today(school: str) -> bool:
    """Check if pool.json was modified today (skip if so)."""
    pool_path = POOL_DIR / school / "pool.json"
    if not pool_path.exists():
        return False
    mtime = datetime.fromtimestamp(pool_path.stat().st_mtime)
    return mdate.date() == datetime.now().date()


def run_school(school: str, python: str, args, log_path: Path) -> bool:
    """Run iterative_optimizer for one school. Returns True on success."""
    metric = SCHOOL_METRICS[school]
    cmd = [
        python,
        str(PROJECT / "scripts" / "iterative_optimizer.py"),
        "--school", school,
        "--trials-per-round", str(args.trials),
        "--max-rounds", str(args.max_rounds),
        "--start-date", args.start_date,
    ]
    log(f"  Cmd: {' '.join(cmd)}", log_path)
    t0 = time.time()

    result = subprocess.run(
        cmd, cwd=PROJECT,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    elapsed = time.time() - t0
    log(f"  Exit: {result.returncode} | Elapsed: {elapsed/60:.0f}min", log_path)

    # Append full output to log
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n--- STDOUT ---\n")
        f.write(result.stdout or "(empty)")
        if result.stderr:
            f.write("\n--- STDERR ---\n")
            f.write(result.stderr[:5000])

    return result.returncode == 0


def build_frontier(school: str, python: str, log_path: Path) -> int:
    """Build frontier file for a school. Returns number of frontier points."""
    code = f"""
import sys
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from etf_report.core.quant_contract import build_frontier_output
result = build_frontier_output(school="{school}", start_date="2020-07-03")
print(f"{{result['points']}} frontier points, {{result['total_trials']}} total trials")
"""
    cmd = [python, "-c", code]
    log(f"  Building frontier for {school}...", log_path)
    result = subprocess.run(
        cmd, cwd=PROJECT,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    output = (result.stdout or "").strip()
    if output:
        log(f"  {output}", log_path)
    if result.stderr:
        # Only log stderr lines that aren't progress bars
        stderr_lines = [l for l in result.stderr.split('\n')
                       if l.strip() and 'WARN' not in l]
        if stderr_lines:
            log(f"  stderr: {stderr_lines[-1][:200]}", log_path)

    # Parse point count from output
    try:
        return int(output.split()[0]) if output else 0
    except (ValueError, IndexError):
        return 0


def main():
    p = argparse.ArgumentParser(
        description="Standalone multi-school optimization pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_optimization.py
  python scripts/run_optimization.py --schools zen,actuary
  python scripts/run_optimization.py --schools gambler --trials 50 --max-rounds 5
  python scripts/run_optimization.py --no-skip  # force re-run even if pool updated today
        """,
    )
    p.add_argument("--schools", default=",".join(DEFAULTS["schools"]),
                   help="Comma-separated school list (default: gambler,zen,actuary)")
    p.add_argument("--trials", type=int, default=DEFAULTS["trials_per_round"],
                   help=f"Trials per round (default: {DEFAULTS['trials_per_round']})")
    p.add_argument("--max-rounds", type=int, default=DEFAULTS["max_rounds"],
                   help=f"Max rounds per school (default: {DEFAULTS['max_rounds']})")
    p.add_argument("--start-date", default=DEFAULTS["start_date"],
                   help=f"Backtest start date (default: {DEFAULTS['start_date']})")
    p.add_argument("--python", default=sys.executable,
                   help="Python executable path (default: current interpreter)")
    p.add_argument("--no-skip", action="store_true",
                   help="Force re-run even if pool was already updated today")
    p.add_argument("--skip-frontier", action="store_true",
                   help="Skip frontier generation after optimization")
    args = p.parse_args()

    schools = [s.strip() for s in args.schools.split(",") if s.strip()]
    unknown = set(schools) - set(SCHOOL_METRICS)
    if unknown:
        print(f"ERROR: Unknown schools: {unknown}. Valid: {list(SCHOOL_METRICS)}")
        sys.exit(1)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"pipeline_{datetime.now():%Y%m%d_%H%M}.log"

    log(f"{'='*60}", log_path)
    log(f"  Optimization Pipeline", log_path)
    log(f"  Schools: {schools}", log_path)
    log(f"  Trials/round: {args.trials}, Max rounds: {args.max_rounds}", log_path)
    log(f"  Start date: {args.start_date}", log_path)
    log(f"  Python: {args.python}", log_path)
    log(f"  Log: {log_path}", log_path)
    log(f"{'='*60}", log_path)

    # ── Pre-flight ──
    log("\n--- Pre-flight ---", log_path)
    if not preflight(args.python):
        log("Pre-flight FAILED. Aborting.", log_path)
        sys.exit(1)
    log("Pre-flight OK", log_path)

    # ── Run schools ──
    results = {}
    for school in schools:
        log(f"\n{'='*60}", log_path)
        log(f"  SCHOOL: {school}", log_path)
        log(f"{'='*60}", log_path)

        if not args.no_skip and pool_updated_today(school):
            log(f"  SKIP: pool.json already updated today", log_path)
            results[school] = "skipped"
            continue

        ok = run_school(school, args.python, args, log_path)
        results[school] = "ok" if ok else "FAILED"

        # ── Build frontier after each school (even if optimization failed, try with existing pool) ──
        if not args.skip_frontier:
            n_pts = build_frontier(school, args.python, log_path)
            if n_pts > 0:
                log(f"  Frontier: {n_pts} points saved", log_path)
            else:
                log(f"  Frontier: 0 points (pool may be empty)", log_path)

    # ── Summary ──
    log(f"\n{'='*60}", log_path)
    log(f"  SUMMARY", log_path)
    for school, status in results.items():
        marker = {"ok": "[OK]", "FAILED": "[FAIL]", "skipped": "[SKIP]"}.get(status, "[??]")
        log(f"  {marker} {school}: {status}", log_path)
    log(f"  Log: {log_path}", log_path)
    log(f"  Done: {datetime.now():%Y-%m-%d %H:%M:%S}", log_path)

    # Return non-zero if any school failed
    if "FAILED" in results.values():
        sys.exit(1)


if __name__ == "__main__":
    main()
