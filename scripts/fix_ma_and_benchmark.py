#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复两个问题：
1. 均线计算开始部分缺失 - 多获取19天数据用于预热
2. 基准指数K线默认不显示 - 修改legend selected配置
"""

import requests
import json
import time
import re
import os
from bs4 import BeautifulSoup

from logger import Logger
from config_manager import get_config

# 日志初始化
logger = Logger(name="kline_data", level="INFO", file_output=True)

# 配置管理器初始化
config = get_config()

# 从配置加载ETF列表和K线参数
ETF_LIST = config.get_etfs()

# K线参数
kline_config = config.get_kline_config()
DISPLAY_DAYS = kline_config.get('daily', {}).get('display_days', 60)
MA_WARMUP_DAYS = kline_config.get('daily', {}).get('warmup_days', 19)
FETCH_DAYS = kline_config.get('daily', {}).get('fetch_days', 79)

DISPLAY_WEEKS = kline_config.get('weekly', {}).get('display_weeks', 52)
MA_WARMUP_WEEKS = kline_config.get('weekly', {}).get('warmup_weeks', 19)
FETCH_WEEKS = kline_config.get('weekly', {}).get('fetch_weeks', 71)

# API参数
api_config = config.get_api_config().get('sina', {})
API_TIMEOUT = api_config.get('timeout', 10)
USER_AGENT = api_config.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
KLINE_DELAY = api_config.get('request_delays', {}).get('kline_fetch', 0.2)

# 记录配置加载
logger.info("配置已加载", {
    "etf_count": len(ETF_LIST),
    "display_days": DISPLAY_DAYS,
    "warmup_days": MA_WARMUP_DAYS,
    "api_timeout": API_TIMEOUT
})


def fetch_kline_sina(symbol, scale=240, days=60):
    """使用新浪财经API获取K线数据
    scale: 240=日线, 1200=周线
    """
    try:
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={days}"
        
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://finance.sina.com.cn/"
        }
        
        response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            
            if data and len(data) > 0:
                dates = []
                kline_data = []
                volumes = []
                
                for item in data:
                    dates.append(item['day'])
                    kline_data.append([
                        float(item['open']),
                        float(item['close']),
                        float(item['low']),
                        float(item['high'])
                    ])
                    volumes.append(int(item['volume']))
                
                # 计算最新涨跌幅
                if len(data) >= 2:
                    latest_close = float(data[-1]['close'])
                    prev_close = float(data[-2]['close'])
                    change_pct = (latest_close - prev_close) / prev_close * 100
                else:
                    latest_close = float(data[-1]['close'])
                    change_pct = 0
                
                return {
                    "dates": dates,
                    "kline": kline_data,
                    "volumes": volumes,
                    "latest_close": latest_close,
                    "latest_change": round(change_pct, 2)
                }
        
        return None
    except Exception as e:
        logger.error("获取数据失败", {"error": str(e)})
        return None


def fetch_index_data_sina(symbol, days=60):
    """获取指数日线数据，返回收盘价序列用于对比"""
    try:
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
        
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://finance.sina.com.cn/"
        }
        
        response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            
            if data and len(data) > 0:
                dates = []
                closes = []
                kline_data = []  # 添加K线数据用于显示
                
                for item in data:
                    dates.append(item['day'])
                    closes.append(float(item['close']))
                    kline_data.append([
                        float(item['open']),
                        float(item['close']),
                        float(item['low']),
                        float(item['high'])
                    ])
                
                # 归一化处理：转换为相对于第一天的百分比变化
                if len(closes) > 0:
                    base = closes[0]
                    normalized = [round((c / base - 1) * 100, 2) for c in closes]
                    return {
                        "dates": dates,
                        "closes": closes,
                        "kline": kline_data,  # K线数据
                        "normalized": normalized  # 百分比变化
                    }
        
        return None
    except Exception as e:
        logger.error("获取指数数据失败", {"error": str(e)})
        return None


def calculate_ma(kline_data, period):
    """计算均线数据（用于预计算，避免前端缺失）"""
    result = []
    for i in range(len(kline_data)):
        if i < period - 1:
            result.append(None)
        else:
            sum_val = sum(k[1] for k in kline_data[i-period+1:i+1])  # 收盘价
            result.append(round(sum_val / period, 3))
    return result


def trim_data_with_ma(data, warmup_days, display_days):
    """裁剪数据，保留显示天数的数据，同时计算完整的MA"""
    if not data or len(data.get('kline', [])) < warmup_days + display_days:
        # 数据不足，返回原数据
        return data
    
    # 先用完整数据计算MA
    full_kline = data['kline']
    ma5_full = calculate_ma(full_kline, 5)
    ma20_full = calculate_ma(full_kline, 20)
    
    # 截取最后display_days天的数据
    start_idx = len(data['dates']) - display_days
    
    trimmed = {
        'dates': data['dates'][start_idx:],
        'kline': data['kline'][start_idx:],
        'volumes': data['volumes'][start_idx:] if 'volumes' in data else [],
        'latest_close': data.get('latest_close'),
        'latest_change': data.get('latest_change'),
        # 预计算的均线数据（已截取）
        'ma5': ma5_full[start_idx:],
        'ma20': ma20_full[start_idx:]
    }
    
    return trimmed


def trim_benchmark_data(data, warmup_days, display_days):
    """裁剪基准指数数据"""
    if not data or len(data.get('dates', [])) < warmup_days + display_days:
        return data
    
    start_idx = len(data['dates']) - display_days
    
    # 重新计算归一化（基于裁剪后的第一天）
    closes_trimmed = data['closes'][start_idx:]
    if len(closes_trimmed) > 0:
        base = closes_trimmed[0]
        normalized = [round((c / base - 1) * 100, 2) for c in closes_trimmed]
    else:
        normalized = []
    
    return {
        'dates': data['dates'][start_idx:],
        'closes': closes_trimmed,
        'kline': data.get('kline', [])[start_idx:] if data.get('kline') else [],
        'normalized': normalized
    }


def update_html_legend_selected(html_file):
    """修改HTML中的legend配置，默认隐藏基准指数
    
    使用字符串替换，不经过 BS4 序列化。
    """
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 检查是否已存在 selected 配置
    if "'沪深300': false" in html_content:
        logger.info("legend selected 配置已存在，跳过修改")
        return True

    # 在 HTML 原始文本中查找并替换
    old_str = 'legend: { data: legendData,'
    new_str = "legend: { data: legendData,\n                    selected: { '沪深300': false },"
    
    if old_str in html_content:
        html_content = html_content.replace(old_str, new_str, 1)
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info("已添加 legend selected 配置（基准指数默认隐藏）")
        return True
    else:
        logger.warn("未找到 legend 配置位置")
        return False


def update_js_file_with_kline_data(js_file, all_data):
    """更新JS文件中的klineData数据"""
    
    # 构建新的klineData
    kline_data_js = json.dumps(all_data, ensure_ascii=False, indent=8)
    new_kline_data = f'const klineData = {kline_data_js};'
    
    # 读取原始JS文件
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    # 找到klineData的位置并替换
    pattern = r'const klineData = \{.*?\};'
    
    # 使用正则替换（考虑多行）
    js_content = re.sub(pattern, new_kline_data, js_content, flags=re.DOTALL)
    
    # 写回文件
    with open(js_file, 'w', encoding='utf-8') as f:
        f.write(js_content)
    
    return True


def main():
    """主函数：获取数据并更新"""
    import os
    
    # 获取skill根目录（scripts的父目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    
    # 定义文件路径
    data_dir = os.path.join(skill_dir, "data")
    outputs_dir = os.path.join(skill_dir, "outputs")
    
    # 确保目录存在
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(outputs_dir, exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("步骤1: 获取ETF和基准指数数据（多获取19天用于MA预热）")
    logger.info("=" * 60)
    
    all_data = {}
    
    for etf in ETF_LIST:
        code = etf["code"]
        market = etf["market"]
        symbol = f"{market}{code}"
        
        logger.info("正在获取ETF数据", {
            "code": code,
            "name": etf['name']
        })
        
        # 获取日线数据（多获取19天用于MA20预热）
        daily_data = fetch_kline_sina(symbol, scale=240, days=FETCH_DAYS)
        time.sleep(0.2)
        
        # 获取周线数据（多获取19周用于MA20预热）
        weekly_data = fetch_kline_sina(symbol, scale=1200, days=FETCH_WEEKS)
        time.sleep(0.2)
        
        # 获取基准指数数据（也多获取19天）
        benchmark_data = fetch_index_data_sina(etf["benchmark"], days=FETCH_DAYS)
        time.sleep(0.2)
        
        if daily_data:
            logger.info("日线数据获取成功", {
                "code": code,
                "original_days": len(daily_data['dates'])
            })
            daily_data = trim_data_with_ma(daily_data, MA_WARMUP_DAYS, DISPLAY_DAYS)
            logger.info("日线数据裁剪完成", {
                "code": code,
                "trimmed_days": len(daily_data['dates']),
                "ma5_first_5": daily_data['ma5'][:5]
            })
        
        if weekly_data:
            logger.info("周线数据获取成功", {
                "code": code,
                "original_weeks": len(weekly_data['dates'])
            })
            weekly_data = trim_data_with_ma(weekly_data, MA_WARMUP_WEEKS, DISPLAY_WEEKS)
            logger.info("周线数据裁剪完成", {
                "code": code,
                "trimmed_weeks": len(weekly_data['dates']),
                "ma5_first_5": weekly_data['ma5'][:5]
            })
        
        if benchmark_data:
            logger.info("基准指数数据获取成功", {
                "code": code,
                "original_days": len(benchmark_data['dates'])
            })
            benchmark_data = trim_benchmark_data(benchmark_data, MA_WARMUP_DAYS, DISPLAY_DAYS)
            logger.info("基准指数裁剪完成", {
                "code": code,
                "trimmed_days": len(benchmark_data['dates'])
            })
        
        # 计算ETF的归一化走势（用于与基准对比）
        etf_normalized = None
        if daily_data and len(daily_data['kline']) > 0:
            base = daily_data['kline'][0][1]  # 第一天收盘价
            etf_normalized = [round((k[1] / base - 1) * 100, 2) for k in daily_data['kline']]
        
        all_data[code] = {
            "name": etf["name"],
            "benchmark_name": etf["benchmark"]["name"],
            "daily": daily_data,
            "weekly": weekly_data,
            "benchmark": benchmark_data,
            "etf_normalized": etf_normalized
        }
    
    # 保存数据
    json_file = os.path.join(data_dir, "etf_full_kline_data.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    logger.info("成功获取ETF完整数据", {
        "etf_count": len(all_data)
    })
    logger.info("数据已保存", {"file": json_file})
    
    # 更新JS文件中的klineData
    logger.info("=" * 60)
    logger.info("步骤2: 更新JS文件中的K线数据")
    logger.info("=" * 60)
    
    # 在 js/main.js 中查找并更新 klineData
    js_main_file = os.path.join(outputs_dir, "js", "main.js")
    
    if os.path.exists(js_main_file):
        update_js_file_with_kline_data(js_main_file, all_data)
        logger.info("已更新JS文件", {"file": js_main_file})
    else:
        logger.warn("JS文件不存在，跳过更新", {"file": js_main_file})
    
    # 检查 js/chart_*.js 是否需要更新
    # （通常不需要，因为数据在 main.js 中定义）
    
    logger.info("=" * 60)
    logger.info("K线数据更新完成")
    logger.info("=" * 60)
    
    return all_data


if __name__ == "__main__":
    data = main()
