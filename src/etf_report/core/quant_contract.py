"""Shared parameter contract for Quant Tuner and backtest engine.

This module is the single place for converting between:
- quant_universe.yaml preset blocks
- Tuner frontend parameter dicts
- quant_backtest.run_backtest(config_override=...) fragments
"""
from copy import deepcopy


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
                {"key": "score_band", "label": "分数带", "unit": "ui_percent_to_ratio", "engine_path": "position.score_band"},
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
        {
            "key": "account",
            "label": "账户模式",
            "params": [
                {"key": "account_mode", "label": "账户模式", "unit": "enum", "engine_path": "account.mode"},
                {"key": "max_gross_exposure", "label": "最大总暴露", "unit": "ratio", "engine_path": "account.max_gross_exposure"},
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
    "score_band":       {"type": "continuous", "min": 0.0, "max": 20.0, "step": 0.5},
    # factors
    "f1_ema_period":    {"type": "integer", "min": 3, "max": 30, "step": 1},
    "f3_vol_window":    {"type": "integer", "min": 5, "max": 60, "step": 1},
    "f7_window":        {"type": "integer", "min": 5, "max": 60, "step": 1},
    # universe
    "universe": {"type": "special"},
    # account
    "account_mode":       {"type": "categorical", "choices": ["cash", "synthetic_leverage"]},
    "max_gross_exposure": {"type": "continuous", "min": 1.0, "max": 2.0, "step": 0.1},
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


def tuner_params_to_config_override(params):
    result = {
        "scoring": {
            "weights": {
                "ema_deviation": _as_float(params.get("w1"), 35.0) / 100.0,
                "volume_ratio": _as_float(params.get("w3"), 50.0) / 100.0,
                "log_return_deviation": _as_float(params.get("w7"), 0.0) / 100.0,
            },
            "sensitivity": {
                "f1": _as_float(params.get("f1_sensitivity"), 8.0),
                "f3": _as_float(params.get("f3_sensitivity"), 1.0),
                "f7_t": _as_float(params.get("f7_t"), 7.0),
                "f7_k": _as_float(params.get("f7_k"), 3.0),
            },
        },
        "confidence": {
            "type": params.get("conf_type", "ma_trend"),
            "dead_zone": _as_int(params.get("dead_zone"), 25),
            "full_zone": _as_int(params.get("full_zone"), 65),
            "ma_bull_pos": _as_float(params.get("ma_bull_pos"), 1.0),
            "ma_bear_pos": _as_float(params.get("ma_bear_pos"), 0.3),
            "ma_trend_period": _as_int(params.get("ma_trend_period"), 26),
            "ma_direction_confirm": _as_bool(params.get("ma_direction_confirm"), True),
            "benchmarks": params.get("benchmarks", ["000300"]),
        },
        "position": {
            "max_holdings": _as_int(params.get("max_holdings"), 6),
            "discretize_step": _as_float(params.get("disc_step"), 0.05),
            "concentration": _as_float(params.get("concentration"), 20.0) / 10.0,
            "c_sensitivity": _as_float(params.get("c_sensitivity"), 0.0) / 10.0,
            "rebalance_freq": params.get("rebalance_freq", "W-FRI"),
            "execution_timing": params.get("execution_timing", "same_close"),
            "score_band": _as_float(params.get("score_band"), 0.0) / 100.0,
            "commission_rate": 0.00026,
        },
        "factors": {
            "f1_active_days": _as_int(params.get("f1_active_days"), 0),
            "ema": {"period_weeks": _as_int(params.get("f1_ema_period"), 20)},
            "volume_ratio": {"window_days": _as_int(params.get("f3_vol_window"), 20)},
            "log_return_deviation": {
                "window_days": _as_int(params.get("f7_window"), 20),
                "lookback_days": 250,
                "min_days": 60,
                "sigma_floor": 0.01,
            },
        },
    }
    # Only include account override if frontend explicitly sends account_mode.
    # Otherwise let the YAML preset's account config pass through untouched.
    _acct_mode = params.get("account_mode")
    if _acct_mode:
        result["account"] = {
            "mode": _acct_mode,
            "max_gross_exposure": _as_float(params.get("max_gross_exposure"), 2.0),
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

    return {
        "label": preset_cfg.get("label", preset_key),
        "description": preset_cfg.get("description", ""),
        "w1": _weight_to_ui_percent(w.get("ema_deviation"), 0.30),
        "w3": _weight_to_ui_percent(w.get("volume_ratio"), 0.30),
        "conf_type": pc.get("type", "regime"),
        "dead_zone": pc.get("dead_zone", global_conf.get("dead_zone", 25)),
        "full_zone": pc.get("full_zone", global_conf.get("full_zone", 65)),
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
        "ma_bull_pos": pc.get("ma_bull_pos", global_conf.get("ma_bull_pos", 1.00)),
        "ma_bear_pos": pc.get("ma_bear_pos", global_conf.get("ma_bear_pos", 0.30)),
        "ma_trend_period": pc.get("ma_trend_period", global_conf.get("ma_trend_period", 26)),
        "ma_direction_confirm": pc.get("ma_direction_confirm", global_conf.get("ma_direction_confirm", True)),
        "benchmarks": pc.get("benchmarks", global_conf.get("benchmarks", ["000300"])),
        "max_holdings": position.get("max_holdings", 6),
        "disc_step": round(position.get("discretize_step", 0.05), 3),
        "concentration": position.get("concentration", 2.0) * 10,
        "c_sensitivity": position.get("c_sensitivity", 0.0) * 10,
        "f1_ema_period": factors.get("ema", {}).get("period_weeks", 20),
        "f3_vol_window": factors.get("volume_ratio", {}).get("window_days", 20),
        "f1_sensitivity": sensitivity.get("f1", 8.0),
        "f3_sensitivity": sensitivity.get("f3", 1.0),
        "rebalance_freq": position.get("rebalance_freq", "W-FRI"),
        "execution_timing": position.get("execution_timing", "same_close"),
        "score_band": round(position.get("score_band", 0) * 100, 1),
        "w7": _weight_to_ui_percent(w.get("log_return_deviation"), 0),
        "f7_t": sensitivity.get("f7_t", 7.0),
        "f7_k": sensitivity.get("f7_k", 3.0),
        "f7_window": factors.get("log_return_deviation", {}).get("window_days", 20),
        "f1_active_days": factors.get("f1_active_days", 1),
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
DEFAULT_PRESET = "gam-2"

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
        "gam": {"max_holdings": 4, "ma_bear_pos": 0.50, "ma_bull_pos": 1.0, "disc_step": 0.10, "concentration": 3.0, "c_sensitivity": 30, "score_band": 2.0, "ma_trend_period": 26},
        "zen": {"max_holdings": 5, "ma_bear_pos": 0.35, "ma_bull_pos": 1.0, "disc_step": 0.08, "concentration": 2.0, "c_sensitivity": 15, "score_band": 1.5, "ma_trend_period": 30},
        "act": {"max_holdings": 4, "ma_bear_pos": 0.25, "ma_bull_pos": 0.80, "disc_step": 0.10, "concentration": 4.0, "c_sensitivity": 25, "score_band": 2.0, "ma_trend_period": 34},
    },
}


# ── Preset library (for Pareto optimizer warm-start) ────────────────

def presets_as_warm_start(preset_names, reliable_only=True):
    """从预设库提取参数列表，供优化器 warm-start 使用。

    Args:
        preset_names: 预设名列表，如 ['gam-1', 'gam-2']
        reliable_only: True 时跳过标记为不可靠的预设

    Returns:
        [{"params": {...}, "source": "gam-1"}, ...]
    """
    import yaml, pathlib
    cfg_path = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "config" / "quant_universe.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    presets = cfg.get("presets", {})
    trials = []
    for name in preset_names:
        p = presets.get(name)
        if not p:
            continue
        if reliable_only and p.get("_unreliable"):
            continue
        # Extract all params from preset
        params = {}
        sc = p.get("scoring", {})
        params["w1"] = int(sc.get("weights", {}).get("ema_deviation", 0.33) * 100)
        params["w3"] = int(sc.get("weights", {}).get("volume_ratio", 0.33) * 100)
        sens = sc.get("sensitivity", {})
        params["f1_sensitivity"] = sens.get("f1", 8.0)
        params["f3_sensitivity"] = sens.get("f3", 4.0)
        params["f7_t"] = sens.get("f7_t", 10.0)
        params["f7_k"] = sens.get("f7_k", 3.0)
        cf = p.get("confidence", {})
        params["ma_bull_pos"] = cf.get("ma_bull_pos", 1.0)
        params["ma_bear_pos"] = cf.get("ma_bear_pos", 0.5)
        params["ma_trend_period"] = cf.get("ma_trend_period", 26)
        params["ma_direction_confirm"] = cf.get("ma_direction_confirm", True)
        pos = p.get("position", {})
        params["max_holdings"] = pos.get("max_holdings", 4)
        params["concentration"] = pos.get("concentration", 3.0) * 10  # config→UI
        params["c_sensitivity"] = pos.get("c_sensitivity", 30) * 10
        params["score_band"] = pos.get("score_band", 0.02) * 100
        params["disc_step"] = pos.get("discretize_step", 0.10)
        fac = p.get("factors", {})
        params["f1_ema_period"] = fac.get("ema", {}).get("period_weeks", 4)
        params["f3_vol_window"] = fac.get("volume_ratio", {}).get("window_days", 30)
        params["f7_window"] = fac.get("log_return_deviation", {}).get("window_days", 20)
        trials.append({"params": params, "source": name})
    return trials


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
