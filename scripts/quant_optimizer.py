#!/usr/bin/env python3
"""
Unified Parameter Optimization Framework for etf-report quant system.

Strategies: grid, random, bayesian (Optuna TPE).
Independent background execution, checkpoint-resume, structured output.

Usage:
  python scripts/quant_optimizer.py --preset daily_aggressive --strategy random --n-trials 200
  python scripts/quant_optimizer.py --preset daily_aggressive --strategy bayesian --auto-bounds --n-trials 100
  python scripts/quant_optimizer.py --preset daily_aggressive --strategy grid --params "w1=30,40,50 concentration=0,0.5,1"
"""
import argparse
import json
import os
import signal
import sys
import time
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    import optuna
except ImportError:
    optuna = None

from etf_report.core.quant_contract import (
    PARAM_BOUNDS, get_param_bounds, get_param_type, auto_bounds,
    tuner_params_to_config_override, validate_tuner_params,
    preset_to_tuner_params,
    _WEIGHT_PARAM_KEYS,
)
from quant_backtest import run_backtest, load_config as _load_backtest_config
from etf_report.core.quant_data_utils import load_etf_data as _load_etf_data

DATA_DIR = PROJECT_ROOT / "data" / "quant"
RESEARCH_DIR = PROJECT_ROOT / "research" / "params"

