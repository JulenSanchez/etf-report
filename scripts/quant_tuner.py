#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-179: Quant Tuner - 本地调参工具

临时 Flask 服务，提供滑块调参 + 一键回测 + NAV 曲线对比。
调完关掉，把最佳参数写回 YAML，正式页面继续走 file://。

用法:
    python scripts/quant_tuner.py
    # -> http://localhost:5179
"""
import gc
import io
import json
import math
import re
import socket
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_factors import compute_all_factors, map_f1, map_f1_residual, map_f2, map_f3, map_f4, map_f5, confidence_function, regime_confidence, infer_regime_from_nav, dd_trigger_confidence, momentum_crash_confidence, ma_trend_confidence, calc_ema, calc_rsi
from quant_backtest import load_etf_data, get_rebalance_dates, DATA_DIR
from data_cleaning import run_data_cleaning_pipeline

CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"

# ============================================================
# Global preloaded data (loaded once at startup)
# ============================================================
CACHE = {
    "cfg": None,
    "all_daily": {},
    "all_weekly": {},
    "hs300_pct": None,
    "eq_weight_pct": None,
    "hs300_above_ma": {},  # {period: {date_str: bool}}
    "hs300_weekly_df": None,
    # Intraday cache: {code: {date, open, close, high, low, volume, amount}}
    # Single entry per code, always overwritten with latest.
    # Only populated during trading hours; cleared after CSV is updated with confirmed close.
    # Never written to CSV — keeps CSV pure (confirmed close data only).
    "intraday_cache": {},
    "intraday_date": None,  # date string the cache is for
}


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _df_to_cleaning_input(daily_df):
    """Convert pandas daily DataFrame → dict format expected by data_cleaning."""
    return {
        "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in daily_df["date"]],
        "kline": [[float(r["open"]), float(r["close"]), float(r["low"]), float(r["high"])] for _, r in daily_df.iterrows()],
        "volumes": [int(v) for v in daily_df["volume"]] if "volume" in daily_df.columns else [],
        "amounts": [float(v) for v in daily_df["amount"]] if "amount" in daily_df.columns else [],
    }


def _apply_cleaning_to_df(daily_df, cleaned):
    """Write cleaned kline/volumes back into the DataFrame (in-place copy)."""
    out = daily_df.copy().reset_index(drop=True)
    kline = cleaned.get("kline", [])
    volumes = cleaned.get("volumes", [])
    for idx in range(len(out)):
        if idx < len(kline):
            o, c, l, h = kline[idx]
            out.at[idx, "open"]  = o
            out.at[idx, "close"] = c
            out.at[idx, "low"]   = l
            out.at[idx, "high"]  = h
        if idx < len(volumes) and "volume" in out.columns:
            out.at[idx, "volume"] = volumes[idx]
    # Note: "amount" (成交额) is intentionally NOT scaled.
    # 价格÷ratio × 成交量×ratio = 原始成交额，所以 amount 字段保持不变即可还原"金额视角"。
    return out


def _rebuild_weekly_from_daily(daily_df):
    """Rebuild weekly OHLCV from cleaned daily data (ISO-week buckets)."""
    if daily_df is None or len(daily_df) == 0:
        return daily_df
    has_amount = "amount" in daily_df.columns
    has_volume = "volume" in daily_df.columns
    rows = []
    cur_key = None
    cur = None
    for _, r in daily_df.iterrows():
        d = pd.Timestamp(r["date"])
        wk = d.isocalendar()[:2]  # (year, week)
        if cur_key != wk:
            if cur is not None:
                rows.append(cur)
            cur_key = wk
            cur = {
                "date": d, "open": float(r["open"]), "close": float(r["close"]),
                "low": float(r["low"]), "high": float(r["high"]),
            }
            if has_volume: cur["volume"] = float(r["volume"])
            if has_amount: cur["amount"] = float(r["amount"])
        else:
            cur["date"]  = d
            cur["close"] = float(r["close"])
            cur["low"]   = min(cur["low"],  float(r["low"]))
            cur["high"]  = max(cur["high"], float(r["high"]))
            if has_volume: cur["volume"] += float(r["volume"])
            if has_amount: cur["amount"] += float(r["amount"])
    if cur is not None:
        rows.append(cur)
    return pd.DataFrame(rows)


def _load_corporate_action_events():
    """Load auto-detected events file. Returns dict code→[events] or {}."""
    path = SKILL_DIR / "data" / "corporate_action_events.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("events_by_code", {}) or {}
    except Exception as e:
        print(f"  [WARN] failed to load corporate_action_events.json: {e}")
        return {}


def preload():
    """One-time data loading at startup."""
    print("Preloading data...")
    cfg = load_config()
    CACHE["cfg"] = cfg

    _load_trading_calendar()

    events_by_code = _load_corporate_action_events()

    for etf in cfg["universe"]:
        code = etf["code"]
        daily, weekly = load_etf_data(code)
        if daily is None:
            continue

        # NOTE: 数据源已切换为前复权(qfq)，价格已包含拆分调整，
        # 无需再对价格做 data_cleaning 的份额变动清洗（否则双重复权）。
        # data_cleaning 仅适用于不复权原始数据。
        # events = events_by_code.get(code) or []
        # if events:
        #     cleaning_input = _df_to_cleaning_input(daily)
        #     cleaned = run_data_cleaning_pipeline(cleaning_input, events)
        #     daily = _apply_cleaning_to_df(daily, cleaned)
        #     weekly = _rebuild_weekly_from_daily(daily)

        CACHE["all_daily"][code] = daily
        CACHE["all_weekly"][code] = weekly

    print(f"  Loaded {len(CACHE['all_daily'])}/{len(cfg['universe'])} ETFs")

    # Precompute benchmarks
    _precompute_benchmarks()

    # Precompute F4 valuation scores from local CSV (no network)
    _precompute_valuation_scores()

    # Load market regimes for F4 regime-aware mapping
    _load_market_regimes()

    print("Preload complete.\n")


# ============================================================
# Data refresh: intraday cache + post-market CSV update
# ============================================================

SINA_URL = "https://hq.sinajs.cn/list="
SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}

# A-share trading schedule (minutes from midnight)
MORNING_OPEN = 570    # 9:30
MORNING_CLOSE = 690   # 11:30
AFTERNOON_OPEN = 780  # 13:00
AFTERNOON_CLOSE = 900 # 15:00
TOTAL_TRADING_MINUTES = 240  # 4 hours
COOL_OFF_TIME = 910   # 15:10 — confirmed data available after this

# Trading calendar (loaded from data/quant/trading_days_YYYY.txt)
_TRADING_DAYS = set()   # set of "YYYY-MM-DD" strings
_TD_LIST = []           # sorted list for binary search


def _load_trading_calendar():
    """Load trading day calendar for the current year (+ prev year for fallback)."""
    global _TRADING_DAYS, _TD_LIST
    _TRADING_DAYS = set()
    _TD_LIST = []
    data_dir = Path(__file__).resolve().parent.parent / "data" / "quant"
    for year in [datetime.now().year - 1, datetime.now().year, datetime.now().year + 1]:
        p = data_dir / f"trading_days_{year}.txt"
        if p.exists():
            with open(p) as f:
                for line in f:
                    ds = line.strip()
                    if ds:
                        _TRADING_DAYS.add(ds)
    _TD_LIST = sorted(_TRADING_DAYS)
    if _TD_LIST:
        print(f"  [Calendar] Loaded {len(_TRADING_DAYS)} trading days ({_TD_LIST[0]} ~ {_TD_LIST[-1]})")


def _is_trading_day(dt=None):
    """Check if a date is a trading day (calendar-aware, not just weekday)."""
    d = dt or datetime.now()
    ds = d.strftime("%Y-%m-%d")
    if _TRADING_DAYS:
        return ds in _TRADING_DAYS
    # Fallback: simple weekday check if no calendar loaded
    return d.weekday() < 5


def _last_trading_day(before=None):
    """Return the most recent trading day on or before `before` as YYYY-MM-DD string.
    If no calendar loaded, falls back to simple weekday logic.
    """
    d = before or datetime.now()
    if _TD_LIST:
        ds = d.strftime("%Y-%m-%d")
        # Binary search: largest element <= ds
        lo, hi = 0, len(_TD_LIST) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if _TD_LIST[mid] <= ds:
                lo = mid + 1
            else:
                hi = mid - 1
        if hi >= 0:
            return _TD_LIST[hi]
    # Fallback: walk backwards to find a weekday
    d2 = d
    for _ in range(7):
        if d2.weekday() < 5:
            return d2.strftime("%Y-%m-%d")
        d2 -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _trading_elapsed_minutes(now=None):
    """How many trading minutes have elapsed today. 0 before open, 240 after close."""
    n = now or datetime.now()
    minutes = n.hour * 60 + n.minute
    if minutes <= MORNING_OPEN:
        return 0
    if minutes <= MORNING_CLOSE:
        return minutes - MORNING_OPEN
    if minutes <= AFTERNOON_OPEN:
        return MORNING_CLOSE - MORNING_OPEN
    if minutes <= AFTERNOON_CLOSE:
        return (MORNING_CLOSE - MORNING_OPEN) + (minutes - AFTERNOON_OPEN)
    return TOTAL_TRADING_MINUTES


def _is_post_market(now=None):
    """True after 15:10 — confirmed close data is available from Tencent API."""
    n = now or datetime.now()
    return n.hour * 60 + n.minute >= COOL_OFF_TIME



def _fetch_sina_realtime(cfg):
    """Fetch real-time quotes for all ETFs from Sina API. One HTTP request, ~2s.
    Returns dict: {code: {name, open, prev_close, price, high, low, volume, amount}}
    """
    symbols = []
    code_list = []
    for etf in cfg["universe"]:
        code = etf["code"]
        m = etf.get("market", "sz")
        symbols.append(f"{m}{code}")
        code_list.append(code)

    url = f"{SINA_URL}{','.join(symbols)}"
    try:
        resp = requests.get(url, headers=SINA_HEADERS, timeout=10)
        resp.encoding = "gbk"
    except Exception as e:
        print(f"  [Sina] API failed: {e}")
        return {}

    results = {}
    lines = resp.text.strip().split("\n")
    for i, line in enumerate(lines):
        if "=" not in line:
            continue
        match = re.search(r'"([^"]*)"', line)
        if not match:
            continue
        data = match.group(1).split(",")
        if len(data) < 10:
            continue
        code = code_list[i] if i < len(code_list) else None
        if not code:
            continue
        try:
            results[code] = {
                "name": data[0],
                "open": float(data[1]) if data[1] else 0,
                "prev_close": float(data[2]) if data[2] else 0,
                "price": float(data[3]) if data[3] else 0,
                "high": float(data[4]) if data[4] else 0,
                "low": float(data[5]) if data[5] else 0,
                "volume": int(float(data[8])) if data[8] else 0,
                "amount": float(data[9]) if data[9] else 0,
            }
        except (ValueError, IndexError):
            continue
    return results


# A-share intraday volume profile template (30-min slots, 8 slots for 4h session)
# Source: composite of A-share market studies — typical cumulative % at slot boundary.
# W-shape: heavy open, morning fade, lunch dip, afternoon trough, close peak.
# Slot:  9:30-10:00  10:00-10:30  10:30-11:00  11:00-11:30  13:00-13:30  13:30-14:00  14:00-14:30  14:30-15:00
_INTRADAY_SLOT_PCT = [0.28, 0.12, 0.08, 0.06, 0.10, 0.07, 0.09, 0.20]
# Cumulative profile: _INTRADAY_CUM[t] = sum of slots 0..t inclusive
_INTRADAY_CUM = []
_cum = 0.0
for _p in _INTRADAY_SLOT_PCT:
    _cum += _p
    _INTRADAY_CUM.append(_cum)
# _INTRADAY_CUM = [0.28, 0.40, 0.48, 0.54, 0.64, 0.71, 0.80, 1.00]


def _intraday_cumulative_pct(now=None):
    """Return the estimated cumulative volume fraction (0..1) at the current time.

    Interpolates linearly within the current 30-min slot using the profile template.
    """
    n = now or datetime.now()
    minutes = n.hour * 60 + n.minute + n.second / 60.0

    if minutes <= MORNING_OPEN:
        return 0.0
    if minutes >= AFTERNOON_CLOSE:
        return 1.0

    # Map current time to a slot index + fractional offset
    if minutes <= MORNING_CLOSE:
        # Morning session: 9:30 - 11:30 → slots 0-3
        elapsed = minutes - MORNING_OPEN
    elif minutes <= AFTERNOON_OPEN:
        # Lunch break — use morning close cumulative
        return _INTRADAY_CUM[3]
    else:
        # Afternoon session: 13:00 - 15:00 → slots 4-7
        elapsed = (MORNING_CLOSE - MORNING_OPEN) + (minutes - AFTERNOON_OPEN)

    slot = min(int(elapsed / 30), 7)
    frac = (elapsed - slot * 30) / 30.0

    prev_cum = _INTRADAY_CUM[slot - 1] if slot > 0 else 0.0
    curr_cum = _INTRADAY_CUM[slot]
    return prev_cum + (curr_cum - prev_cum) * frac


def _estimate_eod_volume(current_volume, now=None):
    """Estimate end-of-day volume from intraday volume using A-share profile template.

    Uses historical intraday volume distribution (W-shape) instead of naive linear
    proportion. The template captures the typical open peak, lunch dip, and close
    surge that linear extrapolation misses.
    """
    cum_pct = _intraday_cumulative_pct(now)
    if cum_pct <= 0.001 or cum_pct >= 0.999:
        return current_volume
    return int(current_volume / cum_pct)


def _run_incremental_fetch(cfg):
    """Run quant_data_fetcher incrementally for all ETFs. Updates CSV files on disk.
    Returns (ok_count, fail_count).
    """
    from quant_data_fetcher import update_single
    import time as _time
    ok, fail = 0, 0
    for etf in cfg["universe"]:
        try:
            update_single(etf, full=False)
            ok += 1
            _time.sleep(1.0)  # 1s between ETFs (faster than default 3s)
        except Exception as e:
            print(f"  [Fetch] {etf['code']} failed: {e}")
            fail += 1
    return ok, fail


def _reload_csv_to_cache(cfg):
    """Reload all CSV data from disk into CACHE (after fetcher has updated them)."""
    for etf in cfg["universe"]:
        code = etf["code"]
        daily, weekly = load_etf_data(code)
        if daily is not None:
            CACHE["all_daily"][code] = daily
            CACHE["all_weekly"][code] = weekly


def refresh_data():
    """Main refresh entry point. Called by /api/refresh_data.

    Both paths first fill historical gaps via incremental CSV fetch.
    Then:
    - Post-market (>=15:10): confirmed close data is already in CSV → clear intraday cache
    - Pre-market / Intraday (<15:10): fetch Sina real-time prices → write intraday cache

    Intraday cache is a single flat dict, always overwritten.
    Computation code merges cache into daily_df on-the-fly (see _get_daily_with_cache).
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    cfg = CACHE.get("cfg") or load_config()
    time_label = now.strftime("%H:%M")

    # === Both paths: fill historical gaps first ===
    print(f"  [Refresh] Filling historical gaps — running incremental fetch...")
    ok, fail = _run_incremental_fetch(cfg)
    _reload_csv_to_cache(cfg)
    _precompute_benchmarks()
    _precompute_valuation_scores()
    _load_market_regimes()
    gap_msg = f"CSV gap-fill | {ok} OK, {fail} fail"

    if _is_post_market(now):
        # === Post-market: confirmed close data is now in CSV ===
        # Clear intraday cache — CSV has the authoritative data
        CACHE["intraday_cache"] = {}
        CACHE["intraday_date"] = None

        msg = f"{time_label} | {gap_msg}"
        print(f"  [Refresh] Post-market — {msg}")

        return {
            "status": "confirmed",
            "message": msg,
            "fetchOk": ok,
            "fetchFail": fail,
            "date": today_str,
            "time": time_label,
        }

    else:
        # === Pre-market / Intraday / Non-trading day ===
        if not _is_trading_day(now):
            # Non-trading day: gap-fill already brought CSV up to last trading day.
            # No intraday data to fetch — just report confirmed status.
            ltd = _last_trading_day(now)
            msg = f"{time_label} | Non-trading day | CSV up to {ltd} | {gap_msg}"
            print(f"  [Refresh] {msg}")
            return {
                "status": "confirmed",
                "message": msg,
                "fetchOk": ok,
                "fetchFail": fail,
                "date": ltd,
                "time": time_label,
            }

        # Trading day but before 15:10 — fetch real-time prices into intraday cache
        rt_prices = _fetch_sina_realtime(cfg)
        if not rt_prices:
            return {"status": "error", "message": f"{time_label} | Sina API failed | {gap_msg}", "date": today_str, "time": time_label}

        updated = 0
        for etf in cfg["universe"]:
            code = etf["code"]
            rt = rt_prices.get(code)
            if not rt or rt["price"] <= 0:
                continue

            vol = rt["volume"]
            amt = rt["amount"]
            # Estimate EOD volume for more accurate F3
            if vol > 0:
                vol = _estimate_eod_volume(vol, now)
                if amt > 0:
                    amt = _estimate_eod_volume(int(amt), now)

            CACHE["intraday_cache"][code] = {
                "date": today_str,
                "open": rt["open"],
                "close": rt["price"],
                "high": rt["high"],
                "low": rt["low"],
                "volume": vol,
                "amount": amt,
            }
            updated += 1

        CACHE["intraday_date"] = today_str
        vol_note = " (vol est. EOD)" if _trading_elapsed_minutes(now) < TOTAL_TRADING_MINUTES else ""
        msg = f"{time_label} | Intraday | {updated} ETFs{vol_note} | {gap_msg}"
        print(f"  [Refresh] {msg}")

        return {
            "status": "intraday",
            "message": msg,
            "count": updated,
            "date": today_str,
            "time": time_label,
        }


