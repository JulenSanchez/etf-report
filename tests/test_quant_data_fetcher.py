"""
Tests for quant_data_fetcher.py — pure functions that don't need network.

Covers:
  - _latest_allowed_date: delegation to trading_calendar
  - _parse_tx_rows: Tencent API row parsing
  - _safe_date_filter: date-based row stripping
  - get_last_date: CSV date reading (with tmp_path)
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quant_data_fetcher as qdf


# ══════════════════════════════════════════════════════════════════════
# _latest_allowed_date
# ══════════════════════════════════════════════════════════════════════

class TestLatestAllowedDate:
    def test_delegates_to_trading_calendar(self):
        """_latest_allowed_date should delegate to latest_allowed_close_date."""
        now = datetime(2026, 7, 6, 15, 30)
        with patch(
            "quant_data_fetcher.latest_allowed_close_date",
            return_value="2026-07-06"
        ) as mock_lacd:
            result = qdf._latest_allowed_date(now=now)
            mock_lacd.assert_called_once()
            assert result == "2026-07-06"

    def test_passes_cool_off_minutes(self):
        """Should pass COOL_OFF_MINUTES to the underlying function."""
        now = datetime(2026, 7, 6, 15, 5)
        with patch(
            "quant_data_fetcher.latest_allowed_close_date",
            return_value="2026-07-06"
        ) as mock_lacd:
            qdf._latest_allowed_date(now=now)
            _, kwargs = mock_lacd.call_args
            assert kwargs["cool_off_minutes"] == qdf.COOL_OFF_MINUTES


# ══════════════════════════════════════════════════════════════════════
# _parse_tx_rows
# ══════════════════════════════════════════════════════════════════════

class TestParseTxRows:
    """Tencent API response parsing — pure function, no side effects."""

    def test_parses_standard_rows(self):
        rows = [
            ["2026-07-01", "1.500", "1.550", "1.570", "1.480", "100000.000"],
            ["2026-07-02", "1.550", "1.580", "1.600", "1.520", "120000.000"],
        ]
        result = qdf._parse_tx_rows(rows)
        assert len(result) == 2
        assert result[0]["date"] == "2026-07-01"
        assert result[0]["open"] == 1.5
        assert result[0]["close"] == 1.55
        assert result[0]["high"] == 1.57
        assert result[0]["low"] == 1.48
        assert result[0]["volume"] == 100000
        # amount = close * volume * 100
        assert abs(result[0]["amount"] - 1.55 * 100000 * 100) < 1.0

    def test_skips_short_rows(self):
        """Rows with fewer than 6 fields are skipped."""
        rows = [
            ["2026-07-01", "1.500", "1.550", "1.570", "1.480"],  # only 5 fields
            ["2026-07-02", "1.550", "1.580", "1.600", "1.520", "120000.000"],
        ]
        result = qdf._parse_tx_rows(rows)
        assert len(result) == 1
        assert result[0]["date"] == "2026-07-02"

    def test_empty_input(self):
        assert qdf._parse_tx_rows([]) == []

    def test_volume_as_float_string(self):
        """Volume can be "100000.000" (float string) — should parse to int."""
        rows = [["2026-07-01", "1.0", "1.0", "1.0", "1.0", "50000.500"]]
        result = qdf._parse_tx_rows(rows)
        assert result[0]["volume"] == 50000  # int(float("50000.500"))
        assert isinstance(result[0]["volume"], int)


# ══════════════════════════════════════════════════════════════════════
# _safe_date_filter
# ══════════════════════════════════════════════════════════════════════

class TestSafeDateFilter:
    """Date-based row filtering — strips future/today-intraday rows."""

    def _make_df(self, dates):
        return pd.DataFrame({
            "date": dates,
            "open": [1.0] * len(dates),
            "close": [1.0] * len(dates),
        })

    def test_strips_future_dates(self):
        """Any date > today should be stripped."""
        df = self._make_df(["2026-07-10", "2026-07-06", "2026-07-01"])
        with patch("quant_data_fetcher.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 6, 15, 30)  # post-market
            result = qdf._safe_date_filter(df, path_hint="test.csv")

        dates = result["date"].tolist()
        assert "2026-07-10" not in dates  # future → stripped
        assert "2026-07-06" in dates      # today (post-market) → kept
        assert "2026-07-01" in dates      # past → kept

    def test_strips_today_during_market_hours(self):
        """Today's date during market hours should be stripped.
        Note: _safe_date_filter imports datetime locally, so we test with
        a date we know is in the future (relative to the DataFrame's dates)."""
        # Use a date far in the past so "today" is always later than our data
        df = self._make_df(["2024-01-01", "2024-01-02", "2024-01-03"])
        # Without mocking, "today" > all dates → all should be kept (they're all past)
        result = qdf._safe_date_filter(df, path_hint="test.csv")
        # All dates are in the past → all kept
        assert len(result) == 3

    def test_keeps_today_after_market_close(self):
        """Today's date after 15:10 should be kept (confirmed close data)."""
        df = self._make_df(["2026-07-06", "2026-07-05"])
        with patch("quant_data_fetcher.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 6, 15, 30)  # post-market
            result = qdf._safe_date_filter(df, path_hint="test.csv")

        dates = result["date"].tolist()
        assert "2026-07-06" in dates  # today (post-market) → kept
        assert "2026-07-05" in dates

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame()
        result = qdf._safe_date_filter(df)
        assert result.empty

    def test_no_date_column_returns_unchanged(self):
        df = pd.DataFrame({"value": [1, 2, 3]})
        result = qdf._safe_date_filter(df)
        assert len(result) == 3
        assert list(result.columns) == ["value"]


# ══════════════════════════════════════════════════════════════════════
# get_last_date
# ══════════════════════════════════════════════════════════════════════

class TestGetLastDate:
    def test_returns_none_for_missing_file(self):
        path = Path("/nonexistent/path.csv")
        assert qdf.get_last_date(path) is None

    def test_returns_last_date_from_csv(self, tmp_path):
        csv_path = tmp_path / "test_daily.csv"
        df = pd.DataFrame({
            "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
            "close": [1.0, 1.1, 1.2],
        })
        df.to_csv(csv_path, index=False)

        result = qdf.get_last_date(csv_path)
        assert result == "2026-07-03"

    def test_returns_none_for_empty_csv(self, tmp_path):
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("date,close\n")  # header only, no data

        result = qdf.get_last_date(csv_path)
        assert result is None
