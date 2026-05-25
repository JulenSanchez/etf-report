#!/usr/bin/env python3
"""Hindsight heatmap data: V2 daily Top-6 picks vs preset1 picks, 6Y.

Output: research/strategy/REQ-189-v2/hindsight_heatmap.json
"""
import json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_data_utils import load_etf_data
from quant_backtest import run_backtest

OUT_DIR = SKILL_DIR / "research" / "strategy" / "REQ-189-v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)
START, END = "2020-05-20", "2026-05-22"


def load_prices():
    import yaml
    with open(SKILL_DIR / "config" / "quant_universe.yaml", "r", encoding="utf-8") as f:
        universe = yaml.safe_load(f)["universe"]
    prices, names, sectors = {}, {}, {}
    for etf in universe:
        code = etf["code"]
        daily, _ = load_etf_data(code)
        if daily is not None and len(daily) > 100:
            df = daily.set_index("date")["close"].sort_index()
            df = df[START:END]
            if len(df) > 200:
                prices[code] = df
                names[code] = etf.get("name", code)
                sectors[code] = etf.get("sector", "")
    return prices, names, sectors


def compute_v2_picks(prices):
    """V2: daily Top-6 by next-day return (God's eye). Returns {date: [code, ...]}."""
    rets = {}
    for code, close in prices.items():
        r = close.pct_change().shift(-1).dropna()
        if len(r) > 0:
            rets[code] = r
    all_dates = sorted(set().union(*[set(r.index) for r in rets.values()]))
    all_dates = [d for d in all_dates if START <= str(d)[:10] <= END]

    picks = {}
    for date in all_dates:
        fwd = {c: rets[c].get(date, np.nan) for c in rets if date in rets[c].index}
        pos = {c: v for c, v in fwd.items() if not np.isnan(v) and v > 0}
        if pos:
            top = sorted(pos, key=pos.get, reverse=True)[:6]
            picks[str(date)[:10]] = top
        else:
            picks[str(date)[:10]] = []
    return picks


def compute_preset1_picks():
    """preset1: daily Top-6 from signal_history."""
    print("Running preset1 backtest...")
    nav, sigs, extra = run_backtest(start_date=START, end_date=END, preset="preset1")
    picks = {}
    for s in sigs:
        date_str = str(s["date"])[:10]
        picks[date_str] = s.get("top6", [])
    return picks


def main():
    t0 = time.time()
    prices, names, sectors = load_prices()
    print(f"Loaded {len(prices)} ETFs")

    v2_picks = compute_v2_picks(prices)
    print(f"V2 picks: {len(v2_picks)} days")

    preset1_picks = compute_preset1_picks()
    print(f"preset1 picks: {len(preset1_picks)} days")

    # Merge: align dates
    all_dates = sorted(set(v2_picks.keys()) | set(preset1_picks.keys()))
    merged = []
    for d in all_dates:
        v2 = v2_picks.get(d, [])
        p1 = preset1_picks.get(d, [])
        both = [c for c in v2 if c in p1]
        only_v2 = [c for c in v2 if c not in p1]
        only_p1 = [c for c in p1 if c not in v2]
        merged.append({
            "date": d,
            "v2": v2,
            "preset1": p1,
            "both": both,
            "onlyV2": only_v2,
            "onlyPreset1": only_p1,
            "overlap": len(both),
        })

    # Sector-level aggregation per date
    def _sector_dist(codes):
        dist = {}
        for c in codes:
            s = sectors.get(c, "?")
            dist[s] = dist.get(s, 0) + 1
        return dist

    v2_sector_timeline = []
    p1_sector_timeline = []
    for d in all_dates:
        v2 = v2_picks.get(d, [])
        p1 = preset1_picks.get(d, [])
        v2_sector_timeline.append({"date": d, "sectors": _sector_dist(v2)})
        p1_sector_timeline.append({"date": d, "sectors": _sector_dist(p1)})

    # Summary stats
    total = len(all_dates)
    avg_overlap = sum(m["overlap"] for m in merged) / max(total, 1)

    output = {
        "meta": {"start": START, "end": END, "tradingDays": total,
                 "avgOverlap": round(avg_overlap, 2),
                 "etfCount": len(prices)},
        "names": names,
        "sectors": sectors,
        "merged": merged,
        "v2SectorTimeline": v2_sector_timeline,
        "preset1SectorTimeline": p1_sector_timeline,
    }
    with open(OUT_DIR / "hindsight_heatmap.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    elapsed = time.time() - t0
    print(f"Done. {total} days, avg overlap={avg_overlap:.1f}/6. Saved ({elapsed:.0f}s)")


if __name__ == "__main__":
    main()
