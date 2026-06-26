#!/usr/bin/env python3
"""帕累托前沿优化器 — 三轮无 prune 收敛, warm-start 缩界。"""
import sys, json, pathlib, argparse, numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from etf_report.core.quant_contract import tuner_params_to_config_override, PARAM_BOUNDS
from quant_backtest import run_backtest
import optuna

# ── Default parameter bounds (from PARAM_BOUNDS) ─────────────────────
DEFAULT_BOUNDS = {
    "w1": (10, 60, 1), "w3": (10, 60, 1),
    "ma_bull_pos": (0.80, 2.0, 0.01), "ma_bear_pos": (0.20, 0.80, 0.01),
    "max_holdings": (1, 8, 1), "ma_trend_period": (8, 40, 2),
    "concentration": (0.5, 6.0, 0.1), "c_sensitivity": (0, 200, 2),
    "score_band": (0.5, 8.0, 0.1), "disc_step": (0.03, 0.15, 0.01),
    "f7_t": (3, 25, 1), "f7_k": (1.5, 5.5, 0.1), "f7_window": (5, 40, 1),
    "f3_vol_window": (10, 60, 1), "f1_sensitivity": (3, 15, 0.1),
    "f3_sensitivity": (1, 8, 0.1), "f1_ema_period": (2, 10, 1),
}


def shrink_bounds(warm_params, margin=0.3):
    """从 warm-start trial 数据推导缩小的参数搜索界。"""
    bounds = {}
    for k, (dlo, dhi, step) in DEFAULT_BOUNDS.items():
        vals = [p.get(k) for p in warm_params if k in p and p.get(k) is not None]
        if len(vals) >= 3:
            lo, hi = min(vals), max(vals)
            m = max((hi - lo) * margin, step * 2)
            bounds[k] = (max(dlo, lo - m), min(dhi, hi + m), step)
        else:
            bounds[k] = (dlo, dhi, step)
    return bounds


def crossover_params(p1, p2):
    """交叉变异：随机取 p1 和 p2 各半参数混合。"""
    import random
    result = {}
    for k in set(list(p1.keys()) + list(p2.keys())):
        result[k] = random.choice([p1.get(k), p2.get(k)]) if k in p1 and k in p2 else (p1.get(k) or p2.get(k))
    return result


# ── Objective ────────────────────────────────────────────────────────

def make_objective(preset, bounds):
    def objective(trial):
        p = {}
        for k, (lo, hi, step) in bounds.items():
            if isinstance(step, int) and step >= 1 and k not in ("ma_bull_pos", "ma_bear_pos",
                    "concentration", "score_band", "disc_step", "f7_k"):
                p[k] = trial.suggest_int(k, int(lo), int(hi), step=step)
            else:
                p[k] = trial.suggest_float(k, lo, hi, step=step)
        if "w1" in p: p["w1"] = int(p["w1"]); p["w3"] = int(p["w3"]); p["w7"] = 100 - p["w1"] - p["w3"]
        p["conf_type"] = "ma_trend"; p["ma_direction_confirm"] = True; p["bias"] = 0
        p["account_mode"] = "synthetic_leverage"
        if p.get("ma_bull_pos", 1) <= p.get("ma_bear_pos", 0.3):
            return -9999
        try:
            ov = tuner_params_to_config_override(p)
            nav, _, _ = run_backtest(start_date="2020-06-25", preset=preset,
                                      config_override=ov, return_data=False)
            if nav is None: return -9999
            N = len(nav); L = nav["date"].iloc[-1]
            y1 = L - pd.DateOffset(years=1); y3 = L - pd.DateOffset(years=3)
            i1 = max(0, min(nav["date"].searchsorted(y1), N - 1))
            i3 = max(0, min(nav["date"].searchsorted(y3), N - 1))
            def _ar(s, e):
                if e <= s: return 0
                d = (nav["date"].iloc[e] - nav["date"].iloc[s]).days
                return (nav["nav"].iloc[e] / nav["nav"].iloc[s]) ** (365.0 / d) - 1 if d > 0 else 0
            a1, a3, a6 = _ar(i1, N - 1), _ar(i3, N - 1), _ar(0, N - 1)
            comp = round((a1 + a3 + a6) / 3 * 100, 2)
            mdd = ((nav["nav"] - nav["nav"].cummax()) / nav["nav"].cummax() * 100).min()
            trial.set_user_attr("mdd", round(mdd, 2))
            trial.set_user_attr("composite", comp)
            trial.set_user_attr("params", json.dumps(p))
            return comp
        except Exception:
            return -9999
    return objective


# ── Pareto ───────────────────────────────────────────────────────────

def compute_frontier(trials):
    pts = [(t.user_attrs.get("mdd"), t.user_attrs.get("composite", t.value), t)
           for t in trials if (t.value is not None and t.value > -9000)]
    pts.sort(key=lambda x: x[0])
    f, mx = [], -9999
    for m, c, t in pts:
        if c > mx: mx = c; f.append((m, c, t))
    return f


