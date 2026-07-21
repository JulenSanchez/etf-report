"""WF 前置诊断脚本 — Step 0.1: 3Y vs 6Y 参数敏感度一致性.

用法: python scripts/wf_diagnostics.py --step 0.1
"""
import argparse, json, pathlib, random, sys, time
from collections import OrderedDict

_PROJ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJ / "scripts"))
from research_utils import backtest, DEFAULT_LOCK

OUT_DIR = _PROJ / "research" / "params" / "wf_readiness"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── WF 参数采样空间 ──
# (key, type, lo, hi)  — type: 'float' | 'int'
WF_PARAM_SPACE = [
    # 组 A: 风险敞口
    ("bull",           "float", 1.2,  2.0),
    ("bear",           "float", 0.5,  1.0),
    ("MA",             "int",   12,   30),
    ("MH",             "int",   2,    6),
    # 组 B: 集中度
    ("C",              "float", 0.3,  1.0),
    ("CS",             "float", 8.0,  24.0),
    ("N",              "int",   20,   50),
    # 组 C: 信号灵敏度
    ("f1_s",           "float", 4.0,  16.0),
    ("f3_s",           "float", 2.0,  8.0),
    ("f7_up_power",    "float", 12.0, 30.0),
    ("f7_up_span",     "float", 1.5,  5.0),
    ("f7_down_power",  "float", 6.0,  24.0),
    ("f7_down_span",   "float", 1.0,  4.0),
    # 组 D: 因子权重 (w7 sampled, w1/w3 redistributed)
    ("w7",             "int",   5,    25),
]

N_TRIALS = 30
SEED = 20260720


def sample_one(rng):
    """Sample one random param dict."""
    p = {}
    for key, kind, lo, hi in WF_PARAM_SPACE:
        if kind == "int":
            p[key] = rng.randint(lo, hi)
        else:
            p[key] = round(rng.uniform(lo, hi), 2)

    # Redistribute weights: gam-0 baseline w1:w3 = 71:13
    w7 = p["w7"]
    rem = 100 - w7
    ratio = 71.0 / (71.0 + 13.0)
    p["w1"] = int(round(rem * ratio))
    p["w3"] = int(round(rem * (1.0 - ratio)))
    return p


