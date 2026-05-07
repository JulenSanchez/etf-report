# -*- coding: utf-8 -*-
"""估值引擎单元测试 (REQ-170 Step 2)"""
from pathlib import Path
from textwrap import dedent

import pytest


# ============================================================
# 算法单元：classify_verdict / rule_based / time_series / blended
# ============================================================
class TestClassifyVerdict:
    def test_five_tiers(self, load_module):
        engine = load_module("valuation_engine")
        assert engine.classify_verdict(5).get("label") == "极度低估"
        assert engine.classify_verdict(25).get("label") == "低估"
        assert engine.classify_verdict(50).get("label") == "合理"
        assert engine.classify_verdict(75).get("label") == "偏高"
        assert engine.classify_verdict(95).get("label") == "极度高估"

    def test_boundary_values(self, load_module):
        engine = load_module("valuation_engine")
        # 边界：< 20 低估 / < 40 低估 / < 60 合理 / < 80 偏高 / 其余极高
        assert engine.classify_verdict(19.9).get("label") == "极度低估"
        assert engine.classify_verdict(20).get("label") == "低估"
        assert engine.classify_verdict(39.9).get("label") == "低估"
        assert engine.classify_verdict(40).get("label") == "合理"
        assert engine.classify_verdict(60).get("label") == "偏高"
        assert engine.classify_verdict(80).get("label") == "极度高估"

    def test_over_hundred(self, load_module):
        engine = load_module("valuation_engine")
        # 理论不可达，但算法应该给兜底
        assert engine.classify_verdict(150).get("label") == "极度高估"


class TestRuleBasedPercentile:
    @pytest.fixture
    def anchors(self):
        return {
            "extreme_low":  {"value": 1.0,  "percentile": 5},
            "low":          {"value": 2.0,  "percentile": 25},
            "median":       {"value": 3.0,  "percentile": 50},
            "high":         {"value": 4.0,  "percentile": 75},
            "extreme_high": {"value": 5.0,  "percentile": 95},
        }

    def test_anchor_exact_values(self, load_module, anchors):
        engine = load_module("valuation_engine")
        # 落在锚点上，返回对应百分位
        assert engine.rule_based_percentile(1.0, anchors) == pytest.approx(3.0)  # 极低-2 兜底
        assert engine.rule_based_percentile(2.0, anchors) == pytest.approx(25)
        assert engine.rule_based_percentile(3.0, anchors) == pytest.approx(50)
        assert engine.rule_based_percentile(4.0, anchors) == pytest.approx(75)
        assert engine.rule_based_percentile(5.0, anchors) == pytest.approx(97)  # 极高+2 兜底

    def test_interpolation(self, load_module, anchors):
        engine = load_module("valuation_engine")
        # 中值 1.5（low 和 extreme_low 中点）→ (5+25)/2 = 15
        assert engine.rule_based_percentile(1.5, anchors) == pytest.approx(15)
        # 2.5（low 和 median 中点）→ (25+50)/2 = 37.5
        assert engine.rule_based_percentile(2.5, anchors) == pytest.approx(37.5)
        # 3.5 → (50+75)/2 = 62.5
        assert engine.rule_based_percentile(3.5, anchors) == pytest.approx(62.5)

    def test_out_of_range_below(self, load_module, anchors):
        engine = load_module("valuation_engine")
        # 跌破 extreme_low（1.0）→ 应返回 3（极低分位 5 - 2），最低 1
        assert engine.rule_based_percentile(0.5, anchors) == pytest.approx(3)
        assert engine.rule_based_percentile(-100, anchors) == pytest.approx(3)

    def test_out_of_range_above(self, load_module, anchors):
        engine = load_module("valuation_engine")
        # 超过 extreme_high（5.0）→ 应返回 97，最高 99
        assert engine.rule_based_percentile(5.5, anchors) == pytest.approx(97)
        assert engine.rule_based_percentile(100, anchors) == pytest.approx(97)


class TestTimeSeriesPercentile:
    def test_empty_history(self, load_module):
        engine = load_module("valuation_engine")
        assert engine.time_series_percentile(10, []) == pytest.approx(50.0)

    def test_basic(self, load_module):
        engine = load_module("valuation_engine")
        history = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        # 当前值 5，低于的有 1,2,3,4 共 4 个 → 40 分位
        assert engine.time_series_percentile(5, history) == pytest.approx(40.0)

    def test_extreme(self, load_module):
        engine = load_module("valuation_engine")
        history = list(range(1, 101))
        # 当前 150，所有都低 → 100 分位
        assert engine.time_series_percentile(150, history) == pytest.approx(100.0)
        # 当前 0，无低于 → 0 分位
        assert engine.time_series_percentile(0, history) == pytest.approx(0.0)


class TestBlendedPercentile:
    @pytest.fixture
    def anchors(self):
        return {
            "extreme_low":  {"value": 1.0, "percentile": 5},
            "low":          {"value": 2.0, "percentile": 25},
            "median":       {"value": 3.0, "percentile": 50},
            "high":         {"value": 4.0, "percentile": 75},
            "extreme_high": {"value": 5.0, "percentile": 95},
        }

    def test_rule_mode_when_history_short(self, load_module, anchors):
        engine = load_module("valuation_engine")
        history = [3.0] * 50  # 只有 50 天样本
        pct, confidence, n = engine.blended_percentile(3.0, history, anchors)
        assert confidence == "rule"
        assert n == 50
        assert pct == pytest.approx(50)  # 锚点中位值

    def test_blend_mode(self, load_module, anchors):
        engine = load_module("valuation_engine")
        history = [3.0] * 300  # 300 天
        pct, confidence, n = engine.blended_percentile(3.0, history, anchors)
        assert confidence == "blend"
        assert n == 300
        # 300 天 weight_ts = 200/400 = 0.5
        # pct_rule = 50, pct_ts = 0（所有样本都等于 3，不满足 "<"）
        # 混合 = 50 * 0.5 + 0 * 0.5 = 25
        assert pct == pytest.approx(25)

    def test_history_mode(self, load_module, anchors):
        engine = load_module("valuation_engine")
        history = [float(i) for i in range(1, 601)]  # 600 天线性序列
        pct, confidence, n = engine.blended_percentile(300, history, anchors)
        assert confidence == "history"
        assert n == 600
        # 当前 300，低于 300 的有 299 个 → 299/600 ≈ 49.83
        assert pct == pytest.approx(49.83, abs=0.1)


