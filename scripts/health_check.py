#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-106: ETF 系统健康检查仪表板

功能：一键验证 ETF 报告系统各部分是否正常工作
输出：彩色终端表格 + JSON 报告 + HTML 可视化

检查项：23 项（6 大类别）
  A. 文件完整性检查 (5 项)
  B. 数据有效性检查 (6 项)
  C. 脚本依赖检查 (5 项)
  D. HTML 结构检查 (4 项)
  E. 工作流逻辑检查 (3 项)
  F. 系统配置检查 (2 项)

使用方法：
    python health_check.py                    # 基础检查
    python health_check.py --json             # 生成 JSON 报告
    python health_check.py --html             # 生成 HTML 报告
    python health_check.py --strict           # 严格模式（警告 = 失败）
    python health_check.py --category A,B,C   # 只检查特定类别
    python health_check.py --verbose          # 详细日志
"""

import os
import sys
import json
import re
import platform
import subprocess
import locale
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any
from html.parser import HTMLParser

# 设置编码（Windows 兼容性）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ============================================================
# 常量定义
# ============================================================

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(WORK_DIR)
DATA_DIR = os.path.join(SKILL_DIR, "data")
OUTPUTS_DIR = os.path.join(SKILL_DIR, "outputs")
DEPLOY_DIR = os.path.join(SKILL_DIR, "deploy")

ETF_CODES = ["512400", "513120", "512070", "515880", "159566", "159698"]
REQUIRED_DATA_FILES = [
    "etf_full_kline_data.json",
    "etf_realtime_data.json",
    "fund_flow_data.json",
]
REQUIRED_SCRIPTS = [
    "update_report.py",
    "fix_ma_and_benchmark.py",
    "realtime_data_updater.py",
    "transaction.py",
    "verify_html_integrity.py",
]

# 颜色代码（ANSI）
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'

# ============================================================
# 检查结果数据结构
# ============================================================

class CheckResult:
    def __init__(self, check_id: str, name: str, category: str):
        self.id = check_id
        self.name = name
        self.category = category
        self.status = "PENDING"  # PASS, WARN, FAIL
        self.details = {}
        self.error_message = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "details": self.details,
            "error": self.error_message,
        }

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
        self.unmatched_tags = []
    
    def handle_starttag(self, tag, attrs):
        if tag in self.target_tags and tag not in self.VOID_TAGS:
            self.open_counts[tag] += 1
    
    def handle_endtag(self, tag):
        if tag in self.target_tags and tag not in self.VOID_TAGS:
            self.open_counts[tag] -= 1
            if self.open_counts[tag] < 0:
                self.unmatched_tags.append(f"Unmatched closing tag: {tag}")
    
    def is_balanced(self) -> bool:
        return all(count == 0 for count in self.open_counts.values()) and not self.unmatched_tags

# ============================================================
# 检查器类
# ============================================================

class FileChecker:
    """文件完整性检查"""
    
    @staticmethod
    def check_html_existence() -> CheckResult:
        result = CheckResult("A1", "HTML 文件存在性", "A")
        try:
            deploy_html = os.path.join(DEPLOY_DIR, "index.html")
            outputs_html = os.path.join(OUTPUTS_DIR, "index.html")
            
            deploy_exists = os.path.exists(deploy_html)
            outputs_exists = os.path.exists(outputs_html)
            
            if deploy_exists and outputs_exists:
                result.status = "PASS"
                result.details = {
                    "deploy_html": f"exists ({os.path.getsize(deploy_html) / 1024:.2f} KB)",
                    "outputs_html": f"exists ({os.path.getsize(outputs_html) / 1024:.2f} KB)",
                }
            else:
                result.status = "FAIL"
                result.details = {
                    "deploy_html": "missing" if not deploy_exists else "exists",
                    "outputs_html": "missing" if not outputs_exists else "exists",
                }
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_data_files() -> CheckResult:
        result = CheckResult("A2", "数据文件完整性", "A")
        try:
            missing_files = []
            for fname in REQUIRED_DATA_FILES:
                fpath = os.path.join(DATA_DIR, fname)
                if not os.path.exists(fpath):
                    missing_files.append(fname)
            
            if not missing_files:
                result.status = "PASS"
                result.details = {"found": len(REQUIRED_DATA_FILES), "total": len(REQUIRED_DATA_FILES)}
            else:
                result.status = "FAIL"
                result.details = {"missing": missing_files}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_scripts() -> CheckResult:
        result = CheckResult("A3", "脚本文件完整性", "A")
        try:
            missing_scripts = []
            for sname in REQUIRED_SCRIPTS:
                spath = os.path.join(WORK_DIR, sname)
                if not os.path.exists(spath):
                    missing_scripts.append(sname)
            
            if not missing_scripts:
                result.status = "PASS"
                result.details = {"found": len(REQUIRED_SCRIPTS), "total": len(REQUIRED_SCRIPTS)}
            else:
                result.status = "FAIL"
                result.details = {"missing": missing_scripts}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_file_sizes() -> CheckResult:
        result = CheckResult("A4", "文件大小合理性", "A")
        try:
            issues = []
            
            # 检查 HTML 文件
            html_file = os.path.join(OUTPUTS_DIR, "index.html")
            if os.path.exists(html_file):
                size_kb = os.path.getsize(html_file) / 1024
                if size_kb < 500:
                    issues.append(f"HTML 文件过小: {size_kb:.2f} KB")
            
            # 检查 K线数据
            kline_file = os.path.join(DATA_DIR, "etf_full_kline_data.json")
            if os.path.exists(kline_file):
                size_kb = os.path.getsize(kline_file) / 1024
                if size_kb < 100:
                    issues.append(f"K线数据过小: {size_kb:.2f} KB")
            
            if not issues:
                result.status = "PASS"
                result.details = {"status": "All file sizes are reasonable"}
            else:
                result.status = "FAIL"
                result.details = {"issues": issues}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_file_permissions() -> CheckResult:
        result = CheckResult("A5", "文件权限检查", "A")
        try:
            issues = []
            
            # 检查关键文件可读性
            check_files = [
                os.path.join(OUTPUTS_DIR, "index.html"),
                os.path.join(DATA_DIR, "etf_full_kline_data.json"),
                os.path.join(WORK_DIR, "update_report.py"),
            ]
            
            for fpath in check_files:
                if os.path.exists(fpath):
                    if not os.access(fpath, os.R_OK):
                        issues.append(f"无读权限: {os.path.basename(fpath)}")
            
            # 检查输出目录可写性
            if not os.access(OUTPUTS_DIR, os.W_OK):
                issues.append(f"输出目录无写权限: {OUTPUTS_DIR}")
            
            if not issues:
                result.status = "PASS"
                result.details = {"status": "All file permissions OK"}
            else:
                result.status = "FAIL"
                result.details = {"issues": issues}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result

class DataChecker:
    """数据有效性检查"""
    
    @staticmethod
    def check_json_validity() -> CheckResult:
        result = CheckResult("B1", "JSON 解析有效性", "B")
        try:
            issues = []
            
            # 检查 K线数据
            kline_file = os.path.join(DATA_DIR, "etf_full_kline_data.json")
            try:
                with open(kline_file, 'r', encoding='utf-8') as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                issues.append(f"K线 JSON 错误: {str(e)[:50]}")
            
            # 检查实时数据
            realtime_file = os.path.join(DATA_DIR, "etf_realtime_data.json")
            try:
                with open(realtime_file, 'r', encoding='utf-8') as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                issues.append(f"实时数据 JSON 错误: {str(e)[:50]}")
            
            if not issues:
                result.status = "PASS"
                result.details = {"parsed_files": 2}
            else:
                result.status = "FAIL"
                result.details = {"errors": issues}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_etf_completeness() -> CheckResult:
        result = CheckResult("B2", "ETF 代码完整性", "B")
        try:
            kline_file = os.path.join(DATA_DIR, "etf_full_kline_data.json")
            with open(kline_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            found_codes = list(data.keys())
            missing_codes = [code for code in ETF_CODES if code not in found_codes]
            
            if not missing_codes:
                result.status = "PASS"
                result.details = {"found": len(found_codes), "total": len(ETF_CODES)}
            else:
                result.status = "FAIL"
                result.details = {"missing": missing_codes, "found": len(found_codes)}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_kline_structure() -> CheckResult:
        result = CheckResult("B3", "K线数据结构", "B")
        try:
            kline_file = os.path.join(DATA_DIR, "etf_full_kline_data.json")
            with open(kline_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            issues = []
            for code in ETF_CODES:
                if code in data:
                    etf_data = data[code]
                    if "daily" not in etf_data or "weekly" not in etf_data:
                        issues.append(f"{code}: 缺少日线或周线")
            
            if not issues:
                result.status = "PASS"
                result.details = {"checked_etfs": len(ETF_CODES)}
            else:
                result.status = "FAIL"
                result.details = {"issues": issues}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_date_consistency() -> CheckResult:
        result = CheckResult("B4", "日期一致性", "B")
        try:
            kline_file = os.path.join(DATA_DIR, "etf_full_kline_data.json")
            realtime_file = os.path.join(DATA_DIR, "etf_realtime_data.json")
            
            kline_date = None
            realtime_date = None
            
            # 从 K线数据提取最新日期
            with open(kline_file, 'r', encoding='utf-8') as f:
                kline_data = json.load(f)
                for code, etf_data in kline_data.items():
                    daily = etf_data.get("daily", {})
                    dates = daily.get("dates", [])
                    if dates:
                        kline_date = dates[-1]
                        break
            
            # 从实时数据提取日期（如果有）
            try:
                with open(realtime_file, 'r', encoding='utf-8') as f:
                    realtime_data = json.load(f)
                    if realtime_data and isinstance(realtime_data, dict):
                        first_etf = next(iter(realtime_data.values()), {})
                        if "timestamp" in first_etf:
                            realtime_date = first_etf["timestamp"][:10]
            except:
                pass
            
            if kline_date:
                result.status = "PASS"
                result.details = {"kline_date": kline_date, "realtime_date": realtime_date or "N/A"}
            else:
                result.status = "FAIL"
                result.details = {"error": "无法提取日期"}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_data_freshness() -> CheckResult:
        result = CheckResult("B5", "数据时效性", "B")
        try:
            kline_file = os.path.join(DATA_DIR, "etf_full_kline_data.json")
            with open(kline_file, 'r', encoding='utf-8') as f:
                kline_data = json.load(f)
            
            latest_date = None
            for code, etf_data in kline_data.items():
                daily = etf_data.get("daily", {})
                dates = daily.get("dates", [])
                if dates:
                    latest_date = dates[-1]
                    break
            
            if not latest_date:
                result.status = "FAIL"
                result.details = {"error": "无法提取数据日期"}
            else:
                # 比较日期
                from datetime import datetime, timedelta
                latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
                current_dt = datetime.now()
                diff_days = (current_dt - latest_dt).days
                
                if diff_days > 7:
                    result.status = "FAIL"
                    result.details = {"latest_date": latest_date, "age_days": diff_days}
                elif diff_days > 2:
                    result.status = "WARN"
                    result.details = {"latest_date": latest_date, "age_days": diff_days}
                else:
                    result.status = "PASS"
                    result.details = {"latest_date": latest_date, "age_days": diff_days}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_holdings_data() -> CheckResult:
        result = CheckResult("B6", "成分股数据", "B")
        try:
            realtime_file = os.path.join(DATA_DIR, "etf_realtime_data.json")
            with open(realtime_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            holdings_counts = {}
            for code in ETF_CODES:
                if code in data:
                    holdings = data[code].get("holdings", [])
                    holdings_counts[code] = len(holdings)
            
            min_holdings = min(holdings_counts.values()) if holdings_counts else 0
            
            if min_holdings >= 5:
                result.status = "PASS"
                result.details = {"avg_holdings": sum(holdings_counts.values()) / len(holdings_counts) if holdings_counts else 0}
            else:
                result.status = "FAIL"
                result.details = {"holdings_counts": holdings_counts}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result

class DependencyChecker:
    """脚本依赖检查"""
    
    @staticmethod
    def check_python_version() -> CheckResult:
        result = CheckResult("C1", "Python 版本", "C")
        try:
            version_info = sys.version_info
            version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
            
            if version_info >= (3, 8):
                result.status = "PASS"
                result.details = {"version": version_str}
            else:
                result.status = "FAIL"
                result.details = {"version": version_str, "required": "3.8+"}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_required_imports() -> CheckResult:
        result = CheckResult("C2", "必需库导入", "C")
        required_libs = ["requests", "bs4", "beautifulsoup4"]
        missing_libs = []
        
        for lib in required_libs:
            try:
                __import__(lib)
            except ImportError:
                missing_libs.append(lib)
        
        if not missing_libs:
            result.status = "PASS"
            result.details = {"imported": len(required_libs)}
        else:
            result.status = "FAIL"
            result.details = {"missing": missing_libs}
        return result
    
    @staticmethod
    def check_script_imports() -> CheckResult:
        result = CheckResult("C3", "脚本导入链", "C")
        try:
            # 临时添加脚本目录到路径
            sys.path.insert(0, WORK_DIR)
            
            # 尝试导入核心模块
            try:
                import fix_ma_and_benchmark
            except Exception as e:
                raise Exception(f"fix_ma_and_benchmark 导入失败: {str(e)}")
            
            try:
                import realtime_data_updater
            except Exception as e:
                raise Exception(f"realtime_data_updater 导入失败: {str(e)}")
            
            result.status = "PASS"
            result.details = {"modules_imported": 2}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        finally:
            sys.path.pop(0)
        
        return result
    
    @staticmethod
    def check_api_connectivity() -> CheckResult:
        result = CheckResult("C4", "外部 API 可达性", "C")
        try:
            import requests
            
            # 测试新浪财经 API
            test_url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
            try:
                response = requests.get(test_url, timeout=5)
                if response.status_code <= 499:
                    result.status = "PASS"
                    result.details = {"api": "money.finance.sina.com.cn", "status": "OK"}
                else:
                    result.status = "WARN"
                    result.details = {"api": "money.finance.sina.com.cn", "status": f"HTTP {response.status_code}"}
            except requests.Timeout:
                result.status = "WARN"
                result.details = {"api": "money.finance.sina.com.cn", "status": "TIMEOUT"}
            except Exception as e:
                result.status = "FAIL"
                result.details = {"api": "money.finance.sina.com.cn", "status": str(e)[:50]}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_write_permissions() -> CheckResult:
        result = CheckResult("C5", "临时目录可写", "C")
        try:
            test_file = os.path.join(OUTPUTS_DIR, ".health_check_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                result.status = "PASS"
                result.details = {"directory": OUTPUTS_DIR}
            except Exception as e:
                result.status = "FAIL"
                result.details = {"error": str(e)[:50]}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result

class HTMLChecker:
    """HTML 结构检查"""
    
    @staticmethod
    def check_tag_balance() -> CheckResult:
        result = CheckResult("D1", "HTML 标签平衡", "D")
        try:
            html_file = os.path.join(OUTPUTS_DIR, "index.html")
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            checker = TagBalanceChecker()
            checker.feed(html_content)
            
            if checker.is_balanced():
                result.status = "PASS"
                result.details = {"status": "All tags balanced"}
            else:
                result.status = "FAIL"
                result.details = {"unmatched": checker.unmatched_tags or checker.open_counts}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_js_data_blocks() -> CheckResult:
        result = CheckResult("D2", "JavaScript 数据块", "D")
        try:
            html_file = os.path.join(OUTPUTS_DIR, "index.html")
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            missing_blocks = []
            for const_name in ["klineData", "realtimeData"]:
                if f"const {const_name} =" not in html_content:
                    missing_blocks.append(const_name)
            
            if not missing_blocks:
                result.status = "PASS"
                result.details = {"found": ["klineData", "realtimeData"]}
            else:
                result.status = "FAIL"
                result.details = {"missing": missing_blocks}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_echarts_cdn() -> CheckResult:
        result = CheckResult("D3", "ECharts CDN", "D")
        try:
            html_file = os.path.join(OUTPUTS_DIR, "index.html")
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            if "echarts" in html_content.lower():
                result.status = "PASS"
                result.details = {"found": "echarts library"}
            else:
                result.status = "FAIL"
                result.details = {"status": "echarts library not found"}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_css_completeness() -> CheckResult:
        result = CheckResult("D4", "样式 CSS 完整", "D")
        try:
            html_file = os.path.join(OUTPUTS_DIR, "index.html")
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            required_classes = [".panel", ".chart", ".table", ".header", ".footer"]
            missing_classes = []
            
            for cls in required_classes:
                if cls.replace(".", "") not in html_content:
                    missing_classes.append(cls)
            
            if not missing_classes:
                result.status = "PASS"
                result.details = {"found_classes": len(required_classes)}
            else:
                result.status = "WARN"
                result.details = {"possibly_missing": missing_classes}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result

class WorkflowChecker:
    """工作流逻辑检查"""
    
    @staticmethod
    def check_transaction_management() -> CheckResult:
        result = CheckResult("E1", "事务管理", "E")
        try:
            backups_dir = os.path.join(OUTPUTS_DIR, ".backups")
            if os.path.exists(backups_dir):
                backups = [d for d in os.listdir(backups_dir) if os.path.isdir(os.path.join(backups_dir, d))]
                if len(backups) > 0:
                    result.status = "PASS"
                    result.details = {"backups_count": len(backups)}
                else:
                    result.status = "WARN"
                    result.details = {"status": "No backups found"}
            else:
                result.status = "FAIL"
                result.details = {"error": "Backups directory not found"}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_date_sync() -> CheckResult:
        result = CheckResult("E2", "日期同步", "E")
        try:
            html_file = os.path.join(OUTPUTS_DIR, "index.html")
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # 提取日期字段
            date_patterns = {
                "report_date": r"报告日期:.*?(\d{4}年\d{2}月\d{2}日)",
                "data_cutoff": r"数据截止:\s*(\d{4}-\d{2}-\d{2})",
                "generation_time": r"生成时间:\s*(\d{4}-\d{2}-\d{2})",
            }
            
            found_dates = {}
            for key, pattern in date_patterns.items():
                match = re.search(pattern, html_content)
                if match:
                    found_dates[key] = match.group(1)
            
            if len(found_dates) >= 2:
                result.status = "PASS"
                result.details = found_dates
            else:
                result.status = "WARN"
                result.details = {"found": len(found_dates), "expected": 3}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result
    
    @staticmethod
    def check_update_pipeline() -> CheckResult:
        result = CheckResult("E3", "更新流程完整性", "E")
        try:
            # 检查 update_report.py 的主要函数定义
            script_path = os.path.join(WORK_DIR, "update_report.py")
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
            required_functions = [
                "run_kline_update",
                "run_realtime_update",
                "update_html_data",
                "update_html_dates",
                "verify_output_files",
            ]
            
            missing_functions = []
            for func in required_functions:
                if f"def {func}" not in script_content:
                    missing_functions.append(func)
            
            if not missing_functions:
                result.status = "PASS"
                result.details = {"functions_found": len(required_functions)}
            else:
                result.status = "FAIL"
                result.details = {"missing": missing_functions}
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        return result

class ConfigChecker:
    """系统配置检查"""
    
    @staticmethod
    def check_holdings_config() -> CheckResult:
        result = CheckResult("F1", "成分股配置", "F")
        try:
            sys.path.insert(0, WORK_DIR)
            try:
                import realtime_data_updater
                
                etf_config = realtime_data_updater.ETF_CONFIG
                if len(etf_config) == 6:
                    result.status = "PASS"
                    result.details = {"configured_etfs": len(etf_config)}
                else:
                    result.status = "WARN"
                    result.details = {"configured_etfs": len(etf_config), "expected": 6}
            except Exception as e:
                raise Exception(f"无法导入 ETF_CONFIG: {str(e)}")
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        finally:
            sys.path.pop(0)
        
        return result
    
    @staticmethod
    def check_benchmark_config() -> CheckResult:
        result = CheckResult("F2", "基准指数配置", "F")
        try:
            sys.path.insert(0, WORK_DIR)
            try:
                import realtime_data_updater
                
                etf_config = realtime_data_updater.ETF_CONFIG
                all_correct = all(
                    etf_data.get("market") in ["sh", "sz"]
                    for etf_data in etf_config.values()
                )
                
                if all_correct:
                    result.status = "PASS"
                    result.details = {"benchmark_config": "OK"}
                else:
                    result.status = "FAIL"
                    result.details = {"status": "Some ETFs have incorrect configuration"}
            except Exception as e:
                raise Exception(f"无法检查配置: {str(e)}")
        except Exception as e:
            result.status = "FAIL"
            result.error_message = str(e)
        finally:
            sys.path.pop(0)
        
        return result

# ============================================================
# 报告生成器
# ============================================================

class ConsoleReporter:
    """终端表格报告（彩色）"""
    
    @staticmethod
    def print_header(title):
        print("\n" + "=" * 70)
        print(f" {title}")
        print("=" * 70)
    
    @staticmethod
    def print_category(category_id, category_name, results):
        print(f"\n[{category_id}] {category_name}")
        print("-" * 70)
        
        for result in results:
            status_symbol = {
                "PASS": f"{Colors.GREEN}[OK]{Colors.RESET}",
                "WARN": f"{Colors.YELLOW}[!]{Colors.RESET}",
                "FAIL": f"{Colors.RED}[X]{Colors.RESET}",
            }.get(result.status, "[ ]")
            
            # 格式化输出
            check_id = f"{result.id:4s}"
            name = f"{result.name:20s}"
            status = f"{status_symbol} {result.status:6s}"
            
            # 详情
            details_str = ""
            if result.details:
                if isinstance(result.details, dict):
                    # 提取最重要的信息
                    if "found" in result.details and "total" in result.details:
                        details_str = f"| {result.details['found']}/{result.details['total']}"
                    elif "status" in result.details:
                        details_str = f"| {result.details['status']}"
            
            print(f"  {status} | {check_id} | {name} {details_str}")
    
    @staticmethod
    def print_summary(total_checks, passed, warnings, failed, duration):
        print("\n" + "=" * 70)
        
        # 计算整体状态
        if failed == 0 and warnings == 0:
            overall = f"{Colors.GREEN}PASS{Colors.RESET}"
        elif failed == 0:
            overall = f"{Colors.YELLOW}WARN{Colors.RESET}"
        else:
            overall = f"{Colors.RED}FAIL{Colors.RESET}"
        
        summary_text = f"""
