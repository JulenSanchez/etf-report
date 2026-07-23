#!/usr/bin/env python3
"""
极端持仓分析器 — 分析回测中单一持仓（全部火力押一支 ETF）的极端集中事件。

核心定义：极端集中 = 调仓后只持有 1 支 ETF。
    这个定义与杠杆倍数/牛熊市无关：
    - 牛市 mbull=1.58 时单一持仓 158% → 极端集中
    - 熊市 mbear=0.54 时单一持仓 54% → 同样是 100% 的火力集中
    - 没有使用权重阈值（权重与杠杆耦合），只看持仓数量。

用途：preset promotion 的标准门禁。评估策略在押注单一方向时的正确性。

用法：
    python scripts/extreme_analyzer.py --preset gam-0 [--max-holdings 1] \
        [--start 2020-01-01] [--output research/params/extreme_gam-0.json]

输出：
    - JSON 文件：逐事件明细 + 按ETF汇总 + 裁决
    - 终端摘要：整体胜率、per-ETF 排名、需回避的 ETF 列表
"""

import argparse, json, sys
from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from quant_backtest import run_backtest

# ── helpers ──────────────────────────────────────────────────────────────

def _find_future_price(all_daily, code, from_date, offset_days):
    """返回 offset_days 个交易日后 ETF 的收盘价，若数据不足返回 None。"""
    df = all_daily.get(code)
    if df is None:
        return None
    future = df[df["date"] > from_date]
    if len(future) < offset_days:
        return None
    return float(future.iloc[offset_days - 1]["close"])


def _analyze(signals, all_daily, max_holdings=1):
    """
    从 signal_history 中提取极端集中事件。

    触发条件：调仓后持仓数 <= max_holdings（默认 1，即单一持仓）。

    返回:
        events: [{date, etf_code, etf_name, weight, total_exposure, n_holdings,
                  fwd_5d, fwd_10d, fwd_20d, ma_above, ...}]
        etf_summary: {code: {name, count, avg5d, avg10d, avg20d, win5d, win10d, win20d}}
        overall: {total_events, avg5d, avg10d, avg20d, win5d, win5d_pct, ...}
    """
    events = []
    etf_events = {}  # code -> list of event dicts

    for sig in signals:
        positions = sig.get("positions", {})
        if not positions:
            continue

        # 过滤幽灵零仓位 (MH=N 但离散化后某些仓位 round 到 0.00)
        effective = {k: v for k, v in positions.items() if v > 0.005}
        n_effective = len(effective)
        if n_effective == 0:
            continue
        if n_effective > max_holdings:
            continue

        date = sig["date"]
        total_exposure = sig.get("actual_exposure", sig.get("total_target", 0))

        # 取有效仓位中权重最大的
        max_code = max(effective, key=effective.get)
        max_weight = effective[max_code]

        # 前瞻价格
        f5d = _find_future_price(all_daily, max_code, date, 5)
        f10d = _find_future_price(all_daily, max_code, date, 10)
        f20d = _find_future_price(all_daily, max_code, date, 20)

        # 当日收盘价 (事件发生当天的执行价)
        entry_price = None
        df = all_daily.get(max_code)
        if df is not None:
            row = df[df["date"] == date]
            if len(row) > 0:
                entry_price = float(row["close"].iloc[0])

        ma_above = sig.get("ma_above", None)

        event = {
            "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
            "etf_code": max_code,
            "weight": round(max_weight, 4),
            "total_exposure": round(total_exposure, 4) if total_exposure else None,
            "n_holdings": n_effective,
            "n_raw": len(positions),
            "ma_above": ma_above,
        }

        for label, fwd_price in [("fwd_5d", f5d), ("fwd_10d", f10d), ("fwd_20d", f20d)]:
            if fwd_price is not None and entry_price is not None and entry_price > 0:
                event[label] = round((fwd_price / entry_price - 1) * 100, 2)
            else:
                event[label] = None

        events.append(event)
        etf_events.setdefault(max_code, []).append(event)

    # Per-ETF summary
    etf_summary = {}
    for code, evts in etf_events.items():
        name = evts[0].get("etf_name", "")
        fs = {"avg5d": "fwd_5d", "avg10d": "fwd_10d", "avg20d": "fwd_20d"}
        summary = {"code": code, "name": name, "count": len(evts)}
        for avg_key, fwd_key in fs.items():
            vals = [e[fwd_key] for e in evts if e.get(fwd_key) is not None]
            if vals:
                summary[avg_key] = round(np.mean(vals), 2)
                win_key = "win" + avg_key[-3:]
                summary[win_key] = "{}/{}".format(sum(1 for v in vals if v > 0), len(vals))
            else:
                summary[avg_key] = None
                win_key = "win" + avg_key[-3:]
                summary[win_key] = "0/0"
        etf_summary[code] = summary

    # Overall summary
    overall = {"total_events": len(events)}
    for fwd_key, label in [("fwd_5d", "5d"), ("fwd_10d", "10d"), ("fwd_20d", "20d")]:
        vals = [e[fwd_key] for e in events if e.get(fwd_key) is not None]
        if vals:
            overall["avg" + label] = round(np.mean(vals), 2)
            wins = sum(1 for v in vals if v > 0)
            overall["win" + label] = "{}/{}".format(wins, len(vals))
            overall["win" + label + "_pct"] = round(wins / len(vals) * 100, 1)
        else:
            overall["avg" + label] = None
            overall["win" + label] = "0/0"
            overall["win" + label + "_pct"] = 0.0

    return events, etf_summary, overall


