"""Shared parameter contract for Quant Tuner and backtest engine.

This module is the single place for converting between:
- quant_universe.yaml preset blocks
- Tuner frontend parameter dicts
- quant_backtest.run_backtest(config_override=...) fragments
"""
import json
from copy import deepcopy
from datetime import datetime


_WEIGHT_KEYS = ("w1", "w3", "w7")

PARAM_SCHEMA = {
    "version": 1,
    "groups": [
        {
            "key": "scoring",
            "label": "因子权重",
            "params": [
                {"key": "w1", "label": "F1 EMA 偏离度权重", "unit": "ui_percent", "engine_path": "scoring.weights.ema_deviation"},
                {"key": "w3", "label": "F3 自归一化量比权重", "unit": "ui_percent", "engine_path": "scoring.weights.volume_ratio"},
                {"key": "w7", "label": "F7 对数收益偏离权重", "unit": "ui_percent", "engine_path": "scoring.weights.log_return_deviation"},
                ],
        },
        {
            "key": "sensitivity",
            "label": "映射灵敏度",
            "params": [
                {"key": "f1_sensitivity", "label": "F1 sigmoid 尺度", "unit": "raw", "engine_path": "scoring.sensitivity.f1"},
                {"key": "f3_sensitivity", "label": "F3 log-sigmoid 尺度", "unit": "raw", "engine_path": "scoring.sensitivity.f3"},
                {"key": "f7_t", "label": "F7 幂次 t", "unit": "raw", "engine_path": "scoring.sensitivity.f7_t"},
                {"key": "f7_k", "label": "F7 标准差倍数 k", "unit": "raw", "engine_path": "scoring.sensitivity.f7_k"},
            ],
        },
        {
            "key": "confidence",
            "label": "仓位控制",
            "params": [
                {"key": "conf_type", "label": "信心函数类型", "unit": "enum", "engine_path": "confidence.type"},
                {"key": "ma_trend_period", "label": "MA Trend 周期", "unit": "weeks", "engine_path": "confidence.ma_trend_period"},
                {"key": "ma_bull_pos", "label": "MA 上方仓位", "unit": "ratio", "engine_path": "confidence.ma_bull_pos"},
                {"key": "ma_bear_pos", "label": "MA 下方仓位", "unit": "ratio", "engine_path": "confidence.ma_bear_pos"},
                {"key": "ma_direction_confirm", "label": "MA 方向确认", "unit": "bool", "engine_path": "confidence.ma_direction_confirm"},
                {"key": "dead_zone", "label": "旧信心函数死区", "unit": "ui_percent", "engine_path": "confidence.dead_zone"},
                {"key": "full_zone", "label": "旧信心函数满配阈值", "unit": "ui_percent", "engine_path": "confidence.full_zone"},
            ],
        },
        {
            "key": "position",
            "label": "仓位分配与调仓",
            "params": [
                {"key": "max_holdings", "label": "最大持仓数", "unit": "count", "engine_path": "position.max_holdings"},
                {"key": "disc_step", "label": "离散化步长", "unit": "ratio", "engine_path": "position.discretize_step"},
                {"key": "concentration", "label": "仓位集中度 C", "unit": "ui_x10_to_raw", "engine_path": "position.concentration"},
                {"key": "c_sensitivity", "label": "C 动态灵敏度", "unit": "ui_x10_to_raw", "engine_path": "position.c_sensitivity"},
                {"key": "rebalance_freq", "label": "调仓频率", "unit": "enum", "engine_path": "position.rebalance_freq"},
                {"key": "band", "label": "B 分数带", "unit": "ui_percent_to_ratio", "engine_path": "position.band"},
                {"key": "band_sensitivity", "label": "BS 分数带灵敏度", "unit": "ui_x10_to_raw", "engine_path": "position.band_sensitivity"},
            ],
        },
        {
            "key": "factors",
            "label": "因子周期与阈值",
            "params": [
                {"key": "f1_ema_period", "label": "F1 EMA 周期", "unit": "weeks", "engine_path": "factors.ema.period_weeks"},
                {"key": "f3_vol_window", "label": "F3 量比窗口", "unit": "days", "engine_path": "factors.volume_ratio.window_days"},
                {"key": "f7_window", "label": "F7 累计收益窗口", "unit": "days", "engine_path": "factors.log_return_deviation.window_days"},
            ],
        },
        {
            "key": "universe",
            "label": "标的池",
            "params": [
                {"key": "universe", "label": "参与回测 ETF 代码", "unit": "csv_codes", "engine_path": "runtime.universe_filter"},
            ],
        },
    ],
}