def _get_daily_with_cache(code):
    """Get daily DataFrame for an ETF, with intraday cache appended if available.
    Does NOT modify CACHE["all_daily"] — returns a new DataFrame.
    If cache exists and its date is newer than CSV's last date, appends one row.
    If cache date equals CSV's last date, replaces the last row.
    """
    daily_df = CACHE["all_daily"].get(code)
    if daily_df is None:
        return None

    cached = CACHE["intraday_cache"].get(code)
    if not cached:
        return daily_df

    cache_date = cached["date"]
    last_date = daily_df["date"].iloc[-1]
    last_str = last_date.strftime("%Y-%m-%d") if hasattr(last_date, "strftime") else str(last_date)[:10]

    df = daily_df.copy()

    if last_str == cache_date:
        # Replace last row with cache data
        df.at[df.index[-1], "open"] = cached["open"]
        df.at[df.index[-1], "close"] = cached["close"]
        df.at[df.index[-1], "high"] = cached["high"]
        df.at[df.index[-1], "low"] = cached["low"]
        if "volume" in df.columns:
            df.at[df.index[-1], "volume"] = cached["volume"]
        if "amount" in df.columns:
            df.at[df.index[-1], "amount"] = cached["amount"]
    elif last_str < cache_date:
        # Append new row
        new_row = pd.DataFrame([{
            "date": pd.Timestamp(cache_date),
            "open": cached["open"],
            "close": cached["close"],
            "high": cached["high"],
            "low": cached["low"],
            "volume": cached["volume"],
            "amount": cached["amount"],
        }])
        df = pd.concat([df, new_row], ignore_index=True)

    return df


def _get_weekly_with_cache(code):
    """Get weekly DataFrame for an ETF, rebuilt from _get_daily_with_cache if cache exists."""
    if code not in CACHE["intraday_cache"]:
        return CACHE["all_weekly"].get(code)

    daily_df = _get_daily_with_cache(code)
    if daily_df is None or len(daily_df) == 0:
        return CACHE["all_weekly"].get(code)

    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["week"] = (df["date"].dt.isocalendar().year.astype(str) + "-"
                  + df["date"].dt.isocalendar().week.astype(str).str.zfill(2))
    weekly = df.groupby("week").agg(
        date=("date", "last"),
        open=("open", "first"),
        close=("close", "last"),
        high=("high", "max"),
        low=("low", "min"),
        volume=("volume", "sum"),
        amount=("amount", "sum"),
    ).reset_index(drop=True)
    return weekly