def _classify_etfs(etf_summary, min_events=3):
    """
    按前瞻收益分类：

    safe:      avg20d > 0 且 win20d >= 50%
    caution:   avg20d > 0 但 win20d < 50%（或 mixed signal）
    danger:    avg20d < 0 且 win20d < 50%
    no_data:   事件数 < min_events，不足以判断
    """
    classified = {"safe": [], "caution": [], "danger": [], "no_data": []}
    for code, s in etf_summary.items():
        if s["count"] < min_events:
            classified["no_data"].append(s)
            continue
        if s.get("avg20d") is None:
            classified["no_data"].append(s)
            continue

        win_str = s.get("win20d", "0/1")
        wins_s, total_s = win_str.split("/")
        win_pct = int(wins_s) / int(total_s) * 100 if int(total_s) > 0 else 0

        if s["avg20d"] > 0 and win_pct >= 50:
            classified["safe"].append(s)
        elif s["avg20d"] > 0 and win_pct < 50:
            classified["caution"].append(s)
        elif s["avg20d"] < 0 and win_pct < 50:
            classified["danger"].append(s)
        else:
            # avg20d < 0 but win_pct >= 50 → mixed signal
            classified["caution"].append(s)

    for cat in classified:
        classified[cat].sort(key=lambda x: x.get("avg20d") or -999, reverse=True)

    return classified


def _verdict(classified, overall):
    """
    输出裁决：
    - pass:   无 danger ETF，且整体 avg20d > 0, win20d >= 50%
    - warn:   无 danger ETF，但存在 caution/no_data（需人工审阅）
    - block:  存在 danger ETF（集中押注历史性亏损方向）
    """
    if classified["danger"]:
        return "block", (
            "存在 {} 支历史性亏损 ETF，单一持仓押注这些标的时平均亏损".format(
                len(classified["danger"]))
        )
    if overall.get("win20d_pct", 0) < 50:
        return "warn", "整体 20d 胜率 < 50%，单一持仓的方向正确性存疑"
    if classified["caution"]:
        return "warn", "存在 {} 支信号混合的 ETF，需人工审阅".format(
            len(classified["caution"]))
    if classified["no_data"]:
        return "warn", "存在 {} 支样本不足的 ETF（<{} 次事件）".format(
            len(classified["no_data"]), 3)
    return "pass", "整体胜率高，无危险 ETF，单一持仓方向正确"


