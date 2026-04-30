#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF K 线数据生成脚本。

职责：
1. 获取 ETF 与基准指数原始 K 线数据
2. 在生成阶段执行数据清洗（如份额变动）
3. 重建周线并计算均线指标
4. 将结果写入 JSON / 前端数据入口
"""


import requests
import json
import time
import re
import os
from datetime import datetime, timedelta

from logger import Logger
from corporate_action_source import detect_corporate_action_events, save_detected_corporate_action_payload
from data_cleaning import apply_share_change_events, normalize_corporate_action_events, run_data_cleaning_pipeline
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
REFERER = api_config.get('referer', 'https://finance.sina.com.cn/')
KLINE_DELAY = api_config.get('request_delays', {}).get('kline_fetch', 0.2)
API_RETRIES = api_config.get('retries', 3)
API_RETRY_DELAY = api_config.get('retry_delay', 0.5)


# 数据清洗配置（兼容旧 adjustments.split_events）
DATA_CLEANING_EVENTS = config.get('data_cleaning.corporate_action_events', {})
LEGACY_SPLIT_EVENTS = config.get('adjustments.split_events', {})
AUTO_DETECTION_CONFIG = config.get('data_cleaning.event_detection', {})
FILES_CONFIG = config.get_files_config()
DATA_FILES = FILES_CONFIG.get('data_files', {})
CORPORATE_ACTION_FILE = DATA_FILES.get('corporate_actions', 'corporate_action_events.json')


# 记录配置加载

logger.info("配置已加载", {
    "etf_count": len(ETF_LIST),
    "display_days": DISPLAY_DAYS,
    "warmup_days": MA_WARMUP_DAYS,
    "api_timeout": API_TIMEOUT
})


MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 0


def should_drop_incomplete_daily_bar(trade_day_str, now=None):
    """若最新日线是今天且尚未收盘，则视为盘中未完成 bar。"""
    try:
        trade_day = datetime.strptime(trade_day_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False

    current = now or datetime.now()
    if trade_day != current.date():
        return False

    market_close = current.replace(
        hour=MARKET_CLOSE_HOUR,
        minute=MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0,
    )
    return current < market_close



def trim_incomplete_daily_bar(data, symbol, scale, now=None):
    """盘中更新时回退到上一收盘日，避免未完成日K污染报告。"""
    if scale != 240 or not isinstance(data, list) or not data:
        return data

    latest_day = data[-1].get('day')
    if not should_drop_incomplete_daily_bar(latest_day, now=now):
        return data

    if len(data) < 2:
        logger.warn("检测到盘中日线但样本不足，保留原始返回", {
            "symbol": symbol,
            "latest_day": latest_day,
            "scale": scale,
        })
        return data

    logger.info("检测到未收盘日线，已回退到上一收盘日", {
        "symbol": symbol,
        "dropped_day": latest_day,
        "fallback_day": data[-2].get('day'),
        "scale": scale,
    })
    return data[:-1]



def get_skill_data_dir():

    """获取技能数据目录。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    return os.path.join(skill_dir, FILES_CONFIG.get('data_dir', 'data'))


def get_detected_corporate_action_file_path(data_dir=None):
    """获取自动识别事件文件路径。"""
    return os.path.join(data_dir or get_skill_data_dir(), CORPORATE_ACTION_FILE)


def merge_data_cleaning_events(*event_groups):
    """合并并去重数据清洗事件，优先保留靠前事件组。"""
    merged = []
    seen = set()
    flat_events = []

    for group in event_groups:
        flat_events.extend(group or [])

    for event in normalize_corporate_action_events(flat_events):
        key = (event['action'], event['ex_date'])
        if key in seen:
            continue
        seen.add(key)
        merged.append(event)

    return merged


