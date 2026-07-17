"""Research toolbelt — composable primitives for parameter optimization.

Each primitive does one thing. Compose them in a few lines per study.

Usage sketch:

    from research_utils import *

    # Single backtest
    m = backtest(MH=2, TB=8, bull=1.80)

    # 1-D sweep
    results = sweep(TB=range(0,9), lock=dict(MH=2, bull=1.80))

    # Grouped sweep
    results = group_sweep(
        group_by='MH', group_values=[2,3,4,5,6],
        vary='TB', vary_fn=lambda mh: range(0, mh*4+1),
        lock=dict(bull=1.80),
    )

    # Pick best per group
    best = pick_best(results, group_by='MH', metric='AR')

    # Write metrics cache for Tuner consumption
    write_preset_metrics('config/preset_metrics.json', best)
"""
import json, hashlib, pathlib, sys, yaml
from datetime import datetime
from typing import Callable

# ── Paths ──────────────────────────────────────────────────────────────────
_PROJ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJ / "src"))
sys.path.insert(0, str(_PROJ / "scripts"))

from quant_backtest import run_backtest

WINDOW_6Y = ("2020-06-01", "2026-06-01")
WINDOW_3Y = ("2023-06-01", "2026-06-01")
WINDOW_1Y = ("2025-06-01", "2026-06-01")
WINDOWS = {"6Y": WINDOW_6Y, "3Y": WINDOW_3Y, "1Y": WINDOW_1Y}
DEFAULT_WINDOW = "6Y"

# ── Default locked params ──────────────────────────────────────────────────
DEFAULT_LOCK = dict(
    bull=1.80, bear=0.60, MA=19,
    N=40, C=0.71, CS=8.68, band=0.03, band_sensitivity=0.0,
    MH=2, TB=8,
)


def redistribute_weights(w7, base_w1=0.71, base_w3=0.13):
    """Redistribute w1/w3 proportionally when w7 changes.

    All values in engine scale (0-1). Returns (w1, w3, w7).
    Preserves w1:w3 ratio = base_w1:base_w3.

    Example:
        redistribute_weights(0.10) → (0.761, 0.139, 0.10)
        redistribute_weights(0)    → (0.845, 0.155, 0.0)
    """
    rem = 1.0 - w7
    w1 = base_w1 * rem / (base_w1 + base_w3)
    w3 = base_w3 * rem / (base_w1 + base_w3)
    return round(w1, 4), round(w3, 4), w7


def _build_override(params: dict) -> dict:
    """Convert flat param dict → config_override for run_backtest."""
    override = {
        "position": {
            "max_holdings": params.get("MH", 2),
            "signal_steps": params.get("N", 40),
            "top_boost": params.get("TB", 0),
            "concentration": params.get("C", 0.71),
            "c_sensitivity": params.get("CS", 8.68),
            "band": params.get("band", 0.03),
            "band_sensitivity": params.get("band_sensitivity", 0.0),
            "rebalance_freq": "daily",
        },
        "confidence": {
            "ma_bull_pos": params.get("bull", 1.80),
            "ma_bear_pos": params.get("bear", 0.60),
            "ma_trend_period": params.get("MA", 19),
        },
        "factors": {
            "log_return_deviation": {
                "window_days": params.get("F7", 17),
            },
        },
    }
    # Scoring weights (F1/F3/F7) and sensitivity overrides
    if any(k in params for k in ('w1','w3','w7')):
        override.setdefault("scoring", {})
        w = {}
        if 'w1' in params: w['ema_deviation'] = params['w1'] / 100.0  # UI % → engine 0-1 scale
        if 'w3' in params: w['volume_ratio'] = params['w3'] / 100.0
        if 'w7' in params: w['log_return_deviation'] = params['w7'] / 100.0
        if w: override['scoring']['weights'] = w
    if any(k in params for k in ('f1_s','f3_s','f7_up_power','f7_up_span','f7_down_power','f7_down_span')):
        override.setdefault("scoring", {}).setdefault("sensitivity", {})
        s = override['scoring']['sensitivity']
        if 'f1_s' in params: s['f1'] = params['f1_s']
        if 'f3_s' in params: s['f3'] = params['f3_s']
        if 'f7_up_power' in params: s['f7_up_power'] = params['f7_up_power']
        if 'f7_up_span' in params: s['f7_up_span'] = params['f7_up_span']
        if 'f7_down_power' in params: s['f7_down_power'] = params['f7_down_power']
        if 'f7_down_span' in params: s['f7_down_span'] = params['f7_down_span']
    return override