# ── CLI defaults ────────────────────────────────────────────────────────
METRIC_NAMES = ["calmar", "sharpe", "sortino", "annual_return", "total_return"]
PERIOD_PRESETS = {
    "1Y": 365,
    "3Y": 1095,
    "6Y": 2190,
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. OptimizationConfig
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class OptimizationConfig:
    preset: str = "daily_aggressive"
    strategy: str = "random"
    n_trials: int = 100
    metric: str = "calmar"
    periods: list = field(default_factory=lambda: [("1Y", None, None)])
    param_overrides: dict = field(default_factory=dict)
    auto_bounds_flag: bool = False
    seed: int = 42
    output_dir: Path = None
    resume: bool = False
    save_nav: int = 0
    end_date: str = None
    universe_str: str = None
    constraints: list = field(default_factory=list)

    @property
    def multi_period(self):
        return len(self.periods) > 1


def _compute_period(label, end_date_str):
    days = PERIOD_PRESETS.get(label, 365)
    end = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else datetime.now()
    start = end - timedelta(days=days)
    return (label, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Quant Parameter Optimizer")
    p.add_argument("--preset", default="daily_aggressive",
                   help="Target preset (default: daily_aggressive)")
    p.add_argument("--strategy", default="random", choices=["grid", "random", "bayesian"],
                   help="Search strategy (default: random)")
    p.add_argument("--n-trials", type=int, default=100,
                   help="Number of trials, ignored for grid (default: 100)")
    p.add_argument("--metric", default="calmar", choices=METRIC_NAMES,
                   help="Optimization objective (default: calmar)")
    p.add_argument("--periods", default="1Y,3Y",
                   help="Comma-separated period labels: 1Y,3Y,6Y")
    p.add_argument("--params", default=None,
                   help='Explicit param space: "w1=20,30,40 concentration=0,0.5,1"')
    p.add_argument("--auto-bounds", action="store_true", dest="auto_bounds_flag",
                   help="Derive search ranges from preset current values")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default=None, dest="output_dir",
                   help="Output directory (auto: research/params/{preset}-{date}/)")
    p.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    p.add_argument("--save-nav", type=int, default=0,
                   help="Save NAV CSVs for top N trials")
    p.add_argument("--universe", default=None, dest="universe_str",
                   help="ETF filter: '*'=all, comma-list=subset, omit=active-only")
    p.add_argument("--constraint", default=None, action="append", dest="constraints",
                   help="Constraint: mdd,-20 = MDD must be >= -20pct, bear,0.15,0.30 = bear pos in [0.15,0.30]. Repeatable.")
    p.add_argument("--end", default=None, dest="end_date",
                   help="End date override (default: today)")
    args = p.parse_args(argv)

    end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")
    periods = [_compute_period(l.strip(), end_date) for l in args.periods.split(",")]

    param_overrides = {}
    if args.params:
        param_overrides = _parse_params_arg(args.params)

    output_dir = args.output_dir
    if output_dir:
        output_dir = Path(output_dir)
        # Auto-bump if directory already exists
        v = 2
        while output_dir.exists():
            output_dir = Path(f"{args.output_dir}-v{v}")
            v += 1
    else:
        ts = datetime.now().strftime("%Y%m%d")
        base = RESEARCH_DIR / f"{args.preset}-{ts}"
        output_dir = base
        v = 2
        while output_dir.exists():
            output_dir = RESEARCH_DIR / f"{args.preset}-{ts}-v{v}"
            v += 1

    return OptimizationConfig(
        preset=args.preset,
        strategy=args.strategy,
        n_trials=args.n_trials,
        metric=args.metric,
        periods=periods,
        param_overrides=param_overrides,
        auto_bounds_flag=args.auto_bounds_flag,
        seed=args.seed,
        output_dir=output_dir,
        resume=args.resume,
        save_nav=args.save_nav,
        universe_str=args.universe_str,
        constraints=args.constraints or [],
        end_date=end_date,
    )


def _parse_params_arg(s):
    """Parse 'key=val1,val2,val3 key2=min:max:step' into bounds overrides."""
    result = {}
    for token in s.strip().split():
        if "=" not in token:
            continue
        key, vals = token.split("=", 1)
        key = key.strip()
        vals = vals.strip()
        if ":" in vals:
            # range format: min:max or min:max:step
            parts = vals.split(":")
            lo, hi = float(parts[0]), float(parts[1])
            step = float(parts[2]) if len(parts) > 2 else None
            b = {"min": lo, "max": hi}
            if step is not None:
                b["step"] = step
            result[key] = b
        else:
            # discrete values: v1,v2,v3
            items = [v.strip() for v in vals.split(",")]
            # try numeric
            numeric = []
            for v in items:
                try:
                    numeric.append(float(v) if "." in v or "e" in v.lower() else int(v))
                except ValueError:
                    numeric.append(v)
            result[key] = {"values": numeric}
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. ParamSpace
# ═══════════════════════════════════════════════════════════════════════════
class ParamSpace:
    def __init__(self, bounds: dict, weight_keys: frozenset = None):
        self.bounds = bounds
        self.weight_keys = weight_keys or _WEIGHT_PARAM_KEYS
        self._cache_all_keys = None

    @property
    def all_keys(self):
        if self._cache_all_keys is None:
            self._cache_all_keys = sorted(self.bounds.keys())
        return self._cache_all_keys

    def get_active_weight_keys(self, keys_subset=None):
        keys = keys_subset or self.all_keys
        return sorted(k for k in keys if k in self.weight_keys)

    def resolve_weights(self, params: dict):
        """Ensure weight params sum to ~100. Fill missing, normalize proportionally."""
        wkeys = self.get_active_weight_keys()
        if len(wkeys) < 2:
            return params
        params = dict(params)
        for wk in wkeys:
            if wk not in params:
                b = self.bounds.get(wk, {})
                lo, hi = b.get("min", 0), b.get("max", 100)
                params[wk] = (lo + hi) // 2
        total = sum(params.get(k, 0) for k in wkeys)
        if total > 0:
            for wk in wkeys:
                params[wk] = max(0, int(round(params[wk] * 100.0 / total)))
        # Fix rounding error on last key
        used = sum(params.get(k, 0) for k in wkeys[:-1])
        params[wkeys[-1]] = max(0, 100 - used)
        return params

    def generate_grid(self):
        """Yield all combinations as param dicts."""
        keys = []
        value_lists = []
        for key in self.all_keys:
            b = self.bounds[key]
            tp = b.get("type", "continuous")
            if "values" in b:
                values = b["values"]
            elif tp == "categorical":
                values = b["choices"]
            elif tp in ("continuous", "integer"):
                lo, hi = b["min"], b["max"]
                step = b.get("step", 1 if tp == "integer" else None)
                if step is None:
                    step = (hi - lo) / 10.0
                vals = []
                v = lo
                while v <= hi + 1e-9:
                    vals.append(round(v, 5) if tp == "continuous" else int(round(v)))
                    v += step
                values = sorted(set(vals))
            elif tp == "special":
                values = [b.get("value")]
            elif tp == "weight":
                lo, hi = b["min"], b["max"]
                step = b.get("step", 5)
                values = list(range(lo, hi + 1, step))
            else:
                values = [None]
            keys.append(key)
            value_lists.append(values)
        # Cartesian product
        from itertools import product
        for combo in product(*value_lists):
            params = dict(zip(keys, combo))
            yield self.resolve_weights(params)

    def sample_random(self, n: int, rng: np.random.Generator):
        """Yield n random param dicts."""
        for _ in range(n):
            params = {}
            weight_vals = {}
            wkeys = self.get_active_weight_keys()
            independent = wkeys[:-1]
            for key in self.all_keys:
                b = self.bounds[key]
                tp = b.get("type", "continuous")
                if key in independent:
                    val = rng.integers(b["min"], b["max"] + 1)
                    weight_vals[key] = int(val)
                    params[key] = int(val)
                elif tp == "weight":
                    continue  # resolved after
                elif tp == "continuous":
                    if "values" in b:
                        params[key] = rng.choice(b["values"])
                    else:
                        step = b.get("step")
                        if step:
                            n = int(round((b["max"] - b["min"]) / step))
                            params[key] = float(b["min"] + rng.integers(0, n + 1) * step)
                        else:
                            params[key] = float(rng.uniform(b["min"], b["max"]))
                elif tp == "integer":
                    step = int(b.get("step", 1))
                    vals = list(range(int(b["min"]), int(b["max"]) + 1, step))
                    params[key] = int(rng.choice(vals))
                elif tp == "categorical":
                    params[key] = rng.choice(b["choices"])
                elif tp == "special":
                    params[key] = b.get("value")
            params = self.resolve_weights(params)
            yield params


# ═══════════════════════════════════════════════════════════════════════════
# 3. BacktestRunner
# ═══════════════════════════════════════════════════════════════════════════
class BacktestRunner:
    def __init__(self, preset: str, data_dir: Path, project_root: Path, universe_filter=None):
        self.preset = preset
        self.data_dir = data_dir
        self.project_root = project_root
        self._preloaded = None
        self.universe_filter = universe_filter

    def _ensure_preloaded(self):
        if self._preloaded is not None:
            return
        print("  [preload] loading config & ETF data ...", flush=True)
        cfg = _load_backtest_config(preset=self.preset)
        universe = cfg.get("universe", [])
        all_daily = {}
        all_weekly = {}
        for e in universe:
            code = e["code"]
            daily, weekly = _load_etf_data(code, self.data_dir)
            if daily is not None:
                all_daily[code] = daily
            if weekly is not None:
                all_weekly[code] = weekly
        self._preloaded = {
            "all_daily": all_daily,
            "all_weekly": all_weekly,
        }
        print(f"  [preload] {len(all_daily)} ETFs loaded", flush=True)

    def run(self, params: dict, start_date: str, end_date: str) -> dict:
        self._ensure_preloaded()
        config_override = tuner_params_to_config_override(params)
        nav_df, signal_history, extra = run_backtest(
            start_date=start_date,
            end_date=end_date,
            preset=self.preset,
            preloaded=self._preloaded,
            config_override=config_override,
            universe_filter=self.universe_filter,
        )
        if nav_df is None or len(nav_df) == 0:
            return None
        return _extract_metrics(nav_df, signal_history, extra)


def _extract_metrics(nav_df, signal_history, extra):
    ic = 1_000_000.0
    fn = nav_df["nav"].iloc[-1]
    total_return = (fn / ic - 1) * 100
    days = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days
    if days > 0:
        annual_return = ((fn / ic) ** (365.0 / days) - 1) * 100
    else:
        annual_return = 0.0
    cummax = nav_df["nav"].cummax()
    mdd = ((nav_df["nav"] - cummax) / cummax * 100).min()
    dr = nav_df["nav"].pct_change().dropna()
    if len(dr) > 0 and dr.std() > 0:
        sharpe = (dr.mean() * 252 - 0.02) / (dr.std() * np.sqrt(252))
    else:
        sharpe = 0.0
    ds = dr[dr < 0]
    if len(ds) > 0 and ds.std() > 0:
        sortino = (dr.mean() * 252 - 0.02) / (ds.std() * np.sqrt(252))
    else:
        sortino = 0.0
    calmar = annual_return / abs(mdd) if mdd != 0 else 0.0
    from quant_backtest import count_actual_rebalances
    actual_trades = count_actual_rebalances(signal_history)
    commission_total = extra.get("total_commission", 0) if extra else 0
    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "max_drawdown": round(mdd, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4),
        "n_trades": actual_trades,
        "n_signals": len(signal_history),
        "commission": round(commission_total, 2),
        "final_nav": round(fn, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. CheckpointManager
# ═══════════════════════════════════════════════════════════════════════════
class CheckpointManager:
    def __init__(self, output_dir: Path):
        self.path = output_dir / "checkpoint.json"
        self._data = None

    def _ensure_loaded(self):
        if self._data is None:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            else:
                self._data = {"completed": []}

    def save(self):
        self._ensure_loaded()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def is_done(self, params: dict, period_label: str):
        self._ensure_loaded()
        sig = _trial_signature(params, period_label)
        for c in self._data.get("completed", []):
            if c.get("sig") == sig:
                return True
        return False

    def mark_done(self, params: dict, period_label: str, metrics: dict):
        self._ensure_loaded()
        sig = _trial_signature(params, period_label)
        self._data.setdefault("completed", []).append({
            "sig": sig,
            "params": _serializable(params),
            "period": period_label,
            "metrics": metrics,
        })
        self.save()

    def get_completed(self):
        self._ensure_loaded()
        return self._data.get("completed", [])


def _trial_signature(params, period_label):
    return f"{_params_fingerprint(params)}|{period_label}"


def _params_fingerprint(params):
    return json.dumps(_serializable(params), sort_keys=True, ensure_ascii=False)


def _serializable(obj):
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ═══════════════════════════════════════════════════════════════════════════
# 5. Search Strategies
# ═══════════════════════════════════════════════════════════════════════════
class SearchStrategy(ABC):
    @abstractmethod
    def generate(self, space: ParamSpace, n: int, seed: int) -> Iterator[dict]:
        ...


class GridSearch(SearchStrategy):
    def generate(self, space: ParamSpace, n: int, seed: int) -> Iterator[dict]:
        yield from space.generate_grid()


class RandomSearch(SearchStrategy):
    def generate(self, space: ParamSpace, n: int, seed: int) -> Iterator[dict]:
        rng = np.random.default_rng(seed)
        yield from space.sample_random(n, rng)


class BayesianSearch(SearchStrategy):
    def generate(self, space: ParamSpace, n: int, seed: int) -> Iterator[dict]:
        # Optuna TPE — we create the study, define suggest logic per param,
        # and yield trial params. The actual objective evaluation happens
        # in the orchestrator, which calls study.tell().
        pass  # Special: orchestrator handles Optuna lifecycle


# ═══════════════════════════════════════════════════════════════════════════
# 6. ReportGenerator
# ═══════════════════════════════════════════════════════════════════════════
class ReportGenerator:
    def __init__(self, cfg: OptimizationConfig, baseline_metrics: dict, all_results: list):
        self.cfg = cfg
        self.baseline = baseline_metrics
        self.results = all_results

    def generate_all(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(output_dir)
        self._write_report(output_dir)

    def _write_json(self, output_dir: Path):
        best = {}
        for m in METRIC_NAMES:
            key_fn = {"max_drawdown": min}.get(m, max)
            try:
                best_trial = key_fn(self.results, key=lambda r: r.get("composite", {}).get(m, -9999))
            except (ValueError, KeyError):
                best_trial = None
            if best_trial:
                best[m] = {"trial_id": best_trial["id"], "params": best_trial["params"],
                           "periods": best_trial["metrics"]}
        payload = {
            "meta": {
                "preset": self.cfg.preset,
                "strategy": self.cfg.strategy,
                "metric": self.cfg.metric,
                "n_trials": len(self.results),
                "periods": {lab: [s, e] for lab, s, e in self.cfg.periods},
                "seed": self.cfg.seed,
                "baseline": self.baseline,
            },
            "trials": [
                {"id": r["id"], "params": r["params"], "metrics": r["metrics"],
                 "composite": r.get("composite", {})}
                for r in self.results
            ],
            "best": best,
        }
        path = output_dir / "results.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  results.json -> {path}")

    def _write_report(self, output_dir: Path):
        best = self.results[0] if self.results else None
        lines = []
        lines.append(f"# {self.cfg.preset} 参数优化报告")
        lines.append(f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**策略**: {self.cfg.strategy}, {len(self.results)} trials")
        lines.append(f"**优化目标**: {self.cfg.metric}")
        lines.append("")

        # Baseline comparison
        lines.append("## 基线对比")
        lines.append("")
        if self.baseline:
            lines.append("| Period | Metric | Baseline | Best | Delta |")
            lines.append("|--------|--------|----------|------|-------|")
            for bl in self.baseline:
                blab = bl["period"]
                bm = bl.get(self.cfg.metric, 0)
                best_m = None
                if best:
                    best_m = best["metrics"].get(blab, {}).get(self.cfg.metric, 0)
                if best_m is not None:
                    delta = best_m - bm
                    lines.append(f"| {blab} | {self.cfg.metric} | {bm:.4f} | {best_m:.4f} | {delta:+.4f} |")
        lines.append("")

        # Top 10
        lines.append(f"## Top 10（按 {self.cfg.metric} 排序）")
        lines.append("")
        if best:
            header = "| Rank | " + " | ".join(METRIC_NAMES[:5]) + " | Key Params |"
            lines.append(header)
            sep = "|------|" + "|".join(["--------"] * 5) + "|------------|"
            lines.append(sep)
            top_n = sorted(self.results, key=lambda r: r.get("composite", {}).get(self.cfg.metric, -9999), reverse=True)[:10]
            for i, r in enumerate(top_n):
                c = r.get("composite", {})
                vals = " | ".join(f"{c.get(m, 0):.4f}" for m in METRIC_NAMES[:5])
                kp = ", ".join(f"{k}={v}" for k, v in sorted(r["params"].items()) if v != 0 and k in ("w1", "w3", "w7", "concentration", "f1_ema_period", "score_band"))
                lines.append(f"| {i+1} | {vals} | {kp} |")
        lines.append("")

        # Best by period
        lines.append("## 各周期最佳")
        lines.append("")
        for lab, sd, ed in self.cfg.periods:
            period_results = [r for r in self.results if lab in r.get("metrics", {})]
            if not period_results:
                continue
            best_p = max(period_results, key=lambda r: r["metrics"][lab].get(self.cfg.metric, -9999))
            m = best_p["metrics"][lab]
            lines.append(f"**{lab}** ({sd} ~ {ed}):")
            lines.append(f"- Total: {m.get('total_return',0):+.2f}%  Annual: {m.get('annual_return',0):+.2f}%  MDD: {m.get('max_drawdown',0):.2f}%")
            lines.append(f"- Sharpe: {m.get('sharpe',0):.2f}  Sortino: {m.get('sortino',0):.2f}  Calmar: {m.get('calmar',0):.2f}")
            lines.append(f"- Trades: {m.get('n_trades',0)}/{m.get('n_signals',0)}")
            lines.append(f"- Params: {json.dumps(best_p['params'], ensure_ascii=False)}")
            lines.append("")

        lines.append("## Promotion 建议")
        lines.append("")
        if best and self.baseline:
            all_better = True
            for bl in self.baseline:
                blab = bl["period"]
                bm = bl.get(self.cfg.metric, 0)
                best_m = best["metrics"].get(blab, {}).get(self.cfg.metric, 0)
                if best_m is not None and best_m < bm:
                    all_better = False
                    break
            if all_better:
                lines.append("**Ready to promote**: 在所有周期上，最优 trial 的优化目标不低于基线。")
            else:
                lines.append("**需人工判断**: 部分周期上最优 trial 低于基线，请检查具体数据。")
        lines.append("")

        path = output_dir / "report.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  report.md -> {path}")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Optimizer Orchestrator
# ═══════════════════════════════════════════════════════════════════════════
def _run_baseline(runner: BacktestRunner, cfg: OptimizationConfig):
    """Run a single backtest with the preset's current values to get baseline."""
    yaml_cfg = _load_backtest_config(preset=cfg.preset)
    preset_cfg = yaml_cfg.get("presets", {}).get(cfg.preset)
    if preset_cfg is None:
        print(f"  [baseline] preset '{cfg.preset}' not found, skipping")
        return []
    global_conf = yaml_cfg.get("confidence", {})
    base_params = preset_to_tuner_params(cfg.preset, preset_cfg, global_conf)
    results = []
    for lab, sd, ed in cfg.periods:
        print(f"  [baseline] running {lab} ({sd} ~ {ed}) ...", flush=True)
        m = runner.run(base_params, sd, ed)
        if m:
            m["period"] = lab
            results.append(m)
    return results



def _check_constraints(trial_params: dict, trial_metrics: dict, constraints: list):
    for cst in (constraints or []):
        parts = cst.split(",")
        if parts[0] == "mdd":
            limit = float(parts[1])
            for lab, m in trial_metrics.items():
                mdd = m.get("max_drawdown", 0)
                if mdd < limit:
                    return f"{lab} MDD={mdd:.1f}% < constraint {limit:.1f}%"
        elif parts[0] == "bear":
            lo, hi = float(parts[1]), float(parts[2])
            bear = trial_params.get("ma_bear_pos")
            if bear is not None and (bear < lo or bear > hi):
                return f"ma_bear_pos={bear:.3f} outside [{lo},{hi}]"
    return None

def _run_trial_optuna(trial, runner: BacktestRunner, cfg: OptimizationConfig, space: ParamSpace, baseline_scores: dict):
    """Optuna objective: suggest params, run backtests, return normalized composite score."""
    params = {}
    for key in space.all_keys:
        b = space.bounds[key]
        tp = b.get("type", "continuous")
        if "values" in b:
            params[key] = trial.suggest_categorical(key, b["values"])
        elif tp == "weight":
            wkeys = space.get_active_weight_keys()
            if key == wkeys[-1]:
                continue  # computed as residual
            lo, hi = b.get("min", 0), b.get("max", 100)
            step = b.get("step", 5)
            # Ensure range is step-aligned for Optuna
            hi = lo + ((hi - lo) // step) * step
            if hi <= lo:
                hi = lo + step
            params[key] = trial.suggest_int(key, lo, hi, step=step)
        elif tp == "continuous":
            step = b.get("step")
            if step:
                hi = b["min"] + int((b["max"] - b["min"]) / step) * step
                params[key] = trial.suggest_float(key, b["min"], hi, step=step)
            else:
                params[key] = trial.suggest_float(key, b["min"], b["max"])
        elif tp == "integer":
            step = int(b.get("step", 1))
            hi = b["min"] + ((b["max"] - b["min"]) // step) * step
            params[key] = trial.suggest_int(key, b["min"], hi, step=step)
        elif tp == "categorical":
            params[key] = trial.suggest_categorical(key, b["choices"])
        elif tp == "special":
            params[key] = b.get("value")
    params = space.resolve_weights(params)
    # Validate
    err = validate_tuner_params(params)
    if err:
        raise optuna.TrialPruned(f"Validation failed: {err}")
    # Run all periods (serial — Python GIL makes threads slower for CPU-bound backtests)
    rel_scores = []
    all_metrics = {}
    for lab, sd, ed in cfg.periods:
        m = runner.run(params, sd, ed)
        if m is None:
            raise optuna.TrialPruned(f"Backtest failed for {lab}")
        trial.set_user_attr(f"{lab}_metrics", json.dumps(m))
        all_metrics[lab] = m
        raw = m.get(cfg.metric, -9999)
        bl = baseline_scores.get(lab, 1.0)
        rel_scores.append(raw / bl if bl != 0 else 0.0)
    # Check constraints
    c_err = _check_constraints(params, all_metrics, cfg.constraints)
    if c_err:
        raise optuna.TrialPruned(f"Constraint: {c_err}")
    return float(np.mean(rel_scores))


def run(cfg: OptimizationConfig):
    if optuna is None:
        print("ERROR: optuna not installed. Run: pip install optuna")
        sys.exit(1)
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = cfg.output_dir / "log.txt"

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    log(f"Optimizer start: preset={cfg.preset} strategy={cfg.strategy} metric={cfg.metric}")
    log(f"  periods={[(l,s,e) for l,s,e in cfg.periods]} seed={cfg.seed}")
    log(f"  output={cfg.output_dir}")

    # ── Build runner and baseline ──
    # Parse universe filter
    universe_filter = None
    if cfg.universe_str is not None:
        if cfg.universe_str.strip() == '*':
            universe_filter = [e["code"] for e in _load_backtest_config(preset=cfg.preset).get("universe", [])]
        elif cfg.universe_str.strip():
            universe_filter = [c.strip() for c in cfg.universe_str.split(",") if c.strip()]

    runner = BacktestRunner(cfg.preset, DATA_DIR, PROJECT_ROOT, universe_filter=universe_filter)
    log("Computing baseline ...")
    baseline_metrics = _run_baseline(runner, cfg)
    for bm in baseline_metrics:
        log(f"  baseline {bm['period']}: calmar={bm['calmar']:.4f} sharpe={bm['sharpe']:.4f} annual={bm['annual_return']:.2f}%")
    baseline_scores = {bm["period"]: bm.get(cfg.metric, 1.0) for bm in baseline_metrics}

    # ── Build param space ──
    if cfg.auto_bounds_flag:
        yaml_cfg = _load_backtest_config(preset=cfg.preset)
        preset_cfg = yaml_cfg.get("presets", {}).get(cfg.preset, {})
        global_conf = yaml_cfg.get("confidence", {})
        tuner_params = preset_to_tuner_params(cfg.preset, preset_cfg, global_conf)
        bounds = auto_bounds(tuner_params, cfg.param_overrides)
    elif cfg.param_overrides:
        bounds = dict(get_param_bounds())
        for key, override in cfg.param_overrides.items():
            if key in bounds:
                bounds[key] = dict(bounds[key], **override)
        override_keys = set(cfg.param_overrides.keys())
        if override_keys:
            # Only include explicitly overridden params + fill missing weights from preset
            bounds = {k: v for k, v in bounds.items() if k in override_keys}
            # Ensure weight params that are needed are present (inherit preset values)
            wkeys_in = set(k for k in override_keys if bounds.get(k, {}).get("type") == "weight")
            if wkeys_in:
                yaml_cfg = _load_backtest_config(preset=cfg.preset)
                preset_cfg = yaml_cfg.get("presets", {}).get(cfg.preset, {})
                global_conf = yaml_cfg.get("confidence", {})
                tuner_params = preset_to_tuner_params(cfg.preset, preset_cfg, global_conf)
                for wk in _WEIGHT_PARAM_KEYS:
                    if wk not in bounds:
                        cur = tuner_params.get(wk, 25)
                        bounds[wk] = {"type": "weight", "min": cur, "max": cur, "step": 1}
    else:
        bounds = get_param_bounds()
    space = ParamSpace(bounds)
    log(f"Param space: {len(space.all_keys)} params")

    # ── Checkpoint ──
    ckpt = CheckpointManager(cfg.output_dir)
    if cfg.resume:
        ckpt._ensure_loaded()
        log(f"Resume: {len(ckpt.get_completed())} already completed")

    # ── Generate trials ──
    all_results = []
    if cfg.resume:
        # Group checkpoint entries by params fingerprint
        by_params = {}
        for c in ckpt.get_completed():
            fp = _params_fingerprint(c.get("params", {}))
            if fp not in by_params:
                by_params[fp] = {"params": c.get("params", {}), "metrics": {}}
            by_params[fp]["metrics"][c.get("period")] = c.get("metrics", {})
        for fp, entry in by_params.items():
            composite = {}
            valid_metrics = {lab: m for lab, m in entry["metrics"].items() if m}
            if valid_metrics:
                for mk in METRIC_NAMES:
                    rel_vals = []
                    for lab, m in valid_metrics.items():
                        raw = m.get(mk, 0)
                        bl = baseline_scores.get(lab, 1.0)
                        rel_vals.append(raw / bl if bl != 0 else 0.0)
                    composite[mk] = float(np.mean(rel_vals)) if rel_vals else 0.0
            all_results.append({
                "id": len(all_results),
                "params": entry["params"],
                "metrics": entry["metrics"],
                "composite": composite,
            })

    trial_start = len(all_results)

    if cfg.strategy == "bayesian":
        # Use Optuna
        study_name = f"{cfg.preset}_{cfg.output_dir.name}"
        storage_name = f"sqlite:///{cfg.output_dir / 'optuna.db'}"
        study = optuna.create_study(
            study_name=study_name,
            storage=storage_name,
            direction="maximize",
            load_if_exists=cfg.resume,
            sampler=optuna.samplers.TPESampler(seed=cfg.seed),
        )

        def objective(trial):
            return _run_trial_optuna(trial, runner, cfg, space, baseline_scores)

        log(f"Bayesian: {cfg.n_trials} trials (Optuna TPE)")
        study.optimize(objective, n_trials=cfg.n_trials, show_progress_bar=True)

        # Collect results from study
        for t in study.trials:
            if t.state != optuna.trial.TrialState.COMPLETE:
                continue
            params = {}
            for key in space.all_keys:
                if key in t.params:
                    params[key] = t.params[key]
            params = space.resolve_weights(params)
            metrics = {}
            for lab, sd, ed in cfg.periods:
                attr_key = f"{lab}_metrics"
                raw = t.user_attrs.get(attr_key)
                if raw:
                    metrics[lab] = json.loads(raw)
            composite = {cfg.metric: t.value} if t.value is not None else {}
            all_results.append({
                "id": len(all_results),
                "params": _serializable(params),
                "metrics": metrics,
                "composite": composite,
            })
    else:
        # Grid or random
        if cfg.strategy == "grid":
            strategy = GridSearch()
            n = None  # grid uses all
        else:
            strategy = RandomSearch()
            n = cfg.n_trials
        trial_iter = strategy.generate(space, n, cfg.seed)

        trial_count = 0
        for params in trial_iter:
            if cfg.strategy != "grid" and trial_count >= cfg.n_trials:
                break
            trial_id = trial_start + trial_count
            trial_count += 1

            # Per-period results
            trial_metrics = {}
            all_completed = True
            for lab, sd, ed in cfg.periods:
                if ckpt.is_done(params, lab):
                    log(f"  [{trial_id}] skip {lab} (checkpoint)")
                    for c in ckpt.get_completed():
                        if c.get("sig") == _trial_signature(params, lab):
                            trial_metrics[lab] = c.get("metrics", {})
                            break
                    continue
                all_completed = False
                log(f"  [{trial_id}] running {lab} ({sd} ~ {ed}) ...")
                t0 = time.time()
                m = runner.run(params, sd, ed)
                elapsed = time.time() - t0
                if m is None:
                    log(f"  [{trial_id}] {lab} FAILED ({elapsed:.1f}s)")
                    trial_metrics[lab] = {}
                else:
                    log(f"  [{trial_id}] {lab} calmar={m['calmar']:.4f} sharpe={m['sharpe']:.4f} ({elapsed:.1f}s)")
                    trial_metrics[lab] = m
                    ckpt.mark_done(params, lab, m)

            if not trial_metrics:
                continue

            # Composite score: mean of relative-to-baseline across periods
            composite = {}
            for m in METRIC_NAMES:
                vals = []
                for lab in trial_metrics:
                    raw = trial_metrics[lab].get(m, 0)
                    bl = baseline_scores.get(lab, 1.0)
                    vals.append(raw / bl if bl != 0 else 0.0)
                if vals:
                    composite[m] = float(np.mean(vals))

            all_results.append({
                "id": trial_id,
                "params": _serializable(params),
                "metrics": trial_metrics,
                "composite": composite,
            })

            # Periodic flush
            if len(all_results) % 20 == 0:
                log(f"  ... {len(all_results)} trials done, saving intermediate results")

    # ── Report ──
    log(f"Generating report ({len(all_results)} trials) ...")
    # Sort by primary metric desc
    all_results.sort(key=lambda r: r.get("composite", {}).get(cfg.metric, -9999), reverse=True)
    ReportGenerator(cfg, baseline_metrics, all_results).generate_all(cfg.output_dir)

    # ── Auto-analyze ──
    study_name = f"{cfg.preset}_{cfg.output_dir.name}"
    log("Running optimization_analyzer...")
    analyzer_cmd = [
        sys.executable, str(PROJECT_ROOT / "scripts" / "optimization_analyzer.py"),
        "--study", study_name, "--preset", cfg.preset, "--baseline-preset", cfg.preset,
        "--start", cfg.periods[-1][1] if cfg.periods else "2020-06-17",
        "--end", cfg.end_date or datetime.now().strftime("%Y-%m-%d"),
        "--top-n", "3", "--output", str(cfg.output_dir / "analysis.json"),
    ]
    try:
        subprocess.run(analyzer_cmd, check=True, capture_output=True, text=True, timeout=1800)
        log("  analysis.json generated")
    except Exception as e:
        print(f"  WARNING: analyzer failed: {e}", file=sys.stderr)

    # ── Done marker ──
    marker = cfg.output_dir / ".optimizer_done"
    marker.write_text(datetime.now().isoformat())
    log(f"DONE. Results in {cfg.output_dir}")
    if all_results:
        best = all_results[0]
        log(f"  Best: {cfg.metric}={best['composite'].get(cfg.metric, 0):.4f}")
        log(f"  Params: {json.dumps(best['params'], ensure_ascii=False)}")


# ── Signal handler ──
def _install_signal_handler(output_dir=None):
    def handler(sig, frame):
        print("\n[optimizer] Interrupted. Checkpoint saved (if any).")
        sys.exit(1)
    signal.signal(signal.SIGINT, handler)


# ═══════════════════════════════════════════════════════════════════════════
def main(argv=None):
    cfg = parse_args(argv)
    _install_signal_handler()
    run(cfg)


if __name__ == "__main__":
    main()
