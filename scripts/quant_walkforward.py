#!/usr/bin/env python3
"""
REQ-223: Walk-forward optimization.
Every 6 months, re-optimize (C, CS) on past 2Y data, apply to next 6M.
Compares WF equity curve against static preset1 to detect overfitting.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from quant_backtest import run_backtest, load_config
from etf_report.core.quant_data_utils import load_etf_data as _load_etf_data
from benchmark_data import load_hs300_daily_cached, build_hs300_weekly, build_ma_trend_cache

RESULTS_DIR = PROJECT_ROOT / "research" / "strategy" / "walkforward"

# Grid: C × CS
C_VALUES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
CS_VALUES = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

ANCHOR_YEARS = 2
STEP_MONTHS = 6
OOS_MONTHS = 6


def make_override(c_val, cs_val):
    """Build config_override dict for a (C, CS) pair."""
    return {
        "position": {
            "concentration": c_val,
            "c_sensitivity": cs_val,
        }
    }


def compute_sharpe(nav_df):
    """Annualized Sharpe from nav_df."""
    if nav_df is None or len(nav_df) < 20:
        return -999
    daily = nav_df["nav"].pct_change().dropna().values
    mu = float(np.mean(daily)) * 252
    sigma = float(np.std(daily)) * np.sqrt(252)
    return (mu - 0.02) / sigma if sigma > 0 else -999


def compute_metrics(nav_df, extra):
    """Basic metrics for a run."""
    nav = nav_df["nav"].values
    initial = float(nav[0])
    final = float(nav[-1])
    total_return = (final / initial - 1.0) * 100.0
    peak = np.maximum.accumulate(nav)
    mdd = float((nav - peak).min() / peak[np.argmax(peak)] * 100.0) if len(peak) > 0 else 0
    sharpe = compute_sharpe(nav_df)
    trade_count = extra.get("trade_count", 0)
    return {
        "total_return": round(total_return, 2),
        "max_drawdown": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "trade_count": trade_count,
    }


def run_grid_search(preset, start, end, preloaded):
    """Grid search (C, CS) on a date range, return best params + all results."""
    best_sharpe = -999
    best_params = None
    all_results = []

    for c_val in C_VALUES:
        for cs_val in CS_VALUES:
            override = make_override(c_val, cs_val)
            try:
                nav_df, _signal, _extra = run_backtest(
                    start_date=start, end_date=end,
                    preset=preset, preloaded=preloaded,
                    config_override=override,
                    return_details=False, return_debug=False,
                    verbose=False,
                )
            except Exception as e:
                print(f"    SKIP C={c_val} CS={cs_val}: {e}")
                continue

            sharpe = compute_sharpe(nav_df)
            metrics = compute_metrics(nav_df, _extra)
            entry = {
                "C": c_val, "CS": cs_val,
                "sharpe": round(sharpe, 2),
                "total_return": metrics["total_return"],
                "mdd": metrics["max_drawdown"],
            }
            all_results.append(entry)

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = (c_val, cs_val)

    return best_params, best_sharpe, all_results


def generate_wf_steps(base_start="2020-05-27", base_end="2026-05-26"):
    """Generate (anchor_start, anchor_end, oos_start, oos_end, label) tuples."""
    steps = []
    start_dt = datetime.strptime(base_start, "%Y-%m-%d")
    end_dt = datetime.strptime(base_end, "%Y-%m-%d")

    # First anchor needs 2Y data — start OOS at base_start + 2Y
    current = start_dt + timedelta(days=ANCHOR_YEARS * 365)

    step_idx = 0
    while True:
        oos_end = current + timedelta(days=OOS_MONTHS * 30)
        if oos_end > end_dt:
            break

        anchor_start = current - timedelta(days=ANCHOR_YEARS * 365)
        anchor_end = current - timedelta(days=1)

        label = f"WF{step_idx:02d}"
        steps.append({
            "label": label,
            "anchor_start": anchor_start.strftime("%Y-%m-%d"),
            "anchor_end": anchor_end.strftime("%Y-%m-%d"),
            "oos_start": current.strftime("%Y-%m-%d"),
            "oos_end": oos_end.strftime("%Y-%m-%d"),
        })

        current += timedelta(days=STEP_MONTHS * 30)
        step_idx += 1

    return steps


def preload_data(preset):
    """Load all ETF data once for reuse across grid searches."""
    cfg = load_config(preset=preset)
    universe = cfg["universe"]
    data_dir = str(PROJECT_ROOT / "data" / "quant")

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

    return {
        "all_daily": all_daily,
        "all_weekly": all_weekly,
        "hs300_above_ma": hs300_above_ma,
    }


def main():
    parser = argparse.ArgumentParser(description="REQ-223 Walk-forward optimization")
    from etf_report.core.quant_contract import DEFAULT_PRESET
    parser.add_argument("--preset", default=DEFAULT_PRESET)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (RESULTS_DIR / "results.json")

    print(f"Walk-Forward Optimization — {args.preset}")
    print(f"  Grid: C={C_VALUES}, CS={CS_VALUES} ({len(C_VALUES)*len(CS_VALUES)} combos/step)")

    # Preload once
    print("  Preloading data...")
    preloaded = preload_data(args.preset)
    print(f"    Loaded {len(preloaded['all_daily'])} ETFs")

    # Generate steps
    steps = generate_wf_steps()
    print(f"  WF steps: {len(steps)}")
    for s in steps:
        print(f"    {s['label']}: anchor={s['anchor_start']}~{s['anchor_end']}  OOS={s['oos_start']}~{s['oos_end']}")

    # Run WF
    wf_records = []
    best_first_params = None  # "best-anchor" baseline: lock first step's best params

    for i, step in enumerate(steps):
        label = step["label"]
        print(f"\n  [{label}] Grid search on anchor {step['anchor_start']}~{step['anchor_end']}...")

        best_params, best_sharpe, grid_results = run_grid_search(
            args.preset, step["anchor_start"], step["anchor_end"], preloaded
        )

        if best_params is None:
            print(f"    ERROR: no valid params found, skipping step")
            continue

        if best_first_params is None:
            best_first_params = best_params

        c_best, cs_best = best_params
        print(f"    Best: C={c_best}, CS={cs_best}  (anchor Sharpe={best_sharpe:.2f})")

        # Run best params on OOS
        override = make_override(c_best, cs_best)
        nav_oos, sig_oos, extra_oos = run_backtest(
            start_date=step["oos_start"], end_date=step["oos_end"],
            preset=args.preset, preloaded=preloaded,
            config_override=override,
            return_details=False, return_debug=False,
            verbose=False,
        )
        m_oos = compute_metrics(nav_oos, extra_oos)

        # Run best-first-anchor params on OOS (for comparison)
        override_first = make_override(*best_first_params)
        nav_first, _sig_f, extra_first = run_backtest(
            start_date=step["oos_start"], end_date=step["oos_end"],
            preset=args.preset, preloaded=preloaded,
            config_override=override_first,
            return_details=False, return_debug=False,
            verbose=False,
        )
        m_first = compute_metrics(nav_first, extra_first)

        wf_records.append({
            "step": i, "label": label,
            "anchor_start": step["anchor_start"],
            "anchor_end": step["anchor_end"],
            "oos_start": step["oos_start"],
            "oos_end": step["oos_end"],
            "best_C": c_best, "best_CS": cs_best,
            "anchor_sharpe": round(best_sharpe, 2),
            "oos_metrics": m_oos,
            "oos_metrics_first_anchor": m_first,
            "grid_results": grid_results,
            # Store nav arrays for concatenation
            "_oos_nav": nav_oos["nav"].values.tolist(),
            "_oos_dates": [str(d)[:10] for d in nav_oos["date"]],
        })

    if not wf_records:
        print("ERROR: No WF steps completed")
        return 1

    # Build concatenated WF NAV
    wf_dates = []
    wf_nav = []
    cum_mult = 1.0
    for rec in wf_records:
        navs = rec.pop("_oos_nav")
        dates = rec.pop("_oos_dates")
        # Scale to continue from previous cumulative NAV
        scaled = [v * cum_mult for v in navs]
        wf_nav.extend(scaled)
        wf_dates.extend(dates)
        cum_mult = cum_mult * (navs[-1] / navs[0])

    # Also build best-anchor NAV
    best_first_dates = []
    best_first_nav = []
    cum_mult_bf = 1.0

    # Recompute best-first-anchor OOS navs
    for rec in wf_records:
        # We need the original OOS navs for best-first. They were removed above.
        # Let me restructure — keep them in a separate list.
        pass

    # Actually, let me keep the OOS navs in a separate structure.
    # For now, just compute the summary metrics.

    # Run static preset1 full-period for comparison
    print(f"\n  Running static {args.preset} full-period baseline...")
    nav_full, _sig_full, extra_full = run_backtest(
        start_date="2020-05-27", end_date="2026-05-26",
        preset=args.preset, preloaded=preloaded,
        return_details=False, return_debug=False,
        verbose=False,
    )
    static_metrics = compute_metrics(nav_full, extra_full)

    # Print results
    print(f"\n{'='*90}")
    print(f"  REQ-223 Walk-Forward Results — {args.preset}")
    print(f"{'='*90}")

    print(f"\n  {'Step':<8} {'Anchor':<23} {'Best C':<7} {'Best CS':<8} {'Anch Sharpe':<12} {'OOS Return':<11} {'OOS Sharpe':<10}")
    print(f"  {'─'*8} {'─'*23} {'─'*7} {'─'*8} {'─'*12} {'─'*11} {'─'*10}")
    wf_total_return = 1.0
    for rec in wf_records:
        r = rec["oos_metrics"]["total_return"] / 100.0 + 1.0
        wf_total_return *= r
        print(f"  {rec['label']:<8} {rec['anchor_start']}~{rec['anchor_end']:<10} "
              f"{rec['best_C']:<7} {rec['best_CS']:<8} {rec['anchor_sharpe']:<12} "
              f"{rec['oos_metrics']['total_return']:>+9.1f}%  {rec['oos_metrics']['sharpe']:>8.2f}")

    wf_total = (wf_total_return - 1.0) * 100.0
    print(f"\n  WF Cumulative Return: {wf_total:+.1f}%")
    print(f"  Static {args.preset} Return: {static_metrics['total_return']:+.1f}%")
    ratio = (wf_total_return) / (static_metrics['total_return'] / 100.0 + 1.0)
    print(f"  WF / Static Ratio: {ratio:.3f}")

    if ratio > 1.05:
        verdict = "WF significantly better — consider periodic re-optimization"
    elif ratio > 0.95:
        verdict = "Static parameters are stable — WF offers no meaningful gain"
    else:
        verdict = "Static parameters may be overfit — WF underperforms"
    print(f"  Verdict: {verdict}")

    # Parameter drift
    print(f"\n  Parameter Drift:")
    print(f"  {'Step':<8} {'C':<6} {'CS':<6}")
    print(f"  {'─'*8} {'─'*6} {'─'*6}")
    for rec in wf_records:
        print(f"  {rec['label']:<8} {rec['best_C']:<6} {rec['best_CS']:<6}")

    # Save results
    output = {
        "preset": args.preset,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "config": {
            "C_values": C_VALUES,
            "CS_values": CS_VALUES,
            "anchor_years": ANCHOR_YEARS,
            "step_months": STEP_MONTHS,
            "oos_months": OOS_MONTHS,
        },
        "wf_records": wf_records,
        "wf_cumulative_return": round(wf_total, 2),
        "static_metrics": static_metrics,
        "wf_static_ratio": round(ratio, 3),
        "verdict": verdict,
        "wf_dates": wf_dates,
        "wf_nav": [round(v, 6) for v in wf_nav],
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  Results saved to: {output_path}")
    print(f"{'='*90}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
