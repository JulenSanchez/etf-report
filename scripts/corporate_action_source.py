#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
份额变动事件源模块。

职责：
1. 从结构化外部数据源抓取基金拆分/折算事件
2. 仅保留当前图表窗口会用到的事件
3. 转换为数据清洗模块可直接消费的标准结构
4. 产出可审计的 JSON 结构化结果
"""

import json
import os
from datetime import date, datetime

from logger import Logger


logger = Logger(name="corporate_action_source", level="INFO", file_output=True)
TYPE_TO_ACTION = {
    "份额分拆": "share_split",
    "份额折算": "share_change",
}


def get_window_years(start_date, end_date):
    """返回检测窗口覆盖的年份列表。"""
    if start_date > end_date:
        return []
    return list(range(start_date.year, end_date.year + 1))


def fetch_fund_split_rows(year, detection_config=None):
    """从 AKShare 拉取指定年份的基金拆分/折算数据。"""
    detection_config = detection_config or {}
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("缺少 akshare，无法自动识别份额变动事件") from exc

    df = ak.fund_cf_em(
        year=str(year),
        typ=str(detection_config.get("typ", "") or ""),
        rank=str(detection_config.get("rank", "FSRQ") or "FSRQ"),
        sort=str(detection_config.get("sort", "desc") or "desc"),
        page=int(detection_config.get("page", -1) or -1),
    )

    if df is None or df.empty:
        return []
    return df.to_dict("records")


def normalize_fund_split_row(row, tracked_codes, start_date, end_date):
    """将原始行映射为标准企业行动事件。"""
    code = str(row.get("基金代码") or "").strip().zfill(6)
    if code not in tracked_codes:
        return None

    raw_date = str(row.get("拆分折算日") or "").strip()[:10]
    try:
        ex_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    if ex_date < start_date or ex_date > end_date:
        return None

    raw_type = str(row.get("拆分类型") or "").strip()
    action = TYPE_TO_ACTION.get(raw_type)
    if not action:
        return None

    try:
        ratio = float(row.get("拆分折算"))
    except (TypeError, ValueError):
        return None

    if ratio <= 0 or ratio == 1:
        return None

    fund_name = str(row.get("基金简称") or "").strip()
    return {
        "code": code,
        "fund_name": fund_name,
        "action": action,
        "ex_date": ex_date.strftime("%Y-%m-%d"),
        "ratio": ratio,
        "raw_type": raw_type,
        "source": "akshare.fund_cf_em",
        "note": f"自动识别到{raw_type}，每份变动比例 {ratio}",
    }


def detect_corporate_action_events(etf_codes, start_date, end_date, detection_config=None):
    """检测窗口内的份额变动事件，并按 ETF 代码聚合。"""
    tracked_codes = {str(code).zfill(6) for code in etf_codes}
    detection_config = detection_config or {}
    years = get_window_years(start_date, end_date)
    events_by_code = {}

    for year in years:
        rows = fetch_fund_split_rows(year, detection_config)
        logger.info("已拉取基金拆分数据", {"year": year, "row_count": len(rows)})

        for row in rows:
            normalized = normalize_fund_split_row(row, tracked_codes, start_date, end_date)
            if not normalized:
                continue

            code = normalized.pop("code")
            events_by_code.setdefault(code, []).append(normalized)

    for code, events in events_by_code.items():
        events.sort(key=lambda item: item["ex_date"])
        deduped = []
        seen = set()
        for event in events:
            key = (event["action"], event["ex_date"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)
        events_by_code[code] = deduped

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "window": {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "years": years,
        },
        "source": "akshare.fund_cf_em",
        "events_by_code": events_by_code,
    }

    logger.info("份额变动事件检测完成", {
        "tracked_etf_count": len(tracked_codes),
        "matched_etf_count": len(events_by_code),
        "event_count": sum(len(items) for items in events_by_code.values()),
    })
    return payload


def save_detected_corporate_action_payload(payload, output_path):
    """保存结构化份额变动事件文件。"""
    parent_dir = os.path.dirname(output_path)
    os.makedirs(parent_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    logger.info("份额变动事件已保存", {
        "file": output_path,
        "event_count": sum(len(items) for items in payload.get("events_by_code", {}).values()),
    })
    return output_path