# ── Parameter search bounds ──────────────────────────────────────────────
# Each key matches a param key in PARAM_SCHEMA.
# Types: continuous (float), integer (int), categorical (list), weight (0-100 int, group-sum=100), special (pass-through)
PARAM_BOUNDS = {
    # scoring weights (UI percentage points, 0-100 int, must sum to 100)
    "w1":  {"type": "weight",  "min": 0,  "max": 100, "step": 1},
    "w3":  {"type": "weight",  "min": 0,  "max": 100, "step": 1},
    "w7":  {"type": "weight",  "min": 0,  "max": 100, "step": 1},
    # sensitivity
    "f1_sensitivity": {"type": "continuous", "min": 3.0, "max": 15.0, "step": 0.1},
    "f3_sensitivity": {"type": "continuous", "min": 0.5, "max": 8.0, "step": 0.1},
    "f7_t":           {"type": "continuous", "min": 1.0, "max": 25.0, "step": 1.0},
    "f7_k":           {"type": "continuous", "min": 0.1, "max": 10.0, "step": 0.1},
    # confidence
    "conf_type":            {"type": "categorical", "choices": ["ma_trend"], "searchable": False},
    "ma_trend_period":      {"type": "integer", "min": 8, "max": 40, "step": 2},
    "ma_bull_pos":          {"type": "continuous", "min": 0.0, "max": 2.0, "step": 0.01},
    "ma_bear_pos":          {"type": "continuous", "min": 0.0, "max": 1.0, "step": 0.01},
    "ma_direction_confirm": {"type": "categorical", "choices": [True, False], "searchable": False},
    "benchmarks":           {"type": "multi_choice", "choices": ["000016", "000300", "000905", "399006"], "searchable": False},
    "dead_zone":            {"type": "continuous", "min": 10, "max": 50, "step": 1, "searchable": False},
    "full_zone":            {"type": "continuous", "min": 40, "max": 90, "step": 1, "searchable": False},
    # position
    "max_holdings":     {"type": "integer", "min": 1, "max": 8, "step": 1},
    "disc_step":        {"type": "continuous", "min": 0.01, "max": 0.20, "step": 0.01},
    "concentration":    {"type": "continuous", "min": 0.0, "max": 30.0, "step": 0.1},
    "c_sensitivity":    {"type": "continuous", "min": 0.0, "max": 200.0, "step": 2.0},
    "rebalance_freq":   {"type": "categorical", "choices": ["W-FRI", "daily"], "searchable": False},
    "execution_timing": {"type": "categorical", "choices": ["same_close"], "searchable": False},
    "f1_active_days":   {"type": "integer", "min": 0, "max": 31, "step": 1, "searchable": False},
    "band":             {"type": "continuous", "min": 0.0, "max": 20.0, "step": 0.5},
    "band_sensitivity": {"type": "continuous", "min": 0.0, "max": 100.0, "step": 1.0},
    # factors
    "f1_ema_period":    {"type": "integer", "min": 3, "max": 30, "step": 1},
    "f3_vol_window":    {"type": "integer", "min": 5, "max": 60, "step": 1},
    "f7_window":        {"type": "integer", "min": 5, "max": 60, "step": 1},
    # universe
    "universe": {"type": "special"},
}

_WEIGHT_PARAM_KEYS = frozenset(k for k, v in PARAM_BOUNDS.items() if v.get("type") == "weight")


def get_param_bounds():
    return deepcopy(PARAM_BOUNDS)


def get_param_type(key):
    b = PARAM_BOUNDS.get(key, {})
    return b.get("type", "continuous")