def load_detected_corporate_action_events(data_dir=None):
    """读取上一次自动识别输出的份额变动事件。"""
    file_path = get_detected_corporate_action_file_path(data_dir)
    if not os.path.exists(file_path):
        return {}

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            payload = json.load(file)
        events_by_code = payload.get('events_by_code', {}) if isinstance(payload, dict) else {}
        return events_by_code if isinstance(events_by_code, dict) else {}
    except Exception as exc:
        logger.warn('读取自动识别事件文件失败', {'file': file_path, 'error': str(exc)})
        return {}


def build_event_detection_window(reference_date=None):
    """根据当前图表窗口估算需要覆盖的份额变动事件区间。"""
    reference_day = reference_date or datetime.now().date()
    lookback_days = int(AUTO_DETECTION_CONFIG.get('lookback_calendar_days') or (max(FETCH_DAYS, FETCH_WEEKS * 7) + 30))
    start_date = reference_day - timedelta(days=lookback_days)
    return start_date, reference_day


def sync_corporate_action_events(data_dir, reference_date=None):
    """在主流程内部同步当前窗口内的份额变动事件。"""
    if AUTO_DETECTION_CONFIG.get('enabled', True) is False:
        logger.info('份额变动自动识别已禁用')
        return {}

    start_date, end_date = build_event_detection_window(reference_date)
    etf_codes = [etf['code'] for etf in ETF_LIST]

    try:
        payload = detect_corporate_action_events(etf_codes, start_date, end_date, AUTO_DETECTION_CONFIG)
        save_detected_corporate_action_payload(payload, get_detected_corporate_action_file_path(data_dir))
        return payload.get('events_by_code', {})
    except Exception as exc:
        logger.warn('份额变动自动识别失败，回退到已有事件文件/手工配置', {'error': str(exc)})
        return load_detected_corporate_action_events(data_dir)


def get_data_cleaning_events(code, detected_events_by_code=None):
    """按 ETF 代码读取数据清洗事件，自动识别命中时优先只用自动结果。"""
    detected_events_by_code = detected_events_by_code or {}
    detected_events = detected_events_by_code.get(code, [])
    if detected_events:
        return merge_data_cleaning_events(detected_events)

    return merge_data_cleaning_events(
        DATA_CLEANING_EVENTS.get(code) or [],
        LEGACY_SPLIT_EVENTS.get(code, []),
    )



def fetch_json_with_retries(url, error_message):


    """带重试地获取 JSON 数据，避免偶发网络错误直接清空整只ETF图表。"""
    last_error = None

    for attempt in range(1, API_RETRIES + 1):
        try:
            with logger.audit_api_call("GET", url):
                response = requests.get(url, headers={
                    "User-Agent": USER_AGENT,
                    "Referer": REFERER
                }, timeout=API_TIMEOUT)

            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")

            data = response.json()
            if not data:
                raise ValueError("empty response")

            if attempt > 1:
                logger.warn("重试后获取成功", {"url": url, "attempt": attempt})
            return data
        except Exception as e:
            last_error = e
            if attempt < API_RETRIES:
                logger.warn("请求失败，准备重试", {
                    "url": url,
                    "attempt": attempt,
                    "max_attempts": API_RETRIES,
                    "error": str(e)
                })
                time.sleep(API_RETRY_DELAY)

    logger.error(error_message, {"error": str(last_error), "attempts": API_RETRIES})
    return None