def backtest(verbose: bool = False, window: str = None, **params) -> dict:
    """Run one backtest. Returns {AR, MDD, Calmar, Sortino, trades, MH, TB, ...}.

    Example: backtest(MH=3, TB=5, bull=1.80, window='3Y')
    Pass verbose=True to see full backtest output (debugging).
    window: '6Y' (default), '3Y', or '1Y'.
    """
    w = window or DEFAULT_WINDOW
    start, end = WINDOWS.get(w, WINDOW_6Y)
    p = {**DEFAULT_LOCK, **params}
    override = _build_override(p)
    _, _, extra = run_backtest(start, end, preset="gam-0",
                               config_override=override, return_data=False,
                               verbose=verbose)
    if not extra:
        return {}
    ar = extra.get("annual_return", 0)
    mdd = extra.get("max_drawdown", 0)
    return {
        "AR": round(ar, 1), "MDD": round(mdd, 1),
        "Calmar": round(ar / abs(mdd), 2) if mdd != 0 else 0,
        "Sortino": round(extra.get("sortino", 0), 3),
        "trades": extra.get("trade_count", 0),
        "MH": p["MH"], "TB": p["TB"],
        "bull": p["bull"], "C": p["C"], "CS": p["CS"],
        "N": p["N"], "bear": p["bear"], "MA": p["MA"],
    }


def sweep(vary: str, values: list, lock: dict = None) -> list[dict]:
    """1-D parameter sweep.

    sweep('TB', range(0,9), lock=dict(MH=2, bull=1.80))

    Returns list of result dicts, one per value.
    """
    base = {**DEFAULT_LOCK, **(lock or {})}
    results = []
    for v in values:
        r = backtest(**{**base, vary: v})
        if r:
            results.append(r)
            print(f"  {vary}={v}  AR={r['AR']:.1f}%  MDD={r['MDD']:.1f}%  "
                  f"Calmar={r['Calmar']:.2f}  Sortino={r['Sortino']:.3f}")
    return results


def group_sweep(group_by: str, group_values: list,
                vary: str, vary_fn: Callable,
                lock: dict = None) -> list[dict]:
    """Nested sweep: for each group value, sweep vary across vary_fn(group_value).

    group_sweep(
        group_by='MH', group_values=[2,3,4,5,6],
        vary='TB', vary_fn=lambda mh: range(0, mh*4+1),
        lock=dict(bull=1.80),
    )
    """
    base = {**DEFAULT_LOCK, **(lock or {})}
    results = []
    for g in group_values:
        vals = vary_fn(g)
        if isinstance(vals, int):
            vals = [vals]
        best = None
        for v in vals:
            r = backtest(**{**base, group_by: g, vary: v})
            if r:
                results.append(r)
                print(f"  {group_by}={g} {vary}={v}  AR={r['AR']:.1f}%  MDD={r['MDD']:.1f}%  "
                      f"Calmar={r['Calmar']:.2f}  Sortino={r['Sortino']:.3f}")
    return results


def grid_sweep(vary: dict, lock: dict = None) -> list[dict]:
    """Multi-dimension grid sweep (cartesian product of all vary values).

    grid_sweep({'C': [0.3,0.5,0.71], 'CS': [0,3,5]}, lock=dict(MH=2))

    Returns list of result dicts.
    """
    import itertools as _it
    base = {**DEFAULT_LOCK, **(lock or {})}
    keys = list(vary.keys())
    results = []
    for combo in _it.product(*vary.values()):
        p = dict(zip(keys, combo))
        r = backtest(**{**base, **p})
        if r:
            results.append(r)
            label = ' '.join(f'{k}={v}' for k, v in p.items())
            print(f"  {label}  AR={r['AR']:.1f}%  MDD={r['MDD']:.1f}%  "
                  f"Calmar={r['Calmar']:.2f}  Sortino={r['Sortino']:.3f}")
    return results


