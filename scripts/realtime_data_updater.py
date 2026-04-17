#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时数据更新器 - 使用新浪财经API统一获取所有股价和涨跌数据

功能：
1. 获取ETF的日涨跌幅
2. 获取成分股的当日涨跌幅
3. 更新HTML报告中的相关数据

数据源：新浪财经实时行情API（与K线数据同源）
"""

import requests
import json
import time
import re
import os
from datetime import datetime

from logger import Logger


from config_manager import get_config

# 日志初始化
logger = Logger(name="realtime_data", level="INFO", file_output=True)

# 配置管理器初始化
config = get_config()

# 从配置加载ETF列表和成分股配置
etfs_list = config.get_etfs()


def calculate_total_ratio(components):
    """按成分股占比回算前十大持仓集中度。"""
    return round(sum(float(item.get('ratio', 0) or 0) for item in (components or [])), 2)



def resolve_total_ratio(total_ratio, components):
    """优先使用有效 total_ratio，缺失或非正值时回退到成分股占比求和。"""
    try:
        numeric = float(total_ratio)
    except (TypeError, ValueError):
        numeric = None
    if numeric is not None and numeric > 0:
        return round(numeric, 2)
    return calculate_total_ratio(components)


# 构建ETF_CONFIG（包含ETF信息和对应的成分股）
ETF_CONFIG = {}
for etf_info in etfs_list:
    etf_code = etf_info['code']
    etf_holdings_data = config.get_holdings(etf_code) or {}
    # 提取成分股数组（在 holdings.yaml 中叫 components）
    components = etf_holdings_data.get('components', [])
    total_ratio = resolve_total_ratio(etf_holdings_data.get('total_ratio'), components)
    # 合并 ETF 基本信息和成分股数据
    ETF_CONFIG[etf_code] = {
        **etf_info,  # 包含 code, name, market, benchmark
        'holdings': components,  # 直接使用 components 数组
        'total_ratio': total_ratio
    }



# API参数
api_config = config.get_api_config().get('sina', {})
API_TIMEOUT = api_config.get('timeout', 10)
REALTIME_DELAY = api_config.get('request_delays', {}).get('realtime_fetch', 0.3)

# 记录配置加载
logger.info("配置已加载", {
    "etf_count": len(ETF_CONFIG),
    "api_timeout": API_TIMEOUT
})


def fetch_realtime_quote_sina(symbols):
    """
    使用新浪财经实时行情API批量获取股票/ETF报价
    
    API格式: https://hq.sinajs.cn/list=sh600000,sz000001,...
    返回格式: var hq_str_sh600000="股票名,开盘,昨收,现价,最高,最低,...";
    
    Args:
        symbols: 股票代码列表，格式如 ["sh600000", "sz000001", "hk00700"]
    
    Returns:
        dict: {symbol: {"name": 名称, "price": 现价, "change_pct": 涨跌幅}}
    """
    if not symbols:
        return {}
    
    # 转换港股代码格式：hk06160 -> rt_hk06160
    converted_symbols = []
    for s in symbols:
        if s.startswith("hk"):
            converted_symbols.append(f"rt_{s}")
        else:
            converted_symbols.append(s)
    
    url = f"https://hq.sinajs.cn/list={','.join(converted_symbols)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/"
    }
    
    try:
        with logger.audit_api_call("GET", url):
            response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
        response.encoding = 'gbk'
        
        results = {}
        lines = response.text.strip().split('\n')
        
        for i, line in enumerate(lines):
            if not line or '=' not in line:
                continue
            
            # 解析返回数据
            original_symbol = symbols[i] if i < len(symbols) else None
            if not original_symbol:
                continue
            
            # 提取引号内的数据
            match = re.search(r'"([^"]*)"', line)
            if not match:
                continue
            
            data = match.group(1).split(',')
            
            if original_symbol.startswith("hk"):
                # 港股数据格式不同
                if len(data) >= 9:
                    name = data[1]
                    price = float(data[6]) if data[6] else 0
                    prev_close = float(data[3]) if data[3] else 0
                    if prev_close > 0:
                        change_pct = round((price - prev_close) / prev_close * 100, 2)
                    else:
                        change_pct = 0
                    results[original_symbol] = {
                        "name": name,
                        "price": price,
                        "change_pct": change_pct
                    }
            else:
                # A股数据格式：名称,今开,昨收,现价,最高,最低,...
                if len(data) >= 4:
                    name = data[0]
                    prev_close = float(data[2]) if data[2] else 0
                    price = float(data[3]) if data[3] else 0
                    
                    if prev_close > 0:
                        change_pct = round((price - prev_close) / prev_close * 100, 2)
                    else:
                        change_pct = 0
                    
                    results[original_symbol] = {
                        "name": name,
                        "price": price,
                        "change_pct": change_pct
                    }
        
        return results
        
    except Exception as e:
        logger.error("获取实时行情失败", {"error": str(e)})
        return {}


def fetch_all_realtime_data():
    """获取所有ETF和成分股的实时数据"""
    
    logger.info("=" * 60)
    logger.info("获取ETF和成分股实时行情数据（新浪财经API）")
    logger.info("=" * 60)
    
    all_data = {}
    
    for etf_code, config in ETF_CONFIG.items():
        logger.info("开始处理ETF", {
            "code": etf_code,
            "name": config['name']
        })
        
        # 构建ETF代码
        etf_symbol = f"{config['market']}{etf_code}"
        
        # 构建成分股代码列表
        holding_symbols = []
        for h in config['holdings']:
            symbol = f"{h['market']}{h['code']}"
            holding_symbols.append(symbol)
        
        # 批量获取ETF + 成分股数据
        all_symbols = [etf_symbol] + holding_symbols
        quotes = fetch_realtime_quote_sina(all_symbols)
        
        # 提取ETF数据
        etf_quote = quotes.get(etf_symbol, {})
        etf_change = etf_quote.get('change_pct', 0)
        logger.info("ETF行情获取", {
            "code": etf_code,
            "etf_change_pct": etf_change
        })
        
        # 提取成分股数据
        holdings_data = []
        for h in config['holdings']:
            symbol = f"{h['market']}{h['code']}"
            quote = quotes.get(symbol, {})
            change = quote.get('change_pct', None)
            
            holdings_data.append({
                "name": h['name'],
                "ratio": h['ratio'],
                "change": change
            })
            
            if change is not None:
                logger.debug("成分股涨跌", {
                    "name": h['name'],
                    "change_pct": change
                })
            else:
                logger.debug("成分股无数据", {
                    "name": h['name']
                })
        
        all_data[etf_code] = {
            "name": config['name'],
            "etf_change": etf_change,
            "etf_price": etf_quote.get('price'),
            "holdings": holdings_data,
            "total_ratio": config.get('total_ratio', 0),
            "timestamp": datetime.now().isoformat()
        }
        
        time.sleep(REALTIME_DELAY)  # 避免请求过快
    
    return all_data


def format_change_html(change, with_sign=True):
    """格式化涨跌幅为HTML"""
    if change is None:
        return '--', '#9ca3af'
    
    if change > 0:
        text = f"+{change:.2f}%" if with_sign else f"{change:.2f}%"
        color = '#10b981'
    elif change < 0:
        text = f"{change:.2f}%"
        color = '#ef4444'
    else:
        text = "0.00%"
        color = '#9ca3af'
    
    return text, color


def update_html_etf_change(html_path, all_data):
    """更新HTML中的ETF日涨跌幅
    
    使用 BS4 定位元素，但只用 get_text/set_content 修改内容，
    不做完整的 str(soup) 写回（避免破坏 script 内容）。
    """
    import re as _re
    
    logger.info("=" * 60)
    logger.info("更新HTML中的ETF日涨跌幅")
    logger.info("=" * 60)
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    for etf_code, data in all_data.items():
        etf_change = data['etf_change']
        change_text, color = format_change_html(etf_change)
        
        # 使用字符串定位：找到 panel-{etf_code} 中的「日涨跌幅」后面紧跟的 info-value
        # 模式：<div class="info-label">日涨跌幅</div>\n<div class="info-value" ...>旧值</div>
        panel_marker = f'id="panel-{etf_code}"'
        panel_start = html_content.find(panel_marker)
        if panel_start == -1:
            logger.warn("未找到panel", {"etf_code": etf_code})
            continue
        
        # 在 panel 范围内查找日涨跌幅
        label_marker = '日涨跌幅</div>'
        label_pos = html_content.find(label_marker, panel_start)
        if label_pos == -1:
            logger.warn("未找到日涨跌幅标签", {"etf_code": etf_code})
            continue
        
        # 找到下一个 <div class="info-value"...>...</div>
        div_start = html_content.find('<div', label_pos)
        if div_start == -1:
            continue
        
        # 找到这个 div 的闭合
        div_end = html_content.find('</div>', div_start)
        if div_end == -1:
            continue
        div_end += len('</div>')
        
        # 提取旧 div 的 class 和其他属性
        old_div = html_content[div_start:div_end]
        class_match = _re.search(r'class="([^"]*)"', old_div)
        div_class = class_match.group(1) if class_match else 'info-value'
        
        # 构建新 div
        color_class = 'text-green' if color == '#10b981' else ('text-red' if color == '#ef4444' else 'text-amber')
        new_div = f'<div class="{div_class} {color_class}">{change_text}</div>'
        html_content = html_content[:div_start] + new_div + html_content[div_end:]
        
        logger.info("ETF涨跌幅更新", {
            "code": etf_code,
            "name": data['name'],
            "change": change_text
        })
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return html_path


def update_html_holdings_pie(html_path, all_data):
    """更新HTML中的持仓股饼图涨跌数据
    
    使用字符串定位和替换，不经过 BS4 序列化。
    """
    
    logger.info("=" * 60)
    logger.info("更新HTML中的持仓股饼图涨跌数据")
    logger.info("=" * 60)
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    for etf_code, data in all_data.items():
        chart_id = f"holdings-chart-{etf_code}"
        
        logger.info("处理饼图数据", {
            "code": etf_code,
            "name": data['name'],
            "chart_id": chart_id
        })

        
        # 构建新的数据数组
        data_items = []
        for h in data['holdings']:
            change = h['change']
            if change is not None:
                if change > 0:
                    change_text = f"+{change:.2f}%"
                    change_color = '#10b981'
                elif change < 0:
                    change_text = f"{change:.2f}%"
                    change_color = '#ef4444'
                else:
                    change_text = "0.00%"
                    change_color = '#9ca3af'
            else:
                change_text = '--'
                change_color = '#9ca3af'
            
            data_items.append(f"{{ name: '{h['name']}', value: {h['ratio']}, change: '{change_text}', changeColor: '{change_color}' }}")
            logger.debug("成分股数据", {
                "name": h['name'],
                "change": change_text
            })
        
        other_ratio = round(100 - data['total_ratio'], 2)
        if other_ratio > 0:
            data_items.append(f"{{ name: '其他', value: {other_ratio}, change: '--', changeColor: '#9ca3af' }}")
        
        new_data_array = "[\n                            " + ",\n                            ".join(data_items) + ",\n                        ]"
        
        # 用字符串定位：找到包含 getElementById('holdings-chart-{etf_code}') 的 script 块

        chart_marker = f"getElementById('{chart_id}')"
        chart_pos = html_content.find(chart_marker)
        if chart_pos == -1:
            logger.warn("未找到饼图", {"chart_id": chart_id})
            continue
        
        # 在 chart_pos 附近找到 const data = [...];
        search_start = max(0, chart_pos - 500)
        const_marker = 'const data = ['
        const_pos = html_content.find(const_marker, search_start)
        if const_pos == -1:
            logger.warn("未找到饼图数据", {"chart_id": chart_id})
            continue
        
        # 找到匹配的 ]; 结尾
        bracket_start = html_content.find('[', const_pos)
        depth = 0
        i = bracket_start
        while i < len(html_content):
            ch = html_content[i]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    # 检查后面是否有 ;
                    if end < len(html_content) and html_content[end] == ';':
                        end += 1
                    html_content = html_content[:const_pos] + f'const data = {new_data_array};' + html_content[end:]
                    break
            i += 1
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return html_path


def save_realtime_data(all_data, data_dir):
    """保存实时数据到JSON文件"""
    import os
    json_file = os.path.join(data_dir, "etf_realtime_data.json")
    with logger.audit_operation("file_io", f"write {json_file}"):
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(json_file)
    logger.audit("file_io", f"Realtime data saved: {json_file}", extra={"file_size_bytes": file_size, "etf_count": len(all_data)})
    logger.info("实时数据已保存", {"file": json_file})


def update_js_realtime_data(js_file, all_data):
    """更新JS文件中的实时行情数据"""
    
    # 构建新的实时数据JavaScript对象
    realtime_data_js = json.dumps(all_data, ensure_ascii=False, indent=8)
    new_realtime_data = f'const realtimeData = {realtime_data_js};'
    
    # 读取原始JS文件
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    # 找到realtimeData的位置并替换
    pattern = r'const realtimeData = \{.*?\};'
    
    # 使用正则替换（考虑多行）
    js_content = re.sub(pattern, new_realtime_data, js_content, flags=re.DOTALL)
    
    # 写回文件
    with open(js_file, 'w', encoding='utf-8') as f:
        f.write(js_content)
    
    return True


def main():
    """主函数"""
    import os
    
    # 获取skill根目录（scripts的父目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    
    # 定义文件路径
    data_dir = os.path.join(skill_dir, "data")
    
    # 1. 获取所有实时数据
    all_data = fetch_all_realtime_data()
    
    # 2. 保存实时数据
    save_realtime_data(all_data, data_dir)
    
    logger.info("=" * 60)
    logger.info("实时数据更新完成")
    logger.info("=" * 60)
    logger.info("完成信息", {
        "data_source": "新浪财经实时行情API",
        "update_content": "ETF日涨跌幅 + ETF实时价格 + 成分股当日涨跌",
        "injected_by": "update_report.py -> update_html_data"
    })
    

if __name__ == "__main__":
    main()
