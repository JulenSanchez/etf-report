#!/usr/bin/env python3
"""REQ-189 重跑: 后视镜最优策略 — 44 ETFs, 6Y, 7 variants + preset1 baseline.

Usage: python scripts/hindsight_optimal.py
Output: research/strategy/REQ-189-v2/
"""
import json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_data_utils import load_etf_data
from benchmark_data import load_hs300_daily_cached

OUT_DIR = SKILL_DIR / "research" / "strategy" / "REQ-189-v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START = "2020-05-20"
END = "2026-05-22"


def load_all_daily(universe_path):
    """Load daily close prices for all ETFs in universe."""
    import yaml
    with open(universe_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    universe = cfg.get("universe", [])
    prices = {}
    names = {}
    for etf in universe:
        code = etf["code"]
        daily, _ = load_etf_data(code)
        if daily is not None and len(daily) > 100:
            df = daily.set_index("date")["close"].sort_index()
            df = df[START:END]
            if len(df) > 200:
                prices[code] = df
                names[code] = etf.get("name", code)
    print(f"Loaded {len(prices)} ETFs with price data")
    return prices, names


def compute_returns(prices, freq="daily"):
    """Compute forward returns for each ETF."""
    rets = {}
    for code, close in prices.items():
        if freq == "daily":
            r = close.pct_change().shift(-1)  # tomorrow's return
        else:
            r = close.resample("W-FRI").last().pct_change().shift(-1)  # next week
        r = r.dropna()
        if len(r) > 0:
            rets[code] = r
    return rets


def run_variant(name, prices, freq, top_n, lookahead, nocash, weekly_end_dates=None):
    """Simulate a hindsight variant.

    lookahead=True: use next period's return (cheating, V1-V5)
    lookahead=False: use last period's return (lagged, V6-V7)
    """
    if freq == "daily":
        rets = compute_returns(prices, "daily")
        # Align to common dates
        all_dates = sorted(set().union(*[set(r.index) for r in rets.values()]))
        all_dates = [d for d in all_dates if START <= str(d)[:10] <= END]
    else:
        rets = compute_returns(prices, "weekly")
        all_dates = sorted(set().union(*[set(r.index) for r in rets.values()]))
        all_dates = [d for d in all_dates if START <= str(d)[:10] <= END]

    if len(all_dates) < 10:
        return None

    nav = 1.0
    nav_history = []
    initial = 1.0

    for i, date in enumerate(all_dates):
        if i == 0:
            nav_history.append(1.0)
            continue
        prev_date = all_dates[i-1]

        if lookahead:
            # Use NEXT period's return for both selection and P&L
            fwd = {c: rets[c].get(date, np.nan) for c in rets if date in rets[c].index}
            select_returns = fwd
            earn_returns = fwd
        else:
            # Lagged: use PREV period's return for SELECTION, CURRENT period's return for P&L
            select_returns = {c: rets[c].get(prev_date, np.nan) for c in rets if prev_date in rets[c].index}
            earn_returns = {c: rets[c].get(date, np.nan) for c in rets if date in rets[c].index}

        if not select_returns:
            nav_history.append(nav)
            continue

        if nocash:
            valid = {c: v for c, v in select_returns.items() if not np.isnan(v) and v > -0.99}
            if not valid:
                nav_history.append(nav)
                continue
            top = sorted(valid, key=valid.get, reverse=True)[:top_n]
            if top:
                port_ret = np.mean([earn_returns.get(c, 0) for c in top])
                nav *= (1 + port_ret)
        else:
            pos = {c: v for c, v in select_returns.items() if not np.isnan(v) and v > 0}
            if not pos:
                nav_history.append(nav)
                continue
            top = sorted(pos, key=pos.get, reverse=True)[:top_n]
            if top:
                port_ret = np.mean([earn_returns.get(c, 0) for c in top])
                nav *= (1 + port_ret)

        nav_history.append(nav)

    if len(nav_history) < 10:
        return None

    nav_series = pd.Series(nav_history, index=all_dates[:len(nav_history)])

    # Metrics
    total_ret = (nav - initial) / initial * 100
    n_periods = len(nav_series)
    cal_days = (all_dates[-1] - all_dates[0]).days if hasattr(all_dates[-1], 'days') else n_periods * (7 if freq == 'weekly' else 1)
    cal_days = max(cal_days, n_periods)
    annual = ((nav / initial) ** (365 / cal_days) - 1) * 100 if cal_days > 0 else 0
    cummax = nav_series.cummax()
    dd = (nav_series - cummax) / cummax * 100
    mdd = float(dd.min())

    return {
        "name": name,
        "totalReturn": round(total_ret, 1),
        "annualReturn": round(annual, 1),
        "maxDrawdown": round(mdd, 1),
        "tradingPeriods": n_periods,
        "finalNav": round(nav, 6),
    }


def run_hs300_baseline(prices):
    """HS300 buy-and-hold over the same period."""
    hs = load_hs300_daily_cached()
    close = hs.set_index("date")["close"].sort_index()
    close = close[START:END]
    if len(close) < 10:
        return None
    total_ret = (close.iloc[-1] / close.iloc[0] - 1) * 100
    days = len(close)
    annual = ((close.iloc[-1] / close.iloc[0]) ** (365 / days) - 1) * 100
    return {"name": "沪深300买入持有", "annualReturn": round(annual, 1),
            "totalReturn": round(total_ret, 1), "maxDrawdown": 0, "tradingPeriods": days}


def main():
    t0 = time.time()
    universe_path = SKILL_DIR / "config" / "quant_universe.yaml"
    prices, names = load_all_daily(universe_path)

    variants = [
        ("V1 daily+Top1",   "daily",  1,  True,  False),
        ("V2 daily+Top6",   "daily",  6,  True,  False),
        ("V3 weekly+Top1",  "weekly", 1,  True,  False),
        ("V4 weekly+Top6",  "weekly", 6,  True,  False),
        ("V5 weekly+Top6_nocash", "weekly", 6, True, True),
        ("V6 lagged+Top6",  "weekly", 6,  False, False),
        ("V7 lagged+Top6_nocash", "weekly", 6, False, True),
    ]

    results = []
    for name, freq, top_n, lookahead, nocash in variants:
        print(f"Running {name}...", end=" ", flush=True)
        r = run_variant(name, prices, freq, top_n, lookahead, nocash)
        if r:
            results.append(r)
            print(f"annual={r['annualReturn']:.1f}% MDD={r['maxDrawdown']:.1f}%")
        else:
            print("FAILED")

    # HS300 baseline
    hs = run_hs300_baseline(prices)
    if hs:
        results.append(hs)

    elapsed = time.time() - t0

    # Print comparison table
    print(f"\n{'='*80}")
    print(f"后视镜最优策略 — 44 ETFs, {START}~{END}")
    print(f"{'='*80}")
    print(f"{'变体':<25} {'年化收益':>10} {'总收益':>10} {'最大回撤':>8} {'周期数':>8}")
    print(f"{'-'*65}")
    for r in results:
        print(f"{r['name']:<25} {r['annualReturn']:>9.1f}% {r['totalReturn']:>9.1f}% {r['maxDrawdown']:>7.1f}% {r.get('tradingPeriods',0):>8}")

    # Save
    output = {
        "meta": {"start": START, "end": END, "etf_count": len(prices), "elapsed_sec": round(elapsed, 1)},
        "results": results,
    }
    with open(OUT_DIR / "hindsight_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUT_DIR / 'hindsight_results.json'} ({elapsed:.0f}s)")


if __name__ == "__main__":
    main()