def group_grid_sweep(group_by: str, group_values: list,
                     vary: dict, lock: dict = None) -> list[dict]:
    """Grouped multi-dim grid: for each group value, run full grid_sweep.

    group_grid_sweep('MH', [2,3,4,5,6],
                     {'C': [0.3,0.5,0.71], 'CS': [0,3,5]},
                     lock=dict(bull=1.80))
    """
    base = {**DEFAULT_LOCK, **(lock or {})}
    results = []
    for g in group_values:
        print(f"-- {group_by}={g} --")
        r = grid_sweep(vary, lock={**base, group_by: g})
        results.extend(r)
    return results


def optimize_group(preset_name: str, vary_keys: list, bounds: dict,
                   metric: str = "AR", mdd_bound: float = None,
                   n_trials: int = 20, seed: int = 42) -> dict:
    """Grouped TPE optimization for one preset.

    vary_keys: ['w7','f7_up_power','f7_up_span'] etc — must be in backtest() signature
    bounds:    {'w7':(5,30), 'f7_up_power':(5,30), 'f7_up_span':(1,5)} etc
    metric:    'AR', 'Sortino', or 'Calmar'
    mdd_bound: MDD floor (e.g. -40 means MDD >= -40%); None = no constraint

    Returns {"params": {...}, "before": {...}, "after": {...}, "trials": N}

    Weight handling: if w7 is among vary_keys, w1 and w3 absorb the
    remainder proportionally (w1_raw:w3_raw ratio preserved).
    """
    import optuna, yaml, pathlib, warnings
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    warnings.filterwarnings("ignore")

    # Load preset params from YAML
    yp = pathlib.Path(__file__).resolve().parent.parent / "config" / "quant_universe.yaml"
    with open(yp, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    preset = cfg["presets"].get(preset_name, {})
    pos = preset.get("position", {})
    conf = preset.get("confidence", {})

    # Baseline
    lock = dict(
        MH=pos.get("max_holdings", 2), TB=pos.get("top_boost", 0),
        C=pos.get("concentration", 0.71), CS=pos.get("c_sensitivity", 8.68),
        bull=conf.get("ma_bull_pos", 1.80), bear=conf.get("ma_bear_pos", 0.60),
        MA=conf.get("ma_trend_period", 19), band=pos.get("band", 0.03),
        band_sensitivity=pos.get("band_sensitivity", 0.0),
    )
    # Current values for the varying keys
    current = {}
    scoring = preset.get("scoring", {})
    if "w7" in vary_keys:
        w = scoring.get("weights", {})
        current["w1"] = int(round(w.get("ema_deviation", 0.71) * 100))
        current["w3"] = int(round(w.get("volume_ratio", 0.13) * 100))
        current["w7"] = int(round(w.get("log_return_deviation", 0.16) * 100))
    sens = scoring.get("sensitivity", {})
    if "f7_up_power" in vary_keys: current["f7_up_power"] = sens.get("f7_up_power", 23)
    if "f7_up_span" in vary_keys: current["f7_up_span"] = sens.get("f7_up_span", 3.1)

    before = backtest(**{**lock, **current})
    if not before:
        return {"error": "baseline backtest failed"}
    b_metric = before[metric]
    b_mdd = before["MDD"]
    print(f"Baseline: {metric}={b_metric:.3f}  MDD={b_mdd:.1f}%  ({preset_name})")

    # Effective MDD bound
    eff_bound = mdd_bound if mdd_bound is not None else (b_mdd - 2.0)
    print(f"MDD constraint: >= {eff_bound:.1f}%")

    # ── Objective ──
    def objective(trial):
        p = dict(lock)
        # Handle w7 with proportional w1/w3
        if "w7" in vary_keys:
            w7_val = trial.suggest_int("w7", *bounds.get("w7", (5, 30)))
            w1r = trial.suggest_int("w1_raw", 30, 80)
            w3r = trial.suggest_int("w3_raw", 5, 40)
            scale = (100 - w7_val) / (w1r + w3r) if (w1r + w3r) > 0 else 1.0
            p["w1"] = int(round(w1r * scale))
            p["w3"] = int(round(w3r * scale))
            p["w7"] = w7_val
        for k in vary_keys:
            if k in ("w1", "w3", "w7"):
                continue  # handled above
            lo, hi = bounds.get(k, (0, 100))
            if isinstance(lo, int):
                p[k] = trial.suggest_int(k, lo, hi)
            else:
                p[k] = trial.suggest_float(k, lo, hi)
        r = backtest(**p)
        if not r:
            return -9999
        if eff_bound is not None and r["MDD"] < eff_bound:
            return -9999  # MDD constraint violated
        return r.get(metric, -9999)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.enqueue_trial(current)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_p = dict(lock)
    for k, v in study.best_params.items():
        if k.startswith("w1_raw"):
            continue
        if k.startswith("w3_raw"):
            continue
        best_p[k] = v
    # Re-derive w1/w3 from w7
    if "w7" in vary_keys and "w1_raw" in study.best_params:
        w7v = study.best_params["w7"]
        w1r = study.best_params["w1_raw"]
        w3r = study.best_params["w3_raw"]
        scale = (100 - w7v) / (w1r + w3r) if (w1r + w3r) > 0 else 1.0
        best_p["w1"] = int(round(w1r * scale))
        best_p["w3"] = int(round(w3r * scale))
        best_p["w7"] = w7v

    after = backtest(**best_p)
    a_metric = after[metric] if after else 0
    a_mdd = after["MDD"] if after else 0

    print(f"Optimized: {metric}={a_metric:.3f}  MDD={a_mdd:.1f}%  "
          f"(delta {metric} {a_metric-b_metric:+.3f}, MDD {a_mdd-b_mdd:+.1f}%)")
    param_str = ', '.join(f'{k}={best_p.get(k,v):.3g}' for k,v in study.best_params.items() if not k.endswith('_raw'))
    print(f"Best params: {{{param_str}}}")

    return {
        "preset": preset_name,
        "params": {k: best_p[k] for k in vary_keys if k in best_p
                   or (k == "w1" and "w1" in best_p)
                   or (k == "w3" and "w3" in best_p)},
        "before": {metric: b_metric, "MDD": b_mdd},
        "after": {metric: a_metric, "MDD": a_mdd},
        "trials": len(study.trials),
    }

def pick_best(results: list[dict], group_by: str = None,
              metric: str = "AR") -> list[dict]:
    """Pick best result per group, sorted by metric descending.

    Without group_by: returns single best.
    With group_by: returns one per group.
    """
    if group_by is None:
        return [max(results, key=lambda r: r.get(metric, -9999))]

    groups = {}
    for r in results:
        g = r[group_by]
        if g not in groups or r.get(metric, -9999) > groups[g].get(metric, -9999):
            groups[g] = r
    return sorted(groups.values(), key=lambda r: r.get(metric, -9999), reverse=True)


def pick_multi(results: list[dict], group_by: str,
               metrics: list[str]) -> dict[str, list[dict]]:
    """Pick best per group for multiple metrics. Returns {metric_name: [best_results]}."""
    return {m: pick_best(results, group_by, m) for m in metrics}


def _fingerprint(presets: dict, window: str) -> str:
    """Hash key params of 15 presets + window."""
    h = hashlib.sha256()
    h.update(window.encode())
    for name in sorted(presets):
        if not (name.startswith("gam-") or name.startswith("zen-") or name.startswith("act-")):
            continue
        p = presets[name]
        pos = p.get("position", {})
        conf = p.get("confidence", {})
        vals = f'{pos.get("max_holdings")}|{pos.get("top_boost")}|{pos.get("signal_steps")}|{pos.get("concentration")}|{pos.get("c_sensitivity")}|{pos.get("band")}|{conf.get("ma_bull_pos")}|{conf.get("ma_bear_pos")}|{conf.get("ma_trend_period")}'
        h.update(f"{name}:{vals}".encode())
    return h.hexdigest()[:16]


def write_preset_metrics(path: str, metrics_by_preset: dict[str, dict],
                          window: str = None):
    """Write config/preset_metrics.json from a dict of {preset_name: metrics}.

    metrics_by_preset is a dict like {'gam-0': {'AR':108.2, 'MDD':-38.4, ...}, ...}
    Computes fingerprint from YAML automatically.
    """
    fp = pathlib.Path(path)
    yaml_path = fp.parent / "quant_universe.yaml"
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        presets = cfg.get("presets", {})
    else:
        presets = {}

    win = window or f"{WINDOW[0]} ~ {WINDOW[1]}"

    data = {
        "window": win,
        "fingerprint": _fingerprint(presets, win),
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "points": metrics_by_preset,
    }
    fp.parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {fp} ({len(metrics_by_preset)} presets, fp={data['fingerprint']})")


# ═══════════════════════════════════════════════════════════════════════════════
# Optimization atoms — extracted from quant_optimizer.py (REQ-362)
# ═══════════════════════════════════════════════════════════════════════════════

import numpy as np

try:
    import optuna
except ImportError:
    optuna = None

from quant_backtest import load_config as _load_backtest_config, count_actual_rebalances
from etf_report.core.quant_data_utils import load_etf_data
from etf_report.core import quant_contract as _qc

_WEIGHT_KEYS = frozenset({"w1", "w3", "w7"})


def _extract_metrics(nav_df, signal_history, extra):
    """Compute standard backtest metrics from NAV DataFrame.

    Returns dict with: total_return, annual_return, max_drawdown,
    sharpe, sortino, calmar, n_trades, n_signals, commission, final_nav.
    """
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


def _check_constraints(trial_params: dict, trial_metrics: dict, constraints: list):
    """Validate trial results against constraint strings.

    Supports: 'mdd,<limit>' (per-period MDD floor), 'bear,<lo>,<hi>' (bear position range).
    Returns error string on violation, or None if all pass.
    """
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


class ParamSpace:
    """Parameter space with bounds, supporting grid enumeration and random sampling.

    Example:
        space = ParamSpace(bounds)
        for params in space.generate_grid():
            ...
        for params in space.sample_random(10, rng):
            ...
    """

    def __init__(self, bounds: dict, weight_keys: frozenset = None):
        self.bounds = bounds
        self.weight_keys = weight_keys or _WEIGHT_KEYS
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
        """Yield all combinations as param dicts (cartesian product of value lists)."""
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
        from itertools import product
        for combo in product(*value_lists):
            params = dict(zip(keys, combo))
            yield self.resolve_weights(params)

    def sample_random(self, n: int, rng: np.random.Generator):
        """Yield n random param dicts using a numpy Generator."""
        for _ in range(n):
            params = {}
            wkeys = self.get_active_weight_keys()
            independent = wkeys[:-1]
            for key in self.all_keys:
                b = self.bounds[key]
                tp = b.get("type", "continuous")
                if key in independent:
                    val = rng.integers(b["min"], b["max"] + 1)
                    params[key] = int(val)
                elif tp == "weight":
                    continue  # resolved after
                elif tp == "continuous":
                    if "values" in b:
                        params[key] = rng.choice(b["values"])
                    else:
                        step = b.get("step")
                        if step:
                            n_steps = int(round((b["max"] - b["min"]) / step))
                            params[key] = float(b["min"] + rng.integers(0, n_steps + 1) * step)
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


class BacktestRunner:
    """Cached backtest runner with ETF data preloading.

    Example:
        runner = BacktestRunner("gam-0", DATA_DIR, PROJECT_ROOT)
        nav, sig, extra = runner.run_raw(params, "2020-06-01", "2026-06-01")
        metrics = runner.run(params, "2020-06-01", "2026-06-01")
    """

    def __init__(self, preset: str, data_dir, project_root,
                 universe_filter=None, verbose: bool = False):
        import pathlib
        self.preset = preset
        self.data_dir = pathlib.Path(data_dir)
        self.project_root = pathlib.Path(project_root)
        self._preloaded = None
        self.universe_filter = universe_filter
        self.verbose = verbose

    def _ensure_preloaded(self):
        if self._preloaded is not None:
            return
        if self.verbose:
            print("  [preload] loading config & ETF data ...", flush=True)
        cfg = _load_backtest_config(preset=self.preset)
        universe = cfg.get("universe", [])
        all_daily = {}
        all_weekly = {}
        for e in universe:
            code = e["code"]
            daily, weekly = load_etf_data(code, self.data_dir)
            if daily is not None:
                all_daily[code] = daily
            if weekly is not None:
                all_weekly[code] = weekly
        self._preloaded = {
            "all_daily": all_daily,
            "all_weekly": all_weekly,
        }
        if self.verbose:
            print(f"  [preload] {len(all_daily)} ETFs loaded", flush=True)

    def run_raw(self, params: dict, start_date: str, end_date: str):
        """Run backtest and return raw (nav_df, signal_history, extra)."""
        self._ensure_preloaded()
        config_override = _qc.tuner_params_to_config_override(params)
        nav_df, signal_history, extra = run_backtest(
            start_date=start_date,
            end_date=end_date,
            preset=self.preset,
            preloaded=self._preloaded,
            config_override=config_override,
            universe_filter=self.universe_filter,
            verbose=self.verbose,
        )
        return nav_df, signal_history, extra

    def run(self, params: dict, start_date: str, end_date: str) -> dict:
        """Run backtest and return metrics dict (or None on failure)."""
        self._ensure_preloaded()
        config_override = _qc.tuner_params_to_config_override(params)
        nav_df, signal_history, extra = run_backtest(
            start_date=start_date,
            end_date=end_date,
            preset=self.preset,
            preloaded=self._preloaded,
            config_override=config_override,
            universe_filter=self.universe_filter,
            verbose=self.verbose,
        )
        if nav_df is None or len(nav_df) == 0:
            return None
        return _extract_metrics(nav_df, signal_history, extra)


def _run_baseline(runner: BacktestRunner, cfg):
    """Run 6Y baseline backtest, extract 1Y/3Y metrics from NAV slices.

    cfg must have: .preset, .periods (list of (label, start, end) tuples).
    """
    yaml_cfg = _load_backtest_config(preset=cfg.preset)
    preset_cfg = yaml_cfg.get("presets", {}).get(cfg.preset)
    if preset_cfg is None:
        print(f"  [baseline] preset '{cfg.preset}' not found, skipping")
        return []
    global_conf = yaml_cfg.get("confidence", {})
    base_params = _qc.preset_to_tuner_params(cfg.preset, preset_cfg, global_conf)

    periods_by_label = {lab: (sd, ed) for lab, sd, ed in cfg.periods}
    sd_6Y, ed_6Y = periods_by_label['6Y']
    nav_6Y, sig_6Y, ext_6Y = runner.run_raw(base_params, sd_6Y, ed_6Y)

    results = []
    for lab, (sd, ed) in periods_by_label.items():
        mask = (nav_6Y['date'] >= sd) & (nav_6Y['date'] <= ed)
        nav_slice = nav_6Y[mask].copy()
        factor = 1_000_000.0 / nav_slice['nav'].iloc[0]
        nav_slice['nav'] = nav_slice['nav'] * factor
        m = _extract_metrics(nav_slice, [], {})
        m["period"] = lab
        results.append(m)
    return results


def optuna_objective(trial, runner: BacktestRunner, cfg, space: ParamSpace,
                     baseline_scores: dict):
    """Optuna TPE objective: suggest params, run backtest, return composite score.

    trial: optuna.Trial
    cfg must have: .metric, .periods, .constraints

    Returns mean relative-to-baseline score across all periods.
    """
    if optuna is None:
        raise RuntimeError("optuna not installed. Run: pip install optuna")

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
            hi = lo + ((hi - lo) // step) * step
            if hi <= lo:
                hi = lo + step
            params[key] = trial.suggest_int(key, lo, hi, step=step)
        elif tp == "continuous":
            step = b.get("step")
            if step:
                n_steps = int(round((b["max"] - b["min"]) / step))
                hi = round(b["min"] + n_steps * step, 10)
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
    err = _qc.validate_tuner_params(params)
    if err:
        raise optuna.TrialPruned(f"Validation failed: {err}")

    # Run 6Y backtest once; extract sub-period metrics from NAV slices
    periods_by_label = {lab: (sd, ed) for lab, sd, ed in cfg.periods}
    sd_6Y, ed_6Y = periods_by_label['6Y']
    nav_6Y, sig_6Y, ext_6Y = runner.run_raw(params, sd_6Y, ed_6Y)
    if nav_6Y is None or len(nav_6Y) == 0:
        raise optuna.TrialPruned("6Y backtest failed")

    rel_scores = []
    all_metrics = {}
    for lab, (sd, ed) in periods_by_label.items():
        mask = (nav_6Y['date'] >= sd) & (nav_6Y['date'] <= ed)
        nav_slice = nav_6Y[mask].copy()
        if len(nav_slice) < 2:
            raise optuna.TrialPruned(f"Not enough data for {lab}")
        factor = 1_000_000.0 / nav_slice['nav'].iloc[0]
        nav_slice['nav'] = nav_slice['nav'] * factor
        m = _extract_metrics(nav_slice, [], {})
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
