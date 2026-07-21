"""REQ-323 Walk-Forward Phase 1: 单轨迹方法验证.

用法: python scripts/wf_phase1.py [--step STEP]

--step 1    层 1: 3 窗 × 4 组 TPE 优化
--step 2    层 2: 样本外测试 + NAV 拼接
--step all  全部 (default)
"""
import argparse, json, pathlib, sys, time

_PROJ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJ / "src"))
sys.path.insert(0, str(_PROJ / "scripts"))

from research_utils import _build_override, DEFAULT_LOCK
sys.path.insert(0, str(_PROJ / "src"))
from etf_report.core.quant_contract import LOCKED_PARAMS as _LOCKED

OUT_DIR = _PROJ / "research" / "params" / "wf_gam_m40"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 滚动窗口 ──
STEPS = [
    {"id": "step1", "train": ("2020-06-01", "2023-06-01"), "test": ("2023-06-01", "2024-06-01")},
    {"id": "step2", "train": ("2021-06-01", "2024-06-01"), "test": ("2024-06-01", "2025-06-01")},
    {"id": "step3", "train": ("2022-06-01", "2025-06-01"), "test": ("2025-06-01", "2026-06-01")},
]

# ── 优化分组 ──
GROUPS = [
    {
        "name": "A_risk",
        "keys": ["bull", "bear", "MA"],
        "bounds": {"bull": (1.2, 1.8), "bear": (0.5, 1.0), "MA": (12, 30)},
    },
    {
        "name": "B_concentration",
        "keys": ["MH", "TB", "C", "CS"],
        "bounds": {"MH": (2, 6), "TB": (0, 16), "C": (0.3, 1.0), "CS": (8.0, 24.0)},
    },
    {
        "name": "C_sensitivity",
        "keys": ["f1_s", "f3_s", "f7_up_power", "f7_up_span", "f7_down_power", "f7_down_span"],
        "bounds": {
            "f1_s": (4.0, 16.0), "f3_s": (2.0, 8.0),
            "f7_up_power": (12.0, 30.0), "f7_up_span": (1.5, 5.0),
            "f7_down_power": (6.0, 24.0), "f7_down_span": (1.0, 4.0),
        },
    },
    {
        "name": "D_weights",
        "keys": ["w7"],
        "bounds": {"w7": (5, 25)},
    },
]

MDD_BOUND = -40
N_TRIALS = 50
SEED_BASE = 20260720


def _weights_from_w7(w7_pct, base_w1=71, base_w3=13):
    """Redistribute w1/w3 proportionally from UI percentage w7."""
    rem = 100 - w7_pct
    ratio = base_w1 / (base_w1 + base_w3)
    w1 = int(round(rem * ratio))
    w3 = int(round(rem * (1.0 - ratio)))
    return w1, w3, w7_pct


def _run_one(params, start, end):
    """Run one backtest, return {AR, MDD, ...} or {}."""
    import os as _os
    p = {**DEFAULT_LOCK, **params}
    if "w7" in params:
        p["w1"], p["w3"], p["w7"] = _weights_from_w7(params["w7"])
    override = _build_override(p)
    from quant_backtest import run_backtest
    # Redirect backtest noise to devnull; harness kills tasks with huge stdout
    old_stdout = _os.dup(1)
    fd_null = _os.open(_os.devnull, _os.O_WRONLY)
    _os.dup2(fd_null, 1)
    _os.close(fd_null)
    try:
        _, _, extra = run_backtest(start, end, preset="gam-0",
                                   config_override=override, return_data=False, verbose=False)
    finally:
        _os.dup2(old_stdout, 1)
        _os.close(old_stdout)
    if not extra:
        return {}
    ar = extra.get("annual_return", 0)
    mdd = extra.get("max_drawdown", 0)
    return {
        "AR": round(ar, 1), "MDD": round(mdd, 1),
        "Calmar": round(ar / abs(mdd), 2) if mdd != 0 else 0,
        "Sortino": round(extra.get("sortino", 0), 3),
    }


