import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from quant_backtest import execution_price_field, get_execution_date, load_config


def test_execution_price_field_always_close():
    assert execution_price_field() == "close"


def test_get_execution_date_same_close():
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-05-18", "2026-05-19", "2026-05-20"]))
    signal_date = pd.Timestamp("2026-05-19")
    assert get_execution_date(signal_date, dates) == signal_date