def fetch_kline_sina(symbol, scale=240, days=60):
    """使用新浪财经API获取K线数据
    scale: 240=日线, 1200=周线
    """
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={days}"
    data = fetch_json_with_retries(url, "获取数据失败")

    if not data:
        return None

    data = trim_incomplete_daily_bar(data, symbol, scale)
    if not data:
        return None

    logger.audit("api_call", f"K line data received: {symbol} scale={scale}", extra={"record_count": len(data)})


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

    if len(data) >= 2:
        latest_close = float(data[-1]['close'])
        prev_close = float(data[-2]['close'])
        change_pct = (latest_close - prev_close) / prev_close * 100
    else:
        latest_close = float(data[-1]['close'])
        change_pct = 0

    # 新浪 getKLineData 接口不返回成交额字段；用 AKShare 封装的新浪新版接口
    # fund_etf_hist_sina 补拉 amount（单位：元），按 dates 对齐后返回与主序列等长的 amounts。
    # 失败返回 None，不阻塞主流程——前端副图会回退到空状态，其他展示不受影响。
    amounts = fetch_amounts_via_akshare(symbol, dates) if scale == 240 else None

    result = {
        "dates": dates,
        "kline": kline_data,
        "volumes": volumes,
        "latest_close": latest_close,
        "latest_change": round(change_pct, 2)
    }
    if amounts is not None:
        result["amounts"] = amounts
    return result


def fetch_amounts_via_akshare(symbol, target_dates):
    """用 AKShare fund_etf_hist_sina 补拉成交额（单位：元），按 target_dates 对齐。

    Args:
        symbol: 如 'sh512400' / 'sz159755'，与新浪 getKLineData 一致的符号格式
        target_dates: 主 K 线返回的 dates 列表（'YYYY-MM-DD'），用于对齐 amount

    Returns:
        与 target_dates 等长的 amounts 列表（int，单位：元）；若任一步失败则返回 None
    """
    if not target_dates:
        return None
    try:
        import akshare as ak
    except ImportError:
        logger.warn("akshare 未安装，跳过成交额补拉", {"symbol": symbol})
        return None
    try:
        df = ak.fund_etf_hist_sina(symbol=symbol)
    except Exception as e:
        logger.warn("fund_etf_hist_sina 调用失败，跳过成交额补拉", {
            "symbol": symbol, "error": f"{type(e).__name__}: {e}"
        })
        return None
    if df is None or df.empty or 'date' not in df.columns or 'amount' not in df.columns:
        logger.warn("fund_etf_hist_sina 返回缺字段，跳过成交额补拉", {"symbol": symbol})
        return None

    amount_map = {}
    for _, row in df.iterrows():
        try:
            amount_map[str(row['date'])[:10]] = int(row['amount'])
        except (TypeError, ValueError):
            continue

    aligned = []
    missing = 0
    for d in target_dates:
        if d in amount_map:
            aligned.append(amount_map[d])
        else:
            aligned.append(0)
            missing += 1

    logger.info("成交额补拉完成", {
        "symbol": symbol,
        "aligned": len(aligned),
        "missing_days": missing,
    })
    return aligned


def fetch_index_data_sina(symbol, days=60):
    """获取指数日线数据，返回收盘价序列用于对比"""
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
    data = fetch_json_with_retries(url, "获取指数数据失败")

    if not data:
        return None

    data = trim_incomplete_daily_bar(data, symbol, 240)
    if not data:
        return None

    logger.audit("api_call", f"Index data received: {symbol}", extra={"record_count": len(data)})


    dates = []
    closes = []
    kline_data = []

    for item in data:
        dates.append(item['day'])
        closes.append(float(item['close']))
        kline_data.append([
            float(item['open']),
            float(item['close']),
            float(item['low']),
            float(item['high'])
        ])

    if len(closes) > 0:
        base = closes[0]
        normalized = [round((c / base - 1) * 100, 2) for c in closes]
        return {
            "dates": dates,
            "closes": closes,
            "kline": kline_data,
            "normalized": normalized
        }

    return None



def apply_split_adjustments(data, split_events=None):
    """兼容旧调用入口：委托给数据清洗模块中的份额变动处理。"""
    return apply_share_change_events(data, split_events)



