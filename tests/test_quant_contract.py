import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from etf_report.core import quant_contract as qc


def sample_params(**overrides):
    """Test params using only active keys."""
    params = {
        "w1": 30,
        "w3": 60,
        "w7": 10,
        "bias": 0,
        "conf_type": "ma_trend",
        "dead_zone": 25,
        "full_zone": 65,
        "ma_bull_pos": 1.0,
        "ma_bear_pos": 0.3,
        "ma_trend_period": 26,
        "ma_direction_confirm": True,
        "max_holdings": 6,
        "disc_step": 0.05,
        "concentration": 2.0,
        "rebalance_freq": "daily",
        "execution_timing": "same_close",
        "score_band": 3,
        "f1_ema_period": 16,
        "f3_vol_window": 20,
        "f1_sensitivity": 8.0,
        "f3_sensitivity": 1.0,
        "f7_t": 15.0,
        "f7_k": 3.5,
        "f7_window": 20,
    }
    params.update(overrides)
    return params


def test_validate_tuner_params_accepts_same_close():
    params = sample_params(execution_timing="same_close")
    assert qc.validate_tuner_params(params) is None


def test_validate_tuner_params_rejects_bad_weight_total():
    params = sample_params(w7=5)
    assert "sum to 100" in qc.validate_tuner_params(params)


def test_validate_tuner_params_rejects_bad_execution_timing():
    params = sample_params(execution_timing="bad")
    assert "execution_timing" in qc.validate_tuner_params(params)


def test_parse_universe_filter_modes():
    assert qc.parse_universe_filter({"universe": ""}) == (None, "all")
    assert qc.parse_universe_filter({"universe": "__NONE__"}) == ([], "empty")
    assert qc.parse_universe_filter({"universe": "512400, 512070,512400"}) == (["512070", "512400"], "filtered")


def test_tuner_params_to_config_override_unit_conversions():
    override = qc.tuner_params_to_config_override(sample_params())

    assert override["scoring"]["weights"]["ema_deviation"] == pytest.approx(0.30)
    assert override["scoring"]["weights"]["volume_ratio"] == pytest.approx(0.60)
    assert override["scoring"]["weights"]["log_return_deviation"] == pytest.approx(0.10)

    assert override["position"]["score_band"] == pytest.approx(0.03)
    assert override["position"]["execution_timing"] == "same_close"
    assert override["position"]["discretize_step"] == pytest.approx(0.05)
    assert override["factors"]["log_return_deviation"]["window_days"] == 20


def test_preset_to_tuner_params_round_trip_core_fields():
    preset = {
        "label": "测试策略",
        "description": "desc",
        "scoring": {
            "weights": {
                "ema_deviation": 0.3,
                "volume_ratio": 0.60,
                "valuation": 0,
                "log_return_deviation": 0.1,
            },
            "bias_bonus": 0,
            "sensitivity": {"f1": 8, "f3": 1.0, "f7_t": 15, "f7_k": 3.5},
        },
        "confidence": {"type": "ma_trend", "ma_bull_pos": 1.0, "ma_bear_pos": 0.3, "ma_trend_period": 26},
        "position": {"max_holdings": 6, "discretize_step": 0.05, "concentration": 2.0, "rebalance_freq": "daily", "execution_timing": "same_close", "score_band": 0.03},
        "factors": {"ema": {"period_weeks": 16}, "volume_ratio": {"window_days": 20}, "log_return_deviation": {"window_days": 20}},
    }

    params = qc.preset_to_tuner_params("test", preset, {"dead_zone": 25, "full_zone": 65})

    assert params["label"] == "测试策略"
    assert params["w1"] == 30
    assert params["w3"] == 60
    assert params["w7"] == 10
    assert params["score_band"] == 3
    assert params["execution_timing"] == "same_close"


def test_preset_to_tuner_params_rounds_float_weights():
    preset = {
        "scoring": {
            "weights": {
                "ema_deviation": 0.57,
                "volume_ratio": 0.17,
                "log_return_deviation": 0.26,
            }
        },
        "confidence": {},
        "position": {},
        "factors": {},
    }

    params = qc.preset_to_tuner_params("test", preset, {})

    assert [params["w1"], params["w3"], params["w7"]] == [57, 17, 26]
    assert params["w1"] + params["w3"] + params["w7"] == 100



def test_param_schema_contains_all_core_tuner_params():
    schema = qc.get_param_schema()
    keys = set(qc.iter_schema_param_keys())

    assert schema["version"] == 1
    for key in sample_params().keys():
        if key not in {"debug", "execution_timing"}:
            assert key in keys, f"Missing key in schema: {key}"

    assert "execution_timing" not in keys
    assert "score_band" in keys
    assert "f7_window" in keys


def test_param_schema_is_a_copy():
    schema = qc.get_param_schema()
    schema["groups"].clear()
    assert qc.get_param_schema()["groups"]


def test_tuner_params_to_preset_patch_preserves_existing_sections():
    base = {
        "scoring": {"legacy": "keep"},
        "confidence": {"regime_base": {"bull_trend": 0.95}},
        "position": {"max_holdings_special": 8},
        "factors": {"existing_factor": {"enabled": True}},
    }

    patch = qc.tuner_params_to_preset_patch(sample_params(), base)

    assert patch["scoring"]["legacy"] == "keep"
    assert patch["confidence"]["regime_base"] == {"bull_trend": 0.95}
    assert patch["position"]["max_holdings_special"] == 8
    assert patch["factors"]["existing_factor"] == {"enabled": True}
    assert patch["position"]["score_band"] == pytest.approx(0.03)