# ── main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="极端持仓分析 — 按单一持仓数（非权重）定义极端集中")
    parser.add_argument("--preset", type=str, default="gam-0",
                        help="预设配置名 (default: gam-0)")
    parser.add_argument("--start", type=str, default="2020-01-01",
                        help="回测起始日期 (default: 2020-01-01)")
    parser.add_argument("--end", type=str, default=None,
                        help="回测结束日期")
    parser.add_argument("--max-holdings", type=int, default=1,
                        help="触发阈值：持仓数 <= N 视为极端集中 (default: 1，即单一持仓)")
    parser.add_argument("--output", type=str, default=None,
                        help="输出 JSON 路径 (default: research/params/extreme_<preset>.json)")
    parser.add_argument("--min-events", type=int, default=3,
                        help="ETF 分类所需最少事件数 (default: 3)")
    args = parser.parse_args()

    preset = args.preset
    print("极端持仓分析 — {}".format(preset))
    print("  回测区间: {} ~ {}".format(args.start, args.end or "today"))
    print("  触发条件: 持仓数 <= {} (单一持仓 = 100% 火力集中)".format(args.max_holdings))

    # 1. 回测
    print("\n[1/3] 运行回测...")
    nav_df, signals, extra = run_backtest(
        start_date=args.start,
        end_date=args.end,
        preset=preset,
        return_data=True,
    )

    if nav_df is None or not signals:
        print("ERROR: 回测无数据")
        sys.exit(1)

    all_daily = extra.get("all_daily", {})
    if not all_daily:
        print("ERROR: 未获取到价格数据")
        sys.exit(1)

    # 加载 ETF 名称映射
    etf_names = {}
    try:
        from etf_report.core.quant_contract import load_universe_config
        universe = load_universe_config()
        for etf in universe.get("etfs", []):
            etf_names[etf["code"]] = etf.get("name", "")
    except Exception:
        pass

    # 2. 分析
    print("\n[2/3] 扫描单一持仓事件...")
    events, etf_summary, overall = _analyze(signals, all_daily, args.max_holdings)

    for evt in events:
        evt["etf_name"] = etf_names.get(evt["etf_code"], "")
    for summary in etf_summary.values():
        summary["name"] = etf_names.get(summary["code"], "")

    # Bull/bear 分布
    bull_events = [e for e in events if e.get("ma_above") is True]
    bear_events = [e for e in events if e.get("ma_above") is False]
    unknown_ma = [e for e in events if e.get("ma_above") is None]

    # 3. 分类 & 裁决
    print("\n[3/3] 分类 & 裁决...")
    classified = _classify_etfs(etf_summary, args.min_events)
    verdict, verdict_reason = _verdict(classified, overall)

    # ── 终端输出 ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("极端持仓分析结果（单一持仓 = 100% 火力集中）")
    print("=" * 60)
    print("  总事件数:      {}".format(overall["total_events"]))
    print("  牛市事件:      {}  熊市事件: {}  未知: {}".format(
        len(bull_events), len(bear_events), len(unknown_ma)))
    print("  整体 5d:       avg {:>7}%  胜率 {} ({:.0f}%)".format(
        str(overall.get("avg5d", "N/A")), overall.get("win5d", "N/A"),
        overall.get("win5d_pct", 0)))
    print("  整体 10d:      avg {:>7}%  胜率 {} ({:.0f}%)".format(
        str(overall.get("avg10d", "N/A")), overall.get("win10d", "N/A"),
        overall.get("win10d_pct", 0)))
    print("  整体 20d:      avg {:>7}%  胜率 {} ({:.0f}%)".format(
        str(overall.get("avg20d", "N/A")), overall.get("win20d", "N/A"),
        overall.get("win20d_pct", 0)))

    # Per-ETF
    all_etfs_sorted = sorted(
        etf_summary.values(),
        key=lambda x: x.get("avg20d") or -999,
        reverse=True,
    )
    print("\n  Per-ETF (avg20d desc, >={} events):".format(args.min_events))
    header = "  {:10s} {:16s} {:>4s} {:>7s} {:>7s} {:>7s} {:>8s}".format(
        "ETF", "Name", "N", "avg5d", "avg10d", "avg20d", "win20d")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for s in all_etfs_sorted:
        if s["count"] < args.min_events:
            continue
        line = "  {:<10s} {:<16s} {:4d} {:>7} {:>7} {:>7} {:>8s}".format(
            s["code"], s["name"], s["count"],
            str(s.get("avg5d") or "N/A"),
            str(s.get("avg10d") or "N/A"),
            str(s.get("avg20d") or "N/A"),
            s.get("win20d", "N/A"))
        print(line)

    # 分类
    def _fmt_items(items, fmt="name_win"):
        if fmt == "name_win":
            return ", ".join(
                "{}={}({})".format(s.get("name") or s["code"],
                                   s.get("avg20d") or "?",
                                   s.get("win20d", "0/0"))
                for s in items)
        return ", ".join(
            "{}={}(n={})".format(s.get("name") or s["code"],
                                 s.get("avg20d") or "?", s["count"])
            for s in items)

    print("\n  分类结果:")
    print("    SAFE     ({}):    {}".format(
        len(classified["safe"]), _fmt_items(classified["safe"])))
    if classified["caution"]:
        print("    CAUTION  ({}):  {}".format(
            len(classified["caution"]), _fmt_items(classified["caution"])))
    if classified["danger"]:
        print("    DANGER   ({}):   {}".format(
            len(classified["danger"]), _fmt_items(classified["danger"])))
    if classified["no_data"]:
        print("    NO_DATA  ({}):  {}".format(
            len(classified["no_data"]), _fmt_items(classified["no_data"], "count")))

    verdict_mark = {"pass": "PASS", "warn": "WARN", "block": "BLOCK"}
    print("\n  >>> 裁决: {}".format(verdict_mark.get(verdict, verdict)))
    print("  >>> {}".format(verdict_reason))

    # ── JSON 输出 ────────────────────────────────────────────────────────
    output_path = args.output
    if output_path is None:
        output_dir = PROJECT_ROOT / "research" / "params"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "extreme_{}.json".format(preset)

    last_date = str(nav_df["date"].iloc[-1].strftime("%Y-%m-%d"))
    result = {
        "preset": preset,
        "max_holdings": args.max_holdings,
        "method": "single_position = extreme concentration (leverage-invariant)",
        "backtest_start": args.start,
        "backtest_end": args.end or last_date,
        "overall": overall,
        "bull_bear_distribution": {
            "bull": len(bull_events),
            "bear": len(bear_events),
            "unknown": len(unknown_ma),
        },
        "classification": {
            "safe": classified["safe"],
            "caution": classified["caution"],
            "danger": classified["danger"],
            "no_data": classified["no_data"],
        },
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "events": events,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n  结果已保存: {}".format(output_path))

    return {"pass": 0, "warn": 1, "block": 2}.get(verdict, 1)


if __name__ == "__main__":
    sys.exit(main())
