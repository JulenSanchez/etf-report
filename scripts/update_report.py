#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF投资报告更新主控脚本

功能：一键执行完整的报告更新流程
触发词："更新今天的投资报告"

执行流程：
1. 获取K线数据（日线+周线+基准指数）
2. 计算MA均线（含预热）
3. 获取实时行情数据（ETF涨跌幅+成分股涨跌幅）
4. 更新HTML中的klineData和realtimeData数据
5. 更新HTML报告中的日期信息

使用方法：
    python update_report.py           # 执行完整更新

数据来源：
    全部使用新浪财经API（K线数据、实时行情数据同源）
"""

import subprocess
import sys
import os
import webbrowser
import time
import json
import argparse
import shutil
import tempfile
from datetime import datetime


from logger import Logger

from config_manager import get_config

# 工作目录
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(WORK_DIR)  # skill根目录
os.chdir(WORK_DIR)

# 配置管理器初始化
config = get_config()

# 从配置加载文件路径
files_config = config.get_files_config()
DATA_DIR = os.path.join(SKILL_DIR, files_config.get('data_dir', 'data'))
OUTPUTS_DIR = os.path.join(SKILL_DIR, files_config.get('outputs_dir', 'outputs'))
# HTML 文件在技能根目录
HTML_FILE = os.path.join(SKILL_DIR, files_config.get('html_file', 'index.html'))

# 日志初始化
logger = Logger(name="update_report", level="INFO", file_output=True)

# 记录配置加载信息
logger.info("配置已加载", {
    "data_dir": DATA_DIR,
    "outputs_dir": OUTPUTS_DIR
})


def prepare_publish_html_snapshot(source_html_file=None):
    """发布模式下复制临时 HTML 快照，避免污染源码工作区。"""
    html_source = source_html_file or HTML_FILE
    if not os.path.exists(html_source):
        raise FileNotFoundError(f"源 HTML 不存在: {html_source}")

    temp_dir = tempfile.mkdtemp(prefix="etf_publish_")
    temp_html_file = os.path.join(temp_dir, os.path.basename(html_source))
    shutil.copy2(html_source, temp_html_file)
    logger.info("发布模式已创建临时 HTML 快照", {
        "source_html": html_source,
        "temp_html": temp_html_file,
    })
    return temp_dir, temp_html_file


def cleanup_publish_html_snapshot(temp_dir):
    """清理发布模式生成的临时 HTML 快照目录。"""
    if not temp_dir:
        return

    shutil.rmtree(temp_dir, ignore_errors=True)
    logger.info("发布模式临时 HTML 快照已清理", {"temp_dir": temp_dir})


def run_kline_update():

    """执行K线数据更新"""
    logger.info("=" * 60)
    logger.info("Step 1: 获取K线数据并更新JS")
    logger.info("=" * 60)
    
    try:
        # 导入并执行fix_ma_and_benchmark模块
        import fix_ma_and_benchmark
        fix_ma_and_benchmark.main()
        return True
    except Exception as e:
        logger.error("K线数据更新失败", {"error": str(e)})
        import traceback
        traceback.print_exc()
        return False


def run_realtime_update():
    """执行实时行情数据更新"""
    logger.info("=" * 60)
    logger.info("Step 2: 获取实时行情数据（ETF涨跌幅+成分股涨跌幅）")
    logger.info("=" * 60)
    
    try:
        # 导入并执行realtime_data_updater模块
        import realtime_data_updater
        realtime_data_updater.main()
        return True
    except Exception as e:
        logger.error("实时数据更新失败", {"error": str(e)})
        import traceback
        traceback.print_exc()
        return False


def _replace_text_in_html(html_content, marker, old_pattern, replacement):
    """在 HTML 原始文本中定位并替换文本内容
    
    Args:
        html_content: HTML 原始文本
        marker: 定位锚点（如 "报告日期:"）
        old_pattern: 需要被替换的旧内容正则
        replacement: 替换后的内容
    
    Returns:
        (html_content, found): 更新后的内容和是否找到
    """
    import re as _re
    pos = html_content.find(marker)
    if pos == -1:
        return html_content, False
    
    # 在 marker 附近搜索旧模式
    search_start = max(0, pos - 200)
    search_end = min(len(html_content), pos + 200)
    region = html_content[search_start:search_end]
    
    match = _re.search(old_pattern, region)
    if match:
        old_text = match.group()
        abs_start = search_start + match.start()
        abs_end = search_start + match.end()
        html_content = html_content[:abs_start] + replacement + html_content[abs_end:]
        return html_content, True
    
    return html_content, False


def update_html_dates(html_file=None):
    """更新HTML报告中的日期信息（报告日期、数据截止、页脚生成时间）
    
    使用字符串定位替换，不经过 BS4 序列化，避免破坏 script 内容。
    """
    logger.info("=" * 60)
    logger.info("Step 3: 更新报告日期")
    logger.info("=" * 60)
    
    # 从配置加载文件路径和定位标记
    files_config = config.get_files_config()
    html_update_config = config.get_html_update_config()
    
    html_file = html_file or HTML_FILE
    kline_file = os.path.join(DATA_DIR, files_config.get('data_files', {}).get('kline', 'etf_full_kline_data.json'))

    
    # 加载定位标记和日期格式
    locators = html_update_config.get('locators', {})
    date_formats = html_update_config.get('date_formats', {})
    date_patterns = html_update_config.get('date_patterns', {})
    
    report_date_label = locators.get('report_date_label', '报告日期:')
    data_cutoff_label = locators.get('data_cutoff_label', '数据截止:')
    generation_time_label = locators.get('generation_time_label', '生成时间:')
    
    report_date_cn_format = date_formats.get('report_date_cn', '%Y年%m月%d日')
    iso_date_format = date_formats.get('iso_date', '%Y-%m-%d')
    
    report_date_pattern = date_patterns.get('report_date', r'\d{4}年\d{2}月\d{2}日')
    iso_date_pattern = date_patterns.get('iso_date', r'\d{4}-\d{2}-\d{2}')
    
    # 从K线数据中提取最新的日线日期作为"数据截止"日期
    data_date = None
    try:
        with open(kline_file, 'r', encoding='utf-8') as f:
            kline_data = json.load(f)
        for code, etf_data in kline_data.items():
            daily = etf_data.get('daily', {})
            dates = daily.get('dates', [])
            if dates:
                data_date = dates[-1]
                break
    except Exception as e:
        logger.warn("无法读取K线数据文件", {"error": str(e)})
    
    if not data_date:
        data_date = datetime.now().strftime(iso_date_format)
        logger.warn("使用当前日期作为数据截止日期", {"date": data_date})
    
    today = datetime.now()
    report_date_cn = today.strftime(report_date_cn_format)
    report_date_iso = today.strftime(iso_date_format)
    
    # 读取原始 HTML 文本
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    updated = False
    
    # 1. 更新"报告日期": 优先保留新的细粒度 ID，再回退到旧结构兼容替换
    html_content, found = _replace_element_by_id(
        html_content,
        "report-date-value",
        report_date_cn,
        class_name="text-blue",
    )
    if not found:
        html_content, found = _replace_text_in_html(
            html_content, report_date_label,
            r'<strong[^>]*>' + report_date_pattern + r'</strong>',
            f'<strong class="text-blue">{report_date_cn}</strong>'
        )
    if found:
        logger.info("报告日期更新成功", {"date": report_date_cn})
        updated = True
    
    # 2. 更新"数据截止": 优先保留新的细粒度 ID，再兼容旧纯文本结构
    html_content, found = _replace_element_by_id(
        html_content,
        "report-cutoff-value",
        data_date,
    )
    if not found:
        html_content, found = _replace_text_in_html(
            html_content, data_cutoff_label,
            data_cutoff_label + r'\s*' + iso_date_pattern,
            f'{data_cutoff_label} {data_date}'
        )
    if found:
        logger.info("数据截止更新成功", {"date": data_date})
        updated = True
    
    # 3. 更新页脚"生成时间": 生成时间: 2026-03-17
    html_content, found = _replace_text_in_html(
        html_content, generation_time_label,
        generation_time_label + r'\s*' + iso_date_pattern,
        f'{generation_time_label} {report_date_iso}'
    )
    if found:
        logger.info("页脚生成时间更新成功", {"time": report_date_iso})
        updated = True
    
    if updated:
        with logger.audit_operation("file_io", f"write {html_file}"):
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
        logger.info("日期更新完成")
    else:
        logger.warn("未找到需要更新的日期字段")
    
    return updated


def _replace_js_const_in_html(html_content, const_name, new_value_str):
    """在 HTML 原始文本中替换 const xxxData = {...}; 块，不经过 BS4 序列化
    
    使用位置定位：找到 const xxxData = 的位置，找到匹配的 }; 结尾，整体替换。
    这避免了 BS4 str(soup) 丢失 script 中其他 JS 代码的问题。
    """
    marker = f'const {const_name} = '
    start = html_content.find(marker)
    if start == -1:
        return html_content, False
    
    # 从 = 后面找到 { 的位置
    brace_start = html_content.find('{', start)
    if brace_start == -1:
        return html_content, False
    
    # 用括号深度匹配找到 }; 结尾
    depth = 0
    i = brace_start
    while i < len(html_content):
        ch = html_content[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                # 找到匹配的 }，检查后面是否有 ;
                end = i + 1
                if end < len(html_content) and html_content[end] == ';':
                    end += 1
                new_section = f'{new_value_str};'
                html_content = html_content[:start] + new_section + html_content[end:]
                return html_content, True
        i += 1
    
    return html_content, False




def write_runtime_payload_file(data_dir, kline_data, realtime_data):
    """生成外置运行时载荷，兼容 file:// 与 http 预览。"""
    payload_file = os.path.join(data_dir, "runtime_payload.js")
    payload = {
        "generatedAt": datetime.now().isoformat(),
        "klineData": kline_data,
        "realtimeData": realtime_data,
    }
    content = 'window.__ETF_REPORT_RUNTIME__ = ' + json.dumps(payload, ensure_ascii=False, indent=2) + ';\n'
    with logger.audit_operation("file_io", f"write {payload_file}"):
        with open(payload_file, 'w', encoding='utf-8') as f:
            f.write(content)
    logger.info("运行时载荷已写入", {"file": payload_file})
    return payload_file