def build_weekly_from_daily(daily_data):
    """从日线数据重建周线，避免跨份额变动周出现错误周 K。"""

    if not daily_data or not daily_data.get("dates"):
        return None

    dates = daily_data.get("dates", [])
    kline = daily_data.get("kline", [])
    volumes = daily_data.get("volumes") or [0] * len(dates)
    amounts = daily_data.get("amounts") or [0] * len(dates)
    has_amounts = "amounts" in daily_data

    weekly_dates = []
    weekly_kline = []
    weekly_volumes = []
    weekly_amounts = []

    current_week_key = None
    current_bucket = None

    for trade_date, candle, volume, amount in zip(dates, kline, volumes, amounts):
        week_key = datetime.strptime(trade_date, "%Y-%m-%d").isocalendar()[:2]

        if current_week_key != week_key:
            if current_bucket is not None:
                weekly_dates.append(current_bucket["date"])
                weekly_kline.append([
                    round(current_bucket["open"], 3),
                    round(current_bucket["close"], 3),
                    round(current_bucket["low"], 3),
                    round(current_bucket["high"], 3),
                ])
                weekly_volumes.append(int(current_bucket["volume"]))
                weekly_amounts.append(int(current_bucket["amount"]))

            current_week_key = week_key
            current_bucket = {
                "date": trade_date,
                "open": candle[0],
                "close": candle[1],
                "low": candle[2],
                "high": candle[3],
                "volume": volume,
                "amount": amount,
            }
            continue

        current_bucket["date"] = trade_date
        current_bucket["close"] = candle[1]
        current_bucket["low"] = min(current_bucket["low"], candle[2])
        current_bucket["high"] = max(current_bucket["high"], candle[3])
        current_bucket["volume"] += volume
        current_bucket["amount"] += amount

    if current_bucket is not None:
        weekly_dates.append(current_bucket["date"])
        weekly_kline.append([
            round(current_bucket["open"], 3),
            round(current_bucket["close"], 3),
            round(current_bucket["low"], 3),
            round(current_bucket["high"], 3),
        ])
        weekly_volumes.append(int(current_bucket["volume"]))
        weekly_amounts.append(int(current_bucket["amount"]))

    latest_close = weekly_kline[-1][1] if weekly_kline else None
    latest_change = 0
    if len(weekly_kline) >= 2 and weekly_kline[-2][1] != 0:
        prev_close = weekly_kline[-2][1]
        latest_change = round((latest_close - prev_close) / prev_close * 100, 2)

    result = {
        "dates": weekly_dates,
        "kline": weekly_kline,
        "volumes": weekly_volumes,
        "latest_close": latest_close,
        "latest_change": latest_change,
    }
    if has_amounts:
        result["amounts"] = weekly_amounts
    return result


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
        logger.audit("data_process", "trim_data_with_ma skipped: insufficient data", extra={"kline_len": len(data.get('kline', [])) if data else 0})
        return data
    
    with logger.audit_operation("data_process", "trim_data_with_ma + MA calculation"):
        full_kline = data['kline']
        ma5_full = calculate_ma(full_kline, 5)
        ma20_full = calculate_ma(full_kline, 20)
        
        start_idx = len(data['dates']) - display_days
        
        trimmed = {
            'dates': data['dates'][start_idx:],
            'kline': data['kline'][start_idx:],
            'volumes': data['volumes'][start_idx:] if 'volumes' in data else [],
            'latest_close': data.get('latest_close'),
            'latest_change': data.get('latest_change'),
            'ma5': ma5_full[start_idx:],
            'ma20': ma20_full[start_idx:]
        }
        if 'amounts' in data:
            trimmed['amounts'] = data['amounts'][start_idx:]
    
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