def _corr(xs, ys):
    """Pearson r."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) / (n - 1) * n


def _direction(r_3y, r_6y, ar_3y, ar_6y):
    """定性判断: 方向是否一致, 强度差异."""
    same_sign = (r_3y > 0 and r_6y > 0) or (r_3y < 0 and r_6y < 0)
    if same_sign:
        return "一致"
    elif abs(r_3y) < 0.15 and abs(r_6y) < 0.15:
        return "均弱相关"
    else:
        return "⚠️ 相反"


def step_01():
    """Step 0.1: Sobol-like random sampling, 3Y vs 6Y correlation."""
    print("=" * 60)
    print("Step 0.1: 3Y vs 6Y 参数敏感度一致性")
    print("=" * 60)

    rng = random.Random(SEED)
    samples = [sample_one(rng) for _ in range(N_TRIALS)]

    results_3y = []
    results_6y = []

    for i, p in enumerate(samples):
        label = f"[{i+1:2d}/{N_TRIALS}]"
        t0 = time.time()

        r3 = backtest(**p, window="3Y")
        elapsed_3y = time.time() - t0
        t0 = time.time()

        r6 = backtest(**p, window="6Y")
        elapsed_6y = time.time() - t0

        ok_3y = "✓" if r3 else "✗"
        ok_6y = "✓" if r6 else "✗"
        ar3 = r3.get("AR", 0) if r3 else 0
        ar6 = r6.get("AR", 0) if r6 else 0
        mdd3 = r3.get("MDD", 0) if r3 else 0
        mdd6 = r6.get("MDD", 0) if r6 else 0

        print(f"{label} 3Y:{ok_3y} AR={ar3:+.1f}% MDD={mdd3:.1f}% "
              f"6Y:{ok_6y} AR={ar6:+.1f}% MDD={mdd6:.1f}% "
              f"({elapsed_3y:.0f}s+{elapsed_6y:.0f}s)")

        if r3:
            results_3y.append((p, r3))
        if r6:
            results_6y.append((p, r6))

    # ── Per-param correlation with AR ──
    print("\n── 参数 ↔ AR 相关系数 ──")
    header = f"{'param':<18} {'r_3Y':>7} {'dir_3Y':>5} {'r_6Y':>7} {'dir_6Y':>5} {'方向':>6}"
    print(header)
    print("-" * len(header))

    report_lines = [header, "-" * len(header)]
    inconsistencies = []

    param_keys = [k for k, _, _, _ in WF_PARAM_SPACE] + ["w1", "w3"]

    for key in param_keys:
        xs_3y = [p[key] for p, _ in results_3y]
        ys_3y = [r["AR"] for _, r in results_3y]
        xs_6y = [p[key] for p, _ in results_6y]
        ys_6y = [r["AR"] for _, r in results_6y]

        r3 = _corr(xs_3y, ys_3y)
        r6 = _corr(xs_6y, ys_6y)
        d3 = "正" if r3 > 0.1 else ("负" if r3 < -0.1 else "≈0")
        d6 = "正" if r6 > 0.1 else ("负" if r6 < -0.1 else "≈0")
        direction = _direction(r3, r6, ys_3y, ys_6y)

        line = f"{key:<18} {r3:+7.3f} {d3:>5} {r6:+7.3f} {d6:>5} {direction:>6}"
        print(line)
        report_lines.append(line)

        if "⚠️" in direction:
            inconsistencies.append(key)

    # ── Summary ──
    print(f"\n方向不一致的参数: {inconsistencies if inconsistencies else '无'}")
    print(f"结论: {'✅ 通过' if not inconsistencies else '⚠️ 需关注 — 列出的参数在 3Y/6Y 上方向相反'}")

    # ── Save ──
    report = {
        "step": "0.1",
        "description": "3Y vs 6Y parameter sensitivity consistency",
        "n_trials": N_TRIALS,
        "seed": SEED,
        "params_tested": param_keys,
        "correlations": {},
        "inconsistencies": inconsistencies,
        "passed": len(inconsistencies) == 0,
    }
    for key in param_keys:
        xs_3y = [p[key] for p, _ in results_3y]
        ys_3y = [r["AR"] for _, r in results_3y]
        xs_6y = [p[key] for p, _ in results_6y]
        ys_6y = [r["AR"] for _, r in results_6y]
        report["correlations"][key] = {
            "r_3Y": round(_corr(xs_3y, ys_3y), 4),
            "r_6Y": round(_corr(xs_6y, ys_6y), 4),
        }

    out_path = OUT_DIR / "step_01_sensitivity.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport saved: {out_path}")

    return report


def step_02():
    """Step 0.2: 3Y 窗口 TPE 收敛质量 — 双 seed 对比."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    print("=" * 60)
    print("Step 0.2: 3Y 窗口 TPE 收敛质量")
    print("=" * 60)

    # Test the 4 most impactful params from Step 0.1
    TEST_PARAMS = ["bull", "C", "w7", "f7_up_power"]
    BOUNDS = {
        "bull": (1.2, 2.0),
        "C": (0.3, 1.0),
        "w7": (5, 25),
        "f7_up_power": (12.0, 30.0),
    }
    N_TRIALS_TPE = 30
    MDD_BOUND = -40

    def _weights_from_w7(w7_pct):
        rem = 100 - w7_pct
        ratio = 71.0 / (71.0 + 13.0)
        w1 = int(round(rem * ratio))
        w3 = int(round(rem * (1.0 - ratio)))
        return w1, w3, w7_pct

    def objective(trial, seed_label):
        p = dict(DEFAULT_LOCK)
        for k in TEST_PARAMS:
            lo, hi = BOUNDS[k]
            if k == "w7":
                p[k] = trial.suggest_int(k, lo, hi)
                p["w1"], p["w3"], _ = _weights_from_w7(p[k])
            elif isinstance(lo, int):
                p[k] = trial.suggest_int(k, lo, hi)
            else:
                p[k] = trial.suggest_float(k, lo, hi)

        r = backtest(**p, window="3Y")
        if not r:
            return -9999.0
        if r["MDD"] < MDD_BOUND:
            return -9999.0
        return r["AR"]

    results = {}
    for seed in [42, 99]:
        print(f"\n-- TPE seed={seed} --")
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=seed),
        )
        study.optimize(
            lambda trial: objective(trial, f"seed{seed}"),
            n_trials=N_TRIALS_TPE,
        )

        best = study.best_params
        best_val = study.best_value
        # Re-run with best params to get full metrics
        p_full = dict(DEFAULT_LOCK)
        for k in TEST_PARAMS:
            if k == "w7":
                p_full["w7"] = best["w7"]
                p_full["w1"], p_full["w3"], _ = _weights_from_w7(best["w7"])
            else:
                p_full[k] = best[k]
        r_full = backtest(**p_full)

        results[seed] = {
            "best_params": best,
            "best_AR": best_val,
            "full_metrics": r_full,
        }
        print(f"  Best: {best} → AR={best_val:.1f}%")
        if r_full:
            print(f"  Full: AR={r_full['AR']:.1f}% MDD={r_full['MDD']:.1f}%")

    # ── Compare ──
    p42 = results[42]["best_params"]
    p99 = results[99]["best_params"]
    ar42 = results[42]["best_AR"]
    ar99 = results[99]["best_AR"]

    print(f"\n── 收敛对比 ──")
    print(f"{'param':<16} {'seed=42':>10} {'seed=99':>10} {'Δ':>10}")
    for k in TEST_PARAMS:
        v42 = p42[k]
        v99 = p99[k]
        delta = v42 - v99
        print(f"{k:<16} {v42:>10.2f} {v99:>10.2f} {delta:>+10.2f}")

    ar_diff = abs(ar42 - ar99)
    print(f"\nAR 差异: {ar_diff:.1f}pp")
    if ar_diff < 5:
        verdict = "✅ 收敛良好"
    elif ar_diff < 10:
        verdict = "⚠️ 收敛一般"
    else:
        verdict = "❌ 不稳定"
    print(f"结论: {verdict}")

    report = {
        "step": "0.2",
        "description": "3Y window TPE convergence (dual seed)",
        "test_params": TEST_PARAMS,
        "n_trials_per_run": N_TRIALS_TPE,
        "mdd_bound": MDD_BOUND,
        "results": {
            "seed_42": {"params": {k: p42[k] for k in TEST_PARAMS}, "AR": ar42},
            "seed_99": {"params": {k: p99[k] for k in TEST_PARAMS}, "AR": ar99},
        },
        "ar_difference_pp": round(ar_diff, 1),
        "verdict": verdict,
    }
    out_path = OUT_DIR / "step_02_convergence.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport saved: {out_path}")
    return report


