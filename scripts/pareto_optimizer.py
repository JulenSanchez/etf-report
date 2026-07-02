#!/usr/bin/env python3
"""冷启动优化器 — Sobol + TPE 三轮收敛，用于无 warm-start 数据时的初始探索。
有 warm-start 数据时优先使用 iterative_optimizer.py（迭代缩界 TPE）。"""
import sys, json, pathlib, argparse, numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from etf_report.core.quant_contract import tuner_params_to_config_override, PARAM_BOUNDS, compute_frontier, create_optuna_objective
from quant_backtest import run_backtest
import optuna

# ── Cold-start search bounds (narrower than PARAM_BOUNDS for unguided exploration) ──
COLD_BOUNDS = {
    k: (v["min"], v["max"], v.get("step", 1))
    for k, v in PARAM_BOUNDS.items()
    if v.get("type") in ("weight", "continuous", "integer")
}
# Override a few key params with narrower cold-start ranges
COLD_BOUNDS.update({
    "w1": (10, 60, 1), "w3": (10, 60, 1),
    "ma_bull_pos": (0.80, 2.0, 0.01), "ma_bear_pos": (0.20, 0.80, 0.01),
    "concentration": (0.5, 6.0, 0.1), "band": (0.5, 8.0, 0.1),
    "f7_window": (5, 40, 1), "f1_ema_period": (2, 10, 1),
})


def shrink_bounds(warm_params, margin=0.3):
    """从 warm-start trial 数据推导缩小的参数搜索界。"""
    bounds = {}
    for k, (dlo, dhi, step) in COLD_BOUNDS.items():
        vals = [p.get(k) for p in warm_params if k in p and p.get(k) is not None]
        if len(vals) >= 3:
            lo, hi = min(vals), max(vals)
            m = max((hi - lo) * margin, step * 2)
            lo = max(dlo, lo - m); hi = min(dhi, hi + m)
        else:
            lo, hi = dlo, dhi
        # Align to step to avoid Optuna warnings
        lo = round(lo / step) * step if step > 0 else lo
        hi = round(hi / step) * step if step > 0 else hi
        bounds[k] = (max(dlo, lo), min(dhi, hi), step)
    return bounds


def crossover_params(p1, p2):
    """交叉变异：随机取 p1 和 p2 各半参数混合。"""
    import random
    result = {}
    for k in set(list(p1.keys()) + list(p2.keys())):
        result[k] = random.choice([p1.get(k), p2.get(k)]) if k in p1 and k in p2 else (p1.get(k) or p2.get(k))
    return result


# ── Objective ────────────────────────────────────────────────────────
# make_objective removed — use create_optuna_objective from quant_contract
# ── Pareto (uses quant_contract.compute_frontier) ──────────────────────

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
    bounds = shrink_bounds(warm_all) if warm_all else COLD_BOUNDS
    if warm_all:
        print("Bounds shrunk from warm-start data")

    objective = create_optuna_objective(args.preset, bounds, "2020-06-25")  # account_mode hardcoded
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
            obj3 = create_optuna_objective(args.preset, bounds3, "2020-06-25")
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
