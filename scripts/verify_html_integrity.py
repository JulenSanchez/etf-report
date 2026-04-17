#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-102: HTML 完整性验证脚本

功能：验证根目录 index.html 更新后的完整性
检查项：
1. HTML 标签平衡检查（div/script/style/table/tr/td）
2. JSON 数据块有效性（const xxxData = {...};）
3. 6 支 ETF 数据完整性（klineData 结构）
4. 日期一致性检查（报告日期/数据截止/生成时间）
5. 必要元素存在性（panel 容器/ECharts CDN）
6. 解释层日期检查（逐条研究卡日期 / 逐条宏观资讯日期）


使用方法：
    python verify_html_integrity.py               # 验证默认 HTML
    python verify_html_integrity.py path/to.html   # 验证指定文件
"""


import os
import re
import json
import sys
from datetime import datetime
from html.parser import HTMLParser

try:
    from config_manager import get_config
except Exception:
    get_config = None


# 工作目录
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(WORK_DIR)  # skill 根目录
HTML_FILE = os.path.join(SKILL_DIR, "index.html")


# 6 支 ETF 代码（优先从配置读取，便于后续替换 ETF 时只维护一份名单）
DEFAULT_ETF_CODES = ["512400", "513120", "512070", "515880", "159566", "159865"]



def load_etf_codes():
    if get_config is None:
        return list(DEFAULT_ETF_CODES)

    try:
        config = get_config()
        configured_codes = config.get('system_check.etf_codes') or config.get_etf_codes()
        normalized = [str(code).zfill(6) for code in (configured_codes or []) if str(code).strip()]
        return normalized or list(DEFAULT_ETF_CODES)
    except Exception:
        return list(DEFAULT_ETF_CODES)


ETF_CODES = load_etf_codes()



def load_editorial_content():
    if get_config is None:
        return {}

    try:
        config = get_config()
        if hasattr(config, "get_editorial_content"):
            return config.get_editorial_content() or {}
    except Exception:
        return {}

    return {}



def _extract_data_cutoff_date(html_content):
    nested_match = re.search(r'id="report-cutoff-value">\s*(\d{4}-\d{2}-\d{2})\s*<', html_content)
    if nested_match:
        return nested_match.group(1)

    match = re.search(r'数据截止:\s*(\d{4}-\d{2}-\d{2})', html_content)
    return match.group(1) if match else None



def _parse_iso_date(date_str):
    if not date_str or not isinstance(date_str, str):
        return None

    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
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



# ============================================================
# HTML 标签平衡检查器
# ============================================================



class TagBalanceChecker(HTMLParser):
    """检查 HTML 标签是否成对出现"""

    VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "area", "base",
                 "col", "embed", "param", "source", "track", "wbr"}

    def __init__(self, target_tags=None):
        super().__init__()
        self.target_tags = target_tags or {"div", "script", "style", "table", "tr", "td"}
        self.open_counts = {tag: 0 for tag in self.target_tags}
        self.tag_stack = []
        self.unmatched_close = []

    def handle_starttag(self, tag, attrs):
        if tag in self.target_tags:
            self.open_counts[tag] += 1
            self.tag_stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in self.target_tags:
            for i in range(len(self.tag_stack) - 1, -1, -1):
                if self.tag_stack[i][0] == tag:
                    self.tag_stack.pop(i)
                    return
            self.unmatched_close.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        pass

    def check(self):
        counts = {tag: self.open_counts[tag] for tag in self.target_tags}
        unclosed = [(tag, pos) for tag, pos in self.tag_stack]
        return {"counts": counts, "unclosed": unclosed, "unmatched_close": self.unmatched_close}


# ============================================================
# 各项检查函数
# ============================================================

def check_html_tag_balance(html_content):
    """检查 1：HTML 标签平衡"""
    checker = TagBalanceChecker()
    try:
        checker.feed(html_content)
    except Exception as e:
        return {"check": "HTML标签平衡", "status": "FAIL", "detail": f"解析错误: {e}"}

    result = checker.check()
    unclosed = result["unclosed"]
    unmatched = result["unmatched_close"]
    counts = result["counts"]

    if not unclosed and not unmatched:
        parts = [f"{tag}: {cnt}" for tag, cnt in counts.items()]
        return {"check": "HTML标签平衡", "status": "PASS", "detail": ", ".join(parts)}
    else:
        errors = []
        for tag, pos in unclosed:
            errors.append(f"<{tag}> 未闭合 (行{pos[0]})")
        for e in unmatched:
            errors.append(e)
        return {"check": "HTML标签平衡", "status": "FAIL", "detail": "; ".join(errors)}


def check_json_data_blocks(html_content):
    """检查 2：JSON 数据块有效性"""
    results = []

    # 匹配 const xxxData = { ... };
    pattern = r'const\s+(\w+Data)\s*=\s*(\{[\s\S]*?\n\s*\});'
    matches = re.findall(pattern, html_content)

    if not matches:
        return [{"check": "JSON数据块", "status": "WARN", "detail": "未找到任何 const xxxData 块"}]

    for var_name, json_str in matches:
        try:
            json.loads(json_str)
            results.append({"check": f"{var_name} JSON", "status": "PASS", "detail": ""})
        except json.JSONDecodeError as e:
            results.append({"check": f"{var_name} JSON", "status": "FAIL",
                            "detail": f"JSON 无效: {e}"})

    return results


def check_etf_data_completeness(html_content):
    """检查 3：6 支 ETF 数据完整性"""
    results = []

    # 提取 klineData JSON
    pattern = r'const\s+klineData\s*=\s*(\{[\s\S]*?\n\s*\});'
    match = re.search(pattern, html_content)

    if not match:
        return [{"check": "ETF数据完整性", "status": "FAIL", "detail": "未找到 klineData"}]

    try:
        kline_data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        return [{"check": "ETF数据完整性", "status": "FAIL", "detail": f"klineData JSON 无效: {e}"}]

    # 检查 ETF 数量
    missing = [code for code in ETF_CODES if code not in kline_data]
    if missing:
        results.append({"check": "ETF数量", "status": "FAIL",
                        "detail": f"缺少: {', '.join(missing)}"})
    else:
        results.append({"check": "ETF数量", "status": "PASS", "detail": f"6 支 ETF"})

    # 检查每支 ETF 的数据结构
    for code in ETF_CODES:
        if code not in kline_data:
            continue
        etf = kline_data[code]
        required_keys = {"daily", "weekly", "benchmark"}
        actual_keys = set(etf.keys())
        missing_keys = required_keys - actual_keys

        if missing_keys:
            results.append({"check": f"{code} 结构", "status": "FAIL",
                            "detail": f"缺少: {', '.join(missing_keys)}"})
        else:
            results.append({"check": f"{code} 结构", "status": "PASS", "detail": ""})

    return results


def check_date_consistency(html_content):
    """检查 4：日期一致性"""
    results = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # 提取报告日期：报告日期: <strong ...>2026年04月07日</strong>
    report_match = re.search(r'报告日期:.*?(\d{4})年(\d{2})月(\d{2})日', html_content)
    if report_match:
        y, m, d = int(report_match.group(1)), int(report_match.group(2)), int(report_match.group(3))
        report_date = datetime(y, m, d)
        if report_date == today:
            results.append({"check": "报告日期", "status": "PASS",
                            "detail": f"= 今天 ({today.strftime('%Y-%m-%d')})"})
        else:
            results.append({"check": "报告日期", "status": "FAIL",
                            "detail": f"{report_date.strftime('%Y-%m-%d')} != 今天 ({today.strftime('%Y-%m-%d')})"})
    else:
        results.append({"check": "报告日期", "status": "FAIL", "detail": "未找到"})

    # 提取数据截止：兼容旧纯文本和新页头嵌套结构
    cutoff_value = _extract_data_cutoff_date(html_content)
    if cutoff_value:
        cutoff_date = datetime.strptime(cutoff_value, "%Y-%m-%d")
        if cutoff_date <= today:
            results.append({"check": "数据截止", "status": "PASS",
                            "detail": f"<= 今天 ({cutoff_value})"})
        else:
            results.append({"check": "数据截止", "status": "FAIL",
                            "detail": f"{cutoff_value} > 今天 ({today.strftime('%Y-%m-%d')})"})
    else:
        results.append({"check": "数据截止", "status": "FAIL", "detail": "未找到"})

    # 提取生成时间：生成时间: 2026-04-07
    gen_match = re.search(r'生成时间:\s*(\d{4}-\d{2}-\d{2})', html_content)
    if gen_match:
        gen_date = datetime.strptime(gen_match.group(1), "%Y-%m-%d")
        if gen_date == today:
            results.append({"check": "生成时间", "status": "PASS",
                            "detail": f"= 今天 ({today.strftime('%Y-%m-%d')})"})
        else:
            results.append({"check": "生成时间", "status": "FAIL",
                            "detail": f"{gen_match.group(1)} != 今天 ({today.strftime('%Y-%m-%d')})"})
    else:
        results.append({"check": "生成时间", "status": "FAIL", "detail": "未找到"})

    return results


def check_required_elements(html_content):
    """检查 5：必要元素存在性"""
    results = []

    # 检查 ECharts CDN
    if 'cdn.jsdelivr.net/npm/echarts' in html_content:
        results.append({"check": "ECharts CDN", "status": "PASS", "detail": ""})
    else:
        results.append({"check": "ECharts CDN", "status": "FAIL", "detail": "未找到 ECharts CDN script"})

    # 检查 6 个 panel 容器
    missing_panels = []
    for code in ETF_CODES:
        if f'id="panel-{code}"' not in html_content:
            missing_panels.append(code)

    if not missing_panels:
        results.append({"check": "Panel容器", "status": "PASS", "detail": "6 个 panel"})
    else:
        results.append({"check": "Panel容器", "status": "FAIL",
                        "detail": f"缺少: {', '.join(missing_panels)}"})

    return results



def _collect_debug_target_ids():
    required_ids = [
        "report-header-card",
        "report-market-badge",
        "report-market-badge-icon",
        "report-market-badge-text",
        "report-header-content",
        "report-title-main",
        "report-meta-info",
        "report-date-item",
        "report-date-icon",
        "report-date-text",
        "report-date-label",
        "report-date-value",
        "report-scope-item",
        "report-scope-icon",
        "report-scope-text",
        "report-scope-label",
        "report-scope-value",
        "report-dimension-item",
        "report-dimension-icon",
        "report-dimension-text",
        "report-dimension-label",
        "report-dimension-value",
        "report-cutoff-item",
        "report-cutoff-icon",
        "report-cutoff-text",
        "report-cutoff-label",
        "report-cutoff-value",
    ]

    for code in ETF_CODES:
        base = f"overview-card-{code}"
        required_ids.extend([
            f"{base}-code",
            f"{base}-name",
            f"{base}-change",
            f"{base}-change-label",
            f"{base}-rating",
            f"{base}-recommendation",
        ])

    overview_highlight_cards = {
        "strong-buy-card-overview": 3,
        "watchlist-card-overview": 3,
        "core-themes-card-overview": 3,
    }
    required_ids.extend(["overview-highlights-title", "overview-highlights-grid"])
    for card_id, item_count in overview_highlight_cards.items():
        required_ids.extend([f"{card_id}-title", f"{card_id}-list"])
        for index in range(1, item_count + 1):
            required_ids.append(f"{card_id}-item-{index}")

    required_ids.extend([
        "fund-flow-title",
        "fund-flow-meta",
        "fund-flow-source-label",
        "fund-flow-source-value",
        "fund-flow-updated-label",
        "fund-flow-updated-value",
        "fund-flow-grid",
        "market-rotation-card-header",
        "market-rotation-card-icon",
        "market-rotation-card-title",
        "market-rotation-stats",
        "market-rotation-stat-leader",
        "market-rotation-stat-leader-label",
        "market-rotation-stat-leader-name",
        "market-rotation-stat-leader-value",
        "market-rotation-stat-laggard",
        "market-rotation-stat-laggard-label",
        "market-rotation-stat-laggard-name",
        "market-rotation-stat-laggard-value",
        "market-rotation-stat-average",
        "market-rotation-stat-average-label",
        "market-rotation-stat-average-name",
        "market-rotation-stat-average-value",
        "market-rotation-stat-breadth",
        "market-rotation-stat-breadth-label",
        "market-rotation-stat-breadth-name",
        "market-rotation-stat-breadth-value",
        "market-rotation-note",
    ])

    for table_id in ["leaders-top5-table", "laggards-top5-table"]:
        required_ids.extend([
            f"{table_id}-head",
            f"{table_id}-header-row",
            f"{table_id}-header-name",
            f"{table_id}-header-weight",
            f"{table_id}-header-change",
            f"{table_id}-body",
        ])
        for index in range(1, 6):
            required_ids.extend([
                f"{table_id}-row-{index}",
                f"{table_id}-name-{index}",
                f"{table_id}-weight-{index}",
                f"{table_id}-change-{index}",
            ])

    editorial_content = load_editorial_content() or {}
    macro_cards = editorial_content.get("macro_cards") or {
        "domestic-policy-card": {"items": ["stub"]},
        "global-news-card": {"items": ["stub"]},
        "market-sentiment-card": {"items": ["stub"]},
    }
    required_ids.extend(["macro-environment-title", "macro-environment-grid"])
    for card_id, card_content in macro_cards.items():
        required_ids.extend([f"{card_id}-title", f"{card_id}-list"])
        items = (card_content or {}).get("items") or ["stub"]
        visible_index = 0
        for entry in items:
            if entry != "stub" and not _resolve_editorial_entry_html(entry):
                continue
            visible_index += 1
            required_ids.extend([
                f"{card_id}-item-{visible_index}",
                f"{card_id}-text-{visible_index}",
            ])

    required_ids.extend(["risk-preference-title", "risk-preference-grid"])
    for card_id in [
        "aggressive-allocation-card",
        "moderate-allocation-card",
        "conservative-allocation-card",
    ]:
        required_ids.extend([f"{card_id}-title", f"{card_id}-strategy"])
        for index in range(1, 4):
            required_ids.extend([
                f"{card_id}-item-{index}",
                f"{card_id}-label-{index}",
                f"{card_id}-value-{index}",
            ])

    required_ids.extend([
        "industry-allocation-title",
        "industry-allocation-table-head",
        "industry-allocation-table-header-row",
        "industry-allocation-table-header-industry",
        "industry-allocation-table-header-risk-preference",
        "industry-allocation-table-header-allocation",
        "industry-allocation-table-header-reason",
        "industry-allocation-table-body",
    ])
    for index in range(1, 7):
        required_ids.extend([
            f"industry-allocation-table-row-{index}",
            f"industry-allocation-table-industry-{index}",
            f"industry-allocation-table-risk-preference-{index}",
            f"industry-allocation-table-allocation-{index}",
            f"industry-allocation-table-reason-{index}",
        ])

    required_ids.extend(["risk-warning-title", "risk-warning-grid"])
    for card_id in [
        "geopolitical-risk-card",
        "monetary-policy-risk-card",
        "economic-downturn-risk-card",
    ]:
        required_ids.extend([f"{card_id}-title", f"{card_id}-content"])

    return required_ids



def check_debug_id_coverage(html_content):
    """检查 6：调试模式依赖的细粒度 ID 是否齐全"""
    required_ids = _collect_debug_target_ids()
    missing_ids = [element_id for element_id in required_ids if f'id="{element_id}"' not in html_content]

    if missing_ids:
        return [{"check": "调试ID覆盖", "status": "FAIL", "detail": f"缺少: {', '.join(missing_ids[:10])}"}]

    return [{"check": "调试ID覆盖", "status": "PASS", "detail": f"已检查 {len(required_ids)} 个细粒度 id"}]



def check_editorial_metadata(html_content):
    """检查 7：解释层逐条日期是否已渲染到页面"""

    editorial_content = load_editorial_content()
    if not editorial_content:
        return [{"check": "解释层日期", "status": "WARN", "detail": "未加载 editorial_content.yaml"}]

    cutoff_date = _extract_data_cutoff_date(html_content)
    cutoff_dt = _parse_iso_date(cutoff_date)
    issues = []
    warnings = []
    checked_count = 0

    for code, card_group in (editorial_content.get("etf_cards") or {}).items():
        group = card_group or {}
        research_cards = group.get("research_cards") or []
        for index, entry in enumerate(research_cards, start=1):
            if not _resolve_editorial_entry_html(entry):
                continue
            checked_count += 1
            date_id = f'research-date-{code}-{index}'
            if f'id="{date_id}"' not in html_content:
                issues.append(date_id)

        policy = group.get("freshness_policy") or "sticky"
        content_date = _resolve_editorial_content_date(editorial_content, group)
        content_dt = _parse_iso_date(content_date)
        delta_days = None if not content_dt or not cutoff_dt else abs((cutoff_dt - content_dt).days)
        if policy in {"daily", "manual_daily"} and (delta_days is None or delta_days != 0):
            warnings.append(f"research-{code}:{content_date or '未标注'}")

    for card_id, card_content in (editorial_content.get("macro_cards") or {}).items():
        card = card_content or {}
        items = card.get("items") or []
        for index, entry in enumerate(items, start=1):
            if not _resolve_editorial_entry_html(entry):
                continue
            checked_count += 1
            date_id = f'editorial-date-{card_id}-{index}'
            if f'id="{date_id}"' not in html_content:
                issues.append(date_id)

        content_date = _resolve_editorial_content_date(editorial_content, card)
        if not content_date:
            warnings.append(f"{card_id}:未标注")

    if issues:
        return [{"check": "解释层日期", "status": "FAIL", "detail": f"缺少: {', '.join(issues[:8])}"}]
    if warnings:
        return [{"check": "解释层日期", "status": "WARN", "detail": f"已渲染 {checked_count} 条日期；待复核: {', '.join(warnings[:6])}"}]
    return [{"check": "解释层日期", "status": "PASS", "detail": f"已渲染 {checked_count} 条日期"}]



# ============================================================
# 主函数
# ============================================================


def verify_html_integrity(html_path):
    """
    验证 HTML 文件完整性

    Returns:
        dict: {
            "passed": bool,
            "results": [...],
            "summary": {"pass": N, "fail": N, "warn": N}
        }
    """
    if not os.path.exists(html_path):
        return {
            "passed": False,
            "results": [{"check": "文件存在", "status": "FAIL", "detail": f"文件不存在: {html_path}"}],
            "summary": {"pass": 0, "fail": 1, "warn": 0}
        }

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 执行所有检查
    all_results = []
    all_results.append(check_html_tag_balance(html_content))
    all_results.extend(check_json_data_blocks(html_content))
    all_results.extend(check_etf_data_completeness(html_content))
    all_results.extend(check_date_consistency(html_content))
    all_results.extend(check_required_elements(html_content))
    all_results.extend(check_debug_id_coverage(html_content))
    all_results.extend(check_editorial_metadata(html_content))



    # 统计
    summary = {"pass": 0, "fail": 0, "warn": 0}
    for r in all_results:
        status = r["status"]
        summary[status.lower()] = summary.get(status.lower(), 0) + 1

    return {
        "passed": summary["fail"] == 0,
        "results": all_results,
        "summary": summary
    }


def print_report(result, html_path):
    """打印验证报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 60)
    print(f" HTML 完整性验证报告 - {now}")
    print("=" * 60)
    print(f"文件: {html_path}\n")

    status_icons = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN"}

    for r in result["results"]:
        icon = status_icons.get(r["status"], "???")
        detail = f" ({r['detail']})" if r["detail"] else ""
        print(f"  [{icon}] {r['check']}{detail}")

    s = result["summary"]
    print(f"\n结果: {s['pass']} PASS, {s['fail']} FAIL, {s['warn']} WARN")

    if result["passed"]:
        print("[OK] 验证通过")
    else:
        print("[FAIL] 验证失败，请检查上述 FAIL 项")


def main():
    """主函数"""
    if len(sys.argv) > 1:
        html_path = sys.argv[1]
    else:
        html_path = HTML_FILE


    result = verify_html_integrity(html_path)
    print_report(result, html_path)

    return result["passed"]


if __name__ == "__main__":
    passed = main()
    sys.exit(0 if passed else 1)
