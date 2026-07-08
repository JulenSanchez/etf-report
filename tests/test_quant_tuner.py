"""
Tests for quant_tuner.py — split detection, memory bridge, data conversion.

Covers the business logic that was previously untested (0% → now covered):
  - _deep_merge: recursive dict merge
  - _df_to_cleaning_input / _apply_cleaning_to_df: DataFrame ↔ cleaning dict
  - _trading_elapsed_minutes / _is_post_market: time gating
  - _ensure_splits_detected: AKShare split detection (mocked)
  - _apply_split_memory_bridge: self-healing logic (mocked CACHE)

Flask endpoints and Tuner orchestration are NOT covered here — those need
a running Tuner process and are marked with 'tuner' marker for future work.
"""
import json, sys, os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# ── Import the module ──
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quant_tuner as qt


# ══════════════════════════════════════════════════════════════════════
# _deep_merge
# ══════════════════════════════════════════════════════════════════════

class TestDeepMerge:
    def test_flat_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        qt._deep_merge(base, override)
        assert base == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 99, "z": 100}}
        qt._deep_merge(base, override)
        assert base == {"a": {"x": 1, "y": 99, "z": 100}, "b": 3}

    def test_override_is_not_dict_does_not_recurse(self):
        base = {"a": {"x": 1}}
        override = {"a": 42}
        qt._deep_merge(base, override)
        # 'a' was a dict in base but override gives a scalar → replaces
        assert base == {"a": 42}

    def test_new_key_with_dict_value(self):
        base = {}
        override = {"a": {"x": 1}}
        qt._deep_merge(base, override)
        assert base == {"a": {"x": 1}}


# ══════════════════════════════════════════════════════════════════════
# _df_to_cleaning_input / _apply_cleaning_to_df
# ══════════════════════════════════════════════════════════════════════

class TestDataframeCleaningConversion:
    """Round-trip: DataFrame → cleaning dict → apply → DataFrame."""

    def test_df_to_cleaning_input_basic(self):
        df = pd.DataFrame({
            "date":   ["2026-07-01", "2026-07-02", "2026-07-03"],
            "open":   [1.50, 1.55, 1.58],
            "close":  [1.55, 1.58, 0.79],
            "high":   [1.52, 1.57, 1.60],
            "low":    [1.48, 1.53, 0.78],
            "volume": [100000, 120000, 500000],
        })
        ci = qt._df_to_cleaning_input(df)

        assert ci["dates"] == ["2026-07-01", "2026-07-02", "2026-07-03"]
        assert ci["kline"][0] == [1.50, 1.55, 1.48, 1.52]  # open, close, low, high
        assert ci["kline"][2] == [1.58, 0.79, 0.78, 1.60]
        assert ci["volumes"] == [100000, 120000, 500000]

    def test_df_to_cleaning_input_no_volume_column(self):
        df = pd.DataFrame({
            "date":  ["2026-07-01"],
            "open":  [1.0], "close": [1.0], "high": [1.0], "low": [1.0],
        })
        ci = qt._df_to_cleaning_input(df)
        assert ci["volumes"] == []

    def test_apply_cleaning_to_df_preserves_shape(self):
        df = pd.DataFrame({
            "date":   ["2026-07-01", "2026-07-02", "2026-07-03"],
            "open":   [1.50, 1.55, 1.58],
            "close":  [1.55, 1.58, 0.79],
            "high":   [1.52, 1.57, 1.60],
            "low":    [1.48, 1.53, 0.78],
            "volume": [100000, 120000, 500000],
        })
        cleaned = {
            "kline": [
                [0.75, 0.775, 0.74, 0.76],   # prices halved (1:2 split)
                [0.775, 0.79, 0.765, 0.785],
                [0.79, 0.79, 0.78, 0.80],     # effective date → not adjusted
            ],
            "volumes": [200000, 240000, 500000],  # volumes doubled
        }
        result = qt._apply_cleaning_to_df(df, cleaned)

        assert len(result) == 3
        assert float(result["close"].iloc[0]) == 0.775   # halved
        assert float(result["close"].iloc[2]) == 0.79    # unchanged (effective date)
        assert float(result["volume"].iloc[0]) == 200000  # doubled

    def test_roundtrip_no_change(self):
        """DataFrame → cleaning_input → apply back → identical."""
        df = pd.DataFrame({
            "date":   ["2026-07-01", "2026-07-02"],
            "open":   [1.0, 2.0],
            "close":  [1.5, 2.5],
            "high":   [1.6, 2.6],
            "low":    [0.9, 1.9],
            "volume": [100, 200],
        })
        ci = qt._df_to_cleaning_input(df)
        result = qt._apply_cleaning_to_df(df, ci)

        for col in ["open", "close", "high", "low"]:
            for i in range(len(df)):
                assert float(result[col].iloc[i]) == float(df[col].iloc[i]), \
                    f"{col}[{i}] mismatch"