def _save(path, trials):
    data = []
    for t in trials:
        mdd = t.user_attrs.get("mdd")
        comp = t.user_attrs.get("composite", t.value)
        if mdd is not None and comp is not None and comp > -9000:
            ps = t.user_attrs.get("params", "{}")
            data.append({"mdd": mdd, "composite": comp, "value": t.value,
                          "params": json.loads(ps) if isinstance(ps, str) else ps})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="帕累托前沿优化器")
    parser.add_argument("--preset", default="gam-2")
    parser.add_argument("--r1-trials", type=int, default=50)
    parser.add_argument("--r2-trials", type=int, default=50)
    parser.add_argument("--r3-trials", type=int, default=0)
    parser.add_argument("--warm-start", type=str, default=None,
                        help="已有 trial JSON (用于缩界)")
    parser.add_argument("--warm-start-2", type=str, default=None,
                        help="第二个已有 trial JSON (用于交叉变异)")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    out_dir = pathlib.Path(args.output or f"research/params/pareto_{args.preset}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load warm-start data ──
    warm_all = []
    for ws in [args.warm_start, args.warm_start_2]:
        if ws:
            wp = pathlib.Path(ws)
            if wp.exists():
                data = json.loads(wp.read_text("utf-8"))
                if isinstance(data, list):
                    warm_all.extend([r["params"] for r in data if "params" in r])
    if warm_all:
        print(f"Warm-start: {len(warm_all)} params loaded")
        # Add crossover if two sources
        if args.warm_start_2:
            ws1 = [r["params"] for r in json.loads(pathlib.Path(args.warm_start).read_text("utf-8")) if "params" in r]
            ws2 = [r["params"] for r in json.loads(pathlib.Path(args.warm_start_2).read_text("utf-8")) if "params" in r]
            import random
            for _ in range(min(10, len(ws1), len(ws2))):
                warm_all.append(crossover_params(random.choice(ws1), random.choice(ws2)))
            print(f"  +{min(10, len(ws1), len(ws2))} crossover params")

    # ── Derive bounds ──
    bounds = shrink_bounds(warm_all) if warm_all else DEFAULT_BOUNDS
    if warm_all:
        print("Bounds shrunk from warm-start data")

    objective = make_objective(args.preset, bounds)
    all_trials = []

    # ── Round 1: Sobol ──
    if args.r1_trials > 0:
        print(f"\n=== R1 Sobol {args.r1_trials} ===")
        r1 = optuna.create_study(direction="maximize", sampler=optuna.samplers.QMCSampler(seed=42))
        r1.optimize(objective, n_trials=args.r1_trials, n_jobs=1)
        r1t = [t for t in r1.trials if (t.value is not None and t.value > -9000)]
        all_trials.extend(r1t)
        f1 = compute_frontier(r1t)
        print(f"R1: {len(r1t)} ok, frontier {len(f1)} pts, best={max(f[1] for f in f1):.1f}" if f1 else "R1: none")
        _save(out_dir / "round1.json", r1t)
        _save(out_dir / "pareto.json", all_trials)

    # ── Round 2: TPE (no enqueue, just narrowed bounds from warm-start) ──
    if args.r2_trials > 0:
        print(f"\n=== R2 TPE {args.r2_trials} ===")
        r2 = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=43))
        r2.optimize(objective, n_trials=args.r2_trials, n_jobs=1)
        r2t = [t for t in r2.trials if (t.value is not None and t.value > -9000)]
        all_trials.extend(r2t)
        f2 = compute_frontier(all_trials)
        print(f"R2: {len(r2t)} ok, combined frontier {len(f2)} pts")
        _save(out_dir / "pareto.json", all_trials)

        if args.r3_trials > 0 and f2:
            # Shrink bounds further from R2 top trials
            r2_top = sorted(r2t, key=lambda t: t.value, reverse=True)[:15]
            r2_params = [json.loads(t.user_attrs.get("params", "{}")) for t in r2_top]
            bounds3 = shrink_bounds(r2_params, margin=0.2)

            print(f"\n=== R3 TPE {args.r3_trials} (narrower bounds) ===")
            obj3 = make_objective(args.preset, bounds3)
            r3 = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=44))
            r3.optimize(obj3, n_trials=args.r3_trials, n_jobs=1)
            r3t = [t for t in r3.trials if (t.value is not None and t.value > -9000)]
            all_trials.extend(r3t)
            f3 = compute_frontier(all_trials)
            print(f"R3: {len(r3t)} ok, final frontier {len(f3)} pts")
            _save(out_dir / "pareto.json", all_trials)

    # ── Final frontier ──
    final_f = compute_frontier(all_trials)
    print(f"\nFinal frontier ({len(all_trials)} trials, {len(final_f)} pts):")
    for m, c, t in final_f:
        if -50 <= m <= -10:
            p = json.loads(t.user_attrs.get("params", "{}"))
            print(f"  MDD={m:+.1f}% COMP={c:+.1f}% bull={p.get('ma_bull_pos',0):.2f} MH={p.get('max_holdings',0):.0f}")
    print("Done.")


if __name__ == "__main__":
    main()