def _precompute_benchmarks():
    """Compute HS300 + equal-weight benchmarks once."""
    all_daily = CACHE["all_daily"]
    if not all_daily:
        return

    # Find common date range
    all_dates = set()
    for df in all_daily.values():
        all_dates.update(df["date"].values)
    all_dates = sorted(all_dates)
    start_dt = min(pd.Timestamp(d) for d in all_dates) if all_dates else pd.Timestamp("2020-01-01")
    all_dates = [d for d in all_dates if pd.Timestamp(d) >= start_dt]
    if not all_dates:
        return

    # Equal-weight: average daily return of all ETFs
    date_returns = {}
    for d in all_dates:
        rets = []
        for code, df in all_daily.items():
            mask = df["date"] == d
            if mask.sum() == 0:
                continue
            idx = df.index[mask][0]
            if idx == 0:
                continue
            prev_close = float(df.loc[idx - 1, "close"])
            cur_close = float(df.loc[idx, "close"])
            if prev_close > 0:
                rets.append(cur_close / prev_close - 1)
        if rets:
            date_returns[d] = np.mean(rets)

    eq_nav = 100.0
    eq_pct = []
    date_strs = []
    for d in all_dates:
        r = date_returns.get(d, 0)
        eq_nav *= (1 + r)
        eq_pct.append(round(eq_nav, 2))
        ds = pd.Timestamp(d).strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        date_strs.append(ds)

    CACHE["eq_weight_pct"] = eq_pct
    CACHE["eq_dates"] = date_strs

    # HS300 benchmark
    try:
        import akshare as ak
        hs = ak.stock_zh_index_daily(symbol="sh000300")
        hs["date"] = pd.to_datetime(hs["date"])
        hs = hs.sort_values("date")
        hs_map = dict(zip(hs["date"].dt.strftime("%Y-%m-%d"), hs["close"].astype(float)))

        anchor = None
        hs_pct = []
        for d in date_strs:
            if d in hs_map:
                if anchor is None:
                    anchor = hs_map[d]
                hs_pct.append(round(hs_map[d] / anchor * 100, 2))
            else:
                hs_pct.append(hs_pct[-1] if hs_pct else 100.0)
        CACHE["hs300_pct"] = hs_pct
    except Exception as e:
        print(f"  [WARN] HS300 benchmark failed: {e}")
        CACHE["hs300_pct"] = None

    # HS300 weekly DataFrame (shared by ma_trend + residual momentum)
    try:
        import akshare as ak
        hs = ak.stock_zh_index_daily(symbol="sh000300")
        hs["date"] = pd.to_datetime(hs["date"])
        hs = hs.sort_values("date").reset_index(drop=True)
        CACHE["hs300_daily_df"] = hs
        # Resample to weekly (Friday close)
        hs["week"] = hs["date"].dt.isocalendar().year.astype(str) + "-" + hs["date"].dt.isocalendar().week.astype(str).str.zfill(2)
        weekly = hs.groupby("week").last().reset_index()[["date", "close"]]
        CACHE["hs300_weekly_df"] = weekly
        # Pre-build ma_trend lookup for default period=20
        _build_ma_trend_cache(20)
    except Exception as e:
        print(f"  [WARN] HS300 data load failed: {e}")
        CACHE["hs300_daily_df"] = None
        CACHE["hs300_weekly_df"] = None


    # HS300 weekly DataFrame for residual momentum (reuse if available)
    if CACHE.get("hs300_weekly_df") is not None:
        CACHE["hs300_weekly"] = CACHE["hs300_weekly_df"].rename(columns={"close": "close"})
        print(f"  HS300 weekly: {len(CACHE['hs300_weekly'])} bars for residual momentum")
    else:
        CACHE["hs300_weekly"] = None


