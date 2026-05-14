#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比 F6 和 F7 的 NAV 曲线，分析交易行为差异。
用法：
    python compare_f6_f7.py
"""
import pandas as pd
import numpy as np

F6_CSV = "data/quant_results/backtest_nav_f6.csv"
F7_CSV = "data/quant_results/backtest_nav.csv"  # F7 的数据

def main():
    df6 = pd.read_csv(F6_CSV, parse_dates=["date"])
    df7 = pd.read_csv(F7_CSV, parse_dates=["date"])

    # 按日期对齐
    merged = pd.merge(df6, df7, on="date", suffixes=("_f6", "_f7"), how="inner")
    merged = merged.sort_values("date").reset_index(drop=True)

    # 计算每日 NAV 差值（F6 - F7，百分比）
    merged["nav_diff_pct"] = merged["nav_pct_f6"] - merged["nav_pct_f7"]
    merged["nav_diff_abs"] = merged["nav_f6"] - merged["nav_f7"]

    print("=" * 60)
    print("F6 vs F7 交易行为对比分析")
    print("=" * 60)

    # 1. 整体统计
    print("\n【1】整体 NAV 对比")
    print(f"  F6 最终 NAV:     {merged['nav_f6'].iloc[-1]:,.0f} ({merged['nav_pct_f6'].iloc[-1]:+.2f}%)")
    print(f"  F7 最终 NAV:     {merged['nav_f7'].iloc[-1]:,.0f} ({merged['nav_pct_f7'].iloc[-1]:+.2f}%)")
    print(f"  NAV 差值（F6-F7): {merged['nav_diff_abs'].iloc[-1]:,.0f} ({merged['nav_diff_pct'].iloc[-1]:+.2f}%)")

    # 2. 最大回撤
    for label, col in [("F6", "nav_pct_f6"), ("F7", "nav_pct_f7")]:
        nav = merged[col]
        peak = nav.cummax()
        dd = (nav - peak) / peak * 100
        max_dd = dd.min()
        dd_date = merged.loc[dd.idxmin(), "date"]
        print(f"  {label} 最大回撤:     {max_dd:.2f}% (日期: {dd_date.date()})")

    # 3. 找 F6 明显领先和落后的区间
    print("\n【2】关键分化区间（NAV 差值扩大/缩小）")
    merged["diff_ma20"] = merged["nav_diff_pct"].rolling(20).mean()
    # 找差值快速扩大的区间
    merged["diff_accel"] = merged["nav_diff_pct"].diff(20)
    top_accel = merged.nlargest(10, "diff_accel")[["date", "nav_diff_pct", "diff_accel", "holdings_f6", "holdings_f7"]]
    print("  F6 加速领先 top 10（每20日差值变化）:")
    for _, r in top_accel.iterrows():
        print(f"    {r['date'].date()}: 差值={r['nav_diff_pct']:+.2f}%, 20日变化={r['diff_accel']:+.2f}%, F6持仓={r['holdings_f6']}支, F7持仓={r['holdings_f7']}支")

    # 4. 持仓对比
    print("\n【3】持仓数量对比")
    merged["holdings_diff"] = merged["holdings_f6"] - merged["holdings_f7"]
    print(f"  F6 平均持仓: {merged['holdings_f6'].mean():.1f} 支")
    print(f"  F7 平均持仓: {merged['holdings_f7'].mean():.1f} 支")
    print(f"  F6 平均现金比例: {merged['cash_f6'].mean():.1f}%")
    print(f"  F7 平均现金比例: {merged['cash_f7'].mean():.1f}%")

    # 5. 关键日期的 NAV 对比（从回测输出中提取的快照日期）
    snap_dates = [
        "2024-09-25", "2024-10-30",  # 2024.9-10 极端行情
        "2025-01-23",  # 1月顶部
        "2025-04-28",  # 4月调整
        "2026-01-21",  # 2026.1 顶部
        "2026-04-24",  # 4月顶部
    ]
    print("\n【4】关键日期 NAV 对比")
    for d in snap_dates:
        row = merged[merged["date"] == d]
        if not row.empty:
            r = row.iloc[0]
            print(f"  {d}: F6={r['nav_pct_f6']:+.2f}%, F7={r['nav_pct_f7']:+.2f}%, 差值={r['nav_diff_pct']:+.2f}%")

    # 6. 保存详细对比 CSV
    out = "data/quant_results/backtest_f6_vs_f7_detail.csv"
    merged.to_csv(out, index=False)
    print(f"\n详细对比数据已保存: {out}")
    print("=" * 60)

if __name__ == "__main__":
    main()