def load_existing_kline_data(data_dir):
    """读取上一版K线数据，供抓数失败时回退。"""
    json_file = os.path.join(data_dir, "etf_full_kline_data.json")
    if not os.path.exists(json_file):
        return {}

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warn("读取历史K线数据失败", {"file": json_file, "error": str(e)})
        return {}


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
    existing_data = load_existing_kline_data(data_dir)
    weekly_source_days = max(FETCH_DAYS, FETCH_WEEKS * 6)
    detected_events_by_code = sync_corporate_action_events(data_dir)
    
    for etf in ETF_LIST:

        code = etf["code"]
        market = etf["market"]
        symbol = f"{market}{code}"
        cleaning_events = get_data_cleaning_events(code, detected_events_by_code)

        previous_entry = existing_data.get(code) if isinstance(existing_data.get(code), dict) else {}
        
        logger.info("正在获取ETF数据", {
            "code": code,
            "name": etf['name'],
            "daily_source_days": weekly_source_days,
            "data_cleaning_event_count": len(cleaning_events)
        })

        
        # 获取足量日线数据：既供日K使用，也用于本地重建周K，避免跨份额变动周失真

        daily_source_data = fetch_kline_sina(symbol, scale=240, days=weekly_source_days)
        time.sleep(KLINE_DELAY)
        
        # 获取基准指数数据（只用于日线对比）
        benchmark_data = fetch_index_data_sina(etf["benchmark"]["code"], days=FETCH_DAYS)

        time.sleep(KLINE_DELAY)

        daily_data = None
        weekly_data = None
        
        if daily_source_data:
            logger.info("日线源数据获取成功", {
                "code": code,
                "original_days": len(daily_source_data['dates'])
            })

            if cleaning_events:
                daily_source_data = run_data_cleaning_pipeline(daily_source_data, cleaning_events)

            weekly_source_data = build_weekly_from_daily(daily_source_data)

            daily_data = trim_data_with_ma(daily_source_data, MA_WARMUP_DAYS, DISPLAY_DAYS)
            logger.info("日线数据裁剪完成", {
                "code": code,
                "trimmed_days": len(daily_data['dates']),
                "ma5_first_5": daily_data.get('ma5', [])[:5]
            })
        
            if weekly_source_data:
                logger.info("周线源数据重建成功", {
                    "code": code,
                    "original_weeks": len(weekly_source_data['dates'])
                })
                weekly_data = trim_data_with_ma(weekly_source_data, MA_WARMUP_WEEKS, DISPLAY_WEEKS)
                logger.info("周线数据裁剪完成", {
                    "code": code,
                    "trimmed_weeks": len(weekly_data['dates']),
                    "ma5_first_5": weekly_data.get('ma5', [])[:5]
                })
        elif previous_entry.get("daily"):
            daily_data = previous_entry.get("daily")
            weekly_data = previous_entry.get("weekly")
            logger.warn("ETF日线抓取失败，回退到上一版K线数据", {"code": code})

        if not weekly_data and previous_entry.get("weekly"):
            weekly_data = previous_entry.get("weekly")
            logger.warn("ETF周线数据缺失，回退到上一版周线数据", {"code": code})

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
        elif previous_entry.get("benchmark"):
            benchmark_data = previous_entry.get("benchmark")
            logger.warn("基准指数抓取失败，回退到上一版基准数据", {"code": code})
        
        # 计算ETF的归一化走势（用于与基准对比）
        etf_normalized = None
        if daily_data and len(daily_data['kline']) > 0:
            base = daily_data['kline'][0][1]  # 第一天收盘价
            etf_normalized = [round((k[1] / base - 1) * 100, 2) for k in daily_data['kline']]
        elif previous_entry.get("etf_normalized") is not None:
            etf_normalized = previous_entry.get("etf_normalized")
        
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
    with logger.audit_operation("file_io", f"write {json_file}"):
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(json_file)
    logger.audit("file_io", f"K line data saved: {json_file}", extra={"file_size_bytes": file_size, "etf_count": len(all_data)})
    
    logger.info("成功获取ETF完整数据", {
        "etf_count": len(all_data)
    })
    logger.info("数据已保存", {"file": json_file})

    # 注：REQ-146 之后数据通过 assets/js/runtime_payload.js 提供，
    # 已无需再向 outputs/js/main.js 注入 klineData；此处的旧注入路径已移除（BUG-013）。

    logger.info("=" * 60)
    logger.info("K线数据更新完成")
    logger.info("=" * 60)

    return all_data