def step_03():
    """Step 0.3: 分组假设 3Y 验证 — 联合扰动响应面对比."""
    print("=" * 60)
    print("Step 0.3: 分组假设 3Y vs 6Y 联合扰动响应面")
    print("=" * 60)

    # Two test pairs from different groups
    # Pair 1: 风险敞口组内 — {bull, MH}
    # Pair 2: 集中度组内 — {C, N}
    PAIRS = [
        {
            "name": "风险敞口: bull×MH",
            "grid": {"bull": [1.2, 1.5, 1.8], "MH": [2, 4, 6]},
        },
        {
            "name": "集中度: C×N",
            "grid": {"C": [0.3, 0.62, 1.0], "N": [20, 30, 40]},
        },
    ]

    all_results = []

    for pair in PAIRS:
        print(f"\n── {pair['name']} ──")
        grid = pair["grid"]
        keys = list(grid.keys())
        values = list(grid.values())

        for window in ["3Y", "6Y"]:
            print(f"\n  {window}:")
            points = []
            import itertools
            for combo in itertools.product(*values):
                p = dict(DEFAULT_LOCK)
                p.update(dict(zip(keys, combo)))
                r = backtest(**p, window=window)
                ar = r["AR"] if r else 0
                mdd = r["MDD"] if r else 0
                label = " ".join(f"{k}={v}" for k, v in zip(keys, combo))
                print(f"    {label:<28} AR={ar:+6.1f}% MDD={mdd:+5.1f}%")
                points.append({
                    "params": dict(zip(keys, combo)),
                    "AR": ar,
                    "MDD": mdd,
                    "window": window,
                })

            # Count local extrema (roughness indicator)
            ars = [p["AR"] for p in points]
            extrema = 0
            for i in range(1, len(ars) - 1):
                if (ars[i] > ars[i-1] and ars[i] > ars[i+1]) or \
                   (ars[i] < ars[i-1] and ars[i] < ars[i+1]):
                    extrema += 1

            all_results.append({
                "pair": pair["name"],
                "window": window,
                "points": points,
                "ar_range": round(max(ars) - min(ars), 1),
                "local_extrema": extrema,
            })
            print(f"    AR 范围={max(ars)-min(ars):.1f}pp  局部极值={extrema}")

    # ── Compare 3Y vs 6Y roughness ──
    print("\n── 响应面崎岖度对比 ──")
    report_pairs = []
    for pair_name in [p["name"] for p in PAIRS]:
        res_3y = [r for r in all_results if r["pair"] == pair_name and r["window"] == "3Y"][0]
        res_6y = [r for r in all_results if r["pair"] == pair_name and r["window"] == "6Y"][0]
        extrema_ratio = res_3y["local_extrema"] / max(res_6y["local_extrema"], 1)
        range_ratio = res_3y["ar_range"] / max(res_6y["ar_range"], 1)

        print(f"{pair_name}:")
        print(f"  3Y extrema={res_3y['local_extrema']}  6Y extrema={res_6y['local_extrema']}  "
              f"ratio={extrema_ratio:.1f}x")
        print(f"  3Y range={res_3y['ar_range']}pp  6Y range={res_6y['ar_range']}pp  "
              f"ratio={range_ratio:.1f}x")

        if extrema_ratio <= 1.5:
            verdict = "✅ 分组假设成立"
        elif extrema_ratio <= 2.5:
            verdict = "⚠️ 3Y 略崎岖，分组需加宽 bounds"
        else:
            verdict = "❌ 3Y 显著崎岖，分组假设不成立"
        print(f"  → {verdict}")
        report_pairs.append({
            "pair": pair_name,
            "extrema_3Y": res_3y["local_extrema"],
            "extrema_6Y": res_6y["local_extrema"],
            "ar_range_3Y": res_3y["ar_range"],
            "ar_range_6Y": res_6y["ar_range"],
            "verdict": verdict,
        })

    report = {
        "step": "0.3",
        "description": "Group hypothesis validation: 3Y vs 6Y joint perturbation response surfaces",
        "pairs": report_pairs,
    }
    out_path = OUT_DIR / "step_03_groups.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport saved: {out_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="WF diagnostics")
    parser.add_argument("--step", required=True, help="0.1 | 0.2 | 0.3 | 0.4")
    args = parser.parse_args()

    steps = {
        "0.1": step_01,
        "0.2": step_02,
        "0.3": step_03,
    }

    fn = steps.get(args.step)
    if fn is None:
        print(f"Unknown step: {args.step}. Available: {list(steps.keys())}")
        sys.exit(1)
    fn()


if __name__ == "__main__":
    main()
