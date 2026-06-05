"""
Tests for shared data cache (quant_data_cache.py).

Coverage:
  - BacktestDataCache: load, idempotency, get_preloaded, singleton
  - Preloaded data consumed by run_backtest()
  - cache_key: determinism, differentiation by preset/date/config_override/universe_filter/timing
  - Result cache: save/load round-trip, missing key returns None

Referenced by: QUANT_SYSTEM.md (验证守卫), runbooks/QUANT_RUNBOOK.md (最小验证)
"""
import pytest, sys, os, yaml
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from quant_data_cache import (
    BacktestDataCache, get_cache, cache_key, load_cached_result, save_cached_result,
)


class TestBacktestDataCache:
    """Verify the shared data cache loads and provides data correctly."""

    @pytest.fixture
    def universe(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "quant_universe.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg["universe"]

    def test_load_populates_all_daily(self, universe):
        cache = BacktestDataCache()
        cache.load(universe)
        assert len(cache.all_daily) > 0
        # Should have loaded most ETFs
        assert len(cache.all_daily) >= len(universe) * 0.9  # at least 90%

    def test_load_is_idempotent(self, universe):
        cache = BacktestDataCache()
        cache.load(universe)
        count1 = len(cache.all_daily)
        cache.load(universe)
        assert len(cache.all_daily) == count1  # No change on re-load

    def test_get_preloaded_returns_expected_keys(self, universe):
        cache = BacktestDataCache()
        cache.load(universe)
        preloaded = cache.get_preloaded()
        assert "all_daily" in preloaded
        assert "all_weekly" in preloaded
        assert isinstance(preloaded["all_daily"], dict)

    def test_get_preloaded_data_usable_in_backtest(self, universe):
        """Verify preloaded data can be consumed by run_backtest."""
        cache = BacktestDataCache()
        cache.load(universe)
        preloaded = cache.get_preloaded()

        from quant_backtest import run_backtest
        nav, _, _ = run_backtest(
            start_date="2025-06-01", end_date="2025-08-01",
            preset="preset2", execution_timing="next_open",
            preloaded=preloaded,
        )
        assert len(nav) > 0
        assert nav["nav"].iloc[-1] > 0

    def test_singleton_get_cache(self):
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2


class TestCacheKey:
    """Hash-based cache key generation."""

    def test_same_params_same_key(self):
        k1 = cache_key("preset1", "2025-01-01", "2025-06-01")
        k2 = cache_key("preset1", "2025-01-01", "2025-06-01")
        assert k1 == k2

    def test_different_preset_different_key(self):
        k1 = cache_key("preset1", "2025-01-01", "2025-06-01")
        k2 = cache_key("preset2", "2025-01-01", "2025-06-01")
        assert k1 != k2

    def test_different_dates_different_key(self):
        k1 = cache_key("preset1", "2025-01-01", "2025-06-01")
        k2 = cache_key("preset1", "2025-01-01", "2025-07-01")
        assert k1 != k2

    def test_config_override_affects_key(self):
        k1 = cache_key("preset1", "2025-01-01", "2025-06-01")
        k2 = cache_key("preset1", "2025-01-01", "2025-06-01",
                       config_override={"scoring": {"weights": {"ema_deviation": 0.5}}})
        assert k1 != k2

    def test_universe_filter_affects_key(self):
        k1 = cache_key("preset1", "2025-01-01", "2025-06-01")
        k2 = cache_key("preset1", "2025-01-01", "2025-06-01",
                       universe_filter=["512400", "513120"])
        assert k1 != k2

    def test_execution_timing_affects_key(self):
        k1 = cache_key("preset1", "2025-01-01", "2025-06-01", execution_timing="same_close")
        k2 = cache_key("preset1", "2025-01-01", "2025-06-01", execution_timing="next_open")
        assert k1 != k2


class TestResultCache:
    """Round-trip save/load for cached results."""

    def test_load_missing_returns_none(self):
        result = load_cached_result("nonexistent_key_12345")
        assert result is None

    def test_save_and_load(self):
        import pandas as pd
        import tempfile, shutil
        nav_df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10),
            "nav": [1_000_000 + i * 1000 for i in range(10)],
            "nav_pct": [100.0 + i * 0.1 for i in range(10)],
            "cash": [500_000 - i * 5000 for i in range(10)],
            "holdings": [5] * 10,
        })
        extra = {"trade_count": 10, "total_commission": 500.0}

        # Save to temp cache dir (override CACHE_DIR)
        import quant_data_cache as qdc
        import tempfile
        orig_dir = qdc.CACHE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                qdc.CACHE_DIR = type(qdc.CACHE_DIR)(td)
                key = "test_cache_key_001"
                save_cached_result(key, nav_df, extra)
                loaded = load_cached_result(key)
                assert loaded is not None
                assert abs(loaded["summary"]["final_nav"] - nav_df["nav"].iloc[-1]) < 1
                assert loaded["summary"]["days"] == 10
        finally:
            qdc.CACHE_DIR = orig_dir
