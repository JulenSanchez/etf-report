import sys
from pathlib import Path

import pandas as pd
import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_consistency_check import compare_summaries, summarize_result


def make_nav(values):
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]),
        "nav": values,
    })


def make_signals():
    return [
        {"date": pd.Timestamp("2026-01-01"), "positions": {"512400": 0.5}},
        {"date": pd.Timestamp("2026-01-05"), "positions": {"512400": 0.3, "512070": 0.2}},
    ]


def test_summarize_result_core_metrics():
    summary = summarize_result(make_nav([100.0, 110.0, 104.5]), make_signals())

    assert summary["start_date"] == "2026-01-01"
    assert summary["end_date"] == "2026-01-05"
    assert summary["trading_days"] == 3
    assert summary["final_nav"] == pytest.approx(104.5)
    assert summary["total_return"] == pytest.approx(4.5)
    assert summary["max_drawdown"] == pytest.approx(-5.0)
    assert summary["rebalance_days"] == 2
    assert summary["last_signal_date"] == "2026-01-05"


def test_compare_summaries_passes_identical_values():
    summary = summarize_result(make_nav([100.0, 110.0, 104.5]), make_signals())
    ok, diffs = compare_summaries(summary, dict(summary))

    assert ok is True
    assert diffs["final_nav"] == 0
    assert diffs["last_positions"] == 0


def test_compare_summaries_fails_on_numeric_delta():
    a = summarize_result(make_nav([100.0, 110.0, 104.5]), make_signals())
    b = dict(a)
    b["final_nav"] = a["final_nav"] + 0.01

    ok, diffs = compare_summaries(a, b, tolerance=1e-6)

    assert ok is False
    assert diffs["final_nav"] > 0


def test_compare_summaries_fails_on_signal_delta():
    a = summarize_result(make_nav([100.0, 110.0, 104.5]), make_signals())
    b = dict(a)
    b["last_signal_date"] = "2026-01-02"

    ok, diffs = compare_summaries(a, b)

    assert ok is False
    assert diffs["last_signal_date"]["direct"] == "2026-01-05"
    assert diffs["last_signal_date"]["contract"] == "2026-01-02"