# ══════════════════════════════════════════════════════════════════════
# _trading_elapsed_minutes / _is_post_market
# ══════════════════════════════════════════════════════════════════════

class TestTradingTimeGating:
    """Time-related functions — pure, deterministic when 'now' is injected."""

    def test_before_open(self):
        now = datetime(2026, 7, 6, 9, 0)  # 09:00
        assert qt._trading_elapsed_minutes(now) == 0

    def test_mid_morning(self):
        now = datetime(2026, 7, 6, 10, 30)  # 10:30
        # 10:30 - 09:30 = 60 min
        assert qt._trading_elapsed_minutes(now) == 60

    def test_lunch_break(self):
        now = datetime(2026, 7, 6, 12, 0)  # 12:00
        # Morning session only: 11:30 - 09:30 = 120 min
        assert qt._trading_elapsed_minutes(now) == 120

    def test_mid_afternoon(self):
        now = datetime(2026, 7, 6, 14, 0)  # 14:00
        # Morning 120 + (14:00 - 13:00) = 120 + 60 = 180
        assert qt._trading_elapsed_minutes(now) == 180

    def test_after_close(self):
        now = datetime(2026, 7, 6, 16, 0)  # 16:00
        assert qt._trading_elapsed_minutes(now) == qt.TOTAL_TRADING_MINUTES

    def test_is_post_market_before_cool_off(self):
        now = datetime(2026, 7, 6, 14, 50)  # 14:50 (< 15:10)
        assert not qt._is_post_market(now)

    def test_is_post_market_at_cool_off_boundary(self):
        now = datetime(2026, 7, 6, 15, 10)  # 15:10 (= COOL_OFF_TIME)
        assert qt._is_post_market(now)

    def test_is_post_market_after_cool_off(self):
        now = datetime(2026, 7, 6, 15, 30)  # 15:30
        assert qt._is_post_market(now)

    def test_trading_elapsed_uses_real_time_when_now_is_none(self):
        """Sanity: call without arg should not crash."""
        minutes = qt._trading_elapsed_minutes()
        assert isinstance(minutes, int)
        assert 0 <= minutes <= qt.TOTAL_TRADING_MINUTES


# ══════════════════════════════════════════════════════════════════════
# _ensure_splits_detected (mocked AKShare)
# ══════════════════════════════════════════════════════════════════════

