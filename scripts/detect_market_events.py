#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-183 Layer 1: 主升 / 大跌事件检测器

设计：
  - 对每支 ETF（清洗后日线）找出"局部高点"和"局部低点"
  - 识别"涨段"（trough → peak）和"跌段"（peak → trough）
  - 用涨幅/时长/中途回撤/量能/EMA 偏离等多因子过滤，留下"涌现型"大行情
  - 输出 JSON 事件清单 + Markdown 可读报告

用法：
  python scripts/detect_market_events.py
  → data/market_events.json
  → data/market_events_report.md
"""

import io
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_backtest import load_etf_data
from data_cleaning import run_data_cleaning_pipeline

# ============================================================
# 阈值参数（基于 515880/512400 标杆案例校准）
# ============================================================

# 主升浪 (RALLY)
RALLY_MIN_GAIN_PCT       = 20.0    # 累计涨幅 ≥ 20%
RALLY_MIN_DAYS           = 15      # 持续 ≥ 15 个交易日（约 3 周）
RALLY_MAX_DAYS           = 90      # 持续 ≤ 90 天（避免长期慢牛）
RALLY_MAX_INTERIM_DD_PCT = 10.0    # 区间内最大回撤 ≤ 10%
RALLY_MIN_VOL_RATIO      = 1.20    # 区间日均量 / 区间前 30 天日均量 ≥ 1.2 (放量确认)

# 大跌 (CRASH)
CRASH_MIN_DROP_PCT       = 15.0    # 累计跌幅 ≥ 15%
CRASH_MIN_DAYS           = 10      # 持续 ≥ 10 个交易日
CRASH_MAX_DAYS           = 60      # 持续 ≤ 60 天
CRASH_MAX_INTERIM_RISE_PCT = 7.0   # 区间内最大反弹 ≤ 7%

# 全局
DETECT_START_DATE = "2024-04-01"   # 事件识别窗口起点（覆盖近 2 年）
PEAK_DETECT_WINDOW = 5             # 局部极值识别窗口（左右各 5 个交易日，共 11 天）

# ============================================================
# Helpers
# ============================================================

def load_corporate_action_events():
    path = SKILL_DIR / "data" / "corporate_action_events.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("events_by_code", {}) or {}


def load_clean_daily(code, events_by_code):
    """加载并清洗 ETF 日线数据。"""
    daily, _ = load_etf_data(code)
    if daily is None:
        return None
    events = events_by_code.get(code) or []
    if not events:
        return daily

    ci = {
        "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in daily["date"]],
        "kline": [[float(r["open"]), float(r["close"]), float(r["low"]), float(r["high"])]
                  for _, r in daily.iterrows()],
        "volumes": [int(v) for v in daily["volume"]] if "volume" in daily.columns else [],
    }
    cleaned = run_data_cleaning_pipeline(ci, events)
    out = daily.copy().reset_index(drop=True)
    for idx in range(len(out)):
        if idx < len(cleaned["kline"]):
            o, c, l, h = cleaned["kline"][idx]
            out.at[idx, "open"]  = o
            out.at[idx, "close"] = c
            out.at[idx, "low"]   = l
            out.at[idx, "high"]  = h
        if idx < len(cleaned["volumes"]) and "volume" in out.columns:
            out.at[idx, "volume"] = cleaned["volumes"][idx]
    return out


def find_local_extrema(prices, window=PEAK_DETECT_WINDOW):
    """找出局部高点 / 低点的索引。

    定义：在 [i-window, i+window] 区间内，prices[i] 是最大值（局部高点）或最小值（局部低点）

    边界处理：
      - 数据末尾 window 天内的高点用更短的右窗口（自适应：右窗口 = min(window, n-1-i)）
      - 这是关键改进：避免漏掉"最近正在发生的"高点（如 515880 4/22 见顶）
      - 数据开头同理（左窗口自适应）
    """
    n = len(prices)
    peaks = []
    troughs = []

    for i in range(1, n - 1):
        left_w  = min(window, i)
        right_w = min(window, n - 1 - i)

        # 边界点至少要有 1 边能比较，跳过两端各 1 个点
        if left_w == 0 or right_w == 0:
            continue

        win = prices[i - left_w: i + right_w + 1]
        is_peak = (
            prices[i] == max(win)
            and prices[i] > prices[i - left_w]
            and prices[i] > prices[i + right_w]
        )
        is_trough = (
            prices[i] == min(win)
            and prices[i] < prices[i - left_w]
            and prices[i] < prices[i + right_w]
        )
        if is_peak:
            peaks.append(i)
        elif is_trough:
            troughs.append(i)
    return peaks, troughs


# ============================================================
# Event detection
# ============================================================

def detect_rallies(df, code):
    """检测主升浪事件。

    算法：枚举 (trough, peak) 对，trough < peak 且 trough 在 detect 窗口内。
    应用 4 重过滤：涨幅 / 时长 / 中途回撤 / 量能放大。
    去重：同一波涨势的多个 (trough, peak) 候选只保留一个（涨幅最大的）。
    """
    closes = df["close"].astype(float).tolist()
    dates = df["date"].tolist()

    # 用 high 作为 peak 价、low 作为 trough 价能更精确，但 close 更代表"收盘事实"
    peaks, troughs = find_local_extrema(closes)

    rallies = []
    for t_idx in troughs:
        if dates[t_idx] < pd.Timestamp(DETECT_START_DATE):
            continue
        for p_idx in peaks:
            if p_idx <= t_idx:
                continue
            duration = (dates[p_idx] - dates[t_idx]).days
            trading_days = p_idx - t_idx
            if trading_days < RALLY_MIN_DAYS or trading_days > 130:
                continue  # 130 个交易日 ≈ 6 个月

            gain = (closes[p_idx] / closes[t_idx] - 1) * 100
            if gain < RALLY_MIN_GAIN_PCT:
                continue

            # 区间内最大回撤
            seg_closes = closes[t_idx: p_idx + 1]
            running_max = seg_closes[0]
            max_dd = 0
            for c in seg_closes:
                running_max = max(running_max, c)
                dd = (c / running_max - 1) * 100
                max_dd = min(max_dd, dd)
            if max_dd < -RALLY_MAX_INTERIM_DD_PCT:
                continue

            # 量能放大：区间日均成交量 / 区间前 30 天日均成交量
            vol_ratio = None
            if "volume" in df.columns:
                seg_vol = df["volume"].iloc[t_idx: p_idx + 1].astype(float).mean()
                pre_start = max(0, t_idx - 30)
                pre_vol = df["volume"].iloc[pre_start: t_idx].astype(float).mean()
                if pre_vol > 0:
                    vol_ratio = seg_vol / pre_vol
                    if vol_ratio < RALLY_MIN_VOL_RATIO:
                        continue

            rallies.append({
                "code": code,
                "type": "rally",
                "trough_date": dates[t_idx].strftime("%Y-%m-%d"),
                "peak_date": dates[p_idx].strftime("%Y-%m-%d"),
                "duration_days": duration,
                "trading_days": trading_days,
                "gain_pct": round(gain, 2),
                "max_interim_dd_pct": round(max_dd, 2),
                "vol_amplify": round(vol_ratio, 2) if vol_ratio else None,
                "trough_price": round(closes[t_idx], 4),
                "peak_price": round(closes[p_idx], 4),
            })

    # 去重策略：按 peak_date 分组，每个 peak 只留最佳起点
    # "最佳"定义：涨幅 / 时长 比值最大（即"最陡的爬升")，这样能找到真正的"主升段"而非"完整慢牛"
    grouped = {}
    for r in rallies:
        key = r["peak_date"]
        slope = r["gain_pct"] / max(r["trading_days"], 1)
        if key not in grouped or slope > grouped[key]["_slope"]:
            r["_slope"] = slope
            grouped[key] = r
    deduped = list(grouped.values())

    # 第二轮去重：相邻 peak（同一波行情可能识别出几个相近的 peak）合并
    # 策略：按 peak_date 排序，若两个 peak 在 30 天内，保留涨幅大的
    deduped.sort(key=lambda x: x["peak_date"])
    merged = []
    for r in deduped:
        if not merged:
            merged.append(r)
            continue
        last = merged[-1]
        days_apart = (pd.Timestamp(r["peak_date"]) - pd.Timestamp(last["peak_date"])).days
        if days_apart <= 30:
            # 同一波，保留涨幅大的
            if r["gain_pct"] > last["gain_pct"]:
                merged[-1] = r
        else:
            merged.append(r)

    for r in merged:
        r.pop("_slope", None)
    return merged


def detect_crashes(df, code):
    """检测大跌事件。镜像版本 of detect_rallies。"""
    closes = df["close"].astype(float).tolist()
    dates = df["date"].tolist()

    peaks, troughs = find_local_extrema(closes)

    crashes = []
    for p_idx in peaks:
        if dates[p_idx] < pd.Timestamp(DETECT_START_DATE):
            continue
        for t_idx in troughs:
            if t_idx <= p_idx:
                continue
            duration = (dates[t_idx] - dates[p_idx]).days
            trading_days = t_idx - p_idx
            if trading_days < CRASH_MIN_DAYS or trading_days > 90:
                continue

            drop = (closes[t_idx] / closes[p_idx] - 1) * 100  # 负数
            if drop > -CRASH_MIN_DROP_PCT:
                continue

            # 区间内最大反弹
            seg_closes = closes[p_idx: t_idx + 1]
            running_min = seg_closes[0]
            max_rise = 0
            for c in seg_closes:
                running_min = min(running_min, c)
                rise = (c / running_min - 1) * 100
                max_rise = max(max_rise, rise)
            if max_rise > CRASH_MAX_INTERIM_RISE_PCT:
                continue

            crashes.append({
                "code": code,
                "type": "crash",
                "peak_date": dates[p_idx].strftime("%Y-%m-%d"),
                "trough_date": dates[t_idx].strftime("%Y-%m-%d"),
                "duration_days": duration,
                "trading_days": trading_days,
                "drop_pct": round(drop, 2),
                "max_interim_rise_pct": round(max_rise, 2),
                "peak_price": round(closes[p_idx], 4),
                "trough_price": round(closes[t_idx], 4),
            })

    # 去重策略：按 trough_date 分组，每个 trough 只留最佳起点（跌得最陡）
    grouped = {}
    for c in crashes:
        key = c["trough_date"]
        slope = abs(c["drop_pct"]) / max(c["trading_days"], 1)
        if key not in grouped or slope > grouped[key]["_slope"]:
            c["_slope"] = slope
            grouped[key] = c
    deduped = list(grouped.values())

    # 第二轮去重：相邻 trough 合并
    deduped.sort(key=lambda x: x["trough_date"])
    merged = []
    for c in deduped:
        if not merged:
            merged.append(c)
            continue
        last = merged[-1]
        days_apart = (pd.Timestamp(c["trough_date"]) - pd.Timestamp(last["trough_date"])).days
        if days_apart <= 30:
            # 同一波下跌，保留跌幅大的
            if c["drop_pct"] < last["drop_pct"]:
                merged[-1] = c
        else:
            merged.append(c)

    for c in merged:
        c.pop("_slope", None)
    return merged


# ============================================================
# Main
# ============================================================

def main():
    print("Layer 1: 主升 / 大跌事件检测")
    print(f"  检测窗口：{DETECT_START_DATE} → 今天")
    print(f"  主升浪条件：涨幅 ≥ {RALLY_MIN_GAIN_PCT}% / 时长 {RALLY_MIN_DAYS}+ 交易日 / 中途回撤 ≤ {RALLY_MAX_INTERIM_DD_PCT}% / 量比 ≥ {RALLY_MIN_VOL_RATIO}")
    print(f"  大跌条件：跌幅 ≥ {CRASH_MIN_DROP_PCT}% / 时长 {CRASH_MIN_DAYS}+ 交易日 / 中途反弹 ≤ {CRASH_MAX_INTERIM_RISE_PCT}%")
    print()

    # 加载 universe
    import yaml
    with (SKILL_DIR / "config" / "quant_universe.yaml").open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    universe = cfg["universe"]
    name_map = {e["code"]: e.get("name", e["code"]) for e in universe}
    sector_map = {e["code"]: e.get("sector", "") for e in universe}

    events_by_code = load_corporate_action_events()

    all_rallies = []
    all_crashes = []
    for etf in universe:
        code = etf["code"]
        df = load_clean_daily(code, events_by_code)
        if df is None or len(df) < 100:
            continue
        rallies = detect_rallies(df, code)
        crashes = detect_crashes(df, code)
        all_rallies.extend(rallies)
        all_crashes.extend(crashes)
        if rallies or crashes:
            print(f"  {code} {name_map[code]}: {len(rallies)} 主升 / {len(crashes)} 大跌")

    print()
    print(f"✓ 完成: {len(all_rallies)} 个主升浪 + {len(all_crashes)} 个大跌段")

    # 输出 JSON
    out_json = {
        "version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "detection_window_start": DETECT_START_DATE,
        "thresholds": {
            "rally_min_gain_pct": RALLY_MIN_GAIN_PCT,
            "rally_min_days": RALLY_MIN_DAYS,
            "rally_max_interim_dd_pct": RALLY_MAX_INTERIM_DD_PCT,
            "rally_min_vol_amplify": RALLY_MIN_VOL_RATIO,
            "crash_min_drop_pct": CRASH_MIN_DROP_PCT,
            "crash_min_days": CRASH_MIN_DAYS,
            "crash_max_interim_rise_pct": CRASH_MAX_INTERIM_RISE_PCT,
        },
        "rallies": sorted(all_rallies, key=lambda x: x["trough_date"]),
        "crashes": sorted(all_crashes, key=lambda x: x["peak_date"]),
    }
    json_path = SKILL_DIR / "data" / "market_events.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(out_json, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")

    # Markdown 报告
    md = []
    md.append("# Layer 1: 主升 / 大跌事件清单")
    md.append("")
    md.append(f"- **检测窗口**：{DETECT_START_DATE} → 今天")
    md.append(f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"- **主升浪**：共 {len(all_rallies)} 个")
    md.append(f"- **大跌段**：共 {len(all_crashes)} 个")
    md.append("")
    md.append("**判定阈值**：")
    md.append(f"- 主升浪：涨幅 ≥ {RALLY_MIN_GAIN_PCT}% / 时长 ≥ {RALLY_MIN_DAYS} 交易日 / 中途回撤 ≤ {RALLY_MAX_INTERIM_DD_PCT}% / 量能放大 ≥ {RALLY_MIN_VOL_RATIO}x")
    md.append(f"- 大跌段：跌幅 ≥ {CRASH_MIN_DROP_PCT}% / 时长 ≥ {CRASH_MIN_DAYS} 交易日 / 中途反弹 ≤ {CRASH_MAX_INTERIM_RISE_PCT}%")
    md.append("")
    md.append("**Review 提示**：检查下表是否漏掉你认为的关键事件，或多识别了不算大行情的小波动。如有偏差，可调整阈值。")
    md.append("")

    md.append("## 主升浪 (rally)")
    md.append("")
    md.append("| 标的 | 名称 | 板块 | 起 (低点) | 止 (高点) | 涨幅 | 交易日 | 中途回撤 | 量比 |")
    md.append("|------|------|------|-----------|-----------|------|--------|---------|------|")
    for r in sorted(all_rallies, key=lambda x: (-x["gain_pct"])):
        vol = f"{r['vol_amplify']}x" if r['vol_amplify'] else "-"
        md.append(f"| {r['code']} | {name_map.get(r['code'], '')} | {sector_map.get(r['code'], '')} "
                  f"| {r['trough_date']} | {r['peak_date']} | **+{r['gain_pct']}%** "
                  f"| {r['trading_days']} | {r['max_interim_dd_pct']}% | {vol} |")
    md.append("")

    md.append("## 大跌段 (crash)")
    md.append("")
    md.append("| 标的 | 名称 | 板块 | 起 (高点) | 止 (低点) | 跌幅 | 交易日 | 中途反弹 |")
    md.append("|------|------|------|-----------|-----------|------|--------|---------|")
    for c in sorted(all_crashes, key=lambda x: x["drop_pct"]):
        md.append(f"| {c['code']} | {name_map.get(c['code'], '')} | {sector_map.get(c['code'], '')} "
                  f"| {c['peak_date']} | {c['trough_date']} | **{c['drop_pct']}%** "
                  f"| {c['trading_days']} | +{c['max_interim_rise_pct']}% |")
    md.append("")

    md.append("---")
    md.append("")
    md.append("## 标杆案例验证")
    md.append("")
    md.append("以下三个案例是用户提供的标杆，必须被识别出来：")
    md.append("")
    md.append("- **515880 通信** ~2026-04 见顶")
    md.append("- **512400 有色** ~2026-01 底见顶")
    md.append("- **159206 卫星** ~2026-01 见顶（用户没参与）")
    md.append("")
    benchmarks = [
        ("515880", "2026-04"),
        ("512400", "2026-01"),
        ("159206", "2026-01"),
    ]
    for code, ym in benchmarks:
        hits = [r for r in all_rallies if r["code"] == code and r["peak_date"].startswith(ym)]
        if hits:
            md.append(f"- ✅ **{code}** {ym}: 识别到 {len(hits)} 个主升浪 (peak_date={hits[0]['peak_date']}, gain={hits[0]['gain_pct']}%)")
        else:
            md.append(f"- ❌ **{code}** {ym}: 未识别到主升浪 (可能阈值太严)")
    md.append("")

    md_path = SKILL_DIR / "data" / "market_events_report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"  Report: {md_path}")
    print()
    print("→ 请 review market_events_report.md 确认事件是否合理，再进入 Layer 2 评分")


if __name__ == "__main__":
    main()
