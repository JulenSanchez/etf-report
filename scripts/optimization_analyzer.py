#!/usr/bin/env python3
"""参数优化分析器 — 根据规范自动生成结构化分析数据。

Usage:
  python scripts/optimization_analyzer.py --study gam-1_gam-1-20260616-v4 \
      --preset gam-1 --baseline-preset gam-2 \
      --start 2020-06-17 --end 2026-06-16

Output: JSON to stdout, containing all dimensions required by optimization-report-guide.md
"""
import sys, json, argparse, math, os
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from quant_data_cache import get_cache
from quant_backtest import run_backtest
from etf_report.core.quant_contract import tuner_params_to_config_override, preset_to_tuner_params
from quant_tuner import _compute_etf_contributions
import yaml


def parse_args():
    p = argparse.ArgumentParser(description="参数优化分析器")
    p.add_argument("--study", required=True, help="Optuna study name")
    p.add_argument("--db", help="Optuna DB path (auto: research/params/{study}/optuna.db)")
    p.add_argument("--preset", required=True, help="Optimized preset (e.g. gam-1)")
    p.add_argument("--baseline-preset", required=True, help="Baseline preset (e.g. gam-2)")
    p.add_argument("--start", default="2020-06-17")
    p.add_argument("--end", default="2026-06-16")
    p.add_argument("--top-n", type=int, default=3, help="Number of top trials to deep-analyze")
    p.add_argument("--output", help="Output JSON path (default: stdout)")
    return p.parse_args()


