"""
Tests for core backtest engine.

Coverage:
  - run_backtest() return structure and types
  - All three presets produce valid, distinct results
  - universe_filter limits the ETF pool correctly
  - return_details provides trade_log
  - softmax numerical stability under extreme c_sensitivity (BUG-050)

Referenced by: docs/ops/quant/overview.md (验证守卫 / 最小验证)
"""
import math
import numpy as np
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from quant_backtest import run_backtest


class TestRunBacktestStructure:
    """Verify run_backtest() returns correct types and structure."""

    def test_returns_three_tuple(self):
        nav, signals, extra = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
        )
        assert nav is not None
        assert isinstance(signals, list)
        assert isinstance(extra, dict)
        assert len(nav) > 0

    def test_nav_has_expected_columns(self):
        nav, _, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
        )
        for col in ["date", "nav", "nav_pct", "cash", "holdings"]:
            assert col in nav.columns

    def test_nav_starts_near_1m(self):
        nav, _, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
        )
        # Initial capital is 1M; first-day portfolio may fluctuate slightly
        assert abs(nav["nav"].iloc[0] / 1_000_000 - 1.0) < 0.05  # within 5%

    def test_extra_has_expected_keys(self):
        _, _, extra = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
        )
        assert "total_commission" in extra
        assert "trade_count" in extra
        assert extra["trade_count"] >= 0

    def test_signals_have_expected_keys(self):
        _, signals, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
        )
        assert len(signals) > 0
        s = signals[0]
        for key in ["date", "scores", "top6", "positions", "regime"]:
            assert key in s, f"Missing key: {key}"


class TestPresets:
    """Verify all three presets produce valid results."""

    @pytest.mark.parametrize("preset", ["act-1", "zen-1", "gam-1"])
    def test_preset_runs(self, preset):
        nav, _, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset=preset,
        )
        assert nav["nav"].iloc[-1] > 0

    def test_different_presets_produce_different_results(self):
        """Three presets should give different final NAVs."""
        results = {}
        for p in ["act-1", "zen-1", "gam-1"]:
            nav, _, _ = run_backtest(
                start_date="2024-06-01", end_date="2025-06-01",
                preset=p,
            )
            results[p] = nav["nav"].iloc[-1]
        # At least one pair should differ by > 1%
        diffs = [abs(results[a] - results[b]) / results[a]
                 for a in results for b in results if a < b]
        assert max(diffs) > 0.01, f"All presets gave nearly identical results: {results}"


class TestUniverseFilter:
    """Verify universe_filter limits the ETF pool."""

    def test_filter_reduces_etf_count(self):
        """With only 5 ETFs, signals should reference only those codes."""
        nav, signals, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
            universe_filter=["512400", "513120", "515880", "159865", "159755"],
        )
        assert len(nav) > 0
        for s in signals:
            top6 = s.get("top6", [])
            for code in top6:
                assert code in ["512400", "513120", "515880", "159865", "159755"]

    def test_single_etf_filter_works(self):
        """With 1 ETF, it should always be in top6."""
        nav, signals, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-08-01",
            preset="zen-1",
            universe_filter=["515880"],
        )
        for s in signals:
            top6 = s.get("top6", [])
            assert len(top6) <= 1


class TestReturnDetails:
    """Verify return_details flag provides extra data."""

    def test_return_details_gives_trade_log(self):
        _, _, extra = run_backtest(
            start_date="2025-06-01", end_date="2025-08-01",
            preset="zen-1",
            return_details=True,
        )
        assert "trade_log" in extra
        assert isinstance(extra["trade_log"], list)

    def test_trade_log_has_expected_fields(self):
        _, _, extra = run_backtest(
            start_date="2025-06-01", end_date="2025-08-01",
            preset="zen-1",
            return_details=True,
        )
        if extra["trade_log"]:
            t = extra["trade_log"][0]
            for key in ["code", "buy_date", "sell_date", "buy_price", "sell_price", "pnl_pct"]:
                assert key in t


class TestSoftmaxStability:
    """Verify softmax numerical stability under extreme c_sensitivity.

    Regression guard for BUG-050: high c_sensitivity × concentration caused
    np.exp overflow → NaN → frontier re-validation dropped 13/18 candidates.
    Fix: stable softmax (_raw - _raw.max()) replaces clip(-700, 700).
    """

    # Extreme params that triggered BUG-050 (same family as BUG-043).
    # c_sensitivity=300 (UI display 30, ÷10 scale), concentration=26 (display 2.6, ÷10)
    # → effective_c can reach 5-8× normal, z_scores×effective_c can exceed 700.
    EXTREME_OVERRIDE = {
        "position": {
            "c_sensitivity": 300.0,
            "concentration": 26.0,
        }
    }

    def test_extreme_c_sensitivity_no_nan(self):
        """Under extreme c_sensitivity, NAV must not contain NaN/Inf.

        Before BUG-050 fix (clip(-700,700)): overflow → NaN.
        After fix (stable softmax): exp(x-max(x)) ≤ 1, never overflows.
        """
        nav, _, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
            config_override=self.EXTREME_OVERRIDE,
        )
        assert len(nav) > 0
        # No NaN or Inf in NAV column
        assert not nav["nav"].isna().any(), "NAV contains NaN — softmax overflow not fixed"
        assert not np.isinf(nav["nav"]).any(), "NAV contains Inf"
        # NAV should be positive (no bankruptcy)
        assert (nav["nav"] > 0).all(), "NAV went non-positive under extreme params"

    def test_normal_c_sensitivity_unchanged(self):
        """Normal c_sensitivity should produce valid results (regression guard).

        Stable softmax is mathematically equivalent to naive softmax
        (numerator and denominator both divided by exp(max), which cancels).
        So normal-range results should be unaffected by the fix.
        """
        normal_override = {"position": {"c_sensitivity": 10.0, "concentration": 2.0}}
        nav, _, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
            config_override=normal_override,
        )
        assert len(nav) > 0
        assert not nav["nav"].isna().any()
        assert nav["nav"].iloc[-1] > 0

    def test_zero_c_sensitivity_no_crash(self):
        """c_sensitivity=0 disables dynamic C (static concentration).

        dispersion-based c_mult is skipped, effective_c = concentration.
        Should not crash and should produce stable results.
        """
        zero_override = {"position": {"c_sensitivity": 0.0, "concentration": 2.0}}
        nav, _, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-09-01",
            preset="zen-1",
            config_override=zero_override,
        )
        assert len(nav) > 0
        assert not nav["nav"].isna().any()
        assert nav["nav"].iloc[-1] > 0