def _build_ma_trend_cache(period):
    """Build or retrieve MA trend above/below and direction lookup for a given period.

    Returns dict with keys:
      'above': {date_str: bool}  — close >= MA
      'ma_rising': {date_str: bool} — MA[t] > MA[t-1]
    """
    ma_cache = CACHE.get("hs300_above_ma", {})
    if period in ma_cache:
        return ma_cache[period]
    hs_daily = CACHE.get("hs300_daily_df")
    weekly = CACHE.get("hs300_weekly_df")
    if hs_daily is None or weekly is None:
        return None
    w = weekly.copy()
    w[f"ma{period}"] = w["close"].rolling(period, min_periods=max(period // 2, 5)).mean()
    w["above"] = w["close"] >= w[f"ma{period}"]
    w["ma_rising"] = w[f"ma{period}"] > w[f"ma{period}"].shift(1)
    above_map = {}
    rising_map = {}
    for _, wr in w.iterrows():
        if pd.isna(wr[f"ma{period}"]):
            continue
        wk_start = wr["date"] - pd.Timedelta(days=6)
        mask = (hs_daily["date"] >= wk_start) & (hs_daily["date"] <= wr["date"])
        is_above = bool(wr["above"])
        is_rising = bool(wr["ma_rising"]) if not pd.isna(wr["ma_rising"]) else None
        for _, dr in hs_daily[mask].iterrows():
            above_map[dr["date"].strftime("%Y-%m-%d")] = is_above
            if is_rising is not None:
                rising_map[dr["date"].strftime("%Y-%m-%d")] = is_rising
    result = {"above": above_map, "ma_rising": rising_map}
    ma_cache[period] = result
    CACHE["hs300_above_ma"] = ma_cache
    above_count = sum(above_map.values())
    rising_count = sum(v for v in rising_map.values() if v is not None)
    print(f"  HS300 MA{period} trend: {len(above_map)} days, above={above_count}, below={len(above_map)-above_count}, rising={rising_count}")
    return result


def _precompute_valuation_scores():
    """Compute F4 valuation scores from local CSV + anchors (no network).
    Score = 100 - historical_percentile (low valuation = high score)."""
    try:
        from valuation_engine import ValuationEngine
        engine = ValuationEngine()
        val_scores = {}
        history_dir = SKILL_DIR / "data" / "valuation_history"

        for etf_code in engine.list_etfs():
            cfg = engine.get_etf_config(etf_code)
            if cfg is None:
                continue

            metric = cfg["primary_metric"]
            # Read latest value from local CSV (no network)
            current_value = None

            if metric == "pb":
                csv_path = history_dir / f"{etf_code}_pb.csv"
            else:
                csv_path = history_dir / f"{etf_code}.csv"

            if csv_path.exists():
                try:
                    with csv_path.open("r", encoding="utf-8") as f:
                        lines = f.readlines()
                    for line in reversed(lines):
                        parts = line.strip().split(",")
                        if len(parts) >= 2 and parts[1]:
                            try:
                                v = float(parts[1])
                                if v > 0:
                                    current_value = v
                                    break
                            except ValueError:
                                continue
                except Exception:
                    pass

            if current_value is not None:
                result = engine.evaluate(etf_code, current_value)
                if result and result.get("percentile") is not None:
                    val_scores[etf_code] = 100.0 - result["percentile"]
                    continue

            val_scores[etf_code] = 50.0  # neutral fallback

        CACHE["val_scores"] = val_scores
        print(f"  F4 valuation scores: {len(val_scores)} ETFs precomputed")
    except Exception as e:
        print(f"  [WARN] F4 valuation precompute failed: {e}")
        CACHE["val_scores"] = {}


def _load_market_regimes():
    """Load market_regimes.json for F4 regime-aware mapping.
    Format: {"regimes": [{"date": "2024-01-02", "regime": "choppy_range"}, ...]}
    Stored as dict: date_str -> regime_str for fast lookup.
    """
    path = SKILL_DIR / "data" / "market_regimes.json"
    if not path.exists():
        print("  [WARN] market_regimes.json not found, F4 will use default regime")
        CACHE["market_regimes"] = {}
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        regimes_list = data.get("regimes", [])
        CACHE["market_regimes"] = {r["date"]: r["regime"] for r in regimes_list}
        print(f"  Market regimes: {len(CACHE['market_regimes'])} days loaded")
    except Exception as e:
        print(f"  [WARN] Failed to load market_regimes.json: {e}")
        CACHE["market_regimes"] = {}


def get_execution_date(signal_date, all_dates, timing):
    """Return trade execution date for a signal date."""
    if timing == "next_open":
        future_dates = all_dates[all_dates > signal_date]
        return future_dates[0] if len(future_dates) else None
    return signal_date


def get_price_on_date(all_daily, code, date, field="close"):
    df = all_daily.get(code)
    if df is None:
        return None
    row = df[df["date"] == date]
    if len(row) == 0 or field not in row.columns:
        return None
    return float(row[field].iloc[0])


# ============================================================
# Core: run backtest with custom params (using preloaded data)
# ============================================================
def run_tuner_backtest(params):
    """Run a backtest with custom parameters, return summary + NAV."""
    t0 = time.time()
    cfg = deepcopy(CACHE["cfg"])

    # Override from params
    cfg["scoring"]["weights"] = {
        "ema_deviation": params["w1"] / 100.0,
        "rsi_adaptive": params.get("w2", 0) / 100.0,
        "volume_ratio": params["w3"] / 100.0,
        "valuation": params.get("w4", 0) / 100.0,
        "volatility": params.get("w5", 0) / 100.0,
        "residual_momentum": params.get("w1r", 0) / 100.0,
        "exhaustion_penalty": params.get("w6", 0) / 100.0,
    }
    cfg["scoring"]["bias_bonus"] = params.get("bias", 0)
    cfg["confidence"]["type"] = params.get("conf_type", "regime")
    # Legacy quadratic params (kept for backward compat)
    cfg["confidence"]["dead_zone"] = params.get("dead_zone", 10) / 100.0
    cfg["confidence"]["full_zone"] = params.get("full_zone", 60) / 100.0
    cfg["confidence"]["dispersion_threshold"] = params.get("dispersion_threshold", 0.0)
    cfg["confidence"]["breadth_power"] = params.get("breadth_power", 0.0)
    # New regime params (defaults must match global confidence in YAML)
    cfg["confidence"]["regime_base"] = {
        "bull_trend": params.get("regime_base_bull", 0.95),
        "choppy_range": params.get("regime_base_choppy", 0.75),
        "bear_trend": params.get("regime_base_bear", 0.35),
    }
    cfg["confidence"]["regime_window"] = params.get("regime_window", 8)
    cfg["confidence"]["regime_threshold"] = params.get("regime_threshold", 0.03)
    cfg["confidence"]["breadth_weight"] = params.get("breadth_weight", 0.2)
    cfg["confidence"]["clarity_threshold"] = params.get("clarity_threshold", 0.03)
    cfg["confidence"]["dd_sensitivity"] = params.get("dd_sensitivity", 0.2)
    # dd_trigger params
    cfg["confidence"]["dd_trigger_level"] = params.get("dd_trigger_level", -0.05)
    cfg["confidence"]["dd_floor"] = params.get("dd_floor", 0.35)
    # momentum_crash params
    cfg["confidence"]["crash_window"] = params.get("crash_window", 2)
    cfg["confidence"]["crash_threshold"] = params.get("crash_threshold", -0.03)
    cfg["confidence"]["recovery_threshold"] = params.get("recovery_threshold", -0.01)
    cfg["confidence"]["crash_pos"] = params.get("crash_pos", 0.20)
    cfg["confidence"]["recovery_pos"] = params.get("recovery_pos", 0.70)
    cfg["confidence"]["recovery_dd_level"] = params.get("recovery_dd_level", -0.05)
    # ma_trend params
    cfg["confidence"]["ma_bull_pos"] = params.get("ma_bull_pos", 1.00)
    cfg["confidence"]["ma_bear_pos"] = params.get("ma_bear_pos", 0.30)
    cfg["confidence"]["ma_trend_period"] = int(params.get("ma_trend_period", 26))
    cfg["confidence"]["ma_direction_confirm"] = bool(params.get("ma_direction_confirm", True))
    cfg["position"]["max_holdings"] = params["max_holdings"]
    cfg["position"]["discretize_step"] = params.get("disc_step", 5) / 100.0
    cfg["position"]["rebalance_freq"] = params.get("rebalance_freq", "W-FRI")
    cfg["position"]["execution_timing"] = params.get("execution_timing", "same_close")
    cfg["position"]["score_band"] = params.get("score_band", 0) / 100.0
    cfg["factors"]["ema"]["period_weeks"] = params.get("ema_period", 20)
    cfg["factors"]["rsi"]["period_days"] = params.get("rsi_period", 14)
    cfg["factors"]["volume_ratio"]["window_days"] = params.get("vol_window", 20)
    cfg["scoring"]["sensitivity"] = {
        "f1": params.get("f1_sensitivity", 8.0),
        "f3": params.get("f3_sensitivity", 1.0),
        "f2_dead_zone": params.get("f2_dead_zone", 1.5),
        "f1_residual": params.get("f1r_sensitivity", 5.0),
    }
    # Residual momentum factor config
    cfg["factors"]["residual_momentum"] = {
        "reg_window": params.get("residual_reg_window", 12),
        "mom_window": params.get("residual_mom_window", 12),
    }
    cfg["factors"]["f6_rsi_thresh"] = params.get("f6_rsi_thresh", 80)
    cfg["factors"]["f6_drop_thresh"] = params.get("f6_drop_thresh", 2.5) / 100.0
    cfg["factors"]["f6_base_penalty"] = params.get("f6_base_penalty", 0.15)

    weights = cfg["scoring"]["weights"]
    bias_bonus = cfg["scoring"]["bias_bonus"]
    sensitivity = cfg["scoring"].get("sensitivity", {})
    f1_sens = sensitivity.get("f1", 8.0)
    f3_sens = sensitivity.get("f3", 1.0)
    f2_dz = sensitivity.get("f2_dead_zone", 1.5)
    conf_type = cfg["confidence"].get("type", "regime")
    dead_zone = cfg["confidence"].get("dead_zone", 0.10)
    full_zone = cfg["confidence"].get("full_zone", 0.60)
    dispersion_threshold = cfg["confidence"].get("dispersion_threshold", 0.0)
    breadth_power = cfg["confidence"].get("breadth_power", 0.0)
    regime_base_cfg = cfg["confidence"].get("regime_base", {"bull_trend": 0.95, "choppy_range": 0.75, "bear_trend": 0.35})
    regime_window = cfg["confidence"].get("regime_window", 8)
    regime_threshold = cfg["confidence"].get("regime_threshold", 0.03)
    breadth_weight = cfg["confidence"].get("breadth_weight", 0.2)
    clarity_threshold = cfg["confidence"].get("clarity_threshold", 0.03)
    dd_sensitivity = cfg["confidence"].get("dd_sensitivity", 0.2)
    dd_trigger_level = cfg["confidence"].get("dd_trigger_level", -0.05)
    dd_floor = cfg["confidence"].get("dd_floor", 0.35)
    crash_window = cfg["confidence"].get("crash_window", 2)
    crash_threshold = cfg["confidence"].get("crash_threshold", -0.03)
    recovery_threshold = cfg["confidence"].get("recovery_threshold", -0.01)
    crash_pos = cfg["confidence"].get("crash_pos", 0.20)
    recovery_pos = cfg["confidence"].get("recovery_pos", 0.70)
    recovery_dd_level = cfg["confidence"].get("recovery_dd_level", -0.05)
    ma_bull_pos = cfg["confidence"].get("ma_bull_pos", 1.00)
    ma_bear_pos = cfg["confidence"].get("ma_bear_pos", 0.30)
    ma_trend_period = cfg["confidence"].get("ma_trend_period", 26)
    ma_direction_confirm = cfg["confidence"].get("ma_direction_confirm", True)
    max_holdings = cfg["position"]["max_holdings"]
    step = cfg["position"]["discretize_step"]
    factor_cfg = cfg["factors"]
    f6_rsi_thresh = factor_cfg.get("f6_rsi_thresh", 80.0)
    f6_drop_thresh = factor_cfg.get("f6_drop_thresh", 0.025)
    f6_base_penalty = factor_cfg.get("f6_base_penalty", 0.15)

    # bias_bonus 从 UI 的 0-12 整数尺度映射到 0-1 的综合分尺度
    bias_map = {e["code"]: bias_bonus / 100.0 for e in cfg["universe"] if e.get("bias")}

    rebalance_freq = cfg["position"].get("rebalance_freq", "W-FRI")
    execution_timing = cfg["position"].get("execution_timing", "same_close")
    if execution_timing not in ("same_close", "next_open"):
        execution_timing = "same_close"
    score_band = cfg["position"].get("score_band", 0)
    commission_rate = cfg["position"].get("commission_rate", 0)

    all_daily = CACHE["all_daily"]
    all_weekly = CACHE["all_weekly"]

    # Merge intraday cache into working copies for backtest computation
    # Cache data is NOT written to CSV — it's only used in-memory
    if CACHE["intraday_cache"]:
        all_daily = {}
        all_weekly = {}
        for code in CACHE["all_daily"]:
            all_daily[code] = _get_daily_with_cache(code)
            all_weekly[code] = _get_weekly_with_cache(code)

    # Universe filter: limit backtest to selected ETFs
    universe_str = params.get("universe", "")
    if universe_str:
        selected_codes = set(universe_str.split(","))
        cfg["universe"] = [e for e in cfg["universe"] if e["code"] in selected_codes]
        all_daily = {k: v for k, v in all_daily.items() if k in selected_codes}
        all_weekly = {k: v for k, v in all_weekly.items() if k in selected_codes}

    # Validate: need at least max_holdings ETFs with data
    available = len(all_daily)
    if available < max_holdings:
        return {"error": f"Only {available} ETFs with data, need at least {max_holdings}"}

    # Date range: user-controlled start/end with hidden warmup
    # User sees results from start_date; system runs backtest from start_date - warmup
    user_start_str = params.get("start_date")
    user_end_str = params.get("end_date")

    all_dates_set = set()
    for df in all_daily.values():
        all_dates_set.update(df["date"].values)
    all_dates_full = pd.DatetimeIndex(sorted(all_dates_set))

    # Determine effective user range
    data_min = all_dates_full.min()
    data_max = all_dates_full.max()
    # Always allow backtest up to today (even if CSV hasn't been updated yet)
    today_ts = pd.Timestamp(datetime.now().strftime("%Y-%m-%d"))
    if today_ts > data_max:
        data_max = today_ts
    try:
        user_start = pd.Timestamp(user_start_str) if user_start_str else (data_max - pd.DateOffset(years=1))
    except Exception:
        user_start = data_max - pd.DateOffset(years=1)
    try:
        user_end = pd.Timestamp(user_end_str) if user_end_str else data_max
    except Exception:
        user_end = data_max
    user_start = max(user_start, data_min)
    user_end = min(user_end, data_max)

    # Warmup: pull extra data before user_start to seed EMA / portfolio diff
    warmup_weeks = factor_cfg["ema"]["period_weeks"] + 4  # extra padding
    warmup_start = user_start - pd.DateOffset(weeks=warmup_weeks)

    all_dates = all_dates_full[(all_dates_full >= warmup_start) & (all_dates_full <= user_end)]

    rebalance_dates = get_rebalance_dates(all_dates, freq=rebalance_freq)
    if len(rebalance_dates) == 0:
        return {"error": "Not enough data in selected range"}

    # --- Backtest loop ---
    portfolio = {}
    cash = 1000000.0
    initial_capital = cash
    signal_history = []  # only records visible (post-warmup) rebalances
    last_targets_dict = {}  # tracks prev rebalance's targets across warmup boundary
    total_commission = 0.0
    nav_history = []       # for regime inference
    nav_peak = cash        # running peak NAV for drawdown calc
    regime = "choppy_range"  # will be updated each rebalance
    prev_hs300_above = True  # for ma_direction_confirm: track previous signal

    # Residual momentum config
    residual_reg_window = cfg.get("factors", {}).get("residual_momentum", {}).get("reg_window", 12)
    residual_mom_window = cfg.get("factors", {}).get("residual_momentum", {}).get("mom_window", 12)
    hs300_weekly_full = CACHE.get("hs300_weekly")

    for rb_date in rebalance_dates:
        execution_date = get_execution_date(rb_date, all_dates, execution_timing)
        if execution_date is None:
            continue
        execution_price_field = "open" if execution_timing == "next_open" else "close"

        factors_data = {}
        prices_today = {}

        # Slice HS300 weekly up to rebalance date
        hs300_w_slice = None
        if hs300_weekly_full is not None:
            hs300_w_slice = hs300_weekly_full[hs300_weekly_full["date"] <= rb_date].copy()

        for code in all_daily:
            daily_df = all_daily[code]
            weekly_df = all_weekly[code]
            daily_slice = daily_df[daily_df["date"] <= rb_date]
            weekly_slice = weekly_df[weekly_df["date"] <= rb_date]

            if len(daily_slice) < 30 or len(weekly_slice) < factor_cfg["ema"]["period_weeks"]:
                continue

            factors = compute_all_factors(
                daily_slice, weekly_slice,
                ema_period=factor_cfg["ema"]["period_weeks"],
                rsi_period=factor_cfg["rsi"]["period_days"],
                vol_window=factor_cfg["volume_ratio"]["window_days"],
                hs300_weekly=hs300_w_slice,
                residual_reg_window=residual_reg_window,
                residual_mom_window=residual_mom_window,
                f6_rsi_thresh=f6_rsi_thresh,
                f6_drop_thresh=f6_drop_thresh,
                f6_base_penalty=f6_base_penalty,
            )
            # Allow NaN in f1_residual_mom (fallback to 0 weight)
            if any(np.isnan(v) for k, v in factors.items() if k != "f1_residual_mom"):
                continue

            exec_price = get_price_on_date(all_daily, code, execution_date, execution_price_field)
            if exec_price is None:
                continue
            factors_data[code] = factors
            prices_today[code] = exec_price

        if len(factors_data) < max_holdings:
            continue

        factors_df = pd.DataFrame(factors_data).T
        mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
        mapped_f2 = factors_df["f2_rsi_adaptive"].apply(lambda v: map_f2(v, f2_dz))
        mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

        # Residual momentum mapping
        f1r_sens = sensitivity.get("f1_residual", 5.0)
        if "f1_residual_mom" in factors_df.columns:
            mapped_f1r = factors_df["f1_residual_mom"].apply(lambda v: map_f1_residual(v, f1r_sens) if not np.isnan(v) else np.nan)
        else:
            mapped_f1r = pd.Series(np.nan, index=factors_df.index)

        w1 = weights.get("ema_deviation", 0.30)
        w2 = weights.get("rsi_adaptive", 0.25)
        w3 = weights.get("volume_ratio", 0.30)
        w4 = weights.get("valuation", 0.15)
        w5 = weights.get("volatility", 0.0)
        w1r = weights.get("residual_momentum", 0.0)
        w6 = weights.get("exhaustion_penalty", 0.0)

        composite = mapped_f1 * w1 + mapped_f2 * w2 + mapped_f3 * w3

        # Residual momentum (skip NaN ETFs)
        if w1r > 0 and mapped_f1r.notna().any():
            valid_mask = mapped_f1r.notna()
            composite[valid_mask] = composite[valid_mask] + mapped_f1r[valid_mask] * w1r

        # F4 valuation factor (precomputed at startup, no network calls)
        # Regime-aware: look up market regime for this rebalance date
        rb_date_str = rb_date.strftime("%Y-%m-%d") if hasattr(rb_date, "strftime") else str(rb_date)[:10]
        market_regime = CACHE.get("market_regimes", {}).get(rb_date_str, "choppy_range")

        if w4 > 0 and "val_scores" in CACHE:
            try:
                val_scores = {code: CACHE["val_scores"].get(code, 50.0) for code in factors_df.index}
                f4_series = pd.Series(val_scores)
                mapped_f4 = f4_series.apply(lambda v: map_f4(v, market_regime))
                composite = composite + mapped_f4 * w4
            except Exception:
                pass  # degrade to 3-factor

        # F5 volatility factor
        if w5 > 0 and "f5_volatility_z" in factors_df.columns:
            try:
                f5_sens = sensitivity.get("f5", 1.0)
                mapped_f5 = factors_df["f5_volatility_z"].apply(lambda v: map_f5(v, f5_sens))
                composite = composite + mapped_f5 * w5
            except Exception:
                pass  # degrade gracefully

        for code, bonus in bias_map.items():
            if code in composite.index:
                composite[code] += bonus

        if w6 > 0 and "f6_exhaustion_penalty" in factors_df.columns:
            f6_score = factors_df["f6_exhaustion_penalty"] - 1.0
            composite = composite + f6_score * w6

        top_n = composite.nlargest(max_holdings)

        # 分数带过滤：新标的替换被挤出持仓时，分数优势必须 > score_band
        if score_band > 0 and portfolio:
            held_in_topn = {c: top_n[c] for c in top_n.index if c in portfolio}
            want_in = [c for c in top_n.index if c not in portfolio]
            ousted = {c: composite[c] for c in portfolio if c not in top_n.index and c in composite.index}

            if want_in and ousted:
                allowed = [c for c in want_in
                           if any(composite[c] - out_score > score_band
                                  for out_score in ousted.values())]
            else:
                allowed = want_in

            merged = dict(held_in_topn)
            for c in allowed:
                merged[c] = top_n[c]
            for c, s in ousted.items():
                if c not in merged:
                    merged[c] = s
            top_n = pd.Series(merged).nlargest(max_holdings)

        # Compute total position target based on confidence type
        score_dispersion = top_n.std()
        market_breadth = (composite > composite.median()).sum() / max(len(composite), 1)

        if top_n.sum() > 0:
            relative_weights = top_n / top_n.sum()
        else:
            relative_weights = pd.Series(0.0, index=top_n.index)

        # Update NAV tracking for regime inference
        holdings_value = sum(portfolio.get(c, 0) * prices_today.get(c, 0) for c in portfolio)
        current_nav = cash + holdings_value
        nav_history.append(current_nav)
        nav_peak = max(nav_peak, current_nav)
        current_dd = (current_nav - nav_peak) / nav_peak

        if conf_type == "regime":
            # Market-state driven position sizing
            regime = infer_regime_from_nav(nav_history, regime_window, regime_threshold)
            total_target = regime_confidence(
                regime=regime,
                breadth=market_breadth,
                clarity=score_dispersion,
                drawdown_pct=current_dd,
                regime_base=regime_base_cfg,
                breadth_weight=breadth_weight,
                clarity_threshold=clarity_threshold,
                dd_sensitivity=dd_sensitivity,
            )
        elif conf_type == "dd_trigger":
            # Drawdown-triggered: full by default, reduce only during S2->B1
            total_target = dd_trigger_confidence(
                drawdown_pct=current_dd,
                dd_trigger_level=dd_trigger_level,
                dd_floor=dd_floor,
            )
            regime = "dd_trigger"
        elif conf_type == "momentum_crash":
            # Momentum crash protection: full by default, floor on S2 crash
            total_target = momentum_crash_confidence(
                nav_history=nav_history,
                crash_window=crash_window,
                crash_threshold=crash_threshold,
                recovery_threshold=recovery_threshold,
                full_pos=0.95,
                crash_pos=crash_pos,
                recovery_pos=recovery_pos,
                recovery_dd_level=recovery_dd_level,
            )
            regime = "momentum_crash"
        elif conf_type == "always_full":
            # Always 95% invested — baseline for comparing confidence functions
            total_target = 0.95
            regime = "always_full"
        elif conf_type == "ma_trend":
            # MA trend following: above HS300 weekly MA → bull, below → bear
            # Optional: ma_direction_confirm requires MA direction to agree
            hs300_above = False
            ma_rising = None
            ma_cache_result = _build_ma_trend_cache(ma_trend_period)
            if ma_cache_result:
                above_map = ma_cache_result.get("above", {})
                rising_map = ma_cache_result.get("ma_rising", {})
                hs300_above = above_map.get(rb_date_str, True)
                ma_rising = rising_map.get(rb_date_str, None)
            # Apply direction confirmation if enabled
            if ma_direction_confirm:
                # BULL only if above MA AND MA rising; BEAR only if below MA AND MA declining
                # Otherwise keep previous signal
                if hs300_above and ma_rising is True:
                    pass  # confirmed bull
                elif not hs300_above and ma_rising is False:
                    pass  # confirmed bear
                else:
                    # Direction disagrees or unknown → keep previous regime
                    hs300_above = prev_hs300_above
            total_target = ma_trend_confidence(
                hs300_above_ma=hs300_above,
                bull_pos=ma_bull_pos,
                bear_pos=ma_bear_pos,
            )
            regime = "ma_above" if hs300_above else "ma_below"
            prev_hs300_above = hs300_above
        else:
            # Legacy: score-based quadratic confidence
            confidences = top_n.apply(lambda s: confidence_function(s, dead_zone, full_zone))
            disp_factor = min(1.0, score_dispersion / dispersion_threshold) if dispersion_threshold > 0 else 1.0
            breadth_factor = market_breadth ** breadth_power if breadth_power > 0 else 1.0
            avg_conf = confidences.mean() * disp_factor * breadth_factor
            total_target = min(0.95, avg_conf * 1.2)
        target_positions = relative_weights * total_target
        # Floor-discretize: always round down, then fill gap to highest-score ETFs
        target_positions = (target_positions / step).apply(math.floor) * step
        target_positions = target_positions.clip(lower=0)

        # Fill gap: distribute remaining steps to ETFs with highest composite scores
        disc_sum = target_positions.sum()
        if disc_sum < total_target - step * 0.01:
            gap_steps = round((total_target - disc_sum) / step)
            if gap_steps > 0:
                top_up = target_positions.index[:min(gap_steps, len(target_positions))]
                for code in top_up:
                    target_positions[code] += step

        # Snapshot previous targets BEFORE executing trades (for action diff)
        prev_targets = last_targets_dict

        # Execute trades
        holdings_value = sum(portfolio.get(c, 0) * prices_today.get(c, 0) for c in portfolio)
        total_value = cash + holdings_value
        target_codes = set(target_positions.index)

        for code in list(portfolio.keys()):
            if code not in target_codes or target_positions.get(code, 0) == 0:
                if code in prices_today:
                    sell_value = portfolio[code] * prices_today[code]
                    commission = sell_value * commission_rate
                    cash += sell_value - commission
                    total_commission += commission
                del portfolio[code]

        for code in target_codes:
            target_value = total_value * target_positions[code]
            current_value = portfolio.get(code, 0) * prices_today.get(code, 0)
            diff = target_value - current_value
            if code not in prices_today or prices_today[code] == 0:
                continue
            if diff > 0:
                buy_value = min(diff, cash)
                commission = buy_value * commission_rate
                net_buy = buy_value - commission
                buy_shares = net_buy / prices_today[code]
                portfolio[code] = portfolio.get(code, 0) + buy_shares
                cash -= buy_value
                total_commission += commission
            elif diff < -step * total_value:
                sell_shares = min(-diff / prices_today[code], portfolio.get(code, 0))
                sell_value = sell_shares * prices_today[code]
                commission = sell_value * commission_rate
                portfolio[code] = portfolio.get(code, 0) - sell_shares
                cash += sell_value - commission
                total_commission += commission
                if portfolio.get(code, 0) <= 0:
                    portfolio.pop(code, None)

        # Build per-ETF detail dict for this rebalance
        etf_detail = {}
        for code in factors_df.index:
            mf1 = mapped_f1.get(code, 0)
            mf2 = mapped_f2.get(code, 0)
            mf3 = mapped_f3.get(code, 0)
            mf4 = mapped_f4.get(code, 0) if w4 > 0 and "val_scores" in CACHE else 0
            pos = target_positions.get(code, 0)
            is_top = code in top_n.index
            conf = float(total_target) if is_top else 0.0  # regime mode: use global target
            # Determine trade action (compare to prev rebalance's target, both in 0-1 scale)
            prev_pos = prev_targets.get(code, 0)  # 0-1 scale (from target_positions.to_dict())
            cur_pos = float(pos)  # 0-1 scale
            if cur_pos > 0 and prev_pos == 0:
                action = "new"
            elif cur_pos > 0 and prev_pos > 0 and abs(cur_pos - prev_pos) > 0.0001:
                action = "adj"
            elif cur_pos > 0 and prev_pos > 0:
                action = "hold"
            elif cur_pos == 0 and prev_pos > 0:
                action = "out"
            else:
                action = ""
            etf_detail[code] = {
                "f1": round(mf1 * 100, 1),
                "f2": round(mf2 * 100, 1),
                "f3": round(mf3 * 100, 1),
                "f4": round(mf4 * 100, 1),
                "score": round(composite.get(code, 0) * 100, 1),
                "confidence": round(conf * 100, 0),
                "position": round(cur_pos * 100, 1),
                "price": round(prices_today.get(code, 0), 3),
                "action": action,
            }

        # Actual total position (after discretization, may differ from total_target)
        actual_total_pos = float(target_positions.sum())

        # Update prev-targets tracker (regardless of warmup boundary)
        last_targets_dict = target_positions.to_dict()

        # Only record post-warmup rebalances in user-visible signal_history
        if execution_date >= user_start:
            signal_history.append({
                "date": execution_date,
                "signal_date": rb_date,
                "execution_date": execution_date,
                "execution_timing": execution_timing,
                "scores": composite.to_dict(),
                "top_n": list(top_n.index),
                "positions": target_positions.to_dict(),
                "detail": etf_detail,
                "avg_confidence": round(float(total_target) * 100, 0),
                "total_position": round(actual_total_pos * 100, 1),
                "cash_pct": round((1.0 - actual_total_pos) * 100, 1),
                "regime": regime if conf_type in ("regime", "always_full", "dd_trigger", "momentum_crash", "ma_trend") else market_regime,
            })

    # --- Compute daily NAV (only over user-visible range) ---
    # Pre-build price lookup: {date_str: {code: price}} for O(1) access
    price_lookup = {}
    for code, df in all_daily.items():
        for _, row in df.iterrows():
            ds = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])[:10]
            if ds not in price_lookup:
                price_lookup[ds] = {}
            price_lookup[ds][code] = float(row["close"])

    portfolio2 = {}
    cash2 = initial_capital
    sig_idx = 0
    nav_records = []
    last_price = {}  # forward-fill: track last known price per ETF

    visible_dates = all_dates[all_dates >= user_start]

    for date in visible_dates:
        ds = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
        prices_now = price_lookup.get(ds, {})
        # Update last known prices (forward fill for missing dates)
        for code, price in prices_now.items():
            last_price[code] = price

        if sig_idx < len(signal_history) and date >= signal_history[sig_idx]["date"]:
            sig = signal_history[sig_idx]
            sig_idx += 1

            hv = sum(portfolio2.get(c, 0) * last_price.get(c, 0) for c in portfolio2)
            tv = cash2 + hv

            target_codes = set(sig["positions"].keys())

            trade_field = "open" if sig.get("execution_timing") == "next_open" else "close"

            for code in list(portfolio2.keys()):
                if code not in target_codes or sig["positions"].get(code, 0) == 0:
                    p = get_price_on_date(all_daily, code, date, trade_field) or prices_now.get(code, last_price.get(code, 0))
                    if p > 0:
                        sell_val = portfolio2[code] * p
                        cash2 += sell_val - sell_val * commission_rate
                    portfolio2.pop(code, None)

            for code in target_codes:
                p = get_price_on_date(all_daily, code, date, trade_field) or prices_now.get(code, last_price.get(code, 0))
                tgt = tv * sig["positions"][code]
                cur = portfolio2.get(code, 0) * p
                diff = tgt - cur
                if p == 0:
                    continue
                if diff > 0:
                    buy_val = min(diff, cash2)
                    shares = (buy_val - buy_val * commission_rate) / p
                    portfolio2[code] = portfolio2.get(code, 0) + shares
                    cash2 -= buy_val
                elif diff < -0.05 * tv:
                    shares = min(-diff / p, portfolio2.get(code, 0))
                    sell_val = shares * p
                    portfolio2[code] = portfolio2.get(code, 0) - shares
                    cash2 += sell_val - sell_val * commission_rate

        hv = sum(portfolio2.get(c, 0) * last_price.get(c, 0) for c in portfolio2)
        nav = cash2 + hv

        nav_records.append({
            "date": date,
            "nav": nav,
            "nav_pct": nav / initial_capital * 100,
            "holdings": len(portfolio2),
        })

    nav_df = pd.DataFrame(nav_records)
    elapsed = time.time() - t0

    # Summary
    if len(nav_df) < 2:
        return {"error": "Backtest produced no results"}

    initial = nav_df["nav"].iloc[0]
    final = nav_df["nav"].iloc[-1]
    total_return = (final / initial - 1) * 100
    days = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days
    annual_return = ((final / initial) ** (365 / max(days, 1)) - 1) * 100

    cummax = nav_df["nav"].cummax()
    dd = (nav_df["nav"] - cummax) / cummax * 100
    max_drawdown = float(dd.min())

    daily_rets = nav_df["nav"].pct_change().dropna()
    if len(daily_rets) > 0 and daily_rets.std() > 0:
        sharpe = (daily_rets.mean() * 252 - 0.02) / (daily_rets.std() * np.sqrt(252))
    else:
        sharpe = 0.0

    downside = daily_rets[daily_rets < 0.02 / 252] - 0.02 / 252
    if len(downside) > 0 and downside.std() > 0:
        sortino = (daily_rets.mean() * 252 - 0.02) / (downside.std() * np.sqrt(252))
    else:
        sortino = 0.0

    calmar = abs(annual_return / max_drawdown) if max_drawdown != 0 else 0.0
    win_rate = (daily_rets > 0).sum() / len(daily_rets) * 100 if len(daily_rets) > 0 else 0.0

    # Latest holdings
    latest_holdings = []
    if signal_history:
        last = signal_history[-1]
        etf_map = {e["code"]: e for e in CACHE["cfg"]["universe"]}
        for code in last["top_n"][:max_holdings]:
            info = etf_map.get(code, {})
            latest_holdings.append({
                "code": code,
                "name": info.get("name", code),
                "sector": info.get("sector", ""),
                "score": round(last["scores"].get(code, 0) * 100, 1),
                "position": round(last["positions"].get(code, 0) * 100, 1),
            })

    # Slice benchmarks to match nav_df dates and rebase to 100 at start
    eq_dates = CACHE.get("eq_dates", [])
    eq_full = CACHE.get("eq_weight_pct") or []
    hs_full = CACHE.get("hs300_pct") or []
    nav_date_strs = [d.strftime("%Y-%m-%d") for d in nav_df["date"]]

    def _rebase_slice(full_series, full_dates, target_dates):
        if not full_series or len(full_series) != len(full_dates):
            return None
        idx_map = {d: i for i, d in enumerate(full_dates)}
        out = []
        anchor = None
        for ds in target_dates:
            if ds in idx_map:
                v = full_series[idx_map[ds]]
                if anchor is None:
                    anchor = v
                out.append(round(v / anchor * 100, 2) if anchor else 100.0)
            else:
                out.append(out[-1] if out else 100.0)
        return out

    eq_sliced = _rebase_slice(eq_full, eq_dates, nav_date_strs)
    hs_sliced = _rebase_slice(hs_full, eq_dates, nav_date_strs)

    # 换仓次数：实际发生持仓变动的调仓日数
    rebalance_actual = sum(
        1 for s in signal_history
        if any(d.get("action") in ("new", "out") for d in s["detail"].values())
    )

    return {
        "summary": {
            "totalReturn": round(total_return, 2),
            "annualReturn": round(annual_return, 2),
            "maxDrawdown": round(max_drawdown, 2),
            "sharpe": round(float(sharpe), 2),
            "sortino": round(float(sortino), 2),
            "calmar": round(float(calmar), 2),
            "winRate": round(win_rate, 1),
            "rebalanceDays": len(signal_history),
            "rebalanceCount": rebalance_actual,
            "totalCommission": round(total_commission, 0),
            "commissionPct": round(total_commission / initial_capital * 100, 2),
            "elapsed": round(elapsed, 1),
            "startDate": user_start.strftime("%Y-%m-%d"),
            "endDate": user_end.strftime("%Y-%m-%d"),
            "executionTiming": execution_timing,
        },
        "nav": {
            "dates": nav_date_strs,
            "pct": [round(float(v), 2) for v in nav_df["nav_pct"]],
        },
        "drawdown": [round(float(v), 2) for v in dd],
        "hs300": hs_sliced,
        "eqWeight": eq_sliced,
        "holdings": latest_holdings,
        "etfNameMap": {e["code"]: e.get("name", e["code"]) for e in CACHE["cfg"].get("universe", [])},
        "etfSectorMap": {e["code"]: e.get("sector", "") for e in CACHE["cfg"].get("universe", [])},
        "signalHistory": [
            {
                "date": s["date"].strftime("%Y-%m-%d"),
                "signalDate": s.get("signal_date", s["date"]).strftime("%Y-%m-%d"),
                "executionDate": s.get("execution_date", s["date"]).strftime("%Y-%m-%d"),
                "executionTiming": s.get("execution_timing", execution_timing),
                "scores": {k: round(v * 100, 1) for k, v in s["scores"].items()},
                "topN": s["top_n"],
                "positions": {k: round(v * 100, 1) for k, v in s["positions"].items()},
                "detail": s["detail"],
                "avgConfidence": s["avg_confidence"],
                "totalPosition": s["total_position"],
                "cashPct": s["cash_pct"],
                "regime": s.get("regime", "choppy_range"),
            }
            for s in signal_history
        ],
    }

    # Free memory from large intermediate objects
    del price_lookup
    del nav_records
    gc.collect()

    return result


