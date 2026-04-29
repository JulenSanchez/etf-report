#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估值引擎 - ETF 估值锚点插值 + 百分位 + 五档判词

功能：
1. 加载 config/valuation_anchors.yaml 锚点表
2. 分段线性插值：把当前 PE/PB 值映射到历史百分位
3. 五档判词：极度低估 / 低估 / 合理 / 偏高 / 极度高估
4. 置信度标注：rule (纯锚点) / blend (锚点+历史) / history (纯历史)

方法论见 docs/VALUATION_METHODOLOGY.md

使用方法：
    from valuation_engine import ValuationEngine

    engine = ValuationEngine()
    result = engine.evaluate("512400", current_value=2.35)
    # {
    #   "etf_code": "512400", "percentile": 42.3,
    #   "verdict": {"label": "合理", "emoji": "⚪", "color": "gray"},
    #   "confidence": "rule", ...
    # }

    # 无当前值时返回 None，由调用方决定 UI 处理（不展示或退到 median）
    result = engine.evaluate("513120", current_value=None)
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError("需要 PyYAML：pip install pyyaml") from exc


# ============================================================
# 五档判词定义（协议：docs/VALUATION_METHODOLOGY.md §5）
# ============================================================
VERDICTS = [
    (20,  {"label": "极度低估", "emoji": "🟢", "color": "deep-green"}),
    (40,  {"label": "低估",     "emoji": "🟢", "color": "green"}),
    (60,  {"label": "合理",     "emoji": "⚪", "color": "gray"}),
    (80,  {"label": "偏高",     "emoji": "🟠", "color": "orange"}),
    (101, {"label": "极度高估", "emoji": "🔴", "color": "red"}),
]


def classify_verdict(percentile: float) -> Dict[str, str]:
    """百分位 -> 五档判词"""
    for threshold, verdict in VERDICTS:
        if percentile < threshold:
            return dict(verdict)
    return dict(VERDICTS[-1][1])


# ============================================================
# 核心算法：分段线性插值
# ============================================================
def rule_based_percentile(current_value: float, anchors: Dict[str, Dict[str, float]]) -> float:
    """
    把 current_value 按 anchors 做分段线性插值，映射到百分位 (0-100)。

    anchors 结构：
        {
          "extreme_low":  {"value": 1.30, "percentile": 5},
          "low":          {"value": 1.90, "percentile": 25},
          "median":       {"value": 2.60, "percentile": 50},
          "high":         {"value": 3.60, "percentile": 75},
          "extreme_high": {"value": 5.20, "percentile": 95},
        }

    - 低于 extreme_low：返回 max(1, 极低分位-2)
    - 高于 extreme_high：返回 min(99, 极高分位+2)
    - 中间区间：分段线性插值
    """
    points = sorted(anchors.values(), key=lambda p: p["value"])
    values = [p["value"] for p in points]
    pcts = [p["percentile"] for p in points]

    if current_value <= values[0]:
        return max(1.0, float(pcts[0] - 2))
    if current_value >= values[-1]:
        return min(99.0, float(pcts[-1] + 2))

    for i in range(len(values) - 1):
        if values[i] <= current_value <= values[i + 1]:
            span = values[i + 1] - values[i]
            if span <= 0:
                return float(pcts[i])
            ratio = (current_value - values[i]) / span
            return float(pcts[i] + ratio * (pcts[i + 1] - pcts[i]))

    return 50.0  # 理论不可达


def time_series_percentile(current_value: float, history: List[float]) -> float:
    """
    把 current_value 在 history 序列中的百分位返回 (0-100)。
    标准时间序列百分位（低于当前值的样本占比）。
    """
    if not history:
        return 50.0
    below = sum(1 for v in history if v < current_value)
    return below / len(history) * 100.0


def blended_percentile(
    current_value: float,
    history: List[float],
    anchors: Dict[str, Dict[str, float]],
) -> Tuple[float, str, int]:
    """
    混合百分位（方法 B'）：
      - history < 100 天 : 纯锚点
      - 100 <= history < 500 天 : 锚点 + 历史加权混合
      - history >= 500 天 : 纯历史百分位

    返回 (percentile, confidence, sample_days)
    """
    n = len(history)

    if n < 100:
        pct = rule_based_percentile(current_value, anchors)
        return pct, "rule", n

    if n < 500:
        pct_rule = rule_based_percentile(current_value, anchors)
        pct_ts = time_series_percentile(current_value, history)
        weight_ts = (n - 100) / 400.0
        pct = pct_rule * (1 - weight_ts) + pct_ts * weight_ts
        return pct, "blend", n

    pct = time_series_percentile(current_value, history)
    return pct, "history", n


