"""
analyze_turnover.py — 换仓次数 + 缩仓行为分析

1. 统计总调仓次数、实际换仓次数、空转次数
2. 用 total_target < 0.6 定义"低仓位日"，列出日频具体日期
"""
import sys
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from run_scenarios import load_result, DEFAULT_START, DEFAULT_END, DEFAULT_PRESETS


def analyze(presets, start, end):
    start_ts = pd.Timestamp(start)
    end_ts   = pd.Timestamp(end)
    days_span = (end_ts - start_ts).days

    for preset in presets:
        nav_df, signals = load_result(preset, start, end)

        total_rebal  = len(signals)
        changed      = 0
        no_change    = 0
        turnover_list = []
        prev_pos     = {}

        low_pos_days = []   # total_target < 0.6 的调仓记录

        for s in signals:
            cur_pos    = s["positions"]
            total_w    = s.get("total_target", sum(cur_pos.values()))
            confidence = s.get("avg_confidence", None)

            # 换手幅度
            all_codes = set(prev_pos) | set(cur_pos)
            turnover  = sum(abs(cur_pos.get(c, 0) - prev_pos.get(c, 0)) for c in all_codes) / 2
            turnover_list.append(turnover)

            if turnover > 0.01:
                changed += 1
            else:
                no_change += 1

            if total_w < 0.60:
                low_pos_days.append({
                    "date": pd.Timestamp(s["date"]).date(),
                    "total_w": total_w,
                    "confidence": confidence,
                    "holdings": len([v for v in cur_pos.values() if v > 0.01]),
                })

            prev_pos = cur_pos

        avg_turnover = np.mean(turnover_list) if turnover_list else 0

        print(f"{'='*60}")
        print(f"策略: {preset}")
        print(f"{'='*60}")
        print(f"  回测天数:          {days_span} 天")
        print(f"  总调仓次数:        {total_rebal}")
        print(f"  平均调仓频率:      每 {days_span/max(total_rebal,1):.1f} 天一次")
        print(f"  实际换仓次数:      {changed}  ({changed/max(total_rebal,1):.0%} 有实际变化)")
        print(f"  空转次数:          {no_change}  (score_band拦截，持仓不变)")
        print(f"  平均单次换手幅度:  {avg_turnover:.1%}")

        print(f"\n  低仓位日（total_target < 60%）: 共 {len(low_pos_days)} 次")
        if low_pos_days:
            print(f"  {'日期':<12} {'总仓位':>8} {'置信度':>8} {'持仓数':>6}")
            print(f"  {'-'*38}")
            for r in low_pos_days:
                conf_str = f"{r['confidence']:.2f}" if r['confidence'] is not None else "  N/A"
                print(f"  {str(r['date']):<12} {r['total_w']:>7.0%} {conf_str:>8} {r['holdings']:>6}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--presets", nargs="+", default=DEFAULT_PRESETS)
    parser.add_argument("--start",   default=DEFAULT_START)
    parser.add_argument("--end",     default=DEFAULT_END)
    args = parser.parse_args()
    analyze(args.presets, args.start, args.end)