def _to_number(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric



def _get_close_series(kline_rows):
    closes = []
    for row in kline_rows or []:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            close_value = _to_number(row[1])
            if close_value is not None:
                closes.append(close_value)
    return closes



def _get_daily_close_series(kline_entry):
    daily_entry = (kline_entry or {}).get("daily") or {}
    return _get_close_series(daily_entry.get("kline") or [])



def _get_latest_daily_close(kline_entry):
    daily_entry = (kline_entry or {}).get("daily") or {}
    latest_close = _to_number(daily_entry.get("latest_close"))
    if latest_close is not None:
        return latest_close
    closes = _get_daily_close_series(kline_entry)
    return closes[-1] if closes else None



def _get_latest_daily_change(kline_entry):
    daily_entry = (kline_entry or {}).get("daily") or {}
    latest_change = _to_number(daily_entry.get("latest_change"))
    if latest_change is not None:
        return latest_change
    return _get_return_from_series(_get_daily_close_series(kline_entry), 1)



def _get_weekly_close_series(kline_entry):

    weekly_entry = (kline_entry or {}).get("weekly") or {}
    return _get_close_series(weekly_entry.get("kline") or [])



def _get_return_from_series(series, lookback_points):
    if not isinstance(series, list) or len(series) < 2:
        return None
    end_value = _to_number(series[-1])
    if end_value is None:
        return None
    safe_lookback = max(1, min(lookback_points, len(series) - 1))
    start_value = _to_number(series[-1 - safe_lookback])
    if start_value in (None, 0):
        return None
    return ((end_value - start_value) / start_value) * 100



def _format_percent(value):
    numeric = _to_number(value)
    if numeric is None:
        return "--"
    if numeric > 0:
        return f"+{numeric:.2f}%"
    if numeric < 0:
        return f"{numeric:.2f}%"
    return "0.00%"



def _format_price(value):
    numeric = _to_number(value)
    if numeric is None:
        return "--"
    digits = 2 if numeric >= 100 else 4
    return f"{numeric:.{digits}f}元"



def _get_trend_class(value):

    numeric = _to_number(value)
    if numeric is None:
        return "text-amber"
    if numeric > 0:
        return "text-green"
    if numeric < 0:
        return "text-red"
    return "text-amber"



def _get_overview_change_class(value):
    numeric = _to_number(value)
    if numeric is None:
        return "etf-change"
    if numeric > 0:
        return "etf-change positive"
    if numeric < 0:
        return "etf-change negative"
    return "etf-change"



def _format_weight_percent(value):
    numeric = _to_number(value)
    if numeric is None:
        return "--"
    return f"{numeric:.2f}%"



def _get_text_value_class(value):
    numeric = _to_number(value)
    if numeric is None:
        return "text-amber text-bold"
    if numeric > 0:
        return "text-green text-bold"
    if numeric < 0:
        return "text-red text-bold"
    return "text-amber text-bold"



def _get_stat_value_class(value):
    numeric = _to_number(value)
    if numeric is None:
        return "stat-value text-amber"
    if numeric > 0:
        return "stat-value text-green"
    if numeric < 0:
        return "stat-value text-red"
    return "stat-value text-amber"



def _format_runtime_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return "--"

    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value.strip().replace("T", " ")[:19]



def _build_fund_flow_snapshot(kline_data, realtime_data):
    etf_entries = []
    holding_map = {}
    latest_timestamp_text = "--"
    latest_timestamp_value = None

    for code, realtime_entry in (realtime_data or {}).items():
        realtime_entry = realtime_entry or {}
        kline_entry = (kline_data or {}).get(code) or {}
        etf_name = str(realtime_entry.get("name") or kline_entry.get("name") or code).strip()
        etf_change = _to_number(realtime_entry.get("etf_change"))
        if etf_change is not None:
            etf_entries.append({"code": code, "name": etf_name, "change": etf_change})

        raw_timestamp = realtime_entry.get("timestamp")
        if isinstance(raw_timestamp, str) and raw_timestamp.strip():
            normalized = raw_timestamp.strip().replace("Z", "+00:00")
            try:
                parsed_timestamp = datetime.fromisoformat(normalized)
            except ValueError:
                parsed_timestamp = None
            if parsed_timestamp and (latest_timestamp_value is None or parsed_timestamp > latest_timestamp_value):
                latest_timestamp_value = parsed_timestamp
                latest_timestamp_text = parsed_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            elif latest_timestamp_text == "--":
                latest_timestamp_text = _format_runtime_timestamp(raw_timestamp)

        for holding in realtime_entry.get("holdings") or []:
            holding_name = str((holding or {}).get("name") or "").strip()
            holding_change = _to_number((holding or {}).get("change"))
            if not holding_name or holding_change is None:
                continue

            ratio = _to_number((holding or {}).get("ratio")) or 0.0
            aggregated = holding_map.setdefault(
                holding_name,
                {"name": holding_name, "ratio": 0.0, "change": holding_change},
            )
            aggregated["ratio"] += ratio
            if aggregated.get("change") is None:
                aggregated["change"] = holding_change

    etf_entries.sort(key=lambda item: (item["change"], item["name"]), reverse=True)
    leader = etf_entries[0] if etf_entries else {"name": "--", "change": None}
    laggard = min(etf_entries, key=lambda item: (item["change"], item["name"])) if etf_entries else {"name": "--", "change": None}

    average_change = None
    if etf_entries:
        average_change = sum(item["change"] for item in etf_entries) / len(etf_entries)

    positive_count = sum(1 for item in etf_entries if item["change"] > 0)
    negative_count = sum(1 for item in etf_entries if item["change"] < 0)
    flat_count = sum(1 for item in etf_entries if item["change"] == 0)

    holding_entries = list(holding_map.values())
    leaders = sorted(
        holding_entries,
        key=lambda item: (item["change"], item["ratio"], item["name"]),
        reverse=True,
    )[:5]
    laggards = sorted(
        holding_entries,
        key=lambda item: (item["change"], -item["ratio"], item["name"]),
    )[:5]

    return {
        "source": "新浪财经实时行情 + 主流程K线快照",
        "updated_at": latest_timestamp_text,
        "leader": leader,
        "laggard": laggard,
        "average_change": average_change,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "flat_count": flat_count,
        "etf_count": len(etf_entries),
        "leaders": leaders,
        "laggards": laggards,
    }



def _sync_ranked_holding_table(html_content, table_prefix, rows):
    visible_rows = list(rows or [])[:5]
    while len(visible_rows) < 5:
        visible_rows.append({"name": "--", "ratio": None, "change": None})

    for index, row in enumerate(visible_rows, start=1):
        html_content, _ = _replace_element_by_id(html_content, f"{table_prefix}-name-{index}", row.get("name") or "--")
        html_content, _ = _replace_element_by_id(html_content, f"{table_prefix}-weight-{index}", _format_weight_percent(row.get("ratio")))
        html_content, _ = _replace_element_by_id(
            html_content,
            f"{table_prefix}-change-{index}",
            _format_percent(row.get("change")),
            class_name=_get_text_value_class(row.get("change")),
        )

    return html_content



def sync_fund_flow_section_html(html_content, kline_data, realtime_data, data_cutoff_date=None):
    snapshot = _build_fund_flow_snapshot(kline_data, realtime_data)
    updated_at = snapshot.get("updated_at") or "--"
    note = f'数据截止：{data_cutoff_date or "--"} · 行情快照：{updated_at}'
    breadth_value = f'{snapshot.get("positive_count", 0)} / {snapshot.get("negative_count", 0)} / {snapshot.get("flat_count", 0)}'
    average_name = f'{snapshot.get("etf_count", 0)}支ETF均值' if snapshot.get("etf_count") else '暂无可用行情'

    html_content, _ = _replace_element_by_id(html_content, "fund-flow-title", "💰 市场热度与轮动")
    html_content, _ = _replace_element_by_id(html_content, "fund-flow-source-value", snapshot.get("source") or "--")
    html_content, _ = _replace_element_by_id(html_content, "fund-flow-updated-value", updated_at)
    html_content, _ = _replace_element_by_id(html_content, "market-rotation-card-title", "ETF日内轮动")
    html_content, _ = _replace_element_by_id(html_content, "market-rotation-stat-leader-name", snapshot.get("leader", {}).get("name") or "--")
    html_content, _ = _replace_element_by_id(
        html_content,
        "market-rotation-stat-leader-value",
        _format_percent(snapshot.get("leader", {}).get("change")),
        class_name=_get_stat_value_class(snapshot.get("leader", {}).get("change")),
    )
    html_content, _ = _replace_element_by_id(html_content, "market-rotation-stat-laggard-name", snapshot.get("laggard", {}).get("name") or "--")
    html_content, _ = _replace_element_by_id(
        html_content,
        "market-rotation-stat-laggard-value",
        _format_percent(snapshot.get("laggard", {}).get("change")),
        class_name=_get_stat_value_class(snapshot.get("laggard", {}).get("change")),
    )
    html_content, _ = _replace_element_by_id(html_content, "market-rotation-stat-average-name", average_name)
    html_content, _ = _replace_element_by_id(
        html_content,
        "market-rotation-stat-average-value",
        _format_percent(snapshot.get("average_change")),
        class_name=_get_stat_value_class(snapshot.get("average_change")),
    )
    html_content, _ = _replace_element_by_id(html_content, "market-rotation-stat-breadth-name", "ETF日内分布")
    html_content, _ = _replace_element_by_id(
        html_content,
        "market-rotation-stat-breadth-value",
        breadth_value,
        class_name="stat-value text-blue",
    )
    html_content, _ = _replace_element_by_id(html_content, "market-rotation-note", note)
    html_content = _sync_ranked_holding_table(html_content, "leaders-top5-table", snapshot.get("leaders"))
    html_content = _sync_ranked_holding_table(html_content, "laggards-top5-table", snapshot.get("laggards"))
    return html_content



def _replace_element_by_id(html_content, element_id, new_inner_html, class_name=None):
    import re as _re

    pattern = rf'(<(?P<tag>\w+)(?=[^>]*\bid="{_re.escape(element_id)}")[^>]*>)(?P<inner>[\s\S]*?)(</(?P=tag)>)'
    match = _re.search(pattern, html_content)
    if not match:
        return html_content, False

    opening_tag = match.group(1)
    if class_name:
        if 'class="' in opening_tag:
            opening_tag = _re.sub(r'class="[^"]*"', f'class="{class_name}"', opening_tag, count=1)
        else:
            opening_tag = opening_tag[:-1] + f' class="{class_name}">'

    replacement = f'{opening_tag}{new_inner_html}{match.group(4)}'
    updated = html_content[:match.start()] + replacement + html_content[match.end():]
    return updated, True



def _get_editorial_content_path():
    files_config = config.get_files_config()
    editorial_filename = files_config.get('editorial_content_file', 'editorial_content.yaml')
    return os.path.join(SKILL_DIR, 'config', editorial_filename)



def _extract_latest_kline_date(kline_data):
    for _code, etf_data in (kline_data or {}).items():
        daily = (etf_data or {}).get('daily', {})
        dates = daily.get('dates', [])
        if dates:
            return dates[-1]
    return None



def _parse_iso_date(date_str):
    if not date_str or not isinstance(date_str, str):
        return None

    normalized = date_str.strip()[:10]
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None



def _resolve_editorial_content_date(editorial_content, card_content):
    if isinstance(card_content, dict):
        content_date = card_content.get("content_date")
        if isinstance(content_date, str) and content_date.strip():
            return content_date.strip()

    global_date = (editorial_content or {}).get("content_date")
    if isinstance(global_date, str) and global_date.strip():
        return global_date.strip()

    return None



def _resolve_editorial_entry_html(entry):
    if isinstance(entry, dict):
        for key in ("html", "content", "text"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    if isinstance(entry, str):
        return entry.strip()

    return ""



def _truncate_inline_editorial_text(item_html, max_chars=44):
    if not isinstance(item_html, str):
        return ""

    normalized = item_html.strip()
    if len(normalized) <= max_chars:
        return normalized

    if "<" in normalized and ">" in normalized:
        return normalized

    truncated = normalized[: max_chars - 1].rstrip("，,、；;：: ")
    return f"{truncated}…"



def _build_editorial_entry_context(card_content, entry):
    context = {}

    if isinstance(card_content, dict):
        policy = card_content.get("freshness_policy")
        if isinstance(policy, str) and policy.strip():
            context["freshness_policy"] = policy.strip()

        content_date = card_content.get("content_date")
        if isinstance(content_date, str) and content_date.strip():
            context["content_date"] = content_date.strip()

    if isinstance(entry, dict):
        entry_policy = entry.get("freshness_policy")
        if isinstance(entry_policy, str) and entry_policy.strip():
            context["freshness_policy"] = entry_policy.strip()

        entry_date = entry.get("content_date")
        if isinstance(entry_date, str) and entry_date.strip():
            context["content_date"] = entry_date.strip()

    return context



def _evaluate_editorial_freshness(editorial_content, card_content, data_cutoff_date):
    policy = ((card_content or {}).get("freshness_policy") or (editorial_content or {}).get("freshness_policy") or "sticky").strip()
    content_date = _resolve_editorial_content_date(editorial_content, card_content)
    content_dt = _parse_iso_date(content_date)
    cutoff_dt = _parse_iso_date(data_cutoff_date)
    delta_days = None if not content_dt or not cutoff_dt else abs((cutoff_dt - content_dt).days)

    severity = "PASS"
    stale = False

    if not content_date:
        severity = "FAIL" if policy == "daily" else "WARN"
        stale = True
    elif policy in {"daily", "manual_daily"}:
        stale = delta_days is None or delta_days != 0
        severity = "FAIL" if policy == "daily" and stale else ("WARN" if stale else "PASS")
    elif policy == "weekly":
        stale = delta_days is None or delta_days > 7
        severity = "WARN" if stale else "PASS"
    else:
        stale = False
        severity = "PASS"

    if not content_date:
        message = f"观点日期：未标注 · {policy}"
    elif policy == "daily":
        message = f"观点日期：{content_date} · {'严格日更待修正' if stale else '严格日更'}"
    elif policy == "manual_daily":
        message = f"观点日期：{content_date} · {'待按数据截止日复核' if stale else '已按数据截止日复核'}"
    elif policy == "weekly":
        message = f"观点日期：{content_date} · {'周更观点待复核' if stale else '周更观点'}"
    else:
        reuse_hint = '沿用上一版编辑内容' if data_cutoff_date and content_date != data_cutoff_date else '编辑态内容'
        message = f"观点日期：{content_date} · {reuse_hint}"

    css_class = "editorial-meta"
    if severity != "PASS":
        css_class += " editorial-meta--warn"

    return {
        "policy": policy,
        "content_date": content_date,
        "data_cutoff_date": data_cutoff_date,
        "delta_days": delta_days,
        "severity": severity,
        "is_stale": stale,
        "message": message,
        "css_class": css_class,
    }



def _render_editorial_date_html(date_element_id, freshness):
    date_text = freshness.get("content_date") or freshness.get("data_cutoff_date") or "未标注"
    css_class = "editorial-date"
    if freshness.get("severity") != "PASS":
        css_class += " editorial-date--warn"
    return f'<span class="{css_class}" id="{date_element_id}">{date_text}</span>'



def load_editorial_content():
    editorial_path = _get_editorial_content_path()
    if not os.path.exists(editorial_path):
        logger.warn("未找到解释层内容配置，沿用当前 HTML 内联内容", {"file": editorial_path})
        return None

    editorial_content = config.get_editorial_content()
    if not editorial_content:
        logger.warn("解释层内容配置为空，沿用当前 HTML 内联内容", {"file": editorial_path})
        return None

    logger.info("解释层内容配置已加载", {
        "file": editorial_path,
        "content_date": editorial_content.get("content_date"),
        "etf_card_groups": len(editorial_content.get("etf_cards") or {}),
        "macro_cards": len(editorial_content.get("macro_cards") or {}),
    })
    return editorial_content



def _remove_element_by_id(html_content, element_id):
    import re as _re

    pattern = rf'<(?P<tag>\w+)(?=[^>]*\bid="{_re.escape(element_id)}")[^>]*>[\s\S]*?</(?P=tag)>'
    updated, count = _re.subn(pattern, '', html_content, count=1)
    return updated, count > 0



def _render_macro_card_inner_html(card_id, card_content, editorial_content, data_cutoff_date):
    title = card_content.get("title") or ""
    items = card_content.get("items") or []
    freshness = _evaluate_editorial_freshness(editorial_content, card_content, data_cutoff_date)
    rendered_items = []

    for index, item in enumerate(items, start=1):
        item_html = _truncate_inline_editorial_text(_resolve_editorial_entry_html(item))
        if not item_html:
            continue
        item_context = _build_editorial_entry_context(card_content, item)
        item_freshness = _evaluate_editorial_freshness(editorial_content, item_context, data_cutoff_date)
        date_html = _render_editorial_date_html(f"editorial-date-{card_id}-{index}", item_freshness)
        rendered_items.append(
            f'<li id="{card_id}-item-{index}"><span class="macro-item-text" id="{card_id}-text-{index}"><span class="macro-item-content">{item_html}</span>{date_html}</span></li>'
        )

    list_html = ''.join(rendered_items)
    return f'<h3 id="{card_id}-title">{title}</h3><ul id="{card_id}-list">{list_html}</ul>', freshness




def sync_editorial_content_html(html_content, editorial_content, data_cutoff_date=None):
    if not editorial_content:
        return html_content

    updated_targets = []
    missing_targets = []
    freshness_summary = {"PASS": 0, "WARN": 0, "FAIL": 0}
    freshness_alerts = []

    for code, card_group in (editorial_content.get("etf_cards") or {}).items():
        group = card_group or {}
        research_cards = group.get("research_cards") or []
        group_freshness = _evaluate_editorial_freshness(editorial_content, group, data_cutoff_date)
        freshness_summary[group_freshness["severity"]] += 1
        if group_freshness["severity"] != "PASS":
            freshness_alerts.append({"target": f"research-{code}", "message": group_freshness["message"]})

        html_content, removed = _remove_element_by_id(html_content, f"research-meta-{code}")
        if removed:
            updated_targets.append(f"research-meta-{code}:removed")

        for index, card_entry in enumerate(research_cards, start=1):
            card_html = _resolve_editorial_entry_html(card_entry)
            target_id = f"report-card-content-{code}-{index}"
            entry_context = _build_editorial_entry_context(group, card_entry)
            entry_freshness = _evaluate_editorial_freshness(editorial_content, entry_context, data_cutoff_date)
            rendered_html = f'<span class="report-card-text">{card_html}</span>{_render_editorial_date_html(f"research-date-{code}-{index}", entry_freshness)}'
            html_content, found = _replace_element_by_id(html_content, target_id, rendered_html)
            if found:
                updated_targets.append(target_id)
            else:
                missing_targets.append(target_id)

    for card_id, card_content in (editorial_content.get("macro_cards") or {}).items():
        rendered_html, freshness = _render_macro_card_inner_html(card_id, card_content or {}, editorial_content, data_cutoff_date)
        freshness_summary[freshness["severity"]] += 1
        if freshness["severity"] != "PASS":
            freshness_alerts.append({"target": card_id, "message": freshness["message"]})

        html_content, removed = _remove_element_by_id(html_content, f"editorial-meta-{card_id}")
        if removed:
            updated_targets.append(f"editorial-meta-{card_id}:removed")

        html_content, found = _replace_element_by_id(html_content, card_id, rendered_html)
        if found:
            updated_targets.append(card_id)
        else:
            missing_targets.append(card_id)

    logger.info("解释层内容已同步", {
        "updated_count": len(updated_targets),
        "missing_count": len(missing_targets),
        "content_date": editorial_content.get("content_date"),
        "data_cutoff_date": data_cutoff_date,
        "freshness_pass": freshness_summary["PASS"],
        "freshness_warn": freshness_summary["WARN"],
        "freshness_fail": freshness_summary["FAIL"],
    })
    if missing_targets:
        logger.warn("部分解释层内容目标未命中", {"targets": missing_targets[:10]})
    if freshness_alerts:
        logger.warn("解释层内容鲜度提醒", {"targets": freshness_alerts[:10]})

    return html_content




def sync_detail_panel_snapshot_html(html_content, kline_data, realtime_data):

    """把详情页首屏静态值同步到数据截止日口径，避免盘中实时价污染报告。"""
    updated_count = 0

    for code, kline_entry in (kline_data or {}).items():
        daily_change = _get_latest_daily_change(kline_entry)
        latest_close = _get_latest_daily_close(kline_entry)
        daily_close_series = _get_daily_close_series(kline_entry)
        performance_values = [
            _get_return_from_series(daily_close_series, 20),
            _get_return_from_series(daily_close_series, 59),
            _get_return_from_series(_get_weekly_close_series(kline_entry), 26),
            _get_return_from_series(_get_weekly_close_series(kline_entry), 51),
        ]

        html_content, found_label = _replace_element_by_id(
            html_content,
            f"latest-nav-label-{code}",
            "最新收盘价",
        )
        html_content, found_price = _replace_element_by_id(
            html_content,
            f"latest-nav-value-{code}",
            _format_price(latest_close),
        )

        html_content, found_daily = _replace_element_by_id(
            html_content,
            f"daily-change-value-{code}",
            _format_percent(daily_change),
            class_name=f"info-value {_get_trend_class(daily_change)}",
        )

        headers = ['近1月', '近3月', '近6月', '近1年']
        cells = []
        for value in performance_values:
            class_name = '' if value is None else ('positive' if value >= 0 else 'negative')
            class_attr = f' class="{class_name}"' if class_name else ''
            cells.append(f'<td{class_attr}>{_format_percent(value)}</td>')
        performance_html = '<tr>' + ''.join(f'<th>{label}</th>' for label in headers) + '</tr><tr>' + ''.join(cells) + '</tr>'
        html_content, found_perf = _replace_element_by_id(
            html_content,
            f"performance-table-{code}",
            performance_html,
        )

        overview_three_month_return = performance_values[1]
        html_content, found_overview_change = _replace_element_by_id(
            html_content,
            f"overview-card-{code}-change",
            _format_percent(overview_three_month_return),
            class_name=_get_overview_change_class(overview_three_month_return),
        )

        if found_label or found_price or found_daily or found_perf or found_overview_change:
            updated_count += 1

    logger.info("详情页静态快照已同步", {"etf_count": updated_count, "basis": "latest_close"})
    return html_content




def update_html_data(html_file=None):



    """更新HTML中的klineData和realtimeData数据
    
    使用字符串直接替换（不经过 BS4 序列化），避免 BS4 破坏 script 内容。
    """
    logger.info("=" * 60)
    logger.info("Step 3.5: 更新HTML中的数据（K线+实时行情）")
    logger.info("=" * 60)
    
    # 从配置加载文件路径
    files_config = config.get_files_config()
    html_update_config = config.get_html_update_config()
    
    html_file = HTML_FILE  # 使用根目录的 index.html
    kline_file = os.path.join(DATA_DIR, files_config.get('data_files', {}).get('kline', 'etf_full_kline_data.json'))
    realtime_file = os.path.join(DATA_DIR, files_config.get('data_files', {}).get('realtime', 'etf_realtime_data.json'))
    
    # 加载HTML定位标记
    locators = html_update_config.get('locators', {})
    kline_const = locators.get('kline_const', 'const klineData = ')
    realtime_const = locators.get('realtime_const', 'const realtimeData = ')
    
    kline_data = None
    realtime_data = None
    
    try:
        with open(kline_file, 'r', encoding='utf-8') as f:
            kline_data = json.load(f)
        data_cutoff_date = _extract_latest_kline_date(kline_data)
        logger.info("读取K线数据成功", {"file": kline_file, "data_cutoff_date": data_cutoff_date})
    except Exception as e:
        logger.error("无法读取K线数据", {"error": str(e), "file": kline_file})
        return False

    
    try:
        with open(realtime_file, 'r', encoding='utf-8') as f:
            realtime_data = json.load(f)
        logger.info("读取实时行情数据成功", {"file": realtime_file})
    except Exception as e:
        logger.error("无法读取实时行情数据", {"error": str(e), "file": realtime_file})
        return False
    
    try:
        write_runtime_payload_file(DATA_DIR, kline_data, realtime_data)
    except Exception as e:
        logger.error("生成运行时载荷失败", {"error": str(e)})
        return False

    # 读取 HTML 原始文本
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        logger.error("无法读取HTML文件", {"error": str(e), "file": html_file})
        return False

    
    # 1. 更新 klineData — 用字符串替换
    try:
        kline_json_str = json.dumps(kline_data, ensure_ascii=False, indent=8)
        new_kline_section = f'{kline_const}{kline_json_str}'
        # 提取const名称用于替换
        const_name = kline_const.replace('const ', '').replace(' = ', '').strip()
        html_content, found = _replace_js_const_in_html(html_content, const_name, new_kline_section)
        if found:
            logger.info("更新klineData成功", {"etf_count": 6, "data_type": "K线数据"})
        else:
            logger.error("未找到klineData段落", {"file": html_file, "const": const_name})
            return False
    except Exception as e:
        logger.error("更新klineData失败", {"error": str(e)})
        import traceback
        traceback.print_exc()
        return False
    
    # 2. 更新 realtimeData — 用字符串替换并强校验
    try:
        realtime_json_str = json.dumps(realtime_data, ensure_ascii=False, indent=8)
        new_realtime_section = f'{realtime_const}{realtime_json_str}'
        # 提取const名称用于替换
        const_name = realtime_const.replace('const ', '').replace(' = ', '').strip()
        html_content, found = _replace_js_const_in_html(html_content, const_name, new_realtime_section)
        if found:
            logger.info("更新realtimeData成功", {"data_type": "实时行情数据"})
        else:
            logger.error("未找到realtimeData段落", {"file": html_file, "const": const_name})
            return False
    except Exception as e:
        logger.error("更新realtimeData失败", {"error": str(e)})
        import traceback
        traceback.print_exc()
        return False
    
    try:
        html_content = sync_detail_panel_snapshot_html(html_content, kline_data, realtime_data)
    except Exception as e:
        logger.error("同步详情页静态快照失败", {"error": str(e)})
        return False

    try:
        html_content = sync_fund_flow_section_html(html_content, kline_data, realtime_data, data_cutoff_date=data_cutoff_date)
    except Exception as e:
        logger.error("同步市场热度模块失败", {"error": str(e)})
        return False

    try:
        editorial_content = load_editorial_content()
        html_content = sync_editorial_content_html(html_content, editorial_content, data_cutoff_date=data_cutoff_date)
    except Exception as e:
        logger.error("同步解释层内容失败", {"error": str(e), "file": _get_editorial_content_path()})
        return False


    # 写回 HTML（直接写字符串，不经过 BS4）

    try:
        with logger.audit_operation("file_io", f"write {html_file}"):
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

        file_size = os.path.getsize(html_file)
        logger.audit("file_io", f"HTML data updated: {html_file}", extra={"file_size_bytes": file_size})
        logger.info("HTML数据更新完成")
        return True
    except Exception as e:
        logger.error("写入HTML失败", {"error": str(e), "file": html_file})
        return False


def verify_output_files(html_file=None):
    """验证输出文件"""

    logger.info("=" * 60)
    logger.info("Step 4: 验证输出文件")
    logger.info("=" * 60)
    
    # 从配置加载文件配置
    files_config = config.get_files_config()
    data_files = files_config.get('data_files', {})
    html_file = html_file or HTML_FILE
    html_file_name = os.path.basename(html_file)
    required_files = [
        (os.path.join(DATA_DIR, data_files.get('kline', 'etf_full_kline_data.json')), data_files.get('kline', 'etf_full_kline_data.json')),
        (os.path.join(DATA_DIR, data_files.get('realtime', 'etf_realtime_data.json')), data_files.get('realtime', 'etf_realtime_data.json')),
        (html_file, html_file_name),
    ]

    
    all_exist = True
    for path, name in required_files:
        if os.path.exists(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            logger.info("文件验证成功", {
                "name": name,
                "path": path,
                "modified_time": mtime.strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            logger.warn("文件缺失", {"name": name, "path": path})
            all_exist = False
    
    return all_exist

def print_summary(html_file=None, source_html_protected=False):
    """打印总结信息"""
    logger.info("=" * 60)
    logger.info("更新完成")
    logger.info("=" * 60)
    
    # 从配置加载消息提示
    messages = config._config.get('messages', {})
    active_html_file = html_file or HTML_FILE
    local_preview = f"file:///{HTML_FILE.replace(os.sep, '/')}"
    html_output_line = f"  - {os.path.basename(HTML_FILE)}  (综合报告，根目录主文件)"
    protection_note = ""

    if source_html_protected and os.path.abspath(active_html_file) != os.path.abspath(HTML_FILE):
        html_output_line = "  - 临时 HTML 快照  (仅用于发布，不回写源码根目录 index.html)"
        protection_note = "\n  - 发布模式保护：根目录 index.html 保持不变，Pages 使用临时 HTML 快照\n"
    
    summary = f"""
报告已更新完成！

输出文件:
  - data/etf_full_kline_data.json  (K线数据)
  - data/etf_realtime_data.json    (实时行情数据)
{html_output_line}

本地预览:
  {local_preview}

数据来源:
  - {messages.get('data_source', 'K线/实时行情：新浪财经API')}

注意事项:
  - {messages.get('update_timing', '建议在交易日收盘后(15:00之后)执行更新')}
  - {messages.get('ma_warmup_note', 'MA均线从第一天即有完整数据(已预热)')}
  - {messages.get('realtime_data_note', 'ETF涨跌幅和成分股涨跌幅为实时数据')}{protection_note}
"""
    logger.info("完成总结", {"summary": summary})




def main(publish: bool = False):
    """主函数
    
    执行以下步骤：
    1. 获取K线数据并更新
    2. 获取实时行情数据并更新
    3. 更新HTML中的数据（klineData + realtimeData）
    4. 更新报告日期
    5. 验证输出文件
    6. HTML 完整性验证（REQ-102）
    7. [发布模式] 企微通知推送
    8. [发布模式] GitHub Pages 部署
    """
    mode_label = "发布模式" if publish else "开发模式"
    logger.info("=" * 60)
    logger.info(f"ETF投资报告更新 - {datetime.now().strftime('%Y-%m-%d')} [{mode_label}]")
    logger.info("=" * 60)

    working_html_file = HTML_FILE
    publish_temp_dir = None
    if publish:
        try:
            publish_temp_dir, working_html_file = prepare_publish_html_snapshot()
        except Exception as e:
            logger.error("创建发布临时 HTML 快照失败", {"error": str(e), "source_html": HTML_FILE})
            return False
    
    logger.info("工作环境信息", {
        "work_dir": WORK_DIR,
        "start_time": datetime.now().strftime('%H:%M:%S'),
        "publish": publish,
        "html_target": working_html_file,
    })
    
    # REQ-103: 事务管理 — 更新 HTML 前创建备份
    from transaction import TransactionManager
    tx = TransactionManager(SKILL_DIR)
    backup_path = tx.backup()
    
    try:
        # Step 1: 更新K线数据
        if not run_kline_update():
            logger.error("K线数据更新失败，流程终止")
            return False
        
        # Step 2: 更新实时行情数据
        if not run_realtime_update():
            logger.warn("实时数据更新失败，继续执行")
        
        # Step 3: 更新HTML中的数据
        if not update_html_data(html_file=working_html_file):
            logger.error("HTML数据注入失败，流程终止")
            return False
        
        # Step 4: 更新报告日期
        update_html_dates(html_file=working_html_file)

        
        # Step 5: 验证输出文件
        if not verify_output_files(html_file=working_html_file):
            logger.warn("部分文件缺失，请检查")
        
        # Step 6: HTML 完整性验证（REQ-102）
        logger.info("=" * 60)
        logger.info("Step 5: HTML 完整性验证")
        logger.info("=" * 60)
        try:
            from verify_html_integrity import verify_html_integrity, print_report
            html_path = working_html_file
            result = verify_html_integrity(html_path)
            print_report(result, html_path)
            
            if not result["passed"]:
                logger.warn("HTML完整性验证失败，正在回滚")
                tx.restore(backup_path)
                return False
        except ImportError:
            logger.info("verify_html_integrity 模块未找到，跳过验证")
        
        # 清理旧备份
        tx.cleanup()
        
        # Step 7: 执行系统健康检查（REQ-106）
        logger.info("=" * 60)
        logger.info("Step 6: 执行系统健康检查")
        logger.info("=" * 60)
        try:
            import health_check
            if os.path.abspath(working_html_file) != os.path.abspath(HTML_FILE):
                health_check.HTML_FILE = working_html_file
            health_check_results = health_check.run_all_checks()
            
            # 统计检查结果
            total = len(health_check_results)
            passed = sum(1 for r in health_check_results if r.status == "PASS")
            warnings = sum(1 for r in health_check_results if r.status == "WARN")
            failed = sum(1 for r in health_check_results if r.status == "FAIL")
            
            logger.info("健康检查完成", {
                "total": total,
                "passed": passed,
                "warnings": warnings,
                "failed": failed
            })
            
            if failed > 0:
                logger.warn("健康检查发现问题，请查看报告")
            elif warnings > 0:
                logger.warn("健康检查有若干警告，但不影响功能")
            else:
                logger.info("系统健康状态: 正常")
        except ImportError:
            logger.info("health_check 模块未找到，跳过健康检查")
        except Exception as e:
            logger.warn("执行健康检查时出错", {"error": str(e)})
        
        # ---- 发布模式专属步骤 ----
        if publish:
            # Step 7: 企微通知推送
            try:
                import notifier
                notifier.main(DATA_DIR)
            except ImportError:
                logger.warn("notifier 模块未找到，跳过企微通知")
            except Exception as e:
                logger.error("企微通知失败，不阻塞后续步骤", {"error": str(e)})
            
            # Step 8: GitHub Pages 部署
            try:
                import deployer
                deployer.main(SKILL_DIR, html_source_path=working_html_file)
            except ImportError:
                logger.warn("deployer 模块未找到，跳过 GitHub 部署")
            except Exception as e:
                logger.error("GitHub 部署失败", {"error": str(e)})
        
        # 打印总结
        print_summary(html_file=working_html_file, source_html_protected=(os.path.abspath(working_html_file) != os.path.abspath(HTML_FILE)))
        
        logger.info("工作完成", {
            "end_time": datetime.now().strftime('%H:%M:%S')
        })
        
        return True
        
    except Exception as e:
        # REQ-103: 事务回滚
        logger.error("更新过程中发生异常", {"error": str(e)})
        import traceback
        traceback.print_exc()
        logger.warn("正在从备份恢复")
        tx.restore(backup_path)
        return False
    finally:
        if publish_temp_dir:
            cleanup_publish_html_snapshot(publish_temp_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETF投资报告更新")
    parser.add_argument("--publish", action="store_true", help="发布模式：企微通知 + GitHub Pages 部署")
    args = parser.parse_args()
    success = main(publish=args.publish)
    sys.exit(0 if success else 1)
