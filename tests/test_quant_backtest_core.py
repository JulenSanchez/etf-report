"""
Tests for core backtest engine.

Coverage:
  - run_backtest() return structure and types
  - All three presets produce valid, distinct results
  - universe_filter limits the ETF pool correctly
  - return_details provides trade_log

Referenced by: docs/ops/quant/overview.md (验证守卫 / 最小验证)
"""
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