# ============================================================
# Flask app
# ============================================================
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)
# Preserve YAML insertion order in API responses (Flask 3.x)
app.json.sort_keys = False

# Force GC after each request to prevent memory buildup on long backtests
@app.after_request
def gc_after_request(response):
    import psutil
    gc.collect()
    mem_mb = psutil.Process().memory_info().rss / 1024 / 1024
    if mem_mb > 800:
        print(f"  [GC] Memory {mem_mb:.0f}MB > 800MB, aggressive cleanup")
        gc.collect(2)  # full collection
    return response

TEMPLATES_DIR = SKILL_DIR / "templates"


@app.route("/")
def index():
    return send_from_directory(TEMPLATES_DIR, "tuner.html")


@app.route("/assets/<path:filepath>")
def serve_assets(filepath):
    """Serve static assets (CSS/JS) from the skill's assets directory."""
    return send_from_directory(SKILL_DIR / "assets", filepath)


@app.route("/api/run", methods=["POST"])
def api_run():
    params = request.json
    result = run_tuner_backtest(params)
    return jsonify(result)


@app.route("/api/presets")
def api_presets():
    """Return strategy presets from YAML config."""
    cfg = CACHE.get("cfg") or load_config()
    presets = cfg.get("presets", {})
    result = {}
    # Use global confidence as fallback for regime params not in preset
    global_conf = cfg.get("confidence", {})
    global_regime_base = global_conf.get("regime_base", {})
    for key, p_data in presets.items():
        pc = p_data.get("confidence", {})
        prb = pc.get("regime_base", {})
        w = p_data.get("scoring", {}).get("weights", {})
        result[key] = {
            "label": p_data.get("label", key),
            "description": p_data.get("description", ""),
            "w1": int(w.get("ema_deviation", 0.30) * 100),
            "w2": int(w.get("rsi_adaptive", 0.25) * 100),
            "w3": int(w.get("volume_ratio", 0.30) * 100),
            "w4": int(w.get("valuation", 0.15) * 100),
            "bias": p_data.get("scoring", {}).get("bias_bonus", 4.0),
            "conf_type": pc.get("type", "regime"),
            "dead_zone": pc.get("dead_zone", global_conf.get("dead_zone", 25)),
            "full_zone": pc.get("full_zone", global_conf.get("full_zone", 65)),
            "regime_base_bull": prb.get("bull_trend", global_regime_base.get("bull_trend", 0.95)),
            "regime_base_choppy": prb.get("choppy_range", global_regime_base.get("choppy_range", 0.75)),
            "regime_base_bear": prb.get("bear_trend", global_regime_base.get("bear_trend", 0.35)),
            "regime_window": pc.get("regime_window", global_conf.get("regime_window", 8)),
            "regime_threshold": pc.get("regime_threshold", global_conf.get("regime_threshold", 0.03)),
            "breadth_weight": pc.get("breadth_weight", global_conf.get("breadth_weight", 0.2)),
            "clarity_threshold": pc.get("clarity_threshold", global_conf.get("clarity_threshold", 0.03)),
            "dd_sensitivity": pc.get("dd_sensitivity", global_conf.get("dd_sensitivity", 0.2)),
            "crash_window": pc.get("crash_window", global_conf.get("crash_window", 2)),
            "crash_threshold": pc.get("crash_threshold", global_conf.get("crash_threshold", -0.03)),
            "recovery_threshold": pc.get("recovery_threshold", global_conf.get("recovery_threshold", -0.01)),
            "crash_pos": pc.get("crash_pos", global_conf.get("crash_pos", 0.20)),
            "recovery_pos": pc.get("recovery_pos", global_conf.get("recovery_pos", 0.70)),
            "recovery_dd_level": pc.get("recovery_dd_level", global_conf.get("recovery_dd_level", -0.05)),
            "ma_bull_pos": pc.get("ma_bull_pos", global_conf.get("ma_bull_pos", 1.00)),
            "ma_bear_pos": pc.get("ma_bear_pos", global_conf.get("ma_bear_pos", 0.30)),
            "ma_trend_period": pc.get("ma_trend_period", global_conf.get("ma_trend_period", 26)),
            "ma_direction_confirm": pc.get("ma_direction_confirm", global_conf.get("ma_direction_confirm", True)),
            "max_holdings": p_data.get("position", {}).get("max_holdings", 6),
            "disc_step": int(p_data.get("position", {}).get("discretize_step", 0.05) * 100),
            "ema_period": p_data.get("factors", {}).get("ema", {}).get("period_weeks", 20),
            "rsi_period": p_data.get("factors", {}).get("rsi", {}).get("period_days", 14),
            "vol_window": p_data.get("factors", {}).get("volume_ratio", {}).get("window_days", 20),
            "f1_sensitivity": p_data.get("scoring", {}).get("sensitivity", {}).get("f1", 8.0),
            "f3_sensitivity": p_data.get("scoring", {}).get("sensitivity", {}).get("f3", 1.0),
            "f2_dead_zone": p_data.get("scoring", {}).get("sensitivity", {}).get("f2_dead_zone", 1.5),
            "rebalance_freq": p_data.get("position", {}).get("rebalance_freq", "W-FRI"),
            "execution_timing": p_data.get("position", {}).get("execution_timing", "same_close"),
            "score_band": int(p_data.get("position", {}).get("score_band", 0) * 100),
            "w6": int(p_data.get("scoring", {}).get("weights", {}).get("exhaustion_penalty", 0) * 100),
            "f6_rsi_thresh": p_data.get("factors", {}).get("f6_rsi_thresh", 80),
            "f6_drop_thresh": p_data.get("factors", {}).get("f6_drop_thresh", 0.025) * 100,
            "f6_base_penalty": p_data.get("factors", {}).get("f6_base_penalty", 0.15),
        }
    # Add universe options for the front-end selector
    result["_universe_options"] = [
        {"code": e["code"], "name": e.get("name", e["code"]),
         "sector": e.get("sector", ""), "bias": bool(e.get("bias", False))}
        for e in cfg.get("universe", [])
    ]
    return jsonify(result)


