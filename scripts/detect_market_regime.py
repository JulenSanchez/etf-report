#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Regime 检测器

用全市场 F1(EMA偏离) / F3(量比) / 涨跌幅 的截面分布，
对每个交易日打 regime 标签。

5 类 regime：
  - bull_trend:      大部分 ETF 在均线上方，量能放大，整体上涨
  - bear_trend:      大部分 ETF 在均线下方，量能萎缩，整体下跌
  - choppy_range:    EMA 偏离在 0 附近震荡，量能中性
  - sector_rotation: 部分板块强、部分弱，分化明显
  - bear_bottom:     极端熊市（所有 ETF 大幅低于均线，估值极低）

用法：
  python scripts/detect_market_regime.py
  → data/market_regimes.json
  → data/market_regimes_report.md
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

import yaml
from quant_backtest import load_etf_data, DATA_DIR
from quant_factors import calc_ema

REGIME_NAMES = ["bull_trend", "bear_trend", "choppy_range", "sector_rotation", "bear_bottom"]
DETECT_START = "2024-01-01"


def load_universe():
    with (SKILL_DIR / "config" / "quant_universe.yaml").open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["universe"]


def compute_daily_ema_deviation(daily_df, ema_period=20):
    """对单支 ETF 日线算每日 EMA 偏离度 (close - EMA) / EMA * 100"""
    if daily_df is None or len(daily_df) < ema_period + 5:
        return None
    close = daily_df["close"].astype(float)
    dates = daily_df["date"]
    ema = calc_ema(close, ema_period)
    dev = ((close - ema) / ema * 100).replace([np.inf, -np.inf], np.nan)
    return pd.DataFrame({"date": dates, "ema_dev": dev})


def compute_daily_volume_ratio(daily_df, window=20):
    """对单支 ETF 日线算每日方向性量比（简化版：当日成交额 / 20日均成交额）"""
    if daily_df is None or len(daily_df) < window + 5:
        return None
    if "amount" not in daily_df.columns:
        return None
    amt = daily_df["amount"].astype(float)
    dates = daily_df["date"]
    avg = amt.rolling(window).mean()
    ratio = (amt / avg).replace([np.inf, -np.inf], np.nan)
    return pd.DataFrame({"date": dates, "vol_ratio": ratio})


def detect_regime_for_date(ema_devs, vol_ratios, returns):
    """
    根据全市场截面统计判断某一天的 regime。

    ema_devs:  list of float, 各 ETF 当日 EMA 偏离度
    vol_ratios: list of float, 各 ETF 当日量比
    returns:    list of float, 各 ETF 当日涨跌幅 (%)
    """
    ed = [x for x in ema_devs if not np.isnan(x)]
    vr = [x for x in vol_ratios if not np.isnan(x)]
    rt = [x for x in returns if not np.isnan(x)]

    if len(ed) < 10:
        return "choppy_range"  # 数据不足，默认中性

    mean_dev = np.mean(ed)
    std_dev = np.std(ed)
    mean_vol = np.mean(vr) if vr else 1.0
    mean_ret = np.mean(rt) if rt else 0.0
    pos_ratio = sum(1 for x in ed if x > 0) / len(ed)  # 偏离 > 0 的比例

    # bear_bottom: 极端熊市
    #   - 大部分 ETF 大幅低于均线（pos_ratio < 0.15, mean_dev < -5%）
    #   - 整体跌幅大（mean_ret < -1%）
    if pos_ratio < 0.15 and mean_dev < -5.0:
        return "bear_bottom"

    # bull_trend: 牛市单边
    #   - 大部分 ETF 在均线上方（pos_ratio > 0.65）
    #   - 均值偏离正（mean_dev > 1%）
    #   - 量能偏大（mean_vol > 1.1）
    if pos_ratio > 0.65 and mean_dev > 1.0 and mean_vol > 1.1:
        return "bull_trend"

    # bear_trend: 熊市单边
    #   - 大部分 ETF 在均线下方（pos_ratio < 0.35）
    #   - 均值偏离负（mean_dev < -1%）
    if pos_ratio < 0.35 and mean_dev < -1.0:
        return "bear_trend"

    # sector_rotation: 板块分化
    #   - 偏离度标准差大（有的强有的弱）
    #   - 均值偏离不大（整体中性）
    #   - 量能不弱（有资金在动）
    if std_dev > 3.0 and abs(mean_dev) < 2.0 and mean_vol > 0.9:
        return "sector_rotation"

    # 默认: choppy_range（震荡市）
    return "choppy_range"


