import sys
from pathlib import Path

import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_backtest import execution_price_field, get_execution_date, load_config


def test_execution_price_field_distinguishes_timing():
    assert execution_price_field("same_close") == "close"
    assert execution_price_field("next_open") == "open"
    assert execution_price_field("bad_value") == "close"


def test_get_execution_date_distinguishes_timing():
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-05-18", "2026-05-19", "2026-05-20"]))
    signal_date = pd.Timestamp("2026-05-19")

    assert get_execution_date(signal_date, dates, "same_close") == signal_date
    assert get_execution_date(signal_date, dates, "next_open") == pd.Timestamp("2026-05-20")


def test_get_execution_date_next_open_returns_none_without_future_date():
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-05-18", "2026-05-19"]))
    assert get_execution_date(pd.Timestamp("2026-05-19"), dates, "next_open") is None


def test_daily_aggressive_default_execution_timing_is_same_close():
    cfg = load_config("daily_aggressive")
    assert cfg["position"]["execution_timing"] == "same_close"