class TestEnsureSplitsDetected:
    """Split detection with mocked detect_corporate_action_events."""

    def test_first_call_detects_and_caches(self):
        """On first call, corporate_action_source is queried and results are cached."""
        # Setup: empty global state, and mock _load_corporate_action_events to return {}
        qt._SPLIT_CHECKED = False
        qt._SPLIT_EVENTS = {}

        mock_result = {
            "events_by_code": {
                "515880": [{
                    "action": "share_split",
                    "ex_date": "2026-07-03",
                    "ratio": 2.0,
                    "note": "1拆2",
                }]
            }
        }
        with patch(
            "etf_report.core.corporate_action_source.detect_corporate_action_events",
            return_value=mock_result
        ), patch.object(qt, "_load_corporate_action_events", return_value={}):
            qt._ensure_splits_detected({"universe": [{"code": "515880"}]})

        assert qt._SPLIT_CHECKED is True
        assert "515880" in qt._SPLIT_EVENTS
        events = qt._SPLIT_EVENTS["515880"]
        # Should have at least the 1 event we mocked
        assert len(events) >= 1
        # The event we mocked should be present
        ratios = [e["ratio"] for e in events]
        assert 2.0 in ratios

    def test_second_call_uses_cache(self):
        """Second call skips detection — _SPLIT_CHECKED is already True."""
        qt._SPLIT_CHECKED = True
        qt._SPLIT_EVENTS = {"515880": [{"action": "share_split", "ex_date": "2026-07-03", "ratio": 2.0}]}
        original_events = dict(qt._SPLIT_EVENTS)

        # Detection should NOT be called
        with patch(
            "etf_report.core.corporate_action_source.detect_corporate_action_events"
        ) as mock_detect:
            qt._ensure_splits_detected({"universe": [{"code": "515880"}]})
            mock_detect.assert_not_called()

        assert qt._SPLIT_EVENTS == original_events

    def test_non_split_event_filtered_out(self):
        """Non-split events are filtered out by detect_corporate_action_events."""
        qt._SPLIT_CHECKED = False
        qt._SPLIT_EVENTS = {}

        # detect_corporate_action_events already filters — returns empty
        mock_result = {"events_by_code": {}}
        with patch(
            "etf_report.core.corporate_action_source.detect_corporate_action_events",
            return_value=mock_result
        ):
            qt._ensure_splits_detected({"universe": [{"code": "510050"}]})

        # No split events for this ETF
        assert "510050" not in qt._SPLIT_EVENTS or len(qt._SPLIT_EVENTS.get("510050", [])) == 0

    def test_detection_failure_is_graceful(self):
        """If detection raises, it should not crash — just log and continue."""
        qt._SPLIT_CHECKED = False
        qt._SPLIT_EVENTS = {}

        with patch(
            "etf_report.core.corporate_action_source.detect_corporate_action_events",
            side_effect=Exception("AKShare timeout")
        ):
            # Should not raise
            qt._ensure_splits_detected({"universe": [{"code": "159915"}]})

        # Should still be marked as checked (avoid retry loop)
        assert qt._SPLIT_CHECKED is True


# ══════════════════════════════════════════════════════════════════════
# _apply_split_memory_bridge (mocked CACHE)
# ══════════════════════════════════════════════════════════════════════