# ============================================================
# 引擎主体
# ============================================================
class ValuationEngine:
    """ETF 估值引擎：锚点 + 历史序列混合演化"""

    DEFAULT_ANCHOR_PATH = Path(__file__).resolve().parent.parent / "config" / "valuation_anchors.yaml"
    DEFAULT_HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "valuation_history"

    def __init__(
        self,
        anchor_path: Optional[Path] = None,
        history_dir: Optional[Path] = None,
    ):
        self.anchor_path = Path(anchor_path) if anchor_path else self.DEFAULT_ANCHOR_PATH
        self.history_dir = Path(history_dir) if history_dir else self.DEFAULT_HISTORY_DIR
        self._anchors_cache: Optional[Dict[str, Any]] = None

    # ---------- 配置加载 ----------
    def _load_anchors(self) -> Dict[str, Any]:
        if self._anchors_cache is not None:
            return self._anchors_cache

        if not self.anchor_path.exists():
            raise FileNotFoundError(f"锚点表不存在: {self.anchor_path}")

        with self.anchor_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict) or "anchors" not in data:
            raise ValueError(f"锚点表格式错误，缺少顶层 'anchors' key: {self.anchor_path}")

        self._anchors_cache = data["anchors"]
        return self._anchors_cache

    def get_etf_config(self, etf_code: str) -> Optional[Dict[str, Any]]:
        """返回某支 ETF 的完整锚点配置，找不到返回 None"""
        anchors_map = self._load_anchors()
        return anchors_map.get(etf_code)

    def list_etfs(self) -> List[str]:
        """列出所有已配置锚点的 ETF 代码"""
        return list(self._load_anchors().keys())

    # ---------- 历史序列读取（方法 B' 演化用） ----------
    def _load_history(self, etf_code: str, metric: str) -> List[float]:
        """
        读取 data/valuation_history/ 下的历史序列。

        优先级：
          1. metric=pb 且存在 <etf>_pb.csv（REQ-172 X6 产出，BPS 反推的成分股加权 PB）
             → 读其 pb 列
          2. 回退到 <etf>.csv 的 metric 列（REQ-170 valuation_fetcher 每日增量 PE）

        文件不存在或格式异常返回 []。
        """
        # Path 1: X6 生成的 <etf>_pb.csv（仅 PB 主指标适用）
        if metric == "pb":
            x6_path = self.history_dir / f"{etf_code}_pb.csv"
            values_x6 = self._read_csv_column(x6_path, "pb")
            if values_x6:
                return values_x6

        # Path 2: 旧路径 <etf>.csv 的 metric 列
        legacy_path = self.history_dir / f"{etf_code}.csv"
        return self._read_csv_column(legacy_path, metric)

    @staticmethod
    def _read_csv_column(csv_path: Path, column: str) -> List[float]:
        """读 CSV 指定列的浮点序列；文件/列不存在返回 []。"""
        if not csv_path.exists():
            return []
        values: List[float] = []
        try:
            with csv_path.open("r", encoding="utf-8") as f:
                header = f.readline().strip().split(",")
                if column not in header:
                    return []
                idx = header.index(column)
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) <= idx:
                        continue
                    try:
                        values.append(float(parts[idx]))
                    except ValueError:
                        continue
        except OSError:
            return []
        return values

    # ---------- 核心接口 ----------
    def evaluate(
        self,
        etf_code: str,
        current_value: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        评估一支 ETF 的估值水位。

        参数:
            etf_code       : ETF 六位代码
            current_value  : 当前主指标值（PE 或 PB）；None 表示无实时数据

        返回 dict:
            {
              "etf_code": "512400",
              "tracking_index": "中证申万有色金属指数",
              "primary_metric": "pb",
              "current_value": 2.35,                  # 或 None
              "percentile": 42.3,                     # 或 None
              "verdict": {"label": "合理", ...},      # 或 None
              "confidence": "rule" | "blend" | "history" | "no-data",
              "sample_days": 0,
              "window_note": "锚点规则 · 仅 0 天真实样本",
              "data_source": "csindex",
            }

        etf_code 不在锚点表时返回 None。
        current_value 为 None 时返回带 confidence="no-data" 的结果，percentile/verdict 都为 None。
        """
        cfg = self.get_etf_config(etf_code)
        if cfg is None:
            return None

        metric = cfg["primary_metric"]
        anchors = cfg["anchors"]
        result = {
            "etf_code": etf_code,
            "name": cfg.get("name", ""),
            "tracking_index": cfg.get("tracking_index", ""),
            "tracking_index_code": cfg.get("tracking_index_code", ""),
            "primary_metric": metric,
            "current_value": current_value,
            "percentile": None,
            "verdict": None,
            "confidence": "no-data",
            "sample_days": 0,
            "window_note": "暂无实时数据",
            "data_source": cfg.get("data_source", "unknown"),
        }

        if current_value is None:
            return result

        history = self._load_history(etf_code, metric)
        pct, confidence, n = blended_percentile(float(current_value), history, anchors)

        if confidence == "rule":
            window_note = f"锚点规则 · 真实样本 {n} 天"
        elif confidence == "blend":
            window_note = f"规则+历史混合 · 真实样本 {n} 天"
        else:
            window_note = f"历史百分位 · 真实样本 {n} 天"

        result.update({
            "percentile": round(pct, 1),
            "verdict": classify_verdict(pct),
            "confidence": confidence,
            "sample_days": n,
            "window_note": window_note,
        })
        return result

    def evaluate_all(
        self,
        current_values: Dict[str, Optional[float]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量评估。

        参数:
            current_values : {etf_code: current_value_or_None}

        返回:
            {etf_code: evaluate_result} （跳过锚点表外的 code）
        """
        output = {}
        for etf in self.list_etfs():
            cur = current_values.get(etf)
            res = self.evaluate(etf, cur)
            if res is not None:
                output[etf] = res
        return output


# ============================================================
# CLI 调试入口
# ============================================================
def _cli_main() -> int:  # pragma: no cover
    import argparse
    import io
    import json
    import sys

    # Windows GBK 终端兼容（输出含 emoji + 中文）
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="ETF 估值引擎 CLI 调试")
    parser.add_argument("--etf", required=True, help="ETF 代码（如 512400）")
    parser.add_argument("--value", type=float, default=None, help="当前 PE/PB 值")
    args = parser.parse_args()

    engine = ValuationEngine()
    result = engine.evaluate(args.etf, args.value)
    if result is None:
        print(f"ETF {args.etf} 不在锚点表")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