# ============================================================
# ValuationEngine 集成：加载真实锚点表
# ============================================================
class TestValuationEngine:
    def test_loads_real_anchors(self, load_module):
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine()
        etfs = engine.list_etfs()
        assert set(etfs) == {"512400", "513120", "512070", "515880", "159755", "159865"}

    def test_evaluate_returns_none_for_unknown_etf(self, load_module):
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine()
        assert engine.evaluate("999999", 1.0) is None

    def test_evaluate_no_data(self, load_module):
        """current_value=None → 返回带 no-data 标记的结果"""
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine()
        result = engine.evaluate("513120", None)  # 港创药无实时数据
        assert result is not None
        assert result["confidence"] == "no-data"
        assert result["percentile"] is None
        assert result["verdict"] is None
        # 2026-04-23 REQ-175 将 513120 主指标从 pb 改 pe_ttm（走 A 股代理 931152）
        assert result["primary_metric"] == "pe_ttm"

    def test_evaluate_with_current_value(self, load_module, tmp_path):
        """515880 通信 PE=80 → 应该判定为偏高/极高区间"""
        engine_mod = load_module("valuation_engine")
        # 用空的 history_dir 隔离，避免真实 data/valuation_history/ 影响 sample_days
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        result = engine.evaluate("515880", 80.0)
        assert result is not None
        assert result["confidence"] == "rule"
        assert result["sample_days"] == 0
        assert result["percentile"] is not None
        assert 75 <= result["percentile"] <= 85
        assert result["verdict"]["label"] == "偏高"
        assert result["tracking_index"] == "中证全指通信设备指数"

    def test_evaluate_median_returns_50(self, load_module, tmp_path):
        """锚点中位值 → 必定返回 50 分位（使用空 history_dir 保证走纯锚点）"""
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        cfg = engine.get_etf_config("512400")
        median_pb = cfg["anchors"]["median"]["value"]
        result = engine.evaluate("512400", median_pb)
        assert result["percentile"] == pytest.approx(50.0)
        assert result["verdict"]["label"] == "合理"

    def test_evaluate_all(self, load_module, tmp_path):
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        current = {
            "512400": None,
            "515880": 80.0,
            "159865": 3.6,  # median
        }
        results = engine.evaluate_all(current)
        # 应该覆盖全部 6 支（未提供 current 的给 no-data）
        assert set(results.keys()) == {"512400", "513120", "512070", "515880", "159755", "159865"}
        assert results["515880"]["verdict"]["label"] == "偏高"
        assert results["159865"]["verdict"]["label"] == "合理"
        assert results["512400"]["confidence"] == "no-data"


# ============================================================
# 自定义锚点表加载（隔离测试）
# ============================================================
class TestCustomAnchorPath:
    def test_load_custom_yaml(self, load_module, tmp_path):
        custom_yaml = tmp_path / "custom_anchors.yaml"
        custom_yaml.write_text(dedent("""\
            anchors:
              "TEST001":
                name: "测试 ETF"
                tracking_index: "测试指数"
                data_source: "test"
                primary_metric: pe_ttm
                anchors:
                  extreme_low:  { value: 10, percentile: 5 }
                  low:          { value: 15, percentile: 25 }
                  median:       { value: 20, percentile: 50 }
                  high:         { value: 30, percentile: 75 }
                  extreme_high: { value: 50, percentile: 95 }
            """), encoding="utf-8")

        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine(anchor_path=custom_yaml)
        result = engine.evaluate("TEST001", 20.0)
        assert result["percentile"] == pytest.approx(50.0)
        assert result["tracking_index"] == "测试指数"

    def test_missing_yaml_raises(self, load_module, tmp_path):
        missing = tmp_path / "no_such.yaml"
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine(anchor_path=missing)
        with pytest.raises(FileNotFoundError):
            engine.list_etfs()


# ============================================================
# 历史文件读取（方法 B' 增量演化接口）
# ============================================================
class TestHistoryLoading:
    def test_missing_history_returns_empty(self, load_module, tmp_path):
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        values = engine._load_history("512400", "pb")
        assert values == []

    def test_read_csv_history(self, load_module, tmp_path):
        hist_file = tmp_path / "512400.csv"
        hist_file.write_text(
            "date,pb,pe_ttm\n"
            "2026-01-01,2.5,30.0\n"
            "2026-01-02,2.6,31.0\n"
            "2026-01-03,2.4,29.0\n",
            encoding="utf-8",
        )
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        pb_values = engine._load_history("512400", "pb")
        assert pb_values == [2.5, 2.6, 2.4]
        pe_values = engine._load_history("512400", "pe_ttm")
        assert pe_values == [30.0, 31.0, 29.0]

    def test_missing_metric_column(self, load_module, tmp_path):
        hist_file = tmp_path / "512400.csv"
        hist_file.write_text("date,pb\n2026-01-01,2.5\n", encoding="utf-8")
        engine_mod = load_module("valuation_engine")
        engine = engine_mod.ValuationEngine(history_dir=tmp_path)
        assert engine._load_history("512400", "pe_ttm") == []