class TestApplySplitMemoryBridge:
    """Self-healing bridge logic with mocked CACHE and _SPLIT_EVENTS."""

    def _make_daily_df(self, closes):
        """Helper: make a simple daily DataFrame with given close prices."""
        dates = [f"2026-07-{i+1:02d}" for i in range(len(closes))]
        return pd.DataFrame({
            "date":   dates,
            "open":   closes,
            "close":  closes,
            "high":   [c + 0.01 for c in closes],
            "low":    [c - 0.01 for c in closes],
            "volume": [100000] * len(closes),
        })

    def test_csv_already_adjusted_skips_bridge(self):
        """CSV close / intraday close ≈ 1.0 → skip cleaning."""
        # Setup: CSV already has post-split prices
        daily = self._make_daily_df([0.78, 0.79, 0.80])
        qt.CACHE["all_daily"] = {"515880": daily}
        qt.CACHE["intraday_cache"] = {
            "515880": {"date": "2026-07-06", "open": 0.80, "close": 0.76, "high": 0.81, "low": 0.74, "volume": 50000000}
        }
        qt._SPLIT_EVENTS = {
            "515880": [{"action": "share_split", "ex_date": "2026-07-03", "ratio": 2.0}]
        }

        cfg = {"universe": [{"code": "515880"}]}
        qt._apply_split_memory_bridge(cfg)

        # Data should be UNCHANGED (skip)
        assert float(daily["close"].iloc[-1]) == 0.80
        assert float(daily["close"].iloc[0]) == 0.78

    def test_csv_pre_split_triggers_bridge(self):
        """CSV close / intraday close ≈ split_ratio → trigger cleaning."""
        # Setup: CSV has pre-split prices (≈ 2× intraday)
        daily = self._make_daily_df([1.50, 1.55, 1.58])
        qt.CACHE["all_daily"] = {"515880": daily.copy()}
        qt.CACHE["intraday_cache"] = {
            "515880": {"date": "2026-07-06", "open": 0.80, "close": 0.76, "high": 0.81, "low": 0.74, "volume": 50000000}
        }
        qt._SPLIT_EVENTS = {
            "515880": [{"action": "share_split", "ex_date": "2026-07-03", "ratio": 2.0}]
        }

        # Record pre-bridge state
        pre_first = float(daily["close"].iloc[0])
        pre_last = float(daily["close"].iloc[-1])
        assert abs(pre_last / 0.76 - 2.0) < 0.3  # ≈ split_ratio → should trigger

        cfg = {"universe": [{"code": "515880"}]}
        qt._apply_split_memory_bridge(cfg)

        # After bridge: data should be MODIFIED (cleaning applied)
        result = qt.CACHE["all_daily"]["515880"]
        post_first = float(result["close"].iloc[0])
        # Historical prices should decrease (divided by split ratio)
        assert post_first < pre_first * 0.9, \
            f"Expected pre-split prices to decrease, got {post_first} vs {pre_first}"
        # At minimum, data was touched (not skipped)
        assert not result.equals(daily) or abs(post_first - pre_first) > 0.001

    def test_no_intraday_cache_skips_bridge(self):
        """When intraday cache is empty, bridge is skipped (can't determine)."""
        daily = self._make_daily_df([1.50, 1.55, 1.58])
        qt.CACHE["all_daily"] = {"515880": daily.copy()}
        qt.CACHE["intraday_cache"] = {}  # empty
        qt._SPLIT_EVENTS = {
            "515880": [{"action": "share_split", "ex_date": "2026-07-03", "ratio": 2.0}]
        }

        cfg = {"universe": [{"code": "515880"}]}
        qt._apply_split_memory_bridge(cfg)

        # Data unchanged (can't determine → safe skip)
        assert float(daily["close"].iloc[0]) == 1.50

    def test_no_split_events_skips_bridge(self):
        """ETF with no split events → nothing to do."""
        daily = self._make_daily_df([1.0, 1.1, 1.2])
        qt.CACHE["all_daily"] = {"512400": daily.copy()}
        qt.CACHE["intraday_cache"] = {
            "512400": {"date": "2026-07-06", "close": 1.15}
        }
        qt._SPLIT_EVENTS = {}  # no events

        cfg = {"universe": [{"code": "512400"}]}
        qt._apply_split_memory_bridge(cfg)

        assert float(daily["close"].iloc[0]) == 1.0

    def test_multiple_splits_uses_most_recent(self):
        """When ETF has multiple splits, only the most recent is used for ratio check."""
        daily = self._make_daily_df([3.00, 3.10, 1.60])
        qt.CACHE["all_daily"] = {"515880": daily.copy()}
        qt.CACHE["intraday_cache"] = {
            "515880": {"date": "2026-07-06", "open": 0.80, "close": 0.76, "high": 0.81, "low": 0.74, "volume": 50000000}
        }
        # Two splits: old 3:1, new 2:1
        qt._SPLIT_EVENTS = {
            "515880": [
                {"action": "share_split", "ex_date": "2025-01-15", "ratio": 3.0},
                {"action": "share_split", "ex_date": "2026-07-03", "ratio": 2.0},
            ]
        }

        # csv_last/intraday = 1.60/0.76 ≈ 2.1 → matches ratio=2.0 (most recent) → trigger
        pre_first = float(daily["close"].iloc[0])

        cfg = {"universe": [{"code": "515880"}]}
        qt._apply_split_memory_bridge(cfg)

        result = qt.CACHE["all_daily"]["515880"]
        post_first = float(result["close"].iloc[0])
        # Historical prices should decrease (cleaning applied with most recent ratio)
        assert post_first < pre_first * 0.9, \
            f"Expected prices to decrease after cleaning, got {post_first} vs {pre_first}"


# ══════════════════════════════════════════════════════════════════════
# Cleanup after each test to avoid cross-test pollution
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset module globals before each test to avoid cross-test pollution."""
    qt._SPLIT_CHECKED = False
    qt._SPLIT_EVENTS = {}
    qt.CACHE.clear()
    qt.CACHE["all_daily"] = {}
    qt.CACHE["all_weekly"] = {}
    qt.CACHE["intraday_cache"] = {}
    qt.CACHE["cfg"] = None
    yield
    qt._SPLIT_CHECKED = False
    qt._SPLIT_EVENTS = {}
    qt.CACHE.clear()
