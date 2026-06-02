#!/usr/bin/env python3
"""
REQ-250: Kelly Criterion Bootstrap Analysis with Bayesian Optimization.
Uses Optuna TPE to find (C, CS) that maximizes geometric growth rate
under bootstrap-resampled histories — much faster than grid search.
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

RESULTS_DIR = SKILL_DIR / "research" / "strategy" / "kelly"

# Bayesian search space (wider than grid)
C_RANGE = (0.05, 1.5)
CS_RANGE = (0.0, 10.0)
N_BOOTSTRAP = 1000
N_TRIALS = 50
N_STARTUP = 10


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


def make_override(c_val, cs_val):
    return {"position": {"concentration": c_val, "c_sensitivity": cs_val}}


def bootstrap_finals(daily_returns, n_bootstrap=N_BOOTSTRAP):
    n_days = len(daily_returns)
    finals = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = np.random.randint(0, n_days, size=n_days)
        finals[i] = np.prod(1.0 + daily_returns[idx])
    return finals


def evaluate(c_val, cs_val, preset, preloaded, n_boot):
    """Run backtest + bootstrap for a (C, CS) pair, return all metrics."""
    override = make_override(c_val, cs_val)
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

    mu = float(np.mean(daily_returns)) * 252
    sigma_daily = float(np.std(daily_returns))
    downside = daily_returns[daily_returns < 0]
    sortino_sigma = float(np.std(downside)) * np.sqrt(252) if len(downside) > 0 else sigma_daily * np.sqrt(252)
    sortino = (mu - 0.02) / sortino_sigma if sortino_sigma > 0 else 0

    # Calmar: annual_return / |MDD|
    annual_return = ((nav[-1] / nav[0]) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else 0
    calmar = annual_return / abs(mdd) if abs(mdd) > 0 else 0
    sortino_calmar = sortino * calmar

    # Geometric growth approx with downside-only variance drag
    # g ≈ μ − σ²_down/2  (penalize only downside volatility, not upside)
    var_down = float(np.var(downside)) * 252 if len(downside) > 0 else 0
    g_down_approx = mu - var_down / 2.0
    g_down_annual = (np.exp(g_down_approx) - 1.0) * 100.0  # convert to readable %

    # Full-variance geometric growth (for comparison)
    var_full = sigma_daily ** 2 * 252
    g_full_approx = mu - var_full / 2.0

    # Bootstrap (for cross-validation, not optimization target)
    finals = bootstrap_finals(daily_returns, n_boot)
    median_final = float(np.median(finals))
    p5_final = float(np.percentile(finals, 5))
    p1_final = float(np.percentile(finals, 1))
    ruin_prob = float(np.mean(finals < 1.0)) * 100.0
    geom_growth = float(np.log(median_final)) / years if median_final > 0 else -999

    return {
        "C": c_val, "CS": cs_val,
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "mdd": round(mdd, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "sortino_calmar": round(sortino_calmar, 2),
        "mu_annual": round(mu * 100, 2),
        "g_down_approx": round(g_down_approx, 4),
        "g_down_annual": round(g_down_annual, 2),
        "g_full_approx": round(g_full_approx, 4),
        "n_days": n_days, "years": round(years, 2),
        "median_final": round(median_final, 4),
        "p5_final": round(p5_final, 4),
        "p1_final": round(p1_final, 4),
        "ruin_prob_pct": round(ruin_prob, 2),
        "geom_growth": round(geom_growth, 4),
    }


def _load_config(preset):
    import yaml
    config_path = SKILL_DIR / "config" / "quant_universe.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="REQ-250 Kelly Bootstrap (Bayesian)")
    parser.add_argument("--preset", default="preset1")
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    parser.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (RESULTS_DIR / "results.json")

    print(f"Kelly Bootstrap (Bayesian TPE) — {args.preset}")
    print(f"  Search: C ∈ {C_RANGE}, CS ∈ {CS_RANGE}")
    print(f"  Trials: {args.trials} (startup={N_STARTUP}), Bootstrap: {args.bootstrap}/trial")

    print("  Preloading data...")
    preloaded = preload_data(args.preset)
    print(f"    Loaded {len(preloaded['all_daily'])} ETFs")

    all_trials = []

    def objective(trial):
        c_val = trial.suggest_float("C", *C_RANGE)
        cs_val = trial.suggest_float("CS", *CS_RANGE)
        # Round to 2 decimals for readability
        c_val = round(c_val, 2)
        cs_val = round(cs_val, 2)

        metrics = evaluate(c_val, cs_val, args.preset, preloaded, args.bootstrap)
        metrics["trial"] = trial.number
        all_trials.append(metrics)

        # Log additional info
        trial.set_user_attr("ruin_prob", metrics["ruin_prob_pct"])
        trial.set_user_attr("total_return", metrics["total_return"])
        trial.set_user_attr("sortino", metrics["sortino"])
        trial.set_user_attr("calmar", metrics["calmar"])
        trial.set_user_attr("g_down_annual", metrics["g_down_annual"])
        trial.set_user_attr("geom_growth", metrics["geom_growth"])

        print(f"    [{trial.number+1}/{args.trials}] C={c_val:.2f} CS={cs_val:.2f}  "
              f"S×C={metrics['sortino_calmar']:.1f}  total={metrics['total_return']:+.1f}%  "
              f"sortino={metrics['sortino']:.2f}  g↓={metrics['g_down_annual']:+.1f}%  "
              f"ruin={metrics['ruin_prob_pct']:.1f}%")

        return metrics["sortino_calmar"]

    # Optuna study with TPE sampler
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=N_STARTUP)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

    best_trial = study.best_trial
    best_params = best_trial.params
    best_metrics = all_trials[best_trial.number]

    # Print summary
    print(f"\n{'='*90}")
    print(f"  Sortino×Calmar Optimization — {args.preset} (Bayesian TPE)")
    print(f"{'='*90}")

    # Best
    print(f"\n  Optimal (max Sortino×Calmar):")
    print(f"    C  = {best_params['C']:.2f}")
    print(f"    CS = {best_params['CS']:.2f}")
    print(f"    Sortino×Calmar:   {best_metrics['sortino_calmar']:.1f}")
    print(f"    Sortino:          {best_metrics['sortino']:.2f}")
    print(f"    Calmar:           {best_metrics['calmar']:.2f}")
    print(f"    g↓ approx (μ−σ²↓/2): {best_metrics['g_down_annual']:+.1f}%/yr")
    print(f"    g full approx:    {best_metrics['g_full_approx']:.4f}")
    print(f"    Total return:     {best_metrics['total_return']:+.1f}%")
    print(f"    MDD:              {best_metrics['mdd']:.1f}%")
    print(f"    Median final:     {best_metrics['median_final']:.2f}x  (bootstrap)")
    print(f"    P5 final:         {best_metrics['p5_final']:.2f}x")
    print(f"    Ruin probability: {best_metrics['ruin_prob_pct']:.2f}%")

    # Top 15 by sortino_calmar
    sorted_trials = sorted(all_trials, key=lambda t: t["sortino_calmar"], reverse=True)
    print(f"\n  Top 15 by Sortino×Calmar:")
    print(f"  {'Rank':<5} {'C':<7} {'CS':<7} {'S×C':>6} {'Sortino':>7} {'Calmar':>7} {'Total%':>8} {'MDD%':>7} {'g↓%':>7} {'Geom':>7}")
    print(f"  {'─'*5} {'─'*7} {'─'*7} {'─'*6} {'─'*7} {'─'*7} {'─'*8} {'─'*7} {'─'*7} {'─'*7}")
    for i, t in enumerate(sorted_trials[:15]):
        marker = " <-- OPT" if i == 0 else ""
        print(f"  {i+1:<5} {t['C']:<7} {t['CS']:<7} {t['sortino_calmar']:>5.1f}  "
              f"{t['sortino']:>6.2f}  {t['calmar']:>6.2f}  "
              f"{t['total_return']:>+7.1f}% {t['mdd']:>6.1f}% {t['g_down_annual']:>+6.1f}% "
              f"{t['geom_growth']:>6.3f}{marker}")

    # Ruin probability landscape
    dangerous = [t for t in all_trials if t["ruin_prob_pct"] > 5.0]
    if dangerous:
        print(f"\n  WARNING: {len(dangerous)}/{len(all_trials)} trials had >5% ruin probability")
        for t in sorted(dangerous, key=lambda x: x["ruin_prob_pct"], reverse=True)[:5]:
            print(f"    C={t['C']:.2f} CS={t['CS']:.2f} ruin={t['ruin_prob_pct']:.1f}%")

    # Preset1 reference
    print("\n  Running preset1 reference (C=0.5, CS=10)...")
    ref = evaluate(0.5, 10.0, args.preset, preloaded, args.bootstrap)
    print(f"    C=0.50 CS=10.00  S×C={ref['sortino_calmar']:.1f}  sortino={ref['sortino']:.2f}  "
          f"total={ref['total_return']:+.1f}%  g↓={ref['g_down_annual']:+.1f}%  "
          f"ruin={ref['ruin_prob_pct']:.1f}%")

    # Also run Kelly optimal from previous run for comparison
    print("\n  Previous Kelly optimal (C=1.4, CS=4.8)...")
    ref2 = evaluate(1.4, 4.8, args.preset, preloaded, args.bootstrap)
    print(f"    C=1.40 CS=4.80  S×C={ref2['sortino_calmar']:.1f}  sortino={ref2['sortino']:.2f}  "
          f"total={ref2['total_return']:+.1f}%  g↓={ref2['g_down_annual']:+.1f}%  "
          f"ruin={ref2['ruin_prob_pct']:.1f}%")

    # Save
    output = {
        "preset": args.preset,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "method": "bayesian_tpe",
        "search_space": {"C": list(C_RANGE), "CS": list(CS_RANGE)},
        "n_trials": args.trials,
        "n_bootstrap": args.bootstrap,
        "optimization_target": "sortino_calmar",
        "kelly_optimal_previously": {"C": 1.4, "CS": 4.8, "target": "geom_growth"},
        "kelly_optimal": {
            "C": best_params["C"], "CS": best_params["CS"],
            "geom_growth": best_metrics["geom_growth"],
            "ruin_prob_pct": best_metrics["ruin_prob_pct"],
        },
        "preset1_reference": ref,
        "best_trial_number": best_trial.number,
        "all_trials": sorted_trials,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")
    print(f"{'='*90}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
