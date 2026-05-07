#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REQ-172 X6 相关模块测试：stock_bps_fetcher + etf_pb_calculator"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ============================================================
# 通用模块加载
# ============================================================
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bps_fetcher():
    return _load("stock_bps_fetcher")


@pytest.fixture(scope="module")
def pb_calc():
    return _load("etf_pb_calculator")


# ============================================================
# BPS 反推公式
# ============================================================
class TestFetchStockHistoryBasics:
    """fetch_stock_history 的 BPS 反推 —— 不打真实 AKShare，直接验数据管理层"""

    def test_save_and_load_roundtrip(self, bps_fetcher, tmp_path):
        records = [
            {"date": "2024-01-02", "close": 10.0, "pb": 2.0, "bps": 5.0, "pe_ttm": 20.0},
            {"date": "2024-01-03", "close": 11.0, "pb": 2.2, "bps": 5.0, "pe_ttm": 22.0},
        ]
        bps_fetcher.save_stock_history("TEST", records, base_dir=tmp_path)
        loaded = bps_fetcher.load_stock_history("TEST", base_dir=tmp_path)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["close"] == 10.0
        assert loaded[0]["pb"] == 2.0
        assert loaded[0]["bps"] == 5.0

    def test_get_latest_bps(self, bps_fetcher, tmp_path):
        records = [
            {"date": "2024-01-02", "close": 10.0, "pb": 2.0, "bps": 5.0, "pe_ttm": 20.0},
            {"date": "2024-01-03", "close": 11.0, "pb": 2.2, "bps": 5.0, "pe_ttm": 22.0},
        ]
        bps_fetcher.save_stock_history("TEST", records, base_dir=tmp_path)
        bps = bps_fetcher.get_latest_bps("TEST", base_dir=tmp_path)
        assert bps == 5.0

    def test_get_latest_bps_missing(self, bps_fetcher, tmp_path):
        assert bps_fetcher.get_latest_bps("NOSUCH", base_dir=tmp_path) is None

    def test_load_missing_returns_none(self, bps_fetcher, tmp_path):
        assert bps_fetcher.load_stock_history("NOSUCH", base_dir=tmp_path) is None


# ============================================================
# 过滤 A 股
# ============================================================
class TestAShareFilter:
    def test_hk_filtered_out(self, bps_fetcher):
        holdings = {
            "513120": {
                "components": [
                    {"code": "06160", "market": "hk", "ratio": 10.0},
                    {"code": "000001", "market": "sz", "ratio": 5.0},
                ]
            }
        }
        a_components = bps_fetcher.get_a_share_components(holdings, "513120")
        assert len(a_components) == 1
        assert a_components[0]["code"] == "000001"

    def test_all_a_share(self, bps_fetcher):
        holdings = {
            "512400": {
                "components": [
                    {"code": "601899", "market": "sh", "ratio": 10.0},
                    {"code": "000807", "market": "sz", "ratio": 5.0},
                ]
            }
        }
        assert len(bps_fetcher.get_a_share_components(holdings, "512400")) == 2

    def test_unknown_etf(self, bps_fetcher):
        assert bps_fetcher.get_a_share_components({}, "999999") == []


