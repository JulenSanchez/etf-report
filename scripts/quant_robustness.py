#!/usr/bin/env python3
"""
REQ-222: Multi-period robustness test.
Split 6Y backtest into sub-periods to verify strategy works in all market regimes.
CS 0.5 baseline calibrated on full history → sub-period sigma distribution must be checked.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_backtest import run_backtest, load_config

RESULTS_DIR = SKILL_DIR / "research" / "strategy" / "robustness"

# Three fixed ~2Y sub-periods covering different market regimes
FIXED_PERIODS = [
    ("P1_COVID",    "2020-05-27", "2022-05-26"),
    ("P2_CRISIS",   "2022-05-27", "2024-05-26"),
    ("P3_AI_BOOM",  "2024-05-27", "2026-05-26"),
]

ROLLING_WINDOW_YEARS = 1
ROLLING_STEP_MONTHS = 3


def compute_metrics(nav_df, signal_history, extra):
    """Extract standard metrics from a backtest run."""
    if nav_df is None or len(nav_df) == 0:
        return None

    nav = nav_df["nav"].values
    initial = float(nav[0])
    final = float(nav[-1])
    total_return = (final / initial - 1.0) * 100.0
    days = len(nav_df)
    annual_return = ((final / initial) ** (365.0 / days) - 1.0) * 100.0 if days > 20 else 0

    # MDD
    peak = np.maximum.accumulate(nav)
    drawdown = (nav - peak) / peak * 100.0
    mdd = float(drawdown.min())

    # Sharpe/Sortino — use pct_change() directly to avoid %/decimal confusion
    daily_returns = nav_df["nav"].pct_change().dropna().values
    if len(daily_returns) > 20:
        mu = float(np.mean(daily_returns)) * 252
        sigma = float(np.std(daily_returns)) * np.sqrt(252)
        sharpe = (mu - 0.02) / sigma if sigma > 0 else 0
        downside = daily_returns[daily_returns < 0]
        sortino_sigma = float(np.std(downside)) * np.sqrt(252) if len(downside) > 0 else sigma
        sortino = (mu - 0.02) / sortino_sigma if sortino_sigma > 0 else 0
        calmar = annual_return / abs(mdd) if abs(mdd) > 0 else 0
    else:
        sharpe = sortino = calmar = 0

    # Win rate from trade_log
    trade_log = extra.get("trade_log", [])
    if trade_log:
        wins = sum(1 for t in trade_log if t.get("pnl_pct", 0) > 0)
        win_rate = wins / len(trade_log) * 100.0
    else:
        win_rate = 0

    # sigma_top6 stats from signal_history
    sigma_vals = []
    for sig in signal_history:
        scores = sig.get("scores", {})
        top6 = sig.get("top6", [])
        if not scores or len(top6) < 2:
            continue
        all_s = np.array(list(scores.values()))
        top6_s = np.array([scores[c] for c in top6 if c in scores])
        if len(all_s) > 5 and len(top6_s) > 1:
            mu_s = float(all_s.mean())
            sd_s = max(float(all_s.std()), 0.02)
            z_top6 = (top6_s - mu_s) / sd_s
            sigma_vals.append(float(z_top6.std()))

    sigma_stats = {}
    if sigma_vals:
        sigma_stats = {
            "sigma_top6_mean": round(float(np.mean(sigma_vals)), 4),
            "sigma_top6_median": round(float(np.median(sigma_vals)), 4),
            "sigma_top6_std": round(float(np.std(sigma_vals)), 4),
            "sigma_top6_count": len(sigma_vals),
        }

    return {
        "start_date": nav_df["date"].iloc[0].strftime("%Y-%m-%d"),
        "end_date": nav_df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "trading_days": days,
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "max_drawdown": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "trade_count": extra.get("trade_count", 0),
        "win_rate": round(win_rate, 1),
        **sigma_stats,
    }


def compute_robustness_score(period_metrics):
    """0-1 score: >0.7 robust, 0.4-0.7 moderate, <0.4 overfit risk."""
    returns = [m["total_return"] for m in period_metrics]
    mdds = [m["max_drawdown"] for m in period_metrics]
    sharpes = [m["sharpe"] for m in period_metrics]

    # Return stability: worst / mean (negative worst = 0)
    mean_ret = np.mean(returns)
    worst_ret = min(returns)
    if mean_ret > 0 and worst_ret > 0:
        ret_score = min(worst_ret / mean_ret, 1.0)
    elif mean_ret > 0 and worst_ret <= 0:
        ret_score = 0.0
    else:
        ret_score = 0.0

    # Risk consistency: 1 - CV of MDDs
    mean_mdd = abs(np.mean(mdds))
    std_mdd = np.std(mdds)
    risk_score = max(0.0, 1.0 - std_mdd / mean_mdd) if mean_mdd > 0 else 1.0

    # Sharpe floor: worst Sharpe should be > 0
    worst_sharpe = min(sharpes)
    if worst_sharpe > 0.5:
        sharpe_score = 1.0
    elif worst_sharpe > 0:
        sharpe_score = worst_sharpe / 0.5
    else:
        sharpe_score = 0.0

    total = (ret_score + risk_score + sharpe_score) / 3.0
    return {
        "total": round(total, 3),
        "return_stability": round(ret_score, 2),
        "risk_consistency": round(risk_score, 2),
        "sharpe_floor": round(sharpe_score, 2),
        "grade": "robust" if total > 0.7 else ("moderate" if total > 0.4 else "overfit_risk"),
    }


def run_fixed_periods(preset, preloaded):
    """Run backtest on 3 fixed sub-periods."""
    results = []
    for label, start, end in FIXED_PERIODS:
        nav_df, signal_history, extra = run_backtest(
            start_date=start, end_date=end,
            preset=preset, preloaded=preloaded,
            return_details=False, return_debug=False,
        )
        m = compute_metrics(nav_df, signal_history, extra)
        if m:
            m["period"] = label
            m["market"] = {
                "P1_COVID": "COVID recovery + China tech crackdown",
                "P2_CRISIS": "Zero-COVID exit + property crisis",
                "P3_AI_BOOM": "AI bull + policy stimulus",
            }.get(label, "")
            results.append(m)
    return results


def run_rolling_windows(preset, preloaded, base_start="2020-05-27", base_end="2026-05-26"):
    """Run 1Y rolling windows with quarterly steps."""
    results = []
    window_days = ROLLING_WINDOW_YEARS * 365
    step_days = ROLLING_STEP_MONTHS * 30

    start_dt = datetime.strptime(base_start, "%Y-%m-%d")
    end_dt = datetime.strptime(base_end, "%Y-%m-%d")

    current = start_dt
    while True:
        window_end = current + timedelta(days=window_days)
        if window_end > end_dt:
            break
        s = current.strftime("%Y-%m-%d")
        e = window_end.strftime("%Y-%m-%d")
        label = f"ROLL_{s[:7]}_{e[:7]}"

        nav_df, signal_history, extra = run_backtest(
            start_date=s, end_date=e,
            preset=preset, preloaded=preloaded,
            return_details=False, return_debug=False,
        )
        m = compute_metrics(nav_df, signal_history, extra)
        if m:
            m["period"] = label
            results.append(m)

        current += timedelta(days=step_days)

    return results


def strip_preloaded(nav_df, signal_history, extra):
    """Return a lightweight preloaded dict from a completed run for reuse."""
    return None  # cache disabled — each run is independent for correctness


def print_report(fixed, rolling, score, preset):
    """Print terminal summary."""
    print(f"\n{'='*80}")
    print(f"  REQ-222 Multi-Period Robustness — {preset}")
    print(f"{'='*80}")

    # Fixed periods comparison
    print(f"\n  {'Period':<16} {'Years':>6} {'Total%':>9} {'MDD%':>7} {'Sharpe':>7} {'Sortino':>7} {'Calmar':>7} {'Win%':>7} {'σ_mean':>7}")
    print(f"  {'─'*16} {'─'*6} {'─'*9} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
    for m in fixed:
        yrs = m["trading_days"] / 252
        sig = m.get("sigma_top6_mean", 0)
        print(f"  {m['period']:<16} {yrs:>5.1f}Y {m['total_return']:>+8.1f}% {m['max_drawdown']:>6.1f}% "
              f"{m['sharpe']:>6.2f}  {m['sortino']:>6.2f}  {m['calmar']:>6.2f}  "
              f"{m['win_rate']:>5.1f}% {sig:>6.3f}")

    # Robustness score
    s = score
    print(f"\n  Robustness Score: {s['total']:.2f} ({s['grade']})")
    print(f"    Return stability:  {s['return_stability']:.2f}  (worst/mean of 3 periods)")
    print(f"    Risk consistency:  {s['risk_consistency']:.2f}  (1 - CV of MDDs)")
    print(f"    Sharpe floor:      {s['sharpe_floor']:.2f}  (worst Sharpe / 0.5)")

    # Rolling window summary
    if rolling:
        rets = [m["total_return"] for m in rolling]
        mdds = [m["max_drawdown"] for m in rolling]
        print(f"\n  Rolling 1Y windows ({len(rolling)} windows):")
        print(f"    Return: min={min(rets):+.1f}%  max={max(rets):+.1f}%  mean={np.mean(rets):+.1f}%")
        print(f"    MDD:    min={min(mdds):.1f}%  max={max(mdds):.1f}%  mean={np.mean(mdds):.1f}%")
        # Count negative rolling windows
        neg = sum(1 for r in rets if r < 0)
        if neg > 0:
            print(f"    WARNING: {neg}/{len(rolling)} rolling windows had negative returns")

    # Sigma check
    if fixed:
        sigmas = [m.get("sigma_top6_mean", 0) for m in fixed if m.get("sigma_top6_mean")]
        if sigmas:
            sig_range = max(sigmas) - min(sigmas)
            if sig_range > 0.15:
                print(f"\n  CS WARNING: sigma_top6 mean drifts {sig_range:.3f} across periods (>0.15)")
                print(f"    The 0.5 baseline may not be stable. Consider rolling-window baseline (see research doc section 7.1).")
            else:
                print(f"\n  CS OK: sigma_top6 mean range {sig_range:.3f} within 0.15 tolerance")

    print(f"\n{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="REQ-222 Multi-period robustness test")
    parser.add_argument("--preset", nargs="+", default=["preset1"],
                        help="Presets to test (default: preset1)")
    parser.add_argument("--no-rolling", action="store_true",
                        help="Skip rolling window analysis")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON path (default: research/strategy/robustness/results.json)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (RESULTS_DIR / "results.json")

    all_results = {}

    for preset in args.preset:
        print(f"\nRunning robustness analysis for {preset}...")

        # Preload once
        print("  Loading data...")
        cfg = load_config(preset=preset)
        preloaded = None  # Let each run_backtest load independently for correctness

        print("  Running fixed sub-periods...")
        fixed = run_fixed_periods(preset, preloaded)

        rolling = []
        if not args.no_rolling:
            print("  Running rolling windows...")
            rolling = run_rolling_windows(preset, preloaded)

        if fixed:
            score = compute_robustness_score(fixed)
        else:
            score = {"total": 0, "grade": "no_data"}

        print_report(fixed, rolling, score, preset)

        all_results[preset] = {
            "preset": preset,
            "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fixed_periods": fixed,
            "rolling_windows": rolling,
            "robustness_score": score,
        }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"Results saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
