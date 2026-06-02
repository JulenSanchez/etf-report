#!/usr/bin/env python3
"""
Optimize factor sensitivities + MA trend period with Sortino×Calmar.
Locks C/CS/weights from preset1, TPE over f1_sens/f3_sens/f7_t/f7_k/ma_period.
"""
import argparse, json, sys
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

RESULTS_DIR = SKILL_DIR / "research" / "strategy" / "sensitivity"
N_TRIALS = 40

def preload_data(preset):
    cfg = _load_config(preset)
    universe = cfg["universe"]
    data_dir = str(SKILL_DIR / "data" / "quant")
    all_daily, all_weekly = {}, {}
    for etf in universe:
        code = etf["code"]
        daily, weekly = _load_etf_data(code, data_dir)
        if daily is not None: all_daily[code] = daily
        if weekly is not None: all_weekly[code] = weekly
    hs300_daily = load_hs300_daily_cached()
    hs300_weekly = build_hs300_weekly(hs300_daily) if hs300_daily is not None else None
    hs300_above_ma = build_ma_trend_cache(hs300_daily, hs300_weekly, period=26)
    return {"all_daily": all_daily, "all_weekly": all_weekly, "hs300_above_ma": hs300_above_ma}

def _load_config(preset):
    import yaml
    with (SKILL_DIR / "config" / "quant_universe.yaml").open("r",encoding="utf-8") as f:
        return yaml.safe_load(f)

def bootstrap_finals(daily_returns, n_boot=1000):
    n_days = len(daily_returns)
    finals = np.empty(n_boot)
    for i in range(n_boot):
        idx = np.random.randint(0, n_days, size=n_days)
        finals[i] = np.prod(1.0 + daily_returns[idx])
    return finals

def evaluate(f1_sens, f3_sens, f7_t, f7_k, ma_period, preset, preloaded):
    override = {
        "scoring": {"sensitivity": {"f1": f1_sens, "f3": f3_sens, "f7_t": f7_t, "f7_k": f7_k}},
        "confidence": {"ma_trend_period": int(ma_period)},
    }
    nav_df, _signal, _extra = run_backtest(
        start_date="2020-05-27", end_date="2026-05-26",
        preset=preset, preloaded=preloaded,
        config_override=override, return_details=False, return_debug=False,
    )
    daily_returns = nav_df["nav"].pct_change().dropna().values
    n_days = len(daily_returns); years = n_days / 252
    nav = nav_df["nav"].values
    total_return = (nav[-1] / nav[0] - 1.0) * 100.0
    dd = (nav - np.maximum.accumulate(nav)) / np.maximum.accumulate(nav) * 100.0
    mdd = float(dd.min())
    ann = ((nav[-1]/nav[0])**(1.0/years)-1.0)*100.0
    mu = float(np.mean(daily_returns))*252
    sd = float(np.std(daily_returns))
    dn = daily_returns[daily_returns<0]
    ss = float(np.std(dn))*np.sqrt(252) if len(dn)>0 else sd*np.sqrt(252)
    sortino = (mu-0.02)/ss if ss>0 else 0
    calmar = ann/abs(mdd) if abs(mdd)>0 else 0
    sc = sortino * calmar
    finals = bootstrap_finals(daily_returns)
    med = float(np.median(finals)); ruin = float(np.mean(finals<1.0))*100.0
    geom = float(np.log(med))/years if med>0 else -999
    return {"f1_sens":round(f1_sens,1),"f3_sens":round(f3_sens,1),"f7_t":round(f7_t,1),
            "f7_k":round(f7_k,1),"ma_period":int(ma_period),
            "total_return":round(total_return,2),"mdd":round(mdd,2),"sortino":round(sortino,2),
            "calmar":round(calmar,2),"sortino_calmar":round(sc,2),"ruin":round(ruin,2),"geom":round(geom,4)}