def resolve_params(trial, bounds_overrides, bl_params):
    """Replicate optimizer's resolve_weights for a trial."""
    from quant_optimizer import ParamSpace
    all_bounds = {}
    # Build bounds from baseline + overrides (same as --auto-bounds --params)
    for key, b in __import__('quant_contract').PARAM_BOUNDS.items():
        if key in bounds_overrides:
            all_bounds[key] = dict(b, **bounds_overrides[key])
        else:
            if key not in bl_params: continue
            cur = bl_params[key]
            tp = b.get("type", "continuous")
            if tp == "weight":
                half = max(5, cur // 4)
                lo = max(b.get("min", 0), cur - half * 2)
                hi = min(b.get("max", 100), cur + half * 2)
                all_bounds[key] = {"type": "weight", "min": lo, "max": hi, "step": max(1, b.get("step", 5))}
            elif tp in ("continuous", "integer"):
                all_bounds[key] = b  # fixed at baseline
            else:
                all_bounds[key] = b
    space = ParamSpace(all_bounds)
    params = dict(trial.params)
    params = space.resolve_weights(params)
    return params


def run_backtest_for_trial(trial, preset, start, end, all_codes, preloaded, bounds_overrides, bl_params, config_path):
    """Run backtest with trial's resolved params."""
    cfg = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
    params = resolve_params(trial, bounds_overrides, bl_params)
    override = tuner_params_to_config_override(params)
    nav, sig, ext = run_backtest(
        start_date=start, end_date=end,
        preset=preset, preloaded=preloaded,
        config_override=override, universe_filter=all_codes
    )
    return nav, sig, ext, params


def main():
    args = parse_args()
    import optuna

    config_path = PROJECT_ROOT / "config" / "quant_universe.yaml"
    cfg = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
    all_codes = [e['code'] for e in cfg['universe']]
    names = {e['code']: e['name'] for e in cfg['universe']}
    sectors = {e['code']: e['sector'] for e in cfg['universe']}

    # Study name format: {preset}_{dirname}, db at research/params/{dirname}/optuna.db
    db_path = args.db
    if not db_path:
        parts = args.study.split("_", 1)
        dirname = parts[1] if len(parts) > 1 else args.study
        db_path = str(PROJECT_ROOT / "research" / "params" / dirname / "optuna.db")
    study = optuna.load_study(study_name=args.study, storage=f"sqlite:///{db_path}")

    # Baseline params
    bl_cfg = cfg['presets'].get(args.baseline_preset, cfg['presets'].get(args.preset, {}))
    bl_tuner = preset_to_tuner_params(args.baseline_preset, bl_cfg, cfg.get('confidence', {}))

    # Preload data once
    cache = get_cache()
    preloaded = cache.get_preloaded()

    # ── Baseline backtest ──
    print("Computing baseline...", file=sys.stderr)
    nav_bl, sig_bl, ext_bl = run_backtest(
        start_date=args.start, end_date=args.end,
        preset=args.baseline_preset, preloaded=preloaded, universe_filter=all_codes
    )
    base_tr = (nav_bl['nav'].iloc[-1] / 1_000_000 - 1) * 100
    base_mdd = (nav_bl['nav'] / nav_bl['nav'].cummax() - 1).min() * 100
    base_daily = nav_bl['nav'].pct_change().dropna()
    base_sh = (base_daily.mean() / base_daily.std()) * np.sqrt(252)

    result = {
        "study": args.study,
        "baseline": {
            "preset": args.baseline_preset,
            "tr": round(base_tr, 2),
            "mdd": round(base_mdd, 2),
            "sharpe": round(base_sh, 2),
            "annual_return": round(((nav_bl['nav'].iloc[-1] / 1_000_000) ** (365.25 / max((nav_bl['date'].iloc[-1] - nav_bl['date'].iloc[0]).days, 1)) - 1) * 100, 2)
        }
    }

    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]

    # ── 1. Convergence trajectory ──
    print("Analyzing convergence...", file=sys.stderr)
    convergence = []
    best_so_far = -999
    for t in sorted(completed, key=lambda x: x.number):
        m = json.loads(t.user_attrs['6Y_metrics'])
        tr = m['total_return']
        if tr > best_so_far:
            best_so_far = tr
            convergence.append({
                "trial": t.number,
                "tr": tr,
                "mdd": m['max_drawdown'],
                "w1": t.params.get('w1'),
                "w3": t.params.get('w3'),
                "max_holdings": t.params.get('max_holdings'),
                "ma_bear_pos": round(t.params.get('ma_bear_pos', 0), 3),
                "disc_step": round(t.params.get('disc_step', 0), 4),
                "f7_t": round(t.params.get('f7_t', 0), 1),
            })
    result["convergence"] = convergence

    # ── 2. Top-Bottom divergence ──
    by_tr = sorted(completed, key=lambda t: json.loads(t.user_attrs['6Y_metrics'])['total_return'], reverse=True)
    top10 = by_tr[:10]
    bot10 = by_tr[-10:]
    divergence = {}
    for param in ['w1', 'w3', 'max_holdings', 'disc_step', 'vol_window', 'dead_zone', 'f7_t', 'ma_bear_pos']:
        if param not in top10[0].params: continue
        tv = [t.params[param] for t in top10]
        bv = [t.params[param] for t in bot10]
        divergence[param] = {
            "top10_mean": round(float(np.mean(tv)), 3),
            "bot10_mean": round(float(np.mean(bv)), 3),
            "gap": round(float(np.mean(tv) - np.mean(bv)), 3),
            "baseline": bl_tuner.get(param)
        }
    result["top_bottom_divergence"] = divergence

    # ── 3. Deep-analyze top trials ──
    print(f"Deep-analyzing top {args.top_n} trials...", file=sys.stderr)

    # Reconstruct bounds (simplified — pass empty for auto-bounds-only params that don't matter here)
    bounds_overrides = {}
    top_results = []
    for t in by_tr[:args.top_n]:
        nav, sig, ext, resolved = run_backtest_for_trial(
            t, args.preset, args.start, args.end, all_codes, preloaded, {}, bl_tuner, config_path
        )
        tr = (nav['nav'].iloc[-1] / 1_000_000 - 1) * 100
        mdd = (nav['nav'] / nav['nav'].cummax() - 1).min() * 100
        daily = nav['nav'].pct_change().dropna()
        sh = (daily.mean() / daily.std()) * np.sqrt(252)

        # ETF contributions
        contrib = _compute_etf_contributions(ext.get('trade_log', []), sig, names, sectors)

        # Holdings distribution
        h_counts = Counter()
        for s in sig:
            n = len([c for c, w in s.get('positions', {}).items() if w > 0])
            h_counts[n] += 1

        top_results.append({
            "trial": t.number,
            "tr": round(tr, 2),
            "mdd": round(mdd, 2),
            "sharpe": round(sh, 2),
            "trade_count": ext['trade_count'],
            "commission": round(ext.get('total_commission', 0), 0),
            "raw_params": {k: t.params[k] for k in t.params},
            "resolved_params": {k: resolved[k] for k in resolved if isinstance(resolved[k], (int, float, bool, str))},
            "holdings_distribution": dict(h_counts.most_common()),
            "etf_contributions": {
                code: {k: round(v, 2) if isinstance(v, float) else v
                       for k, v in c.items() if k in ('totalPnlPct', 'selectionRate', 'winRate', 'payoffRatio', 'tradeCount', 'sectorShare')}
                for code, c in contrib.items() if c.get('tradeCount', 0) > 0
            }
        })
    result["top_trials"] = top_results

    # ── 4. ETF quadrants (from best trial) ──
    best_contrib = top_results[0]['etf_contributions'] if top_results else {}
    quadrants = {"core": [], "snipers": [], "problematic": [], "marginal": []}
    for code, c in best_contrib.items():
        sel = c.get('selectionRate', 0)
        pnl = c.get('totalPnlPct', 0)
        trades = c.get('tradeCount', 0)
        if trades == 0: continue
        entry = {"code": code, "name": names.get(code, code), "pnl": pnl, "sel_rate": sel,
                 "win_rate": c.get('winRate', 0), "payoff": c.get('payoffRatio', 0), "trades": trades}
        if sel >= 10 and pnl >= 0: quadrants["core"].append(entry)
        elif sel < 10 and pnl >= 50: quadrants["snipers"].append(entry)
        elif sel >= 10 and pnl < 0: quadrants["problematic"].append(entry)
        else: quadrants["marginal"].append(entry)
    for q in quadrants:
        quadrants[q].sort(key=lambda x: -x['pnl'])
    result["etf_quadrants"] = quadrants

    # ── 5. Phase performance ──
    phases = [
        ("2020-2021_bull", "2020-06-17", "2021-02-10"),
        ("2021_chop", "2021-02-10", "2022-10-31"),
        ("2022-2023_recovery", "2022-10-31", "2024-09-30"),
        ("2024-2026_rocket", "2024-09-30", args.end),
    ]
    nav_bl_idx = nav_bl.set_index('date')['nav']
    phase_perf = {}
    for name, start, end in phases:
        mask = (nav_bl_idx.index >= start) & (nav_bl_idx.index <= end)
        if mask.sum() == 0: continue
        p = nav_bl_idx[mask]
        old_ret = (p.iloc[-1] / p.iloc[0] - 1) * 100
        old_mdd = (p / p.cummax() - 1).min() * 100
        phase_perf[name] = {"baseline_tr": round(old_ret, 1), "baseline_mdd": round(old_mdd, 2)}
    # Add new strategy phase perf from best trial
    if top_results:
        best_nav = None
        nav_best, _, _, _ = run_backtest_for_trial(
            by_tr[0], args.preset, args.start, args.end, all_codes, preloaded, {}, bl_tuner, config_path
        )
        best_nav_idx = nav_best.set_index('date')['nav']
        for name, start, end in phases:
            mask = (best_nav_idx.index >= start) & (best_nav_idx.index <= end)
            if mask.sum() == 0: continue
            p = best_nav_idx[mask]
            new_ret = (p.iloc[-1] / p.iloc[0] - 1) * 100
            new_mdd = (p / p.cummax() - 1).min() * 100
            if name in phase_perf:
                phase_perf[name]["new_tr"] = round(new_ret, 1)
                phase_perf[name]["new_mdd"] = round(new_mdd, 2)
                phase_perf[name]["delta_tr"] = round(new_ret - phase_perf[name]["baseline_tr"], 1)
    result["phase_performance"] = phase_perf

    # ── 6. Behavioral: holdings trend ──
    h_by_year = {}
    for s in sig_bl:
        yr = str(s['date'])[:4]
        n = len([c for c, w in s.get('positions', {}).items() if w > 0])
        h_by_year.setdefault(yr, []).append(n)
    result["behavioral_baseline"] = {
        "avg_holdings_by_year": {yr: round(np.mean(vals), 1) for yr, vals in sorted(h_by_year.items())},
        "trade_count": ext_bl['trade_count'],
        "commission": round(ext_bl.get('total_commission', 0), 0),
    }

    # Output
    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