# ============================================================
# ETF 加权 PB 历史聚合
# ============================================================
class TestComputeEtfPbHistory:
    def _stage(self, bps_fetcher, tmp_path, code: str, pb_by_date):
        records = [
            {"date": d, "close": 100.0, "pb": pb, "bps": 100.0 / pb, "pe_ttm": None}
            for d, pb in pb_by_date.items()
        ]
        bps_fetcher.save_stock_history(code, records, base_dir=tmp_path)

    def test_simple_two_stocks_equal_weight(self, bps_fetcher, tmp_path):
        self._stage(bps_fetcher, tmp_path, "A001", {"2024-01-02": 2.0, "2024-01-03": 3.0})
        self._stage(bps_fetcher, tmp_path, "A002", {"2024-01-02": 4.0, "2024-01-03": 5.0})
        components = [
            {"code": "A001", "ratio": 50.0},
            {"code": "A002", "ratio": 50.0},
        ]
        result = bps_fetcher.compute_etf_pb_history("TEST", components, stock_bps_dir=tmp_path)
        assert len(result) == 2
        assert result[0] == ("2024-01-02", 3.0)  # (2+4)/2
        assert result[1] == ("2024-01-03", 4.0)  # (3+5)/2

    def test_weighted_average(self, bps_fetcher, tmp_path):
        self._stage(bps_fetcher, tmp_path, "B001", {"2024-01-02": 2.0})
        self._stage(bps_fetcher, tmp_path, "B002", {"2024-01-02": 6.0})
        components = [
            {"code": "B001", "ratio": 75.0},  # 大权重
            {"code": "B002", "ratio": 25.0},
        ]
        result = bps_fetcher.compute_etf_pb_history("TEST", components, stock_bps_dir=tmp_path)
        # 2.0 * 0.75 + 6.0 * 0.25 = 1.5 + 1.5 = 3.0
        assert result[0][1] == pytest.approx(3.0)

    def test_date_intersection(self, bps_fetcher, tmp_path):
        """不同成分股日期不完整时应取交集"""
        self._stage(bps_fetcher, tmp_path, "C001",
                    {"2024-01-02": 2.0, "2024-01-03": 3.0, "2024-01-04": 4.0})
        self._stage(bps_fetcher, tmp_path, "C002",
                    {"2024-01-03": 5.0, "2024-01-04": 6.0, "2024-01-05": 7.0})
        components = [
            {"code": "C001", "ratio": 50.0},
            {"code": "C002", "ratio": 50.0},
        ]
        result = bps_fetcher.compute_etf_pb_history("TEST", components, stock_bps_dir=tmp_path)
        assert [d for d, _ in result] == ["2024-01-03", "2024-01-04"]

    def test_missing_stock_skipped(self, bps_fetcher, tmp_path):
        self._stage(bps_fetcher, tmp_path, "D001", {"2024-01-02": 2.0})
        components = [
            {"code": "D001", "ratio": 50.0},
            {"code": "DNOTEXIST", "ratio": 50.0},  # 缺数据
        ]
        result = bps_fetcher.compute_etf_pb_history("TEST", components, stock_bps_dir=tmp_path)
        # 仅 D001 可用，100% 权重归它
        assert result == [("2024-01-02", 2.0)]

    def test_empty_components(self, bps_fetcher, tmp_path):
        assert bps_fetcher.compute_etf_pb_history("TEST", [], stock_bps_dir=tmp_path) == []


# ============================================================
# 日更入口 compute_etf_pb_today
# ============================================================
class TestComputeEtfPbToday:
    def _stage(self, bps_fetcher, tmp_path, code: str, bps: float):
        records = [{"date": "2024-01-02", "close": 10.0, "pb": 10.0 / bps, "bps": bps, "pe_ttm": None}]
        bps_fetcher.save_stock_history(code, records, base_dir=tmp_path)

    def test_basic(self, bps_fetcher, tmp_path):
        self._stage(bps_fetcher, tmp_path, "E001", bps=5.0)
        self._stage(bps_fetcher, tmp_path, "E002", bps=10.0)
        components = [
            {"code": "E001", "ratio": 60.0},
            {"code": "E002", "ratio": 40.0},
        ]
        # 今日 close：E001=15 (PB=3), E002=20 (PB=2)
        today_closes = {"E001": 15.0, "E002": 20.0}
        pb = bps_fetcher.compute_etf_pb_today(components, today_closes, stock_bps_dir=tmp_path)
        # 3.0 * 0.6 + 2.0 * 0.4 = 1.8 + 0.8 = 2.6
        assert pb == pytest.approx(2.6)

    def test_missing_close_skipped(self, bps_fetcher, tmp_path):
        self._stage(bps_fetcher, tmp_path, "F001", bps=5.0)
        components = [{"code": "F001", "ratio": 50.0}]
        pb = bps_fetcher.compute_etf_pb_today(components, today_closes={}, stock_bps_dir=tmp_path)
        assert pb is None

    def test_all_missing_returns_none(self, bps_fetcher, tmp_path):
        components = [{"code": "NO1", "ratio": 50.0}]
        assert bps_fetcher.compute_etf_pb_today(components, {}, stock_bps_dir=tmp_path) is None


