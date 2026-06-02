#!/usr/bin/env python3
"""
Optimize factor weights (w1/w3/w7) with Sortino×Calmar target.
Locks C=0.5, CS=10 (preset1 baseline), TPE Bayesian search.
Weights constraint: w1 + w3 + w7 = 1.0, all > 0.
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

import optuna
from quant_backtest import run_backtest
from quant_data_utils import load_etf_data as _load_etf_data
from benchmark_data import load_hs300_daily_cached, build_hs300_weekly, build_ma_trend_cache

RESULTS_DIR = SKILL_DIR / "research" / "strategy" / "factor_weights"
N_BOOTSTRAP = 1000
N_TRIALS = 30


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


def bootstrap_finals(daily_returns, n_bootstrap=N_BOOTSTRAP):
    n_days = len(daily_returns)
    finals = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = np.random.randint(0, n_days, size=n_days)
        finals[i] = np.prod(1.0 + daily_returns[idx])
    return finals


def evaluate(w1, w3, w7, preset, preloaded, n_boot):
    """Run backtest with given weights, return all metrics."""
    override = {
        "scoring": {"weights": {"ema_deviation": w1, "volume_ratio": w3, "log_return_deviation": w7}}
    }
    nav_df, _signal, _extra = run_backtest(
        start_date="2020-05-27", end_date="2026-05-26",
        preset=preset, preloaded=preloaded,
        config_override=override,
        return_details=False, return_debug=False,
    )

    daily_returns = nav_df["nav"].pct_change().dropna().values
    n_days = len(daily_returns)
    years = n_days / 252
    nav = nav_df["nav"].values

    total_return = (nav[-1] / nav[0] - 1.0) * 100.0
    drawdown = (nav - np.maximum.accumulate(nav)) / np.maximum.accumulate(nav) * 100.0
    mdd = float(drawdown.min())
    annual_return = ((nav[-1] / nav[0]) ** (1.0 / years) - 1.0) * 100.0

    mu = float(np.mean(daily_returns)) * 252
    sigma_daily = float(np.std(daily_returns))
    downside = daily_returns[daily_returns < 0]
    sortino_sigma = float(np.std(downside)) * np.sqrt(252) if len(downside) > 0 else sigma_daily * np.sqrt(252)
    sortino = (mu - 0.02) / sortino_sigma if sortino_sigma > 0 else 0

    calmar = annual_return / abs(mdd) if abs(mdd) > 0 else 0
    sortino_calmar = sortino * calmar

    # Bootstrap
    finals = bootstrap_finals(daily_returns, n_boot)
    median_final = float(np.median(finals))
    geom_growth = float(np.log(median_final)) / years if median_final > 0 else -999
    ruin_prob = float(np.mean(finals < 1.0)) * 100.0

    return {
        "w1": round(w1, 3), "w3": round(w3, 3), "w7": round(w7, 3),
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "mdd": round(mdd, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "sortino_calmar": round(sortino_calmar, 2),
        "n_days": n_days, "years": round(years, 2),
        "median_final": round(median_final, 4),
        "ruin_prob_pct": round(ruin_prob, 2),
        "geom_growth": round(geom_growth, 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Factor Weight Optimization (TPE)")
    parser.add_argument("--preset", default="preset1")
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    parser.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "results.json"

    print(f"Factor Weight Optimization — {args.preset} (C=0.5, CS=10 locked)")
    print(f"  Search: w1+w3+w7=1.0, all > 0 | Trials: {args.trials}")

    print("  Preloading data...")
    preloaded = preload_data(args.preset)
    print(f"    Loaded {len(preloaded['all_daily'])} ETFs")

    all_trials = []

    def objective(trial):
        # w1 + w3 + w7 = 1.0. Sample w1 first, then w3 from remaining budget.
        w1 = trial.suggest_float("w1", 0.05, 0.90)
        w3_upper = max(0.06, 0.95 - w1)
        w3 = trial.suggest_float("w3", 0.05, w3_upper)
        w7 = round(max(0.01, 1.0 - w1 - w3), 3)
        w1, w3 = round(w1, 3), round(w3, 3)
        # Normalize to ensure exact sum = 1.0
        total = w1 + w3 + w7
        w1, w3, w7 = round(w1/total, 3), round(w3/total, 3), round(1.0 - w1/total - w3/total, 3)
        w7 = round(1.0 - w1 - w3, 3)  # ensure exact

        metrics = evaluate(w1, w3, w7, args.preset, preloaded, args.bootstrap)
        metrics["trial"] = trial.number
        all_trials.append(metrics)

        trial.set_user_attr("total_return", metrics["total_return"])
        trial.set_user_attr("sortino", metrics["sortino"])
        trial.set_user_attr("mdd", metrics["mdd"])
        trial.set_user_attr("ruin", metrics["ruin_prob_pct"])

        print(f"    [{trial.number+1}/{args.trials}] w1={w1:.2f} w3={w3:.2f} w7={w7:.2f}  "
              f"S×C={metrics['sortino_calmar']:.1f}  total={metrics['total_return']:+.1f}%  "
              f"sortino={metrics['sortino']:.2f}  MDD={metrics['mdd']:.1f}%")

        return metrics["sortino_calmar"]

    sampler = optuna.samplers.TPESampler(seed=42, n_startup_trials=8)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

    best = study.best_trial
    best_metrics = all_trials[best.number]

    # Print summary
    print(f"\n{'='*80}")
    print(f"  Factor Weight Optimization — {args.preset}")
    print(f"{'='*80}")

    print(f"\n  Optimal weights (max Sortino×Calmar):")
    print(f"    w1 (趋势)  = {best_metrics['w1']:.3f}")
    print(f"    w3 (量价)  = {best_metrics['w3']:.3f}")
    print(f"    w7 (反转)  = {best_metrics['w7']:.3f}")
    print(f"    Sortino×Calmar: {best_metrics['sortino_calmar']:.1f}")
    print(f"    Sortino:        {best_metrics['sortino']:.2f}")
    print(f"    Total return:   {best_metrics['total_return']:+.1f}%")
    print(f"    MDD:            {best_metrics['mdd']:.1f}%")
    print(f"    Bootstrap ruin: {best_metrics['ruin_prob_pct']:.2f}%")

    # Preset1 reference
    print("\n  Running preset1 reference (0.5/0.4/0.1)...")
    ref = evaluate(0.5, 0.4, 0.1, args.preset, preloaded, args.bootstrap)
    print(f"    w1=0.50 w3=0.40 w7=0.10  "
          f"S×C={ref['sortino_calmar']:.1f}  sortino={ref['sortino']:.2f}  "
          f"total={ref['total_return']:+.1f}%  MDD={ref['mdd']:.1f}%")

    # Top 10
    sorted_trials = sorted(all_trials, key=lambda t: t["sortino_calmar"], reverse=True)
    print(f"\n  Top 10:")
    print(f"  {'Rank':<5} {'w1':<7} {'w3':<7} {'w7':<7} {'S×C':>6} {'Sortino':>7} {'Total%':>8} {'MDD%':>7}")
    print(f"  {'─'*5} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*7} {'─'*8} {'─'*7}")
    for i, t in enumerate(sorted_trials[:10]):
        marker = " <-- OPT" if i == 0 else ""
        print(f"  {i+1:<5} {t['w1']:<7} {t['w3']:<7} {t['w7']:<7} "
              f"{t['sortino_calmar']:>5.1f}  {t['sortino']:>6.2f}  "
              f"{t['total_return']:>+7.1f}% {t['mdd']:>6.1f}%{marker}")

    # Save
    output = {
        "preset": args.preset,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "method": "bayesian_tpe_sortino_calmar",
        "locked_params": {"concentration": 0.5, "c_sensitivity": 10.0},
        "optimal": {"w1": best_metrics["w1"], "w3": best_metrics["w3"], "w7": best_metrics["w7"],
                    "sortino_calmar": best_metrics["sortino_calmar"]},
        "preset1_reference": {"w1": 0.5, "w3": 0.4, "w7": 0.1, "sortino_calmar": ref["sortino_calmar"],
                              "total_return": ref["total_return"], "sortino": ref["sortino"]},
        "all_trials": sorted_trials,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")
    print(f"{'='*80}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
