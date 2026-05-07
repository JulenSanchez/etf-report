#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
etf_pb_calculator.py — REQ-172 X6 日更入口

职责：
  读 data/valuation_history/<etf>_pb.csv 的最后一行 → 作为 ETF 当前 PB

设计解释：
  - X6 方案里，stock_bps_fetcher.py 已经一次性拉完 5 年历史 PB 序列
  - 本模块不再调远程接口，只读本地聚合结果
  - "最新 PB" 来自 stock_value_em 最后一个交易日的 close/pb，
    如果用户今天刚跑过 fetcher 就是今天的，否则是上次跑的那天
  - 更新频率由用户通过 CLI 手动决定（REQ-161 周更基建就绪后自动化接管）
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

SKILL_ROOT = _SCRIPT_DIR.parent
DEFAULT_VALUATION_HISTORY_DIR = SKILL_ROOT / "data" / "valuation_history"


def get_etf_current_pb(
    etf_code: str,
    history_dir: Path = DEFAULT_VALUATION_HISTORY_DIR,
) -> Optional[Dict[str, object]]:
    """
    从 <etf>_pb.csv 读取最新一行 PB。

    返回 {"date": str, "pb": float} 或 None。
    """
    csv_path = history_dir / f"{etf_code}_pb.csv"
    if not csv_path.exists():
        return None

    last_row: Optional[Dict[str, str]] = None
    try:
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                last_row = row
    except OSError:
        return None

    if not last_row:
        return None

    try:
        pb = float(last_row.get("pb", 0) or 0)
    except (TypeError, ValueError):
        return None

    if pb <= 0:
        return None

    return {
        "date": last_row.get("date", ""),
        "pb": pb,
    }


def get_etf_current_pb_all(
    etf_codes: list,
    history_dir: Path = DEFAULT_VALUATION_HISTORY_DIR,
) -> Dict[str, Dict[str, object]]:
    """批量读多支 ETF 的当前 PB"""
    result = {}
    for code in etf_codes:
        data = get_etf_current_pb(code, history_dir)
        if data:
            result[code] = data
    return result
