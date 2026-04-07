#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-102: HTML 完整性验证脚本

功能：验证 outputs/index.html 更新后的完整性
检查项：
1. HTML 标签平衡检查（div/script/style/table/tr/td）
2. JSON 数据块有效性（const xxxData = {...};）
3. 6 支 ETF 数据完整性（klineData 结构）
4. 日期一致性检查（报告日期/数据截止/生成时间）
5. 必要元素存在性（panel 容器/ECharts CDN）

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

# 工作目录
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(WORK_DIR)  # skill 根目录
OUTPUTS_DIR = os.path.join(SKILL_DIR, "outputs")

# 6 支 ETF 代码
ETF_CODES = ["512400", "513120", "512070", "515880", "159566", "159698"]


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

    # 提取数据截止：数据截止: 2026-04-03
    cutoff_match = re.search(r'数据截止:\s*(\d{4}-\d{2}-\d{2})', html_content)
    if cutoff_match:
        cutoff_date = datetime.strptime(cutoff_match.group(1), "%Y-%m-%d")
        if cutoff_date <= today:
            results.append({"check": "数据截止", "status": "PASS",
                            "detail": f"<= 今天 ({cutoff_match.group(1)})"})
        else:
            results.append({"check": "数据截止", "status": "FAIL",
                            "detail": f"{cutoff_match.group(1)} > 今天 ({today.strftime('%Y-%m-%d')})"})
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
        html_path = os.path.join(OUTPUTS_DIR, "index.html")

    result = verify_html_integrity(html_path)
    print_report(result, html_path)

    return result["passed"]


if __name__ == "__main__":
    passed = main()
    sys.exit(0 if passed else 1)
