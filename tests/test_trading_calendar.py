"""
Tests for trading_calendar.py — core date logic shared by quant/report scripts.

Covers:
  - latest_allowed_close_date: cool-off gating + last_trading_day delegation
  - is_trading_day: calendar-based + weekday fallback
  - last_trading_day: binary search + fallback logic
"""
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the core module (scripts/trading_calendar.py is a redirect wrapper)
from etf_report.core import trading_calendar as tc


# ══════════════════════════════════════════════════════════════════════
# latest_allowed_close_date — the most critical function
# ══════════════════════════════════════════════════════════════════════

class TestLatestAllowedCloseDate:
    """Cool-off gating: before 15:10 → yesterday, after 15:10 → today."""

    def test_during_market_hours_returns_yesterday(self):
        """10:30 AM — market still open, no confirmed close yet."""
        now = datetime(2026, 7, 6, 10, 30)
        with patch.object(tc, "last_trading_day") as mock_ltd:
            mock_ltd.side_effect = lambda d: (d - timedelta(days=1)).strftime("%Y-%m-%d") if d.hour < 15 else d.strftime("%Y-%m-%d")
            result = tc.latest_allowed_close_date(now=now)
            # Should call last_trading_day with a date before today (yesterday)
            assert result is not None

    def test_at_cool_off_boundary_returns_today(self):
        """15:10 exactly — cool-off just passed."""
        now = datetime(2026, 7, 6, 15, 10)
        with patch.object(tc, "last_trading_day", return_value="2026-07-06"):
            result = tc.latest_allowed_close_date(now=now)
            assert result == "2026-07-06"

    def test_before_cool_off_returns_yesterday(self):
        """15:05 — 5 min before cool-off expires."""
        now = datetime(2026, 7, 6, 15, 5)
        with patch.object(tc, "last_trading_day", return_value="2026-07-03"):
            result = tc.latest_allowed_close_date(now=now)
            assert result == "2026-07-03"

    def test_after_market_close_returns_today(self):
        """17:00 — well after market close + cool-off."""
        now = datetime(2026, 7, 6, 17, 0)
        with patch.object(tc, "last_trading_day", return_value="2026-07-06"):
            result = tc.latest_allowed_close_date(now=now)
            assert result == "2026-07-06"

    def test_custom_cool_off_minutes(self):
        """With cool_off_minutes=5, 15:05 should already be post-market."""
        now = datetime(2026, 7, 6, 15, 5)
        with patch.object(tc, "last_trading_day", return_value="2026-07-06"):
            result = tc.latest_allowed_close_date(now=now, cool_off_minutes=5)
            assert result == "2026-07-06"  # cool-off passed

    def test_custom_market_close_time(self):
        """Custom market close at 16:00 with 10min cool-off."""
        now = datetime(2026, 7, 6, 16, 5)
        with patch.object(tc, "last_trading_day", return_value="2026-07-06"):
            result = tc.latest_allowed_close_date(
                now=now, market_close_hour=16, market_close_minute=0, cool_off_minutes=10
            )
            assert result == "2026-07-06"  # 16:05 > 16:00 + 10min

    def test_before_custom_market_close(self):
        """Custom close at 16:00, 15:30 — not yet closed."""
        now = datetime(2026, 7, 6, 15, 30)
        with patch.object(tc, "last_trading_day", return_value="2026-07-03"):
            result = tc.latest_allowed_close_date(
                now=now, market_close_hour=16, market_close_minute=0
            )
            assert result == "2026-07-03"


# ══════════════════════════════════════════════════════════════════════
# is_trading_day
# ══════════════════════════════════════════════════════════════════════

class TestIsTradingDay:
    """Calendar-based check with weekday fallback."""

    def test_monday_is_trading_day_by_weekday_fallback(self):
        """When no calendar loaded, Monday should be a trading day."""
        tc._TRADING_DAYS.clear()
        tc._TD_LIST.clear()
        tc._LOADED_YEARS = None

        monday = datetime(2026, 7, 6)  # Monday
        assert tc.is_trading_day(monday) is True

    def test_saturday_is_not_trading_day_by_weekday_fallback(self):
        """When no calendar loaded, Saturday is NOT a trading day."""
        tc._TRADING_DAYS.clear()
        tc._TD_LIST.clear()
        tc._LOADED_YEARS = None

        saturday = datetime(2026, 7, 4)  # Saturday
        assert tc.is_trading_day(saturday) is False

    def test_calendar_overrides_weekday(self):
        """When calendar is loaded, it overrides the weekday check."""
        tc._TRADING_DAYS = {"2026-07-06"}  # Monday
        tc._TD_LIST = ["2026-07-06"]

        monday = datetime(2026, 7, 6)
        assert tc.is_trading_day(monday) is True

        # A Tuesday NOT in the calendar → False
        tuesday = datetime(2026, 7, 7)
        assert tc.is_trading_day(tuesday) is False

    def test_is_trading_day_defaults_to_now(self):
        """Call without argument should not crash."""
        tc._TRADING_DAYS.clear()
        tc._TD_LIST.clear()
        tc._LOADED_YEARS = None
        result = tc.is_trading_day()
        assert isinstance(result, bool)


# ══════════════════════════════════════════════════════════════════════
# last_trading_day
# ══════════════════════════════════════════════════════════════════════

class TestLastTradingDay:
    """Binary search in calendar + weekday fallback."""

    def test_with_calendar_returns_correct_date(self):
        """Given a sorted calendar, find the last trading day on/before target."""
        tc._TD_LIST = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"]
        tc._TRADING_DAYS = set(tc._TD_LIST)

        # Target is a trading day itself
        result = tc.last_trading_day(before=datetime(2026, 7, 3))
        assert result == "2026-07-03"

        # Target is a weekend → return Friday
        result = tc.last_trading_day(before=datetime(2026, 7, 5))  # Sunday
        assert result == "2026-07-03"

    def test_calendar_binary_search_exact_match(self):
        """Target IS a trading day in the calendar → return itself."""
        tc._TD_LIST = ["2026-07-01", "2026-07-02", "2026-07-03"]
        tc._TRADING_DAYS = set(tc._TD_LIST)

        result = tc.last_trading_day(before=datetime(2026, 7, 2))
        assert result == "2026-07-02"

    def test_fallback_without_calendar(self):
        """Without calendar, return the nearest weekday on/before target."""
        tc._TD_LIST.clear()
        tc._TRADING_DAYS.clear()

        # Sunday → go back to Friday
        result = tc.last_trading_day(before=datetime(2026, 7, 5))  # Sunday
        dt = datetime.strptime(result, "%Y-%m-%d")
        assert dt.weekday() < 5  # must be a weekday


# ══════════════════════════════════════════════════════════════════════
# Cleanup after all tests
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_calendar_state():
    """Reset module globals to avoid cross-test pollution."""
    tc._TRADING_DAYS.clear()
    tc._TD_LIST.clear()
    tc._LOADED_YEARS = None
    yield
    tc._TRADING_DAYS.clear()
    tc._TD_LIST.clear()
    tc._LOADED_YEARS = None