@app.route("/api/save", methods=["POST"])
def api_save():
    params = request.json
    try:
        cfg = load_config()
        cfg["scoring"]["weights"] = {
            "ema_deviation": params["w1"] / 100.0,
            "rsi_adaptive": params.get("w2", 0) / 100.0,
            "volume_ratio": params["w3"] / 100.0,
            "valuation": params.get("w4", 0) / 100.0,
            "exhaustion_penalty": params.get("w6", 0) / 100.0,
        }
        cfg["scoring"]["bias_bonus"] = float(params.get("bias", 0))
        cfg["confidence"]["type"] = params.get("conf_type", "quadratic")
        cfg["confidence"]["dead_zone"] = int(params["dead_zone"])
        cfg["confidence"]["full_zone"] = int(params["full_zone"])
        cfg["position"]["max_holdings"] = int(params["max_holdings"])
        cfg["position"]["discretize_step"] = int(params.get("disc_step", 5)) / 100.0
        cfg["factors"]["ema"]["period_weeks"] = int(params.get("ema_period", 20))
        cfg["factors"]["rsi"]["period_days"] = int(params.get("rsi_period", 14))
        cfg["factors"]["volume_ratio"]["window_days"] = int(params.get("vol_window", 20))
        cfg["scoring"]["sensitivity"] = {
            "f1": float(params.get("f1_sensitivity", 8.0)),
            "f3": float(params.get("f3_sensitivity", 1.0)),
            "f2_dead_zone": float(params.get("f2_dead_zone", 1.5)),
        }
        cfg["confidence"]["ma_bull_pos"] = float(params.get("ma_bull_pos", 1.0))
        cfg["confidence"]["ma_bear_pos"] = float(params.get("ma_bear_pos", 0.3))
        cfg["confidence"]["ma_trend_period"] = int(params.get("ma_trend_period", 26))
        cfg["position"]["execution_timing"] = params.get("execution_timing", "same_close")
        cfg["position"]["score_band"] = int(params.get("score_band", 0)) / 100.0
        cfg["factors"]["f6_rsi_thresh"] = float(params.get("f6_rsi_thresh", 80))
        cfg["factors"]["f6_drop_thresh"] = float(params.get("f6_drop_thresh", 2.5)) / 100.0
        cfg["factors"]["f6_base_penalty"] = float(params.get("f6_base_penalty", 0.15))

        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/kline")