def auto_bounds(preset_tuner_params, user_overrides=None):
    """Derive search ranges centered on a preset's current values.

    Returns a dict of param_key -> bounds spec suitable for ParamSpace.
    Continuous: [current * 0.3, current * 3.0] clamped to global bounds.
    Integer: [current - 50%, current + 50%] clamped.
    Categorical: all choices.
    Weight: the preset's current value +/- a delta.
    """
    overrides = user_overrides or {}
    result = {}
    for key, b in PARAM_BOUNDS.items():
        if key in overrides:
            result[key] = dict(b, **overrides[key])
            continue
        # Non-searchable params: pin to preset baseline value
        if not b.get("searchable", True):
            val = preset_tuner_params.get(key)
            if val is not None:
                result[key] = {"type": b["type"], "values": [val]}
            else:
                result[key] = dict(b)
            continue
        tp = b.get("type", "continuous")
        cur = preset_tuner_params.get(key)
        if tp == "weight":
            if cur is None:
                cur = 25
            half = max(5, cur // 4)
            lo = max(b.get("min", 0), cur - half * 2)
            hi = min(b.get("max", 100), cur + half * 2)
            result[key] = {"type": "weight", "min": lo, "max": hi, "step": max(1, b.get("step", 5))}
        elif tp == "continuous":
            if cur is None:
                cur = (b["min"] + b["max"]) / 2
            lo = max(b["min"], cur * 0.3)
            hi = min(b["max"], cur * 3.0)
            if hi <= lo:
                hi = lo * 1.5
            result[key] = {"type": "continuous", "min": lo, "max": hi, "step": b.get("step")}
        elif tp == "integer":
            if cur is None:
                cur = (b["min"] + b["max"]) // 2
            lo = max(b["min"], int(cur * 0.5))
            hi = min(b["max"], int(cur * 1.5))
            if hi <= lo:
                hi = lo + 1
            result[key] = {"type": "integer", "min": lo, "max": hi, "step": b.get("step", 1)}
        elif tp == "categorical":
            result[key] = {"type": "categorical", "choices": list(b["choices"])}
        elif tp == "special":
            result[key] = {"type": "special", "value": cur}
    return result


def get_param_schema():
    return deepcopy(PARAM_SCHEMA)


def iter_schema_param_keys():
    for group in PARAM_SCHEMA["groups"]:
        for param in group["params"]:
            yield param["key"]


def _as_float(value, default=0.0):
    if value is None or value == "":
        return default
    return float(value)


def _as_int(value, default=0):
    if value is None or value == "":
        return default
    return int(float(value))


def _weight_to_ui_percent(value, default=0.0):
    return int(round(_as_float(value, default) * 100))


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def weight_total_pct(params):
    return sum(_as_float(params.get(k), 0.0) for k in _WEIGHT_KEYS)


def parse_universe_filter(params):
    universe_str = (params.get("universe", "") or "").strip()
    if universe_str == "__NONE__":
        return [], "empty"
    if not universe_str:
        return None, "all"
    codes = [c.strip() for c in universe_str.split(",") if c.strip()]
    return sorted(set(codes)), "filtered"


def validate_tuner_params(params):
    total = weight_total_pct(params)
    if abs(total - 100.0) > 1e-6:
        return f"Factor weights must sum to 100%, got {total:g}%"

    universe_filter, mode = parse_universe_filter(params)
    if mode == "empty":
        return "Universe is empty; select at least 6 ETFs"
    if universe_filter is not None and len(universe_filter) < 6:
        return f"Only {len(universe_filter)} ETFs selected, need at least 6"

    if _as_float(params.get("ma_bull_pos"), 1.0) <= _as_float(params.get("ma_bear_pos"), 0.3):
        return "Bull position must be greater than bear position"

    execution_timing = params.get("execution_timing", "same_close")
    if execution_timing != "same_close":
        return "execution_timing must be same_close"

    return None


# Params that must be present — missing = silent bug, refuse to proceed
_REQUIRED_PARAMS = frozenset([
    'w1', 'w3', 'w7', 'ma_bull_pos', 'ma_bear_pos', 'max_holdings', 'ma_trend_period',
    'concentration', 'c_sensitivity', 'band', 'band_sensitivity', 'disc_step',
    'f7_t', 'f7_k', 'f7_window', 'f3_vol_window', 'f1_sensitivity', 'f3_sensitivity',
    'f1_ema_period',
])


def load_defaults():
    """Load non-searchable parameter defaults from config/defaults.yaml."""
    import yaml as _yaml, pathlib as _pl
    _path = _pl.Path(__file__).resolve().parent.parent.parent.parent / "config" / "defaults.yaml"
    with open(_path, "r", encoding="utf-8") as f:
        return _yaml.safe_load(f)


def tuner_params_to_config_override(params):
    missing = [k for k in _REQUIRED_PARAMS if k not in params]
    if missing:
        raise ValueError(
            f"Missing required params: {missing}. "
            f"Old pool trials may lack params added in newer versions. "
            f"Re-run iterative_optimizer.py to auto-backfill, or call build_frontier_output which backfills automatically."
        )
    df = load_defaults()
    sc_df = df.get("scoring", {})
    sens_df = sc_df.get("sensitivity", {})
    cf_df = df.get("confidence", {})
    pos_df = df.get("position", {})
    fac_df = df.get("factors", {})
    acct_df = df.get("account", {})

    result = {
        "scoring": {
            "weights": {
                "ema_deviation": _as_float(params.get("w1"), int(sc_df.get("weights", {}).get("ema_deviation", 0.33) * 100)) / 100.0,
                "volume_ratio": _as_float(params.get("w3"), int(sc_df.get("weights", {}).get("volume_ratio", 0.33) * 100)) / 100.0,
                "log_return_deviation": _as_float(params.get("w7"), 0.0) / 100.0,
            },
            "sensitivity": {
                "f1": _as_float(params.get("f1_sensitivity"), sens_df.get("f1", 8.0)),
                "f3": _as_float(params.get("f3_sensitivity"), sens_df.get("f3", 1.0)),
                "f7_t": _as_float(params.get("f7_t"), sens_df.get("f7_t", 7.0)),
                "f7_k": _as_float(params.get("f7_k"), sens_df.get("f7_k", 3.0)),
            },
        },
        "confidence": {
            "type": params.get("conf_type", cf_df.get("type", "ma_trend")),
            "dead_zone": _as_int(params.get("dead_zone"), cf_df.get("dead_zone", 25)),
            "full_zone": _as_int(params.get("full_zone"), cf_df.get("full_zone", 65)),
            "ma_bull_pos": _as_float(params.get("ma_bull_pos"), cf_df.get("ma_bull_pos", 1.0)),
            "ma_bear_pos": _as_float(params.get("ma_bear_pos"), cf_df.get("ma_bear_pos", 0.3)),
            "ma_trend_period": _as_int(params.get("ma_trend_period"), cf_df.get("ma_trend_period", 26)),
            "ma_direction_confirm": _as_bool(params.get("ma_direction_confirm"), cf_df.get("ma_direction_confirm", True)),
            "benchmarks": params.get("benchmarks", cf_df.get("benchmarks", ["000300"])),
        },
        "position": {
            "max_holdings": _as_int(params.get("max_holdings"), pos_df.get("max_holdings", 6)),
            "discretize_step": _as_float(params.get("disc_step"), pos_df.get("discretize_step", 0.05)),
            "concentration": _as_float(params.get("concentration"), pos_df.get("concentration", 2.0) * 10) / 10.0,
            "c_sensitivity": _as_float(params.get("c_sensitivity"), pos_df.get("c_sensitivity", 0.0)) / 10.0,
            "rebalance_freq": params.get("rebalance_freq", pos_df.get("rebalance_freq", "daily")),
            "execution_timing": params.get("execution_timing", pos_df.get("execution_timing", "same_close")),
            "band": _as_float(params.get("band"), pos_df.get("band", 0.0) * 100) / 100.0,
            "band_sensitivity": _as_float(params.get("band_sensitivity"), pos_df.get("band_sensitivity", 0.0)) / 1000.0,
            "commission_rate": pos_df.get("commission_rate", 0.00026),
        },
        "factors": {
            "f1_active_days": _as_int(params.get("f1_active_days"), fac_df.get("f1_active_days", 1)),
            "ema": {"period_weeks": _as_int(params.get("f1_ema_period"), fac_df.get("ema", {}).get("period_weeks", 20))},
            "volume_ratio": {"window_days": _as_int(params.get("f3_vol_window"), fac_df.get("volume_ratio", {}).get("window_days", 20))},
            "log_return_deviation": {
                "window_days": _as_int(params.get("f7_window"), fac_df.get("log_return_deviation", {}).get("window_days", 20)),
                "lookback_days": fac_df.get("log_return_deviation", {}).get("lookback_days", 250),
                "min_days": fac_df.get("log_return_deviation", {}).get("min_days", 60),
                "sigma_floor": fac_df.get("log_return_deviation", {}).get("sigma_floor", 0.01),
            },
        },
    }
    result["account"] = {
        "max_gross_exposure": _as_float(params.get("max_gross_exposure"), acct_df.get("max_gross_exposure", 2.0)),
    }
    return result


def tuner_params_to_preset_patch(params, base_cfg=None):
    if base_cfg is None:
        return tuner_params_to_config_override(params)

    cfg = deepcopy(base_cfg)
    cfg.setdefault("scoring", {})
    cfg.setdefault("confidence", {})
    cfg.setdefault("position", {})
    cfg.setdefault("factors", {})
    cfg["factors"].setdefault("ema", {})
    cfg["factors"].setdefault("volume_ratio", {})
    cfg["scoring"].setdefault("sensitivity", {})

    override = tuner_params_to_config_override(params)

    cfg["scoring"].update(override["scoring"])
    cfg["confidence"].update(override["confidence"])
    cfg["position"].update(override["position"])
    cfg["factors"].update(override["factors"])

    return {
        "scoring": cfg["scoring"],
        "confidence": cfg["confidence"],
        "position": cfg["position"],
        "factors": cfg["factors"],
    }


def preset_to_tuner_params(preset_key, preset_cfg, global_conf=None):
    global_conf = global_conf or {}
    global_regime_base = global_conf.get("regime_base", {})
    pc = preset_cfg.get("confidence", {})
    prb = pc.get("regime_base", {})
    w = preset_cfg.get("scoring", {}).get("weights", {})
    scoring = preset_cfg.get("scoring", {})
    sensitivity = scoring.get("sensitivity", {})
    position = preset_cfg.get("position", {})
    factors = preset_cfg.get("factors", {})

    _df = load_defaults()
    _pos_df = _df["position"]
    _fac_df = _df["factors"]
    _sens_df = _df["scoring"]["sensitivity"]
    _cf_df = _df["confidence"]
    _acct_df = _df["account"]
    return {
        "label": preset_cfg.get("label", preset_key),
        "description": preset_cfg.get("description", ""),
        "w1": _weight_to_ui_percent(w.get("ema_deviation"), 0.30),
        "w3": _weight_to_ui_percent(w.get("volume_ratio"), 0.30),
        "conf_type": pc.get("type", _cf_df["type"]),
        "dead_zone": pc.get("dead_zone", global_conf.get("dead_zone", _cf_df["dead_zone"])),
        "full_zone": pc.get("full_zone", global_conf.get("full_zone", _cf_df["full_zone"])),
        "regime_base_bull": prb.get("bull_trend", global_regime_base.get("bull_trend", 0.95)),
        "regime_base_choppy": prb.get("choppy_range", global_regime_base.get("choppy_range", 0.75)),
        "regime_base_bear": prb.get("bear_trend", global_regime_base.get("bear_trend", 0.35)),
        "regime_window": pc.get("regime_window", global_conf.get("regime_window", 8)),
        "regime_threshold": pc.get("regime_threshold", global_conf.get("regime_threshold", 0.03)),
        "breadth_weight": pc.get("breadth_weight", global_conf.get("breadth_weight", 0.2)),
        "clarity_threshold": pc.get("clarity_threshold", global_conf.get("clarity_threshold", 0.03)),
        "dd_sensitivity": pc.get("dd_sensitivity", global_conf.get("dd_sensitivity", 0.2)),
        "crash_window": pc.get("crash_window", global_conf.get("crash_window", 2)),
        "crash_threshold": pc.get("crash_threshold", global_conf.get("crash_threshold", -0.03)),
        "recovery_threshold": pc.get("recovery_threshold", global_conf.get("recovery_threshold", -0.01)),
        "crash_pos": pc.get("crash_pos", global_conf.get("crash_pos", 0.20)),
        "recovery_pos": pc.get("recovery_pos", global_conf.get("recovery_pos", 0.70)),
        "recovery_dd_level": pc.get("recovery_dd_level", global_conf.get("recovery_dd_level", -0.05)),
        "ma_bull_pos": pc.get("ma_bull_pos", global_conf.get("ma_bull_pos", _cf_df["ma_bull_pos"])),
        "ma_bear_pos": pc.get("ma_bear_pos", global_conf.get("ma_bear_pos", _cf_df["ma_bear_pos"])),
        "ma_trend_period": pc.get("ma_trend_period", global_conf.get("ma_trend_period", _cf_df["ma_trend_period"])),
        "ma_direction_confirm": pc.get("ma_direction_confirm", global_conf.get("ma_direction_confirm", _cf_df["ma_direction_confirm"])),
        "benchmarks": pc.get("benchmarks", global_conf.get("benchmarks", _cf_df["benchmarks"])),
        "max_holdings": position.get("max_holdings", _pos_df["max_holdings"]),
        "disc_step": round(position.get("discretize_step", _pos_df["discretize_step"]), 3),
        "concentration": position.get("concentration", _pos_df["concentration"]) * 10,
        "c_sensitivity": position.get("c_sensitivity", _pos_df["c_sensitivity"]) * 10,
        "f1_ema_period": factors.get("ema", {}).get("period_weeks", _fac_df["ema"]["period_weeks"]),
        "f3_vol_window": factors.get("volume_ratio", {}).get("window_days", _fac_df["volume_ratio"]["window_days"]),
        "f1_sensitivity": sensitivity.get("f1", _sens_df["f1"]),
        "f3_sensitivity": sensitivity.get("f3", _sens_df["f3"]),
        "rebalance_freq": position.get("rebalance_freq", _pos_df["rebalance_freq"]),
        "execution_timing": position.get("execution_timing", _pos_df["execution_timing"]),
        "band": round(position.get("band", _pos_df["band"]) * 100, 1),
        "band_sensitivity": int(position.get("band_sensitivity", _pos_df.get("band_sensitivity", 0)) * 1000),
        "w7": _weight_to_ui_percent(w.get("log_return_deviation"), 0),
        "f7_t": sensitivity.get("f7_t", _sens_df["f7_t"]),
        "f7_k": sensitivity.get("f7_k", _sens_df["f7_k"]),
        "f7_window": factors.get("log_return_deviation", {}).get("window_days", _fac_df["log_return_deviation"]["window_days"]),
        "f1_active_days": factors.get("f1_active_days", _fac_df["f1_active_days"]),
        "max_gross_exposure": preset_cfg.get("account", {}).get("max_gross_exposure", _acct_df["max_gross_exposure"]),
    }


def build_presets_response(cfg):
    presets = cfg.get("presets", {})
    global_conf = cfg.get("confidence", {})
    result = {
        key: preset_to_tuner_params(key, preset_cfg, global_conf)
        for key, preset_cfg in presets.items()
    }

    if "cst-1" not in result:
        template = result.get("act-1", {}) or result.get("zen-1", {})
        if template:
            cst = dict(template)
            cst["label"] = "自定义策略"
            cst["description"] = "用户自定义策略，初始参数继承自趋势锚定。"
            result["cst-1"] = cst

    result["_universe_options"] = [
        {
            "code": e["code"],
            "name": e.get("name", e["code"]),
            "sector": e.get("sector", ""),
            "active": e.get("active", True),
            "marginable": e.get("marginable", True),
            "group1": e.get("group1", ""),
        }
        for e in cfg.get("universe", [])
    ]
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Pareto Frontier — compute non-dominated set from trial data
# ═══════════════════════════════════════════════════════════════════════════

def compute_frontier(trials, mdd_range=(-40, -20)):
    """Compute Pareto frontier from a list of trial dicts.

    A point A dominates B if A has better (less negative) MDD AND higher COMP.
    Returns non-dominated points sorted by MDD ascending (worst first).

    Args:
        trials: list[dict] with keys 'mdd' (float, negative) and 'composite' (float)
        mdd_range: (lo, hi) MDD filter range

    Returns:
        list[dict]: frontier points sorted by MDD
    """
    in_range = [r for r in trials
                if mdd_range[0] <= r.get('mdd', -99) <= mdd_range[1]
                and r.get('composite', -999) > -900]
    if not in_range:
        return []
    # Sort by MDD descending (best MDD first), track max COMP
    sorted_by_mdd = sorted(in_range, key=lambda r: -r['mdd'])
    frontier = []
    max_comp = -999
    for r in sorted_by_mdd:
        if r['composite'] > max_comp:
            max_comp = r['composite']
            frontier.append(r)
    frontier.sort(key=lambda r: r['mdd'])
    return frontier


# ═══════════════════════════════════════════════════════════════════════════


def build_frontier_output(school="gambler", data_dir="research/params",
                          output_path=None, mdd_range=(-50, -15),
                          start_date="2020-06-25", end_date=None):
    """Load pool.json for a school, compute frontier, re-validate, save Tuner-ready JSON.

    Returns dict with points (int) and total_trials (int).
    """
    import json as _json
    import pathlib as _pl

    if output_path is None:
        output_path = f"research/params/frontier_{school}.json"
    # Preset per school for re-validation fallback
    _PRESET_FOR = {'gambler': 'gam-0', 'zen': 'zen-1', 'actuary': 'act-1'}

    all_data = load_pool(school, data_dir)

    # Backfill missing B/BS params in pool trials so re-validation doesn't drop them.
    # Unlike iterative_optimizer's random backfill, we use deterministic defaults
    # so frontier generation is reproducible.
    _bf_count = 0
    for _t in all_data:
        _p = _t.get('params', {})
        if 'band' not in _p:
            _p['band'] = 2.0
            _bf_count += 1
        if 'band_sensitivity' not in _p:
            _p['band_sensitivity'] = 20
            _bf_count += 1
    if _bf_count:
        print(f"  Backfilled {_bf_count} missing B/BS params in pool (defaults)")

    # Gambler: Pareto frontier (AR monotonic with MDD)
    # Zen/Actuary: per-slot best (Sortino/Calmar not monotonic, dominance meaningless)
    if school == 'gambler':
        selected = compute_frontier(all_data, mdd_range=mdd_range)
    else:
        in_range = [t for t in all_data
                    if t.get('mdd') is not None and mdd_range[0] <= t['mdd'] <= mdd_range[1]]
        slots = {}
        for t in in_range:
            key = round(t['mdd'])
            if key not in slots or t.get('composite', -999) > slots[key].get('composite', -999):
                slots[key] = t
        selected = sorted(slots.values(), key=lambda t: t['mdd'])

    _FIXED_PARAMS = {}  # deprecated — use load_defaults() instead

    pts = []
    for r in selected:
        p = r.get("params", {})
        w1 = int(float(str(p.get("w1", 35))))
        w3 = int(float(str(p.get("w3", 25))))
        w7 = int(float(str(p.get("w7", 100 - w1 - w3))))
        bull = float(p.get("ma_bull_pos", 1.0))
        bear = float(p.get("ma_bear_pos", 0.3))
        if w1 + w3 > 100 or bull <= bear:
            continue

        entry = {
            "mdd": 0.0,  # placeholder — filled by re-validation below
            "ar_6y": 0.0,
            "params": {
                "ma_bull_pos": round(bull, 3),
                "ma_bear_pos": round(bear, 3),
                "max_holdings": int(float(str(p.get("max_holdings", 6)))),
                "ma_trend_period": int(float(str(p.get("ma_trend_period", 26)))),
                "concentration": round(float(p.get("concentration", 2.0)), 2),
                "c_sensitivity": int(float(str(p.get("c_sensitivity", 200)))),
                "band": round(float(p.get("band", 0)), 2),
                "band_sensitivity": int(float(str(p.get("band_sensitivity", 0)))),
                "disc_step": round(float(p.get("disc_step", 0.05)), 2),
                "f7_t": int(float(str(p.get("f7_t", 5)))),
                "f7_k": round(float(p.get("f7_k", 1.0)), 2),
                "f7_window": int(float(str(p.get("f7_window", 20)))),
                "f3_vol_window": int(float(str(p.get("f3_vol_window", 20)))),
                "f1_sensitivity": round(float(p.get("f1_sensitivity", 5.0)), 1),
                "f3_sensitivity": round(float(p.get("f3_sensitivity", 5.0)), 1),
                "f1_ema_period": int(float(str(p.get("f1_ema_period", 12)))),
                "w1": w1, "w3": w3, "w7": w7,
            },
        }
        entry["params"].update(_FIXED_PARAMS)
        pts.append(entry)

    output = {
        school: {
            "type": "slider",
            "risk_axis": "MDD",
            "risk_unit": "%",
            "risk_range": list(mdd_range),
            "risk_step": 0.5,
            "points": pts,
            "references": [],
            "updated": datetime.now().strftime("%Y-%m-%d"),
        }
    }
    # Re-validate each frontier point with current data.
    # Points that fail re-validation are dropped (no silent placeholders).
    from quant_backtest import run_backtest as _rb
    import pandas as _pd
    validated = []
    for pt in pts:
        try:
            ov = tuner_params_to_config_override(pt["params"])
            nav, _, extra = _rb(start_date=start_date, end_date=end_date,
                                preset=_PRESET_FOR.get(school, "gam-2"), config_override=ov, return_data=False)
            if nav is not None and len(nav) > 1:
                L = nav["date"].iloc[-1]
                d = (L - nav["date"].iloc[0]).days
                ar = round(((nav["nav"].iloc[-1] / nav["nav"].iloc[0]) ** (365.0 / d) - 1) * 100, 1) if d > 0 else 0.0
                md = round(((nav["nav"] - nav["nav"].cummax()) / nav["nav"].cummax() * 100).min(), 1)
                pt["ar_6y"] = ar
                pt["mdd"] = md
                pt["sortino"] = round(extra.get("sortino", 0), 3) if extra else 0
                pt["calmar"] = round(ar / abs(md), 2) if md != 0 else 0
                if mdd_range[0] <= md <= mdd_range[1]:
                    validated.append(pt)
                else:
                    print(f"  [WARN] frontier point MDD={md:.1f}% outside [{mdd_range[0]}, {mdd_range[1]}] — dropped")
            else:
                print(f"  [WARN] frontier point re-validation returned null — dropped")
        except Exception as e:
            print(f"  [WARN] frontier point re-validation failed: {e} — dropped")

    output[school]["points"] = validated
    # ── Auto-add gam-0 reference (gambler only) ──
    if school == 'gambler':
        try:
            from quant_backtest import run_backtest as _rb2
            _nav, _, _extra = _rb2(start_date=start_date, end_date=end_date,
                                    preset="gam-0", return_data=False)
            if _nav is not None and len(_nav) > 1:
                _d = (_nav["date"].iloc[-1] - _nav["date"].iloc[0]).days
                _ar = round(((_nav["nav"].iloc[-1] / _nav["nav"].iloc[0]) ** (365.0 / _d) - 1) * 100, 1) if _d > 0 else 0.0
                _md = round(((_nav["nav"] - _nav["nav"].cummax()) / _nav["nav"].cummax() * 100).min(), 1)
                _so = round(_extra.get("sortino", 0), 3) if _extra else 0
                _ca = round(_ar / abs(_md), 2) if _md != 0 else 0
                output[school]["references"] = [{"label": "gam-0", "mdd": _md, "ar_6y": _ar, "sortino": _so, "calmar": _ca}]
        except Exception:
            pass
    _pl.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _pl.Path(output_path).write_text(_json.dumps(output, ensure_ascii=True, indent=2), encoding="ascii")
    return {"points": len(validated), "total_trials": len(all_data)}


# ═══════════════════════════════════════════════════════════════════════════
# Pool management — loose seed bank for iterative optimization
# ═══════════════════════════════════════════════════════════════════════════

import pathlib as _pool_pl


def _pool_path(school, base_dir="research/params"):
    return _pool_pl.Path(base_dir) / school / "pool.json"


def load_pool(school, base_dir="research/params"):
    """Load pool.json for a school. Returns list of trial dicts, empty if absent."""
    p = _pool_path(school, base_dir)
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return []


def save_pool(school, trials, base_dir="research/params"):
    """Save pool.json for a school. Creates directory if missing."""
    p = _pool_path(school, base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(trials, ensure_ascii=False, indent=1))


def prune_pool(trials, school, band=1.0, per_band=1):
    """流派自减负 — 每轮结束后调用。三派统一按 MDD 槽位。

    band:   MDD 槽位宽度 (default 1.0%)
    per_band: 每槽保留数 (default 1)
    school: 仅用于日志/兼容，不影响 prune 逻辑
    """
    if not trials:
        return []
    seed = [t for t in trials if t.get('mdd') is None or t.get('composite') is None]
    valid = [t for t in trials if t.get('mdd') is not None and t.get('composite') is not None]
    if not valid:
        return seed

    inv = int(1 / band)
    slots = {}
    for t in valid:
        key = round(t['mdd'] * inv) / inv
        slots.setdefault(key, []).append(t)
    kept = []
    for slot_trials in slots.values():
        slot_trials.sort(key=lambda t: t.get('composite', -999), reverse=True)
        kept.extend(slot_trials[:per_band])
    return kept + seed


def merge_runs(school, run_files, base_dir="research/params"):
    """Merge multiple run outputs into pool.json. Dedupe + prune.

    Args:
        school: 'gambler' | 'zen' | 'actuary'
        run_files: list of file paths (JSON arrays of trial dicts)
        base_dir: pool.json directory
    """
    pool = load_pool(school, base_dir)
    for rf in run_files:
        p = _pool_pl.Path(rf)
        if p.exists():
            pool.extend(json.loads(p.read_text("utf-8")))
    pool = prune_pool(pool, school, band=1.0, per_band=1)
    save_pool(school, pool, base_dir)
    valid = [t for t in pool if t.get('mdd') is not None]
    return len(pool), len(valid)


def seed_params_from_presets(school):
    """Extract seed params from YAML presets for the given school.

    gambler → gam-0/1/2/3
    zen     → zen-1
    actuary → act-1/2
    """
    import yaml as _yaml
    cfg_path = _pool_pl.Path(__file__).resolve().parent.parent.parent.parent / "config" / "quant_universe.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = _yaml.safe_load(f)
    presets = cfg.get("presets", {})

    school_preset_map = {
        'gambler': ['gam-0', 'gam-1', 'gam-2', 'gam-3'],
        'zen': ['zen-1'],
        'actuary': ['act-1'],
    }
    names = school_preset_map.get(school, [])
    seeds = []
    for name in names:
        pc = presets.get(name)
        if not pc or pc.get('_unreliable'):
            continue
        sc = pc.get("scoring", {})
        w = sc.get("weights", {})
        sens = sc.get("sensitivity", {})
        cf = pc.get("confidence", {})
        pos = pc.get("position", {})
        fac = pc.get("factors", {})
        p = {
            "w1": int(w.get("ema_deviation", 0.33) * 100),
            "w3": int(w.get("volume_ratio", 0.33) * 100),
            "w7": int(w.get("log_return_deviation", 0.0) * 100),
            "f1_sensitivity": sens.get("f1", 8.0),
            "f3_sensitivity": sens.get("f3", 4.0),
            "f7_t": sens.get("f7_t", 10.0),
            "f7_k": sens.get("f7_k", 3.0),
            "ma_bull_pos": cf.get("ma_bull_pos", 1.0),
            "ma_bear_pos": cf.get("ma_bear_pos", 0.5),
            "ma_trend_period": cf.get("ma_trend_period", 26),
            "max_holdings": pos.get("max_holdings", 4),
            "concentration": pos.get("concentration", 3.0) * 10,
            "c_sensitivity": pos.get("c_sensitivity", 30) * 10,
            "band": pos.get("band", 0.02) * 100,
            "band_sensitivity": pos.get("band_sensitivity", 0.0) * 1000,
            "disc_step": pos.get("discretize_step", 0.10),
            "f1_ema_period": fac.get("ema", {}).get("period_weeks", 4),
            "f3_vol_window": fac.get("volume_ratio", {}).get("window_days", 30),
            "f7_window": fac.get("log_return_deviation", {}).get("window_days", 20),
            "rebalance_freq": pos.get("rebalance_freq", "W-FRI"),
            "max_gross_exposure": pc.get("account", {}).get("max_gross_exposure", 2.0),
            "dead_zone": cf.get("dead_zone", 25),
            "full_zone": cf.get("full_zone", 65),
            "f1_active_days": fac.get("f1_active_days", 1),
        }
        seeds.append({"params": p, "source": f"preset:{name}"})
    return seeds


# Shared Optuna objective factory (used by iterative_optimizer + pareto_optimizer)
# ═══════════════════════════════════════════════════════════════════════════

def create_optuna_objective(preset, bounds, start_date, end_date=None,
                            target_metric="6y_ar"):
    """Create an Optuna objective function for parameter optimization.

    All three schools share the same account config. The only difference
    is target_metric: "6y_ar" (gambler) | "6y_sortino" (zen/actuary).

    Args:
        preset: base preset name for config defaults
        bounds: {param_key: (lo, hi, step)} — narrowed search bounds
        start_date: backtest start (e.g. '2020-06-25' for 6Y)
        end_date: backtest end (None = latest CSV data)
        target_metric: "6y_ar" | "3y_ar" | "6y_sortino"

    Returns:
        callable(trial) -> float (AR * 100, or -9999 on failure)
    """
    # Capture bounds keys at factory time (param type lookup)
    _param_types = {k: PARAM_BOUNDS[k]["type"] for k in bounds if k in PARAM_BOUNDS}

    def objective(trial):
        import json as _json
        from quant_backtest import run_backtest as _rb

        p = {}
        for k, (lo, hi, step) in bounds.items():
            btype = _param_types.get(k, "continuous")
            if btype in ("integer",):
                p[k] = trial.suggest_int(k, int(lo), int(hi), step=int(step))
            else:
                p[k] = trial.suggest_float(k, lo, hi, step=step)

        # ── Weight constraint ──
        if 'w1' in p:
            p['w1'] = int(p['w1']); p['w3'] = int(p['w3'])
            if p['w1'] + p['w3'] > 100: return -9999
            p['w7'] = 100 - p['w1'] - p['w3']

        # ── Fixed params ──
        p['conf_type'] = 'ma_trend'; p['ma_direction_confirm'] = True
        p['bias'] = 0

        if p.get('ma_bull_pos', 1) <= p.get('ma_bear_pos', 0.3):
            return -9999

        try:
            ov = tuner_params_to_config_override(p)
            nav, _, extra = _rb(start_date=start_date, end_date=end_date,
                                preset=preset, config_override=ov, return_data=False)
            if nav is None: return -9999

            N = len(nav); L = nav['date'].iloc[-1]
            import pandas as _pd

            def _ar(s, e):
                if e <= s: return 0
                d = (nav['date'].iloc[e] - nav['date'].iloc[s]).days
                return (nav['nav'].iloc[e] / nav['nav'].iloc[s]) ** (365.0 / d) - 1 if d > 0 else 0

            mdd = ((nav['nav'] - nav['nav'].cummax()) / nav['nav'].cummax() * 100).min()

            ar_full = _ar(0, N - 1)
            if target_metric == "6y_sortino":
                comp = round(extra.get("sortino", 0), 4)
            elif target_metric == "6y_calmar":
                comp = round(ar_full * 100 / abs(mdd), 4) if mdd != 0 else 0
            elif target_metric == "3y_ar":
                y3 = L - _pd.DateOffset(years=3)
                i3 = max(0, min(nav['date'].searchsorted(y3), N - 1))
                comp = round(_ar(i3, N - 1) * 100, 2)
            else:  # "6y_ar" (default): full-window AR
                comp = round(ar_full * 100, 2)

            trial.set_user_attr('mdd', round(mdd, 2))
            trial.set_user_attr('composite', comp)
            trial.set_user_attr('params', _json.dumps(p))
            return comp
        except Exception:
            return -9999

    return objective


# ═══════════════════════════════════════════════════════════════════════════
# Shared bounds narrowing (used by iterative_optimizer + pareto_optimizer)
# ═══════════════════════════════════════════════════════════════════════════

def narrow_bounds_from_trials(trials, top_n=15, margin_pct=0.3, band_width=5):
    """Derive narrowed search bounds from per-MDD-band top trials.

    Each MDD band contributes its best trial equally to the KDE,
    preventing a single high-AR outlier from dominating the search space.

    Args:
        trials: list[dict] with keys 'composite', 'mdd', 'params'
        top_n: max number of trials for bounds derivation
        margin_pct: expand bounds by fraction beyond observed range
        band_width: MDD band width for balanced sampling (None=global top-N)

    Returns:
        dict: {param_key: (lo, hi, step)}
    """
    if not trials:
        return {}

    if band_width is None:
        sorted_trials = sorted(trials, key=lambda r: r.get('composite', -999), reverse=True)
        top = sorted_trials[:min(top_n, len(sorted_trials))]
    else:
        valid = [t for t in trials if t.get('mdd') is not None and t.get('composite') is not None]
        if not valid:
            return {}
        bands = {}
        for t in valid:
            key = int(t['mdd'] // band_width) * band_width
            bands.setdefault(key, []).append(t)

        # Auto-merge sparse bands: < 3 trials → merge into next band (toward conservative)
        sorted_bands = sorted(bands.items())  # [(mdd_key, [trials]), ...] ascending
        merged = []
        i = 0
        while i < len(sorted_bands):
            key, bt = sorted_bands[i]
            while len(bt) < 3 and i + 1 < len(sorted_bands):
                i += 1
                bt = bt + list(sorted_bands[i][1])  # merge next band in
            merged.append((key, bt))
            i += 1

        band_tops = []
        for key, bt in merged:
            bt.sort(key=lambda r: r.get('composite', -999), reverse=True)
            band_tops.append(bt[0])
        band_tops.sort(key=lambda r: r.get('composite', -999), reverse=True)
        top = band_tops[:max(top_n, len(merged))]
        if len(top) < top_n:
            seen = {id(t) for t in top}
            remaining = [t for t in valid if id(t) not in seen]
            remaining.sort(key=lambda r: r.get('composite', -999), reverse=True)
            top.extend(remaining[:top_n - len(top)])

    bounds = {}
    for k, pb in PARAM_BOUNDS.items():
        btype = pb.get("type", "")
        if btype in ("categorical", "multi_choice", "special"):
            continue
        if not pb.get("searchable", True):
            continue

        vals = [r['params'].get(k) for r in top
                if k in r.get('params', {}) and r['params'].get(k) is not None]
        if len(vals) < 3:
            continue

        lo, hi = min(vals), max(vals)
        if lo <= 0:
            lo = 0.1
        if hi <= lo:
            hi = lo * 1.5

        margin = max((hi - lo) * margin_pct, 0.1)
        lo, hi = lo - margin, hi + margin

        glo, ghi = pb.get("min", lo), pb.get("max", hi)
        step = pb.get("step", 1)
        lo = max(glo, lo)
        hi = min(ghi, hi)

        if hi <= lo:
            hi = min(lo * 1.5, ghi)

        bounds[k] = (lo, hi, step)

    # ── Diversity report: per-param min/max/std across selected top trials ──
    if bounds:
        import statistics
        parts = []
        for k in sorted(bounds.keys()):
            pvals = [r['params'].get(k) for r in top
                     if k in r.get('params', {}) and r['params'].get(k) is not None]
            if len(pvals) >= 2:
                parts.append(f"{k}=[{min(pvals):.2f},{max(pvals):.2f}] std={statistics.stdev(pvals):.2f}")
        if parts:
            print(f"  Diversity: {' | '.join(parts)}")

    return bounds


# ═══════════════════════════════════════════════════════════════════════════
# Preset optimization profiles — default metric + constraints per preset
# ═══════════════════════════════════════════════════════════════════════════
PRESET_OPT_PROFILES = {
    "gam-0": {"metric": "annual_return", "constraints": ["mdd,-25"]},
    "gam-1": {"metric": "annual_return", "constraints": ["mdd,-25"]},
    "gam-2": {"metric": "annual_return", "constraints": ["mdd,-25"]},
    "gam-3": {"metric": "annual_return", "constraints": ["mdd,-25"]},
    "zen-1": {"metric": "sortino", "constraints": []},
    "act-1": {"metric": "calmar", "constraints": ["bear,0.15,0.30"]},
    "act-2": {"metric": "calmar", "constraints": ["bear,0.15,0.30"]},
}
OPT_PERIODS = ["1Y", "3Y", "6Y"]
DEFAULT_PRESET = "gam-0"

# ── Initial presets for optimization (neutral starting points) ─────────
INITIAL_PRESETS = {
    "signal": {
        "w1": 33, "w3": 33, "w7": 34,
        "f7_t": 10.0, "f7_k": 3.0, "f7_window": 20,
        "f3_vol_window": 30,
        "f1_sensitivity": 8.0, "f3_sensitivity": 4.0,
        "f1_ema_period": 4,
    },
    "execution": {
        "gam": {"max_holdings": 4, "ma_bear_pos": 0.50, "ma_bull_pos": 1.0, "disc_step": 0.10, "concentration": 3.0, "c_sensitivity": 30, "band": 2.0, "band_sensitivity": 0, "ma_trend_period": 26},
        "zen": {"max_holdings": 5, "ma_bear_pos": 0.35, "ma_bull_pos": 1.0, "disc_step": 0.08, "concentration": 2.0, "c_sensitivity": 15, "band": 1.5, "band_sensitivity": 15, "ma_trend_period": 30},
        "act": {"max_holdings": 4, "ma_bear_pos": 0.25, "ma_bull_pos": 0.80, "disc_step": 0.10, "concentration": 4.0, "c_sensitivity": 25, "band": 2.0, "band_sensitivity": 25, "ma_trend_period": 34},
    },
}


def mark_preset_unreliable(name):
    """标记预设不可靠（如 BUG 修复后旧参数失效）。下次 warm-start 自动跳过。"""
    import yaml, pathlib
    cfg_path = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "config" / "quant_universe.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if name in cfg.get("presets", {}):
        cfg["presets"][name]["_unreliable"] = True
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
