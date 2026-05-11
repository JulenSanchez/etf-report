"""
analyze_checkpoint.py — 逃顶行为审计

三个真实顶部作为checkpoint，审计各preset在顶后首次调仓时的持仓变化。
逃顶标准：顶后首次调仓权重下降≥5% 或 从持仓→清仓，得1分，满分3分。

用法：
  python scripts/analyze_checkpoint.py
  python scripts/analyze_checkpoint.py --start 2023-01-01 --end 2026-05-08
"""
import sys
import argparse
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from run_scenarios import load_result, DEFAULT_START, DEFAULT_END, DEFAULT_PRESETS

TOPS = [
    ("卫星ETF", "159206", pd.Timestamp("2026-01-12")),
    ("有色ETF", "512400", pd.Timestamp("2026-01-29")),
    ("通信ETF", "515880", pd.Timestamp("2026-04-22")),
]


def get_weight_at(signals, code, date):
    """返回 date 时刻的持仓权重（date之前最近一次调仓）"""
    w = 0.0
    for s in signals:
        if pd.Timestamp(s["date"]) <= date:
            w = s["positions"].get(code, 0.0)
        else:
            break
    return w


def audit(presets, start, end):
    # 加载结果
    all_signals = {}
    for p in presets:
        _, signals = load_result(p, start, end)
        all_signals[p] = signals

    scores = {p: 0 for p in presets}

    for etf_name, etf_code, top_date in TOPS:
        print(f"\n{'='*68}")
        print(f"CHECKPOINT: {etf_name}({etf_code})  真实顶 {top_date.date()}")
        print(f"{'='*68}")
        print(f"  {'策略':<22} {'顶部权重':>9} {'顶后首调日':>12} {'调后权重':>9} {'变化':>8}  逃顶")
        print(f"  {'-'*66}")

        for preset, signals in all_signals.items():
            pre_w = get_weight_at(signals, etf_code, top_date)

            post_signals = [s for s in signals if pd.Timestamp(s["date"]) > top_date]
            if not post_signals:
                print(f"  {preset:<22} {pre_w:>8.1%}  (顶后无调仓记录)")
                continue

            first = post_signals[0]
            post_date = pd.Timestamp(first["date"])
            post_w    = first["positions"].get(etf_code, 0.0)
            delta     = post_w - pre_w
            days_gap  = (post_date - top_date).days

            escaped = (delta <= -0.05) or (pre_w > 0.01 and post_w == 0.0)
            flag = "YES ✓" if escaped else "---"
            if escaped:
                scores[preset] += 1

            print(f"  {preset:<22} {pre_w:>8.1%}  {str(post_date.date()):>12} {post_w:>8.1%} "
                  f"  {delta:>+7.1%}  {flag}  (+{days_gap}d)")

    # 汇总
    print(f"\n{'='*68}")
    print(f"CHECKPOINT 汇总  (满分 {len(TOPS)} 分)")
    print(f"{'='*68}")
    for preset in presets:
        s = scores[preset]
        bar = "★" * s + "☆" * (len(TOPS) - s)
        print(f"  {preset:<22} {bar}  {s}/{len(TOPS)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--presets", nargs="+", default=DEFAULT_PRESETS)
    parser.add_argument("--start",   default=DEFAULT_START)
    parser.add_argument("--end",     default=DEFAULT_END)
    args = parser.parse_args()
    audit(args.presets, args.start, args.end)