def api_kline():
    """Return daily K-line (60d, OHLCV + RSI14 + Volume) and weekly K-line (30w, OHLCV + EMA20)
    for a given ETF, truncated to the rebalance date.

    Query params:
        code: ETF code (e.g. "512400")
        date: rebalance date (YYYY-MM-DD); data will be cut at this date
        rsi_period: RSI lookback (default 14)
        ema_period: EMA lookback in weeks (default 20)
    """
    code = request.args.get("code", "").strip()
    date_str = request.args.get("date", "").strip()
    rsi_period = int(request.args.get("rsi_period", 14))
    ema_period = int(request.args.get("ema_period", 20))

    if not code or code not in CACHE.get("all_daily", {}):
        return jsonify({"error": f"Unknown code: {code}"}), 404

    try:
        cutoff = pd.Timestamp(date_str) if date_str else None
    except Exception:
        return jsonify({"error": f"Bad date: {date_str}"}), 400

    daily = CACHE["all_daily"][code].copy()
    weekly = CACHE["all_weekly"][code].copy()

    # Truncate to cutoff
    if cutoff is not None:
        daily = daily[daily["date"] <= cutoff]
        weekly = weekly[weekly["date"] <= cutoff]

    # Take last 60 days / 30 weeks
    daily = daily.tail(60).reset_index(drop=True)
    weekly = weekly.tail(30).reset_index(drop=True)

    # Compute RSI on daily (need enough warmup; use full daily then tail again)
    full_daily = CACHE["all_daily"][code]
    if cutoff is not None:
        full_daily = full_daily[full_daily["date"] <= cutoff]
    rsi_full = calc_rsi(full_daily["close"].astype(float), period=rsi_period)
    daily_rsi = rsi_full.tail(len(daily)).tolist()

    # Compute EMA on weekly
    full_weekly = CACHE["all_weekly"][code]
    if cutoff is not None:
        full_weekly = full_weekly[full_weekly["date"] <= cutoff]
    ema_full = calc_ema(full_weekly["close"].astype(float), span=ema_period)
    weekly_ema = ema_full.tail(len(weekly)).tolist()

    def _ohlcv(df):
        # Returns lists for [date, open, close, low, high, volume] (echarts candlestick order: O,C,L,H)
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in df["date"]],
            "ohlc": [[float(r["open"]), float(r["close"]), float(r["low"]), float(r["high"])] for _, r in df.iterrows()],
            "volume": [float(v) for v in df["volume"]],
        }

    daily_data = _ohlcv(daily)
    daily_data["rsi"] = [None if pd.isna(v) else round(float(v), 2) for v in daily_rsi]

    weekly_data = _ohlcv(weekly)
    weekly_data["ema"] = [None if pd.isna(v) else round(float(v), 4) for v in weekly_ema]

    name = next((e.get("name", code) for e in CACHE["cfg"].get("universe", []) if e["code"] == code), code)

    return jsonify({
        "code": code,
        "name": name,
        "date": date_str,
        "daily": daily_data,
        "weekly": weekly_data,
        "rsiPeriod": rsi_period,
        "emaPeriod": ema_period,
    })


