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
from datetime import datetime
from bs4 import BeautifulSoup

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


def update_html_dates():
    """更新HTML报告中的日期信息（报告日期、数据截止、页脚生成时间）
    
    使用字符串定位替换，不经过 BS4 序列化，避免破坏 script 内容。
    """
    logger.info("=" * 60)
    logger.info("Step 3: 更新报告日期")
    logger.info("=" * 60)
    
    # 从配置加载文件路径和定位标记
    files_config = config.get_files_config()
    html_update_config = config.get_html_update_config()
    
    html_file = HTML_FILE  # 使用根目录的 index.html
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
    
    # 1. 更新"报告日期": <strong ...>2026年03月17日</strong>（可能有 style 属性）
    html_content, found = _replace_text_in_html(
        html_content, report_date_label,
        r'<strong[^>]*>' + report_date_pattern + r'</strong>',
        f'<strong style="color: #3b82f6;">{report_date_cn}</strong>'
    )
    if found:
        logger.info("报告日期更新成功", {"date": report_date_cn})
        updated = True
    
    # 2. 更新"数据截止": 数据截止: 2026-03-17
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


def update_html_data():
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
        logger.info("读取K线数据成功", {"file": kline_file})
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
            logger.warn("未找到klineData段落")
    except Exception as e:
        logger.error("更新klineData失败", {"error": str(e)})
        import traceback
        traceback.print_exc()
    
    # 2. 更新 realtimeData（如果存在）— 用字符串替换
    try:
        realtime_json_str = json.dumps(realtime_data, ensure_ascii=False, indent=8)
        new_realtime_section = f'{realtime_const}{realtime_json_str}'
        # 提取const名称用于替换
        const_name = realtime_const.replace('const ', '').replace(' = ', '').strip()
        html_content, found = _replace_js_const_in_html(html_content, const_name, new_realtime_section)
        if found:
            logger.info("更新realtimeData成功", {"data_type": "实时行情数据"})
        else:
            logger.info("未找到realtimeData段落（这可能是正常的）")
    except Exception as e:
        logger.error("更新realtimeData失败", {"error": str(e)})
        import traceback
        traceback.print_exc()
    
    # 写回 HTML（直接写字符串，不经过 BS4）
    try:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info("HTML数据更新完成")
        return True
    except Exception as e:
        logger.error("写入HTML失败", {"error": str(e), "file": html_file})
        return False


def verify_output_files():
    """验证输出文件"""
    logger.info("=" * 60)
    logger.info("Step 4: 验证输出文件")
    logger.info("=" * 60)
    
    # 从配置加载文件配置
    files_config = config.get_files_config()
    data_files = files_config.get('data_files', {})
    html_file_name = files_config.get('html_file', 'index.html')
    required_files = [
        (os.path.join(DATA_DIR, data_files.get('kline', 'etf_full_kline_data.json')), data_files.get('kline', 'etf_full_kline_data.json')),
        (os.path.join(DATA_DIR, data_files.get('realtime', 'etf_realtime_data.json')), data_files.get('realtime', 'etf_realtime_data.json')),
        (os.path.join(OUTPUTS_DIR, html_file_name), html_file_name),
    ]
    
    all_exist = True
    for path, name in required_files:
        if os.path.exists(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            logger.info("文件验证成功", {
                "name": name,
                "modified_time": mtime.strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            logger.warn("文件缺失", {"name": name})
            all_exist = False
    
    return all_exist

def print_summary():
    """打印总结信息"""
    logger.info("=" * 60)
    logger.info("更新完成")
    logger.info("=" * 60)
    
    # 从配置加载消息提示
    messages = config._config.get('messages', {})
    
    # 本地预览路径
    local_preview = f"file:///{OUTPUTS_DIR.replace(os.sep, '/')}/index.html"
    
    summary = f"""
报告已更新完成！

输出文件:
  - data/etf_full_kline_data.json  (K线数据)
  - data/etf_realtime_data.json    (实时行情数据)
  - outputs/index.html              (综合报告)

本地预览:
  {local_preview}

数据来源:
  - {messages.get('data_source', 'K线/实时行情：新浪财经API')}

注意事项:
  - {messages.get('update_timing', '建议在交易日收盘后(15:00之后)执行更新')}
  - {messages.get('ma_warmup_note', 'MA均线从第一天即有完整数据(已预热)')}
  - {messages.get('realtime_data_note', 'ETF涨跌幅和成分股涨跌幅为实时数据')}
"""
    logger.info("完成总结", {"summary": summary})


def main():
    """主函数
    
    执行以下步骤：
    1. 获取K线数据并更新
    2. 获取实时行情数据并更新
    3. 更新HTML中的数据（klineData + realtimeData）
    4. 更新报告日期
    5. 验证输出文件
    6. HTML 完整性验证（REQ-102）
    """
    logger.info("=" * 60)
    logger.info(f"ETF投资报告更新 - {datetime.now().strftime('%Y-%m-%d')}")
    logger.info("=" * 60)
    
    logger.info("工作环境信息", {
        "work_dir": WORK_DIR,
        "start_time": datetime.now().strftime('%H:%M:%S')
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
        update_html_data()
        
        # Step 4: 更新报告日期
        update_html_dates()
        
        # Step 5: 验证输出文件
        if not verify_output_files():
            logger.warn("部分文件缺失，请检查")
        
        # Step 6: HTML 完整性验证（REQ-102）
        logger.info("=" * 60)
        logger.info("Step 5: HTML 完整性验证")
        logger.info("=" * 60)
        try:
            from verify_html_integrity import verify_html_integrity, print_report
            html_path = HTML_FILE
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
        
        # 打印总结
        print_summary()
        
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

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