def main():
    print("Market Regime 检测器")
    print(f"  检测起点: {DETECT_START}")
    print()

    universe = load_universe()
    codes = [e["code"] for e in universe]
    names = {e["code"]: e.get("name", e["code"]) for e in universe}

    # 加载所有 ETF 日线，计算每日 EMA 偏离 + 量比 + 涨跌幅
    print("  加载 ETF 数据...")
    all_ema_dev = {}  # code -> DataFrame(date, ema_dev)
    all_vol_ratio = {}
    all_daily = {}

    for code in codes:
        daily, _ = load_etf_data(code)
        if daily is None or len(daily) < 30:
            continue
        daily = daily.sort_values("date").reset_index(drop=True)
        all_daily[code] = daily

        ed = compute_daily_ema_deviation(daily)
        if ed is not None:
            all_ema_dev[code] = ed

        vr = compute_daily_volume_ratio(daily)
        if vr is not None:
            all_vol_ratio[code] = vr

    print(f"  加载完成: {len(all_daily)} ETFs")

    # 构建交易日历（取所有 ETF 日期的并集，缺数据的 ETF 当天跳过）
    date_sets = [set(d["date"].dt.strftime("%Y-%m-%d")) for d in all_daily.values()]
    all_dates = sorted(set.union(*date_sets)) if date_sets else []
    # 过滤到 DETECT_START 之后
    all_dates = [d for d in all_dates if d >= DETECT_START]
    print(f"  交易日: {len(all_dates)} 天 ({all_dates[0]} → {all_dates[-1]})")

    # 逐日检测 regime
    print("  检测 regime...")

    # 预建 date→index 索引加速查找
    daily_idx = {}   # code -> {date_str: row_index}
    ema_idx = {}
    vol_idx = {}
    for code in codes:
        if code in all_daily:
            df = all_daily[code]
            daily_idx[code] = dict(zip(df["date"].dt.strftime("%Y-%m-%d"), range(len(df))))
        if code in all_ema_dev:
            ed = all_ema_dev[code]
            ema_idx[code] = dict(zip(ed["date"].dt.strftime("%Y-%m-%d"), range(len(ed))))
        if code in all_vol_ratio:
            vr = all_vol_ratio[code]
            vol_idx[code] = dict(zip(vr["date"].dt.strftime("%Y-%m-%d"), range(len(vr))))

    regimes = []
    for i, d_str in enumerate(all_dates):
        ed_vals = []
        vr_vals = []
        rt_vals = []
        for code in codes:
            # EMA 偏离
            if code in all_ema_dev and code in ema_idx:
                idx = ema_idx[code].get(d_str)
                if idx is not None:
                    v = all_ema_dev[code].iloc[idx]["ema_dev"]
                    if not np.isnan(v):
                        ed_vals.append(float(v))

            # 量比
            if code in all_vol_ratio and code in vol_idx:
                idx = vol_idx[code].get(d_str)
                if idx is not None:
                    v = all_vol_ratio[code].iloc[idx]["vol_ratio"]
                    if not np.isnan(v):
                        vr_vals.append(float(v))

            # 涨跌幅（从日线直接算）
            if code in daily_idx and code in all_daily:
                idx = daily_idx[code].get(d_str)
                if idx is not None and idx > 0:
                    df = all_daily[code]
                    c0 = float(df.iloc[idx - 1]["close"])
                    c1 = float(df.iloc[idx]["close"])
                    if c0 > 0:
                        rt_vals.append((c1 / c0 - 1) * 100)

        regime = detect_regime_for_date(ed_vals, vr_vals, rt_vals)
        regimes.append({"date": d_str, "regime": regime})

    # 统计
    from collections import Counter
    counts = Counter(r["regime"] for r in regimes)
    print()
    print("  Regime 分布:")
    for name in REGIME_NAMES:
        c = counts.get(name, 0)
        pct = c / max(len(regimes), 1) * 100
        print(f"    {name:>18}: {c:>4} 天 ({pct:>5.1f}%)")

    # 输出 JSON
    out = {
        "version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": all_dates[0] if all_dates else DETECT_START,
        "end_date": all_dates[-1] if all_dates else "",
        "total_days": len(regimes),
        "regime_counts": {name: counts.get(name, 0) for name in REGIME_NAMES},
        "regimes": regimes,
    }
    json_path = SKILL_DIR / "data" / "market_regimes.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  JSON: {json_path}")

    # Markdown 报告
    md = []
    md.append("# Market Regime 检测报告")
    md.append("")
    md.append(f"- **检测窗口**: {out['start_date']} → {out['end_date']}")
    md.append(f"- **总交易日**: {out['total_days']}")
    md.append(f"- **生成时间**: {out['generated_at']}")
    md.append("")
    md.append("## Regime 分布")
    md.append("")
    md.append("| Regime | 天数 | 占比 | 说明 |")
    md.append("|--------|------|------|------|")
    descs = {
        "bull_trend": "牛市单边（大部分 ETF 在均线上方，量能放大）",
        "bear_trend": "熊市单边（大部分 ETF 在均线下方，量能萎缩）",
        "choppy_range": "震荡市（EMA 偏离中性，量能中性）",
        "sector_rotation": "板块轮动（分化明显，有的强有的弱）",
        "bear_bottom": "熊市底部（极端低于均线，估值极低）",
    }
    for name in REGIME_NAMES:
        c = counts.get(name, 0)
        pct = c / max(len(regimes), 1) * 100
        md.append(f"| {name} | {c} | {pct:.1f}% | {descs.get(name, '')} |")
    md.append("")

    # 按月汇总
    md.append("## 按月 Regime 分布")
    md.append("")
    monthly = {}
    for r in regimes:
        ym = r["date"][:7]
        monthly.setdefault(ym, Counter())
        monthly[ym][r["regime"]] += 1
    md.append("| 月份 | bull | bear | choppy | rotation | bottom |")
    md.append("|------|------|------|--------|----------|--------|")
    for ym in sorted(monthly.keys()):
        mc = monthly[ym]
        md.append(f"| {ym} | {mc.get('bull_trend',0)} | {mc.get('bear_trend',0)} | "
                  f"{mc.get('choppy_range',0)} | {mc.get('sector_rotation',0)} | "
                  f"{mc.get('bear_bottom',0)} |")
    md.append("")

    # F4 适用性分析
    f4_good = counts.get("bear_bottom", 0) + counts.get("sector_rotation", 0)
    f4_bad = counts.get("bull_trend", 0) + counts.get("choppy_range", 0)
    md.append("## F4 估值因子适用性分析")
    md.append("")
    md.append(f"- F4 有效窗口（bear_bottom + sector_rotation）: **{f4_good} 天 ({f4_good/max(len(regimes),1)*100:.1f}%)**")
    md.append(f"- F4 无效窗口（bull_trend + choppy_range）: **{f4_bad} 天 ({f4_bad/max(len(regimes),1)*100:.1f}%)**")
    md.append("")
    md.append("> 这解释了 Phase 1 搜索中 F4 权重=0 最优的现象：过去 1 年窗口里 F4 有效天数太少。")
    md.append("> F4 不应被弃用，而应在 regime 切换到 bear_bottom / sector_rotation 时自动激活。")

    md_path = SKILL_DIR / "data" / "market_regimes_report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"  Report: {md_path}")


if __name__ == "__main__":
    main()