def _run_one_with_nav(params, start, end):
    """Run backtest and return NAV series for stitching."""
    p = {**DEFAULT_LOCK, **params}
    if "w7" in params:
        p["w1"], p["w3"], p["w7"] = _weights_from_w7(params["w7"])
    override = _build_override(p)
    from quant_backtest import run_backtest
    nav_df, _, extra = run_backtest(start, end, preset="gam-0",
                                    config_override=override, return_data=True)
    if nav_df is None or len(nav_df) == 0:
        return None, {}
    ar = extra.get("annual_return", 0)
    mdd = extra.get("max_drawdown", 0)
    return nav_df, {
        "AR": round(ar, 1), "MDD": round(mdd, 1),
        "Calmar": round(ar / abs(mdd), 2) if mdd != 0 else 0,
        "Sortino": round(extra.get("sortino", 0), 3),
    }


def optimize_group_tpe(locked_params, group, train_start, train_end, step_id):
    """Run TPE optimization for one group on a training window."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    keys = [k for k in group["keys"] if k not in _LOCKED]
    bounds = {k: v for k, v in group["bounds"].items() if k not in _LOCKED}
    seed = SEED_BASE + hash(group["name"]) % 1000
    if not keys:
        print(f"  {group['name']}: all keys locked, skipping"); return {}

    def objective(trial):
        p = dict(locked_params)
        for k in keys:
            lo, hi = bounds[k]
            if k in ("MH", "MA", "N", "w7") or isinstance(lo, int):
                p[k] = trial.suggest_int(k, int(lo), int(hi))
            else:
                p[k] = trial.suggest_float(k, lo, hi)
        r = _run_one(p, train_start, train_end)
        if not r:
            return -9999.0
        if r["MDD"] < MDD_BOUND:
            return -9999.0
        return r["AR"]

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=N_TRIALS)

    best = {k: study.best_params[k] for k in keys}
    # Re-run with best params to get full metrics
    p_full = {**locked_params, **best}
    r_full = _run_one(p_full, train_start, train_end)

    # Count how many trials satisfied MDD constraint
    n_pruned = sum(1 for t in study.trials if t.value == -9999.0)
    n_valid = N_TRIALS - n_pruned

    result = {
        "group": group["name"],
        "best_params": best,
        "best_AR": study.best_value,
        "AR": r_full.get("AR", 0),
        "MDD": r_full.get("MDD", 0),
        "n_trials": N_TRIALS,
        "n_valid": n_valid,
        "n_pruned": n_pruned,
    }
    print(f"  {group['name']}: best_AR={study.best_value:.1f}%  full_AR={r_full.get('AR',0):.1f}%  "
          f"MDD={r_full.get('MDD',0):.1f}%  valid={n_valid}/{N_TRIALS}")
    for k in keys:
        print(f"    {k}={best[k]}")

    return result


def step1():
    """层 1: 3 窗 × 4 组 TPE 优化."""
    print("=" * 60)
    print("WF Phase 1 — 层 1: in-sample 优化")
    print("=" * 60)

    all_step_results = {}

    for step_info in STEPS:
        sid = step_info["id"]
        t_start, t_end = step_info["train"]
        print(f"\n{'='*60}")
        print(f"  {sid}: train={t_start} ~ {t_end}")
        print(f"{'='*60}")

        # Resume: load partial results if step file exists
        step_path = OUT_DIR / f"{sid}_result.json"
        locked = dict(DEFAULT_LOCK)
        group_results = []
        start_from = 0
        if step_path.exists():
            existing = json.loads(step_path.read_text("utf-8"))
            group_results = existing.get("groups", [])
            locked = existing.get("locked_params", dict(DEFAULT_LOCK))
            start_from = len(group_results)
            print(f"  (loaded {start_from}/{len(GROUPS)} groups from existing result)")

        for gi, group in enumerate(GROUPS):
            if gi < start_from:
                continue
            t0 = time.time()
            print(f"\n-- {group['name']} ({len(group['keys'])} params, {N_TRIALS} trials) --")
            gr = optimize_group_tpe(locked, group, t_start, t_end, sid)
            group_results.append(gr)

            # Lock optimized params for next groups
            for k in group["keys"]:
                locked[k] = gr["best_params"][k]
            if "w7" in group["keys"]:
                locked["w1"], locked["w3"], _ = _weights_from_w7(locked["w7"])

            elapsed = time.time() - t0
            print(f"  elapsed: {elapsed:.0f}s")

        # Save step result
        step_result = {
            "step_id": sid,
            "train_window": [t_start, t_end],
            "test_window": step_info["test"],
            "locked_params": {k: locked[k] for k in sorted(locked)},
            "groups": group_results,
        }
        out_path = OUT_DIR / f"{sid}_result.json"
        out_path.write_text(json.dumps(step_result, indent=2, ensure_ascii=False), encoding="utf-8")
        all_step_results[sid] = step_result
        print(f"\n  Saved: {out_path}")

    return all_step_results


def step2():
    """层 2: 样本外测试 + NAV 拼接."""
    print("=" * 60)
    print("WF Phase 1 — 层 2: 样本外验证 + NAV 拼接")
    print("=" * 60)

    # Load step results
    step_results = {}
    for step_info in STEPS:
        sid = step_info["id"]
        path = OUT_DIR / f"{sid}_result.json"
        if not path.exists():
            print(f"  ERROR: {path} not found — run --step 1 first")
            return None
        step_results[sid] = json.loads(path.read_text("utf-8"))

    # Run out-of-sample tests
    nav_segments = []
    oos_metrics = []

    for step_info in STEPS:
        sid = step_info["id"]
        locked = step_results[sid]["locked_params"]
        test_start, test_end = step_info["test"]

        print(f"\n-- {sid} OOS: {test_start} ~ {test_end} --")
        nav_df, metrics = _run_one_with_nav(locked, test_start, test_end)

        if nav_df is None:
            print(f"  ERROR: OOS backtest failed for {sid}")
            return None

        nav_segments.append(nav_df)
        oos_metrics.append({"step": sid, "metrics": metrics, "window": [test_start, test_end]})
        print(f"  AR={metrics['AR']:+.1f}%  MDD={metrics['MDD']:+.1f}%  "
              f"Calmar={metrics['Calmar']:.2f}  Sortino={metrics['Sortino']:.3f}")

    # ── Stitch NAV with proper re-basing ──
    print("\n── NAV 拼接 ──")
    import pandas as pd

    # Re-base each segment to continue from previous segment's ending NAV
    rebased = []
    prev_end_nav = None
    for i, seg in enumerate(nav_segments):
        seg = seg.copy()
        seg_start_nav = seg["nav"].iloc[0]
        if i == 0:
            factor = 1_000_000.0 / seg_start_nav
        else:
            factor = prev_end_nav / seg_start_nav
        seg["nav"] = seg["nav"] * factor
        prev_end_nav = seg["nav"].iloc[-1]
        rebased.append(seg)

    stitched = pd.concat(rebased, ignore_index=True)
    stitched = stitched.drop_duplicates(subset=["date"], keep="last")
    stitched = stitched.sort_values("date").reset_index(drop=True)

    # Compute spliced metrics directly from stitched NAV
    nav_series = stitched["nav"]
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    years = (pd.to_datetime(stitched["date"].iloc[-1]) - pd.to_datetime(stitched["date"].iloc[0])).days / 365.25
    ar = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    peak = nav_series.expanding().max()
    dd = (nav_series - peak) / peak
    mdd = dd.min()
    # Sortino: downside deviation
    daily_ret = nav_series.pct_change().dropna()
    downside = daily_ret[daily_ret < 0]
    sortino = (daily_ret.mean() / downside.std() * (252 ** 0.5)) if len(downside) > 1 and downside.std() > 0 else 0
    spliced_metrics = {
        "total_return_pct": round(total_return * 100, 1),
        "AR": round(ar * 100, 1),
        "MDD": round(mdd * 100, 1),
        "Calmar": round(ar / abs(mdd), 2) if mdd != 0 else 0,
        "Sortino": round(sortino, 3),
        "years": round(years, 2),
        "start_nav": round(nav_series.iloc[0], 0),
        "end_nav": round(nav_series.iloc[-1], 0),
    }

    print(f"  日期范围: {stitched['date'].min()} ~ {stitched['date'].max()}")
    print(f"  交易日: {len(stitched)}")
    print(f"  总收益: {spliced_metrics['total_return_pct']:+.1f}%")
    print(f"  WF AR: {spliced_metrics['AR']:+.1f}%")
    print(f"  WF MDD: {spliced_metrics['MDD']:+.1f}%")
    print(f"  WF Calmar: {spliced_metrics['Calmar']:.2f}")
    print(f"  WF Sortino: {spliced_metrics['Sortino']:.3f}")
    print(f"  NAV: {spliced_metrics['start_nav']:.0f} -> {spliced_metrics['end_nav']:.0f}")

    # ── Parameter variation check ──
    print("\n── 参数步间变化 ──")
    key_params = ["bull", "bear", "MH", "C", "N", "w7", "f7_up_power"]
    p_sets = []
    for step_info in STEPS:
        sid = step_info["id"]
        p = step_results[sid]["locked_params"]
        p_sets.append(tuple(p.get(k) for k in key_params))
        vals = "  ".join(f"{k}={p.get(k)}" for k in key_params)
        print(f"  {sid}: {vals}")

    n_unique = len(set(p_sets))
    print(f"\n  唯一参数组合: {n_unique}/3")
    if n_unique >= 2:
        print("  ✅ 参数在步间确实变化")
    else:
        print("  ⚠️ 所有步参数相同，WF 可能是原地踏步")

    # ── IS vs OOS gap ──
    print("\n── IS vs OOS 对比 ──")
    is_ars = []
    for step_info in STEPS:
        sid = step_info["id"]
        sr = step_results[sid]
        is_ar = sr["groups"][-1]["AR"]  # last group's full-metrics AR
        is_ars.append(is_ar)

    is_avg = sum(is_ars) / len(is_ars)
    oos_ar = spliced_metrics["AR"]
    gap = is_avg - oos_ar
    ratio = oos_ar / is_avg * 100 if is_avg != 0 else 0

    print(f"  IS AR (均值): {is_avg:+.1f}%")
    print(f"  OOS WF AR:    {oos_ar:+.1f}%")
    print(f"  Gap:          {gap:+.1f}pp")
    print(f"  OOS/IS:       {ratio:.0f}%")

    if ratio >= 50:
        print(f"  ✅ 通过 (OOS ≥ IS 的 50%)")
        verdict = "PASS"
    else:
        print(f"  ❌ 失败 (OOS < IS 的 50%) — 框架可能过拟合")
        verdict = "FAIL"

    # ── Save ──
    final = {
        "phase": 1,
        "verdict": verdict,
        "oos_metrics": oos_metrics,
        "spliced_metrics": spliced_metrics,
        "param_sets": [step_results[s["id"]]["locked_params"] for s in STEPS],
        "n_unique_param_sets": n_unique,
        "is_ar_mean": round(is_avg, 1),
        "oos_ar": oos_ar,
        "oos_is_ratio_pct": round(ratio, 0),
    }
    out_path = OUT_DIR / "spliced_result.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save NAV CSV for reference
    nav_path = OUT_DIR / "spliced_nav.csv"
    stitched.to_csv(nav_path, index=False, encoding="utf-8")

    print(f"\nFinal saved: {out_path}")
    print(f"NAV saved: {nav_path}")
    return final


def main():
    parser = argparse.ArgumentParser(description="WF Phase 1")
    parser.add_argument("--step", default="all", help="1 | 2 | all")
    parser.add_argument("--step-id", default=None, help="step1 | step2 | step3 (single window)")
    parser.add_argument("--group-id", type=int, default=None, help="0-3 (single group)")
    args = parser.parse_args()

    if args.step_id and args.group_id is not None:
        # Single group mode
        _run_single_group(args.step_id, args.group_id)
    elif args.step_id:
        # Single window mode
        _run_single_window(args.step_id)
    else:
        if args.step in ("1", "all"):
            step1()
        if args.step in ("2", "all"):
            step2()


def _run_single_window(sid):
    """Run all groups for a single training window."""
    step_info = next(s for s in STEPS if s["id"] == sid)
    t_start, t_end = step_info["train"]
    print(f"{sid}: train={t_start} ~ {t_end}")

    step_path = OUT_DIR / f"{sid}_result.json"
    locked = dict(DEFAULT_LOCK)
    group_results = []
    start_from = 0
    if step_path.exists():
        existing = json.loads(step_path.read_text("utf-8"))
        group_results = existing.get("groups", [])
        locked = existing.get("locked_params", dict(DEFAULT_LOCK))
        start_from = len(group_results)
        print(f"  loaded {start_from}/{len(GROUPS)} groups")

    for gi, group in enumerate(GROUPS):
        if gi < start_from:
            continue
        t0 = time.time()
        print(f"-- {group['name']} ({len(group['keys'])} params, {N_TRIALS} trials) --", flush=True)
        gr = optimize_group_tpe(locked, group, t_start, t_end, sid)
        group_results.append(gr)
        for k in group["keys"]:
            locked[k] = gr["best_params"][k]
        if "w7" in group["keys"]:
            locked["w1"], locked["w3"], _ = _weights_from_w7(locked["w7"])
        elapsed = time.time() - t0
        print(f"  elapsed: {elapsed:.0f}s  AR={gr['AR']:.1f}% MDD={gr['MDD']:.1f}%", flush=True)

        # Save after each group
        step_result = {
            "step_id": sid, "train_window": [t_start, t_end],
            "test_window": step_info["test"],
            "locked_params": {k: locked[k] for k in sorted(locked)},
            "groups": group_results,
        }
        step_path.write_text(json.dumps(step_result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  saved: {step_path}", flush=True)


def _run_single_group(sid, gi):
    """Run a single group for a single window."""
    step_info = next(s for s in STEPS if s["id"] == sid)
    t_start, t_end = step_info["train"]
    group = GROUPS[gi]

    step_path = OUT_DIR / f"{sid}_result.json"
    locked = dict(DEFAULT_LOCK)
    group_results = []
    if step_path.exists():
        existing = json.loads(step_path.read_text("utf-8"))
        group_results = existing.get("groups", [])
        locked = existing.get("locked_params", dict(DEFAULT_LOCK))
        print(f"  loaded {len(group_results)} existing groups")

    # Use locked_params from saved result if available
    if group_results and step_path.exists():
        saved = json.loads(step_path.read_text("utf-8"))
        locked = {**DEFAULT_LOCK, **saved.get("locked_params", {})}
    else:
        locked = dict(DEFAULT_LOCK)

    print(f"{sid}/{group['name']}: train={t_start} ~ {t_end}", flush=True)
    t0 = time.time()
    gr = optimize_group_tpe(locked, group, t_start, t_end, sid)
    group_results.append(gr)

    for k in group["keys"]:
        locked[k] = gr["best_params"][k]
    if "w7" in group["keys"]:
        locked["w1"], locked["w3"], _ = _weights_from_w7(locked["w7"])

    elapsed = time.time() - t0
    print(f"  elapsed: {elapsed:.0f}s  AR={gr['AR']:.1f}% MDD={gr['MDD']:.1f}%", flush=True)

    step_result = {
        "step_id": sid, "train_window": [t_start, t_end],
        "test_window": step_info["test"],
        "locked_params": {k: locked[k] for k in sorted(locked)},
        "groups": group_results,
    }
    step_path.write_text(json.dumps(step_result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  saved: {step_path}", flush=True)


if __name__ == "__main__":
    main()
