#!/usr/bin/env python3
"""ETF contribution analysis — reads cached backtest, applies framework rules.

Usage: python scripts/analyze_contributions.py
Requires: a completed backtest (disk cache at data/quant/cache/last_backtest.json)
"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")

CACHE_PATH = __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "quant" / "cache" / "last_backtest.json"


def load():
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    cache = load()
    result = cache["result"]
    contribs = result.get("etfContributions", {})
    summary = result.get("summary", {})
    sh = result.get("signalHistory", [])
    total = len(sh)

    print(f"=== 回测概况 ===")
    print(f"区间: {summary.get('startDate')} ~ {summary.get('endDate')}")
    print(f"信号数: {total} | 总收益: {summary.get('totalReturn',0):+.1f}% | 超额: {summary.get('excessReturn',0):+.1f}%")
    print(f"年化: {summary.get('annualReturn',0):+.1f}% | MDD: {summary.get('maxDrawdown',0):.1f}% | Sharpe: {summary.get('sharpe',0):.2f}")
    print()

    # ── 观察期 ──
    obs = {k: v for k, v in contribs.items() if v.get("observation")}
    if obs:
        print("=== 观察期 ETF ===")
        for code, c in obs.items():
            print(f"  {code} {c['name']}: 仅 {c.get('tradingDays', 0)} 交易日 · 暂不参与排名")
        print()

    # ── 核心品种 ──
    print("=== 核心品种 (选中率 >20%) ===")
    core = sorted(
        [(k, v) for k, v in contribs.items() if v.get("selectionRate", 0) > 20 and not v.get("observation")],
        key=lambda x: -x[1]["selectionRate"])
    for code, c in core:
        print(f"  {code} {c['name']:<10} 选中={c['selectionRate']}% 均权={c['avgWeight']}% 持有={c['avgHoldDays']}d 笔数={c['tradeCount']} 胜率={c['winRate']}% 赔率={c['payoffRatio']} 盈亏={c['totalPnlPct']:+.0f}% 趋势={c['trend']}")

    # ── 精准狙击手 ──
    snipers = sorted(
        [(k, v) for k, v in contribs.items() if 0 < v.get("selectionRate", 0) < 10 and v.get("payoffRatio", 0) > 2.5 and not v.get("observation")],
        key=lambda x: -x[1]["payoffRatio"])
    if snipers:
        print("\n=== 精准狙击手 (选中率<10%, 赔率>2.5) ===")
        for code, c in snipers:
            print(f"  {code} {c['name']:<10} 选中={c['selectionRate']}% 均权={c['avgWeight']}% 赔率={c['payoffRatio']} 盈亏={c['totalPnlPct']:+.0f}% 胜率={c['winRate']}%")

    # ── 趋势下降 ──
    declining = sorted(
        [(k, v) for k, v in contribs.items() if v.get("trend") == "declining" and v.get("selectionRate", 0) > 5 and not v.get("observation")],
        key=lambda x: -x[1]["selectionRate"])
    print("\n=== 趋势下降 (策略关注度衰减) ===")
    for code, c in declining[:8]:
        print(f"  {code} {c['name']:<10} 选中={c['selectionRate']}% ↓ | 盈亏={c['totalPnlPct']:+.0f}%")

    # ── 趋势上升 ──
    rising = sorted(
        [(k, v) for k, v in contribs.items() if v.get("trend") == "rising" and v.get("selectionRate", 0) > 3 and not v.get("observation")],
        key=lambda x: -x[1]["selectionRate"])
    print("\n=== 趋势上升 (策略关注度增长) ===")
    for code, c in rising[:8]:
        print(f"  {code} {c['name']:<10} 选中={c['selectionRate']}% ↑ | 盈亏={c['totalPnlPct']:+.0f}% 赔率={c['payoffRatio']}")

    # ── 淘汰候选 ──
    print("\n=== 淘汰候选 ===")
    for code, c in contribs.items():
        if c.get("observation"):
            continue
        sel = c.get("selectionRate", 0)
        pnl = c.get("totalPnlPct", 0)
        trend = c.get("trend", "")
        if trend == "declining" and sel < 3 and pnl < 0:
            print(f"  {code} {c['name']:<10} 边缘+负收益: 选中={sel}% 盈亏={pnl:+.0f}% 扇区={c['sector']}")
        if sel > 10 and pnl < -30:
            print(f"  {code} {c['name']:<10} 频繁亏损: 选中={sel}% 盈亏={pnl:+.0f}% 笔数={c['tradeCount']}")

    # ── 扇区领导者 ──
    print("\n=== 扇区领导者 (份额 >40%) ===")
    for code, c in sorted(contribs.items(), key=lambda x: -x[1].get("sectorShare", 0)):
        ss = c.get("sectorShare", 0)
        if ss > 40 and c.get("selectionRate", 0) > 5 and not c.get("observation"):
            print(f"  {c['sector']:<8} {code} {c['name']:<10} 份额={ss}% 选中={c['selectionRate']}%")


    # ── 成分股重叠分析 ──
    meta_path = __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "quant" / "etf_metadata.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        print("\n=== 成分股重叠分析 (前十大口径) ===")
        pairs = []
        codes = [c for c in contribs if c in meta and meta[c].get("top10")]
        for i in range(len(codes)):
            for j in range(i + 1, len(codes)):
                a, b = codes[i], codes[j]
                top_a = {h["code"]: h["weight_pct"] for h in meta[a].get("top10", [])}
                top_b = {h["code"]: h["weight_pct"] for h in meta[b].get("top10", [])}
                common = set(top_a) & set(top_b)
                if common:
                    overlap_wt = sum(min(top_a[s], top_b[s]) for s in common)
                    if overlap_wt > 5:
                        pairs.append((a, b, len(common), overlap_wt,
                                      contribs[a].get("sector", ""), contribs[b].get("sector", "")))
        pairs.sort(key=lambda x: -x[3])
        for a, b, n, wt, sa, sb in pairs[:15]:
            tag = " ⚠高度重叠" if wt > 30 else ""
            cross = " 跨扇区" if sa != sb else ""
            print(f"  {a} {contribs[a]['name']} ↔ {b} {contribs[b]['name']}: {n}支 {wt:.1f}%{tag}{cross}")

        print("\n=== 持仓集中度 (Top10合计权重) ===")
        conc = [(c, sum(h["weight_pct"] for h in meta[c].get("top10", []))) for c in codes]
        conc.sort(key=lambda x: -x[1])
        for code, s in conc[:5]:
            print(f"  {code} {contribs[code]['name']}: 集中度 {s:.1f}%")
        print("  ...")
        for code, s in conc[-5:]:
            print(f"  {code} {contribs[code]['name']}: 集中度 {s:.1f}%")

        print("\n=== 流动性 (AUM) ===")
        for code, c in sorted(contribs.items(), key=lambda x: (meta.get(x[0]) or {}).get("aum_yi") or 0):
            aum = (meta.get(code) or {}).get("aum_yi")
            if aum is not None and aum < 15:
                tag = " ⚠低流动性" if aum < 5 else " 偏小"
                print(f"  {code} {c['name']}: {aum:.1f}亿{tag}")


if __name__ == "__main__":
    main()