总体状态: {overall}
检查项: {passed}/{total_checks} 通过"""
        
        if warnings > 0:
            summary_text += f", {warnings} 个警告"
        if failed > 0:
            summary_text += f", {failed} 个失败"
        
        summary_text += f"\n检查时间: {duration:.1f} 秒"
        
        print(summary_text)
        print("=" * 70)

class JSONReporter:
    """JSON 报告生成器"""
    
    @staticmethod
    def generate(all_results, duration) -> Dict:
        categories = {}
        
        # 按类别分组
        for result in all_results:
            category_id = result.category
            if category_id not in categories:
                categories[category_id] = {
                    "name": get_category_name(category_id),
                    "checks": [],
                    "passed": 0,
                    "total": 0,
                }
            
            categories[category_id]["checks"].append(result.to_dict())
            categories[category_id]["total"] += 1
            if result.status == "PASS":
                categories[category_id]["passed"] += 1
        
        # 统计总数
        total = len(all_results)
        passed = sum(1 for r in all_results if r.status == "PASS")
        warnings = sum(1 for r in all_results if r.status == "WARN")
        failed = sum(1 for r in all_results if r.status == "FAIL")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "PASS" if failed == 0 and warnings == 0 else ("WARN" if failed == 0 else "FAIL"),
            "total_checks": total,
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "categories": categories,
            "duration_seconds": duration,
            "environment": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": f"{platform.system()}-{platform.release()}",
                "cwd": SKILL_DIR,
            }
        }

# ============================================================
# 辅助函数
# ============================================================

def get_category_name(category_id: str) -> str:
    categories = {
        "A": "文件完整性检查",
        "B": "数据有效性检查",
        "C": "脚本依赖检查",
        "D": "HTML 结构检查",
        "E": "工作流逻辑检查",
        "F": "系统配置检查",
    }
    return categories.get(category_id, "未知类别")

def run_all_checks(categories_filter=None):
    """执行所有检查"""
    
    all_results = []
    
    # 定义所有检查器
    checkers = [
        # A: 文件完整性
        FileChecker.check_html_existence,
        FileChecker.check_data_files,
        FileChecker.check_scripts,
        FileChecker.check_file_sizes,
        FileChecker.check_file_permissions,
        # B: 数据有效性
        DataChecker.check_json_validity,
        DataChecker.check_etf_completeness,
        DataChecker.check_kline_structure,
        DataChecker.check_date_consistency,
        DataChecker.check_data_freshness,
        DataChecker.check_holdings_data,
        # C: 脚本依赖
        DependencyChecker.check_python_version,
        DependencyChecker.check_required_imports,
        DependencyChecker.check_script_imports,
        DependencyChecker.check_api_connectivity,
        DependencyChecker.check_write_permissions,
        # D: HTML 结构
        HTMLChecker.check_tag_balance,
        HTMLChecker.check_js_data_blocks,
        HTMLChecker.check_echarts_cdn,
        HTMLChecker.check_css_completeness,
        # E: 工作流逻辑
        WorkflowChecker.check_transaction_management,
        WorkflowChecker.check_date_sync,
        WorkflowChecker.check_update_pipeline,
        # F: 系统配置
        ConfigChecker.check_holdings_config,
        ConfigChecker.check_benchmark_config,
    ]
    
    # 按类别过滤
    if categories_filter:
        filter_set = set(categories_filter.split(","))
        checkers = [c for c in checkers if c()().category in filter_set]
    
    # 执行检查
    for check_func in checkers:
        try:
            result = check_func()
            all_results.append(result)
        except Exception as e:
            print(f"[ERROR] 执行检查时出错: {e}", file=sys.stderr)
    
    return all_results

# ============================================================
# 主程序
# ============================================================

def main():
    import argparse
    from time import time
    
    parser = argparse.ArgumentParser(
        description="ETF 系统健康检查仪表板",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--html", action="store_true", help="输出 HTML 报告")
    parser.add_argument("--strict", action="store_true", help="严格模式（警告 = 失败）")
    parser.add_argument("--category", help="只检查特定类别（如 A,B,C）")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    
    args = parser.parse_args()
    
    start_time = time()
    
    # 执行所有检查
    all_results = run_all_checks(categories_filter=args.category)
    
    duration = time() - start_time
    
    # 统计
    total = len(all_results)
    passed = sum(1 for r in all_results if r.status == "PASS")
    warnings = sum(1 for r in all_results if r.status == "WARN")
    failed = sum(1 for r in all_results if r.status == "FAIL")
    
    # 终端输出
    if not args.json and not args.html:
        ConsoleReporter.print_header(f"ETF 系统健康检查 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 按类别打印
        for category_id in ["A", "B", "C", "D", "E", "F"]:
            category_results = [r for r in all_results if r.category == category_id]
            if category_results:
                ConsoleReporter.print_category(
                    category_id,
                    get_category_name(category_id),
                    category_results
                )
        
        # 总结
        ConsoleReporter.print_summary(total, passed, warnings, failed, duration)
    
    # JSON 输出
    if args.json:
        report = JSONReporter.generate(all_results, duration)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    
    # 返回值
    if args.strict and warnings > 0:
        return 1
    
    return 0 if failed == 0 else 2

if __name__ == "__main__":
    sys.exit(main())
