#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_csindex_pe.py — REQ-175 配套：一次性从 csindex 拉指数历史 PE 写入本地

用途：
  - 对 PE 主指标 + csindex/csindex-proxy 数据源的 ETF，一次性拉取 tracking_index_code 的历史 PE
  - 写入 data/valuation_history/<etf>.csv（字段 date, pe_ttm, pb）
  - 让 valuation_engine 的时间序列百分位立刻可用（原来靠 20 天接口增量累积要等很久）

使用：
  # 回填单个
  python scripts/backfill_csindex_pe.py --etf 513120

  # 回填所有 csindex / csindex-proxy 的 PE 主指标 ETF
  python scripts/backfill_csindex_pe.py --all
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path
from typing import Optional

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from logger import Logger  # noqa: E402

logger = Logger(name="backfill_csindex_pe", file_output=False)

SKILL_ROOT = _SCRIPT_DIR.parent
DEFAULT_ANCHORS = SKILL_ROOT / "config" / "valuation_anchors.yaml"
DEFAULT_HIST = SKILL_ROOT / "data" / "valuation_history"


def backfill_pe_history(etf_code: str, index_code: str,
                        hist_dir: Path = DEFAULT_HIST) -> Optional[int]:
    """
    从 csindex 历史接口拉取 index_code 的 PE 序列，写入 <etf>.csv。
    返回写入的行数；接口失败返回 None。
    """
    try:
        import akshare as ak
    except ImportError:
        logger.error("akshare 未安装")
        return None

    try:
        df = ak.stock_zh_index_hist_csindex(
            symbol=index_code,
            start_date="20180101",
            end_date="20991231",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warn("csindex 历史接口失败", {
            "etf": etf_code,
            "index_code": index_code,
            "error": f"{type(exc).__name__}: {str(exc)[:120]}",
        })
        return None

    if df is None or len(df) == 0:
        logger.warn("csindex 历史接口返回空", {"etf": etf_code})
        return None

    # 过滤出 滚动市盈率 非空的行
    if "滚动市盈率" not in df.columns:
        logger.warn("历史数据缺 '滚动市盈率' 列", {"cols": list(df.columns)})
        return None

    valid = df[df["滚动市盈率"].notna()][["日期", "滚动市盈率"]].copy()
    valid = valid.sort_values("日期")

    if len(valid) == 0:
        return 0

    hist_dir.mkdir(parents=True, exist_ok=True)
    csv_path = hist_dir / f"{etf_code}.csv"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "pe_ttm", "pb"])
        for _, row in valid.iterrows():
            date_str = str(row["日期"])
            pe = float(row["滚动市盈率"])
            writer.writerow([date_str, f"{pe:.4f}", ""])

    logger.info("PE 历史回填完成", {
        "etf": etf_code,
        "index_code": index_code,
        "rows": len(valid),
        "date_range": f"{str(valid['日期'].iloc[0])} ~ {str(valid['日期'].iloc[-1])}",
        "latest_pe": float(valid["滚动市盈率"].iloc[-1]),
    })
    return len(valid)


def main() -> int:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="REQ-175 csindex PE 历史回填")
    parser.add_argument("--etf", type=str, default=None)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    with DEFAULT_ANCHORS.open("r", encoding="utf-8") as f:
        anchors = yaml.safe_load(f)["anchors"]

    if args.etf:
        targets = [args.etf]
    elif args.all:
        targets = [
            code for code, cfg in anchors.items()
            if cfg.get("primary_metric") == "pe_ttm"
            and cfg.get("data_source") in ("csindex", "csindex-proxy")
            and cfg.get("tracking_index_code")
        ]
    else:
        parser.error("请指定 --etf 或 --all")
        return 2

    print(f"目标 ETF: {targets}")
    print("=" * 60)

    for code in targets:
        cfg = anchors.get(code)
        if cfg is None:
            print(f"[SKIP] {code} 不在锚点表")
            continue
        index_code = cfg.get("tracking_index_code", "")
        if not index_code:
            print(f"[SKIP] {code} 无 tracking_index_code")
            continue
        print(f"\n>>> {code} 代理指数 {index_code}")
        n = backfill_pe_history(code, index_code)
        print(f"    写入行数：{n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