# ============================================================
# save_etf_pb_history + etf_pb_calculator 对接
# ============================================================
class TestEtfPbCalculator:
    def test_reads_last_row(self, bps_fetcher, pb_calc, tmp_path):
        # 写一个 ETF PB 历史
        data = [
            ("2024-01-02", 2.5),
            ("2024-01-03", 2.6),
            ("2024-01-04", 2.8),
        ]
        bps_fetcher.save_etf_pb_history("512400", data, base_dir=tmp_path)

        result = pb_calc.get_etf_current_pb("512400", history_dir=tmp_path)
        assert result is not None
        assert result["date"] == "2024-01-04"
        assert result["pb"] == pytest.approx(2.8)

    def test_missing_returns_none(self, pb_calc, tmp_path):
        assert pb_calc.get_etf_current_pb("NOSUCH", history_dir=tmp_path) is None

    def test_batch_interface(self, bps_fetcher, pb_calc, tmp_path):
        bps_fetcher.save_etf_pb_history("A", [("2024-01-02", 1.0)], base_dir=tmp_path)
        bps_fetcher.save_etf_pb_history("B", [("2024-01-02", 2.0)], base_dir=tmp_path)
        result = pb_calc.get_etf_current_pb_all(["A", "B", "NONE"], history_dir=tmp_path)
        assert set(result.keys()) == {"A", "B"}
        assert result["A"]["pb"] == 1.0
        assert result["B"]["pb"] == 2.0


# ============================================================
# 引擎读 X6 历史：<etf>_pb.csv 路径
# ============================================================
class TestEngineReadsX6History:
    def test_pb_metric_prefers_x6(self, bps_fetcher, tmp_path):
        """引擎看到 <etf>_pb.csv 时应优先读，而不是 <etf>.csv"""
        engine_mod = _load("valuation_engine")
        # 写两份数据：
        # <etf>_pb.csv（X6，100 行低值）
        # <etf>.csv（旧路径，100 行高值）
        low_data = [(f"2024-{m:02d}-01", 1.0) for m in range(1, 13)]  # 12 行低值 PB
        bps_fetcher.save_etf_pb_history("TEST", low_data, base_dir=tmp_path)
        legacy = tmp_path / "TEST.csv"
        legacy.write_text("date,pe_ttm,pb\n2024-01-01,20,50\n", encoding="utf-8")

        # 检查 _load_history 优先读 X6
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        values = engine._load_history("TEST", "pb")
        # 应该是 X6 的 12 行 1.0，而不是旧路径的 50
        assert len(values) == 12
        assert all(v == 1.0 for v in values)

    def test_pe_metric_uses_legacy(self, bps_fetcher, tmp_path):
        """PE 主指标仍走旧路径 <etf>.csv"""
        engine_mod = _load("valuation_engine")
        bps_fetcher.save_etf_pb_history("TEST", [("2024-01-01", 5.0)], base_dir=tmp_path)  # X6 只对 PB 生效
        legacy = tmp_path / "TEST.csv"
        legacy.write_text("date,pe_ttm,pb\n2024-01-01,25,\n2024-01-02,30,\n", encoding="utf-8")
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        values = engine._load_history("TEST", "pe_ttm")
        assert values == [25.0, 30.0]