@app.route("/api/refresh_data", methods=["POST"])
def api_refresh_data():
    """Fetch latest data: intraday cache (pre-market) or confirmed CSV update (post-market)."""
    result = refresh_data()
    return jsonify(result)


@app.route("/api/data_status")
def api_data_status():
    """Return current data freshness: latest CSV date, intraday cache status."""
    all_daily = CACHE.get("all_daily", {})
    ic = CACHE.get("intraday_cache", {})
    ic_date = CACHE.get("intraday_date")

    csv_latest = ""
    for df in all_daily.values():
        if len(df) > 0:
            d = df["date"].iloc[-1]
            ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            if ds > csv_latest:
                csv_latest = ds

    today = datetime.now().strftime("%Y-%m-%d")
    return jsonify({
        "csvLatestDate": csv_latest,
        "todayDate": today,
        "intradayCacheDate": ic_date,
        "intradayCacheCount": len(ic),
        "isPostMarket": _is_post_market(),
    })


@app.route("/api/etf_prices")
def api_etf_prices():
    """Return OHLCV + RSI series for an ETF, between optional start/end.
    Supports daily or weekly frequency.

    Query params:
        code: ETF code
        start: YYYY-MM-DD (inclusive, optional)
        end: YYYY-MM-DD (inclusive, optional)
        rsi_period: int (default 14)
        freq: "daily" (default) or "weekly"
    """
    code = request.args.get("code", "").strip()
    start_str = request.args.get("start", "").strip()
    end_str = request.args.get("end", "").strip()
    rsi_period = int(request.args.get("rsi_period", 14))
    freq = request.args.get("freq", "daily").strip().lower()

    if not code or code not in CACHE.get("all_daily", {}):
        return jsonify({"error": f"Unknown code: {code}"}), 404

    # Source dataframe: weekly uses preloaded all_weekly; daily uses all_daily
    if freq == "weekly":
        full = CACHE["all_weekly"][code]
    else:
        full = CACHE["all_daily"][code]

    # Compute RSI on full history (so values inside [start, end] have proper warmup)
    rsi_full = calc_rsi(full["close"].astype(float), period=rsi_period)

    df = full.copy()
    rsi_series = rsi_full.copy()
    rsi_series.index = df.index

    if start_str:
        try:
            mask = df["date"] >= pd.Timestamp(start_str)
            df = df[mask]
            rsi_series = rsi_series[mask]
        except Exception:
            pass
    if end_str:
        try:
            mask = df["date"] <= pd.Timestamp(end_str)
            df = df[mask]
            rsi_series = rsi_series[mask]
        except Exception:
            pass

    # Volume: try column "amount" (成交额) if present, else fallback to "volume"
    vol_col = "amount" if "amount" in df.columns else "volume"
    has_vol = vol_col in df.columns

    return jsonify({
        "code": code,
        "freq": freq,
        "dates": [d.strftime("%Y-%m-%d") for d in df["date"]],
        "open":  [round(float(v), 4) for v in df["open"]]  if "open"  in df.columns else [],
        "high":  [round(float(v), 4) for v in df["high"]]  if "high"  in df.columns else [],
        "low":   [round(float(v), 4) for v in df["low"]]   if "low"   in df.columns else [],
        "close": [round(float(v), 4) for v in df["close"]],
        "volume": [round(float(v), 2) for v in df[vol_col]] if has_vol else [],
        "volumeLabel": "成交额" if vol_col == "amount" else "成交量",
        "rsi": [None if pd.isna(v) else round(float(v), 2) for v in rsi_series],
        "rsiPeriod": rsi_period,
    })


TUNER_PORT = 5179


def is_port_in_use(port):
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_tuner_alive(port):
    """Check if the Tuner Flask server is actually running on the port."""
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/presets", timeout=2)
        data = json.loads(resp.read())
        return isinstance(data, dict) and len(data) > 0
    except Exception:
        return False


def try_open_browser(url):
    """Open browser on Windows if not already open."""
    try:
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        import os
        if os.path.isfile(edge):
            subprocess.Popen([edge, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser(description="Quant Tuner - 量化策略调参服务器")
    _parser.add_argument("--auto", action="store_true",
                         help="自动检测并更新数据（冷启动或增量），然后启动 Tuner")
    _parser.add_argument("--full", action="store_true",
                         help="配合 --auto 使用，全量重新拉取数据")
    _parser.add_argument("--no-browser", action="store_true",
                         help="启动服务但不自动打开浏览器，供外部启动器统一控制")
    _args = _parser.parse_args()

    if is_port_in_use(TUNER_PORT):
        if is_tuner_alive(TUNER_PORT):
            print(f"Tuner already running at http://localhost:{TUNER_PORT}")
        else:
            print(f"Port {TUNER_PORT} is in use but NOT by Tuner.")
            print(f"Another process is occupying this port. Kill it or change TUNER_PORT.")
            print(f"Hint: netstat -ano | findstr :{TUNER_PORT}")
        sys.exit(0)

    # --auto: 自动更新数据
    if _args.auto:
        print("=" * 50)
        print("Auto mode: checking data freshness...")
        print("=" * 50)
        try:
            from quant_data_fetcher import load_universe, get_last_date, update_single
            universe = load_universe()
            csv_dir = Path(SKILL_DIR) / "data" / "quant"

            # 统计缺失/过期数量
            missing = 0
            outdated = 0
            for etf in universe:
                daily_path = csv_dir / f"{etf['code']}_daily.csv"
                weekly_path = csv_dir / f"{etf['code']}_weekly.csv"
                if not daily_path.exists() or not weekly_path.exists():
                    missing += 1
                else:
                    last = get_last_date(daily_path)
                    if last:
                        import pandas as _pd
                        last_dt = _pd.Timestamp(last)
                        if (_pd.Timestamp.now() - last_dt).days > 3:
                            outdated += 1

            if missing > 0:
                print(f"  Cold start: {missing} ETFs missing data, will fetch full history")
            if outdated > 0:
                print(f"  Incremental: {outdated} ETFs have stale data, will update")
            if missing == 0 and outdated == 0:
                print("  All data up to date")

            # 执行更新
            ok, fail = 0, 0
            for i, etf in enumerate(universe, 1):
                try:
                    daily_rows, weekly_rows, mode = update_single(etf, full=_args.full)
                    tag = f"{mode}" + (f" daily+{daily_rows}" if daily_rows else "")
                    print(f"  [{i:2d}/{len(universe)}] {etf['name']}({etf['code']}) {tag}")
                    ok += 1
                    if i < len(universe):
                        time.sleep(1.0)
                except Exception as e:
                    print(f"  [{i:2d}/{len(universe)}] {etf['name']}({etf['code']}) FAIL: {e}")
                    fail += 1

            print(f"  Data update: OK={ok}, FAIL={fail}")
            if fail > 0:
                print("  WARNING: Some ETFs failed to update, Tuner may have incomplete data")
            print()

        except ImportError:
            print("  quant_data_fetcher not available, skipping data update")
        except Exception as e:
            print(f"  Data update error: {e}")

    preload()
    print("=" * 50)
    print(f"Quant Tuner ready: http://localhost:{TUNER_PORT}")
    print("Open in browser: http://localhost:" + str(TUNER_PORT))
    print("Ctrl+C to stop")
    print("=" * 50)

    if not _args.no_browser:
        try_open_browser(f"http://localhost:{TUNER_PORT}")
    app.run(host="127.0.0.1", port=TUNER_PORT, debug=False, threaded=True)
