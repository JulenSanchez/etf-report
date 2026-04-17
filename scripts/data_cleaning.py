#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K 线数据清洗管线。

当前首个正式动作类型为“份额变动（如 1 拆 3）”，用于在生成日线数据后、
派生周线与指标前，统一清洗历史价格与成交量，避免把企业行动处理散落在图表补丁里。
"""

from copy import deepcopy

from logger import Logger


logger = Logger(name="data_cleaning", level="INFO", file_output=True)
SUPPORTED_SHARE_CHANGE_ACTIONS = {"share_split", "share_change"}


def normalize_corporate_action_events(events=None):
    """标准化企业行动事件配置。"""
    normalized = []

    for raw_event in events or []:
        action = (raw_event.get("action") or raw_event.get("type") or "share_split").strip()
        ex_date = str(raw_event.get("ex_date") or "").strip()[:10]

        try:
            ratio = float(raw_event.get("ratio", 1) or 1)
        except (TypeError, ValueError):
            logger.warn("忽略非法份额变动事件", {"event": raw_event, "reason": "ratio 不是数字"})
            continue

        if not ex_date or ratio <= 0 or ratio == 1:
            logger.warn("忽略无效份额变动事件", {"event": raw_event})
            continue

        if action not in SUPPORTED_SHARE_CHANGE_ACTIONS:
            logger.warn("忽略暂不支持的数据清洗动作", {"event": raw_event, "action": action})
            continue

        normalized.append({
            **raw_event,
            "action": action,
            "ex_date": ex_date,
            "ratio": ratio,
        })

    normalized.sort(key=lambda item: item["ex_date"])
    return normalized


def extract_close_price(kline_rows, index):
    """安全读取指定交易日的收盘价。"""
    if index < 0 or index >= len(kline_rows):
        return None
    row = kline_rows[index]
    if not isinstance(row, (list, tuple)) or len(row) < 2:
        return None
    try:
        return float(row[1])
    except (TypeError, ValueError):
        return None



def is_share_change_boundary(left_close, right_close, ratio, tolerance=0.12):
    """判断相邻两个交易日之间是否出现与份额变动比例相符的跳变。"""
    if left_close in (None, 0) or right_close in (None, 0) or ratio in (None, 0, 1):
        return False
    expected = ratio if ratio > 1 else 1 / ratio
    observed = (left_close / right_close) if ratio > 1 else (right_close / left_close)
    if observed <= 0 or expected <= 0:
        return False
    return abs(observed - expected) / expected <= tolerance



def resolve_share_change_effective_ex_date(event, dates, kline_rows):
    """将外部事件日期对齐到真正应停止复权的交易日。"""
    raw_ex_date = event["ex_date"]
    try:
        event_index = dates.index(raw_ex_date)
    except ValueError:
        return raw_ex_date

    current_close = extract_close_price(kline_rows, event_index)
    next_close = extract_close_price(kline_rows, event_index + 1)
    if next_close is not None and is_share_change_boundary(current_close, next_close, event["ratio"]):
        effective_ex_date = str(dates[event_index + 1]).strip()[:10]
        logger.info("份额变动边界命中，顺延生效日以覆盖变动前最后一天", {
            "raw_ex_date": raw_ex_date,
            "effective_ex_date": effective_ex_date,
            "ratio": event["ratio"],
        })
        return effective_ex_date

    return raw_ex_date



def apply_share_change_events(data, events=None):
    """对份额变动生效日前的历史价格/成交量做清洗。"""
    normalized_events = normalize_corporate_action_events(events)
    if not data or not normalized_events:
        return data

    adjusted = deepcopy(data)
    dates = adjusted.get("dates", [])
    kline_rows = adjusted.get("kline", [])
    volumes = adjusted.get("volumes") or []
    effective_events = sorted([
        {
            **event,
            "effective_ex_date": resolve_share_change_effective_ex_date(event, dates, kline_rows),
        }
        for event in normalized_events
    ], key=lambda item: (item["effective_ex_date"], item["ex_date"]))

    for idx, trade_date in enumerate(dates):
        trade_date_key = str(trade_date).strip()[:10]
        factor = 1.0

        for event in effective_events:
            if trade_date_key < event["effective_ex_date"]:
                factor *= event["ratio"]

        if factor == 1.0 or idx >= len(kline_rows):
            continue

        open_price, close_price, low_price, high_price = kline_rows[idx]
        kline_rows[idx] = [
            round(open_price / factor, 3),
            round(close_price / factor, 3),
            round(low_price / factor, 3),
            round(high_price / factor, 3),
        ]

        if idx < len(volumes):
            volumes[idx] = int(round(volumes[idx] * factor))

    if kline_rows:
        adjusted["latest_close"] = kline_rows[-1][1]
        if len(kline_rows) >= 2 and kline_rows[-2][1] != 0:
            prev_close = kline_rows[-2][1]
            adjusted["latest_change"] = round((adjusted["latest_close"] - prev_close) / prev_close * 100, 2)

    logger.info("已完成份额变动数据清洗", {
        "event_count": len(effective_events),
        "first_event": effective_events[0]["effective_ex_date"],
        "raw_first_event": normalized_events[0]["ex_date"],
    })
    return adjusted



def run_data_cleaning_pipeline(data, events=None):
    """运行 K 线数据清洗管线。"""
    normalized_events = normalize_corporate_action_events(events)
    if not normalized_events:
        return data

    cleaned = data
    share_change_events = [event for event in normalized_events if event["action"] in SUPPORTED_SHARE_CHANGE_ACTIONS]
    if share_change_events:
        cleaned = apply_share_change_events(cleaned, share_change_events)

    return cleaned