def main():
    p = argparse.ArgumentParser(); p.add_argument("--preset",default="preset1"); p.add_argument("--trials",type=int,default=N_TRIALS)
    args = p.parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Sensitivity Optimization — {args.preset} | Trials: {args.trials}")
    preloaded = preload_data(args.preset)
    all_trials = []

    def obj(trial):
        f1s = trial.suggest_float("f1_sens", 3.0, 15.0)
        f3s = trial.suggest_float("f3_sens", 0.3, 5.0)
        f7t = trial.suggest_float("f7_t", 5.0, 25.0)
        f7k = trial.suggest_float("f7_k", 1.0, 8.0)
        mp = trial.suggest_int("ma_period", 10, 40)
        m = evaluate(round(f1s,1), round(f3s,1), round(f7t,1), round(f7k,1), mp, args.preset, preloaded)
        m["trial"] = trial.number; all_trials.append(m)
        for k in ["total_return","sortino","ruin"]: trial.set_user_attr(k, m[k])
        print(f"    [{trial.number+1}/{args.trials}] f1s={m['f1_sens']} f3s={m['f3_sens']} f7_t={m['f7_t']} f7_k={m['f7_k']} MA={m['ma_period']}  "
              f"S×C={m['sortino_calmar']:.1f} total={m['total_return']:+.1f}% sortino={m['sortino']:.2f}")
        return m["sortino_calmar"]

    sampler = optuna.samplers.TPESampler(seed=42, n_startup_trials=10)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(obj, n_trials=args.trials, show_progress_bar=False)

    best = all_trials[study.best_trial.number]
    ref = evaluate(8.0, 1.5, 15.0, 3.5, 26, args.preset, preloaded)

    print(f"\n{'='*80}\n  Sensitivity Optimization — {args.preset}\n{'='*80}")
    print(f"\n  Optimal:")
    print(f"    f1_sens={best['f1_sens']}  f3_sens={best['f3_sens']}  f7_t={best['f7_t']}  f7_k={best['f7_k']}  MA={best['ma_period']}")
    print(f"    S×C={best['sortino_calmar']:.1f}  sortino={best['sortino']:.2f}  total={best['total_return']:+.1f}%  MDD={best['mdd']:.1f}%")
    print(f"\n  Preset1 ref (f1s=8 f3s=1.5 f7_t=15 f7_k=3.5 MA=26):")
    print(f"    S×C={ref['sortino_calmar']:.1f}  sortino={ref['sortino']:.2f}  total={ref['total_return']:+.1f}%  MDD={ref['mdd']:.1f}%")

    sorted_t = sorted(all_trials, key=lambda t: t["sortino_calmar"], reverse=True)
    print(f"\n  Top 10:")
    print(f"  {'Rank':<5} {'f1s':<6} {'f3s':<6} {'f7_t':<6} {'f7_k':<6} {'MA':<5} {'S×C':>6} {'Sortino':>7} {'Total%':>8} {'MDD%':>7}")
    print(f"  {'─'*5} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*5} {'─'*6} {'─'*7} {'─'*8} {'─'*7}")
    for i,t in enumerate(sorted_t[:10]):
        m = " <-- OPT" if i==0 else ""
        print(f"  {i+1:<5} {t['f1_sens']:<6} {t['f3_sens']:<6} {t['f7_t']:<6} {t['f7_k']:<6} {t['ma_period']:<5} "
              f"{t['sortino_calmar']:>5.1f}  {t['sortino']:>6.2f}  {t['total_return']:>+7.1f}% {t['mdd']:>6.1f}%{m}")

    output = {"preset":args.preset,"analyzed_at":datetime.now().strftime("%Y-%m-%d %H:%M"),
              "optimal":{k:best[k] for k in ["f1_sens","f3_sens","f7_t","f7_k","ma_period","sortino_calmar","sortino","total_return","mdd"]},
              "preset1_ref":{k:ref[k] for k in ["f1_sens","f3_sens","f7_t","f7_k","ma_period","sortino_calmar","sortino","total_return","mdd"]},
              "all_trials":sorted_t}
    op = RESULTS_DIR / "results.json"
    with op.open("w",encoding="utf-8") as f: json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {op}\n{'='*80}\n")

if __name__=="__main__": raise SystemExit(main())
