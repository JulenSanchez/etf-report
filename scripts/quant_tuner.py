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
import threading
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

from quant_factors import calc_ema, calc_rsi
from quant_data_utils import load_etf_data, rebuild_weekly_from_daily
from benchmark_data import load_hs300_daily_cached, build_hs300_pct, build_hs300_weekly, build_ma_trend_cache
from trading_calendar import load_trading_calendar, is_trading_day, last_trading_day
import quant_contract as qc

CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
OVERRIDES_PATH = SKILL_DIR / "config" / "quant_user_overrides.yaml"

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
    "ready": False,  # True after preload() completes — frontend polls this
}


def _deep_merge(base, override):
    """Merge override dict into base dict recursively (in-place)."""
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("scoring") is None:
        cfg["scoring"] = {}

    # Merge user overrides (tuner /api/save output) — preserves base YAML comments
    if OVERRIDES_PATH.exists():
        with OVERRIDES_PATH.open("r", encoding="utf-8") as f:
            overrides = yaml.safe_load(f)
        if overrides:
            _deep_merge(cfg, overrides)

    return cfg


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

    load_trading_calendar()

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
        #     weekly = rebuild_weekly_from_daily(daily)

        CACHE["all_daily"][code] = daily
        CACHE["all_weekly"][code] = weekly

    print(f"  Loaded {len(CACHE['all_daily'])}/{len(cfg['universe'])} ETFs")

    # Precompute benchmarks
    _precompute_benchmarks()

    # Precompute F4 valuation scores from local CSV (no network)
    _precompute_valuation_scores()

    # Load market regimes for F4 regime-aware mapping
    _load_market_regimes()

    # Precompute heatmap returns (5d / 20d rolling pct_change)
    _precompute_heatmap_returns()

    # Load ETF metadata (AUM + top10 holdings)
    _load_etf_metadata()

    CACHE["ready"] = True
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
    Returns dict: {code: {name, open, prev_close, price, high, low, volume, amount, possibly_halted}}
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
            opn = float(data[1]) if data[1] else 0
            prev = float(data[2]) if data[2] else 0
            price = float(data[3]) if data[3] else 0
            vol = int(float(data[8])) if data[8] else 0
            results[code] = {
                "name": data[0],
                "open": opn,
                "prev_close": prev,
                "price": price,
                "high": float(data[4]) if data[4] else 0,
                "low": float(data[5]) if data[5] else 0,
                "volume": vol,
                "amount": float(data[9]) if data[9] else 0,
                # L1 halt detection: open==prev_close and zero volume → hasn't started trading
                "possibly_halted": (opn > 0 and abs(opn - prev) < 0.001 and vol == 0),
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


def _run_incremental_fetch(cfg, end_date=None):
    """Run quant_data_fetcher incrementally for all ETFs. Updates CSV files on disk.
    end_date: passed through to fetch_etf_kline to cap the data range.
    Returns (ok_count, fail_count).
    """
    from quant_data_fetcher import update_single, FRESH_MARKER, _latest_allowed_date
    from datetime import datetime as _dt
    import time as _time

    # Global freshness check: require data up to latest allowed close date
    if FRESH_MARKER.exists():
        try:
            expected = _latest_allowed_date()
            if FRESH_MARKER.read_text().strip() >= expected:
                print(f"  (All {len(cfg['universe'])} ETFs already fresh, skipping fetch)")
                return len(cfg["universe"]), 0
        except Exception:
            pass

    ok, fail, fresh = 0, 0, 0
    for etf in cfg["universe"]:
        try:
            _, _, mode = update_single(etf, full=False, end_date=end_date)
            if mode == "fresh":
                fresh += 1
            else:
                ok += 1
                _time.sleep(1.0)  # only sleep when we actually hit the API
        except Exception as e:
            print(f"  [Fetch] {etf['code']} failed: {e}")
            fail += 1
    if fresh > 0:
        print(f"  (Skipped {fresh} already-fresh ETFs)")
    # Write freshness marker if all succeeded
    if fail == 0:
        try:
            FRESH_MARKER.parent.mkdir(parents=True, exist_ok=True)
            FRESH_MARKER.write_text(_dt.now().strftime("%Y-%m-%d"))
        except Exception:
            pass
    return ok, fail


def _reload_csv_to_cache(cfg):
    """Reload all CSV data from disk into CACHE (after fetcher has updated them)."""
    for etf in cfg["universe"]:
        code = etf["code"]
        daily, weekly = load_etf_data(code)
        if daily is not None:
            CACHE["all_daily"][code] = daily
            CACHE["all_weekly"][code] = weekly


def _sina_batch_append(cfg, date_str, rt_prices):
    """Append one day's Sina realtime data to all ETF CSVs (single-day only)."""
    from quant_data_fetcher import append_csv, save_csv, DATA_DIR as QDATA_DIR
    import pandas as _pd
    ok, fail = 0, 0
    for etf in cfg["universe"]:
        code = etf["code"]
        rt = rt_prices.get(code)
        if not rt or rt["price"] <= 0:
            fail += 1
            continue
        daily_path = QDATA_DIR / f"{code}_daily.csv"
        weekly_path = QDATA_DIR / f"{code}_weekly.csv"
        new_row = _pd.DataFrame([{
            "date": date_str, "open": rt["open"], "close": rt["price"],
            "high": rt["high"], "low": rt["low"],
            "volume": int(rt["volume"]), "amount": rt["amount"],
        }])
        append_csv(new_row, daily_path)
        full_daily = _pd.read_csv(daily_path)
        weekly = rebuild_weekly_from_daily(full_daily)
        save_csv(weekly, weekly_path)
        ok += 1
    return ok, fail


def refresh_data():
    """Main refresh entry point. Called by /api/refresh_data.

    Rule (REQ-196):
      - Pre-market (before 09:30): same as non-trading — incremental fetch to backfill
        historical gaps, no intraday data yet.
      - Intraday (09:30–15:10, trading day): incremental fetch with end_date=today
        (excludes today's incomplete bar from the API), then add today's live data
        via intraday cache.  CSV stays clean.
      - Post-market (>=15:10): incremental fetch → CSV (now has confirmed close).
        Clear intraday cache.
      - Non-trading day: incremental fetch to fill historical gaps.  No intraday data.

    Intraday cache is a single flat dict, always overwritten.
    Computation code merges cache into daily_df on-the-fly (see _get_daily_with_cache).
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    cfg = CACHE.get("cfg") or load_config()
    time_label = now.strftime("%H:%M")

    post_market = _is_post_market(now)
    trading = is_trading_day(now)
    pre_market = trading and now.hour * 60 + now.minute < MORNING_OPEN
    intraday = trading and not pre_market and not post_market

    ok, fail = 0, 0
    ran_fetch = False
    used_sina = False

    # ── Single-day Sina fast path (post-market only, gap = exactly 1 trading day) ──
    if post_market:
        from quant_data_fetcher import get_last_date, DATA_DIR as QDATA_DIR
        prev_td = last_trading_day(now)  # last trading day before today (handles weekends)
        all_yesterday = True
        for etf in cfg["universe"]:
            last = get_last_date(QDATA_DIR / f"{etf['code']}_daily.csv")
            if last is None or last < prev_td:
                all_yesterday = False
                break
        if all_yesterday:
            print(f"  [Refresh] Post-market — trying Sina single-day fast path...")
            rt = _fetch_sina_realtime(cfg)
            if rt:
                ok, fail = _sina_batch_append(cfg, today_str, rt)
                if fail == 0:
                    used_sina = True
                    _reload_csv_to_cache(cfg)
                    print(f"  [Refresh] Sina fast path: {ok} OK, ~2s")
                else:
                    print(f"  [Refresh] Sina fast path partial: {ok} OK, {fail} fail — falling back")
            else:
                print(f"  [Refresh] Sina API failed — falling back to incremental")

    # ── Incremental fetch (Tencent per-ETF, fallback or non-post-market) ──
    if not used_sina and (post_market or not trading or pre_market):
        print(f"  [Refresh] Running incremental fetch...")
        ok, fail = _run_incremental_fetch(cfg)
        ran_fetch = True
    elif intraday:
        print(f"  [Refresh] Intraday — CSV write skipped (live data → cache only)")
        _reload_csv_to_cache(cfg)

    if used_sina:
        gap_msg = f"Sina batch | {ok} OK, {fail} fail"
    elif ran_fetch:
        gap_msg = f"CSV gap-fill | {ok} OK, {fail} fail"
    else:
        gap_msg = ""

    _precompute_benchmarks()
    _precompute_valuation_scores()
    _load_market_regimes()
    _precompute_heatmap_returns()

    # ── Post-market (>=15:10) ──
    if post_market:
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

    # ── Non-trading day / Pre-market ──
    if not trading or pre_market:
        ltd = last_trading_day(now)
        tag = "Pre-market" if pre_market else "Non-trading day"
        msg = f"{time_label} | {tag} | CSV up to {ltd} | {gap_msg}"
        print(f"  [Refresh] {msg}")
        return {
            "status": "confirmed",
            "message": msg,
            "fetchOk": ok,
            "fetchFail": fail,
            "date": ltd,
            "time": time_label,
        }

    # ── Intraday (09:30–15:10): historical gaps filled + intraday cache ──
    rt_prices = _fetch_sina_realtime(cfg)
    if not rt_prices:
        return {"status": "error", "message": f"{time_label} | Sina API failed", "date": today_str, "time": time_label}

    # Retry missing ETFs (transient API glitches — single ETF may fail parsing in batch call)
    missing = [e for e in cfg["universe"] if e["code"] not in rt_prices or rt_prices[e["code"]]["price"] <= 0]
    if missing:
        print(f"  [Refresh] {len(missing)} ETFs missing from first fetch, retrying...")
        time.sleep(2)
        # Build a minimal cfg with only the missing ETFs
        retry_cfg = dict(cfg)
        retry_cfg["universe"] = missing
        retry_rt = _fetch_sina_realtime(retry_cfg)
        for code, data in retry_rt.items():
            if data.get("price", 0) > 0:
                rt_prices[code] = data
        still_missing = [e["code"] for e in missing if e["code"] not in rt_prices or rt_prices[e["code"]]["price"] <= 0]
        if still_missing:
            print(f"  [Refresh] Still missing after retry: {still_missing}")

    # Build quick lookup: QDII ETF codes + their previous intraday cache
    qdii_codes = {e["code"] for e in cfg["universe"] if e.get("qdii")}
    prev_ic = CACHE.get("intraday_cache", {})

    updated = 0
    halted_count = 0
    for etf in cfg["universe"]:
        code = etf["code"]
        rt = rt_prices.get(code)
        if not rt or rt["price"] <= 0:
            continue

        is_qdii = code in qdii_codes
        vol = rt["volume"]
        amt = rt["amount"]

        # ── Halt detection for QDII ETFs ──
        halted = False
        if is_qdii:
            # L1: morning halt — open==prev_close and no volume (from Sina)
            if rt.get("possibly_halted"):
                halted = True
            # L2: afternoon halt — same price & volume as previous refresh (stale data)
            elif code in prev_ic:
                prev = prev_ic[code]
                if (prev.get("halted") and
                    abs(rt["price"] - prev["close"]) < 0.001 and
                    vol == prev.get("raw_volume", 0)):
                    halted = True  # persisted halt

        # ── Estimate EOD volume (skip if halted) ──
        raw_vol = vol
        raw_amt = amt
        if not halted and vol > 0:
            vol = _estimate_eod_volume(vol, now)
            if amt > 0:
                amt = _estimate_eod_volume(int(amt), now)

        if halted:
            halted_count += 1

        CACHE["intraday_cache"][code] = {
            "date": today_str,
            "time": time_label,
            "open": rt["open"],
            "close": rt["price"],
            "high": rt["high"],
            "low": rt["low"],
            "volume": vol,
            "amount": amt,
            "raw_volume": raw_vol,     # pre-estimation volume (for L2 halt detection)
            "raw_amount": raw_amt,     # pre-estimation amount
            "halted": halted,
        }
        updated += 1

    CACHE["intraday_date"] = today_str
    vol_note = " (vol est. EOD)" if _trading_elapsed_minutes(now) < TOTAL_TRADING_MINUTES else ""
    halt_note = f" | {halted_count} halted" if halted_count > 0 else ""
    msg = f"{time_label} | Intraday | {updated} ETFs{vol_note}{halt_note} | {gap_msg}"
    print(f"  [Refresh] {msg}")

    return {
        "status": "intraday",
        "message": msg,
        "count": updated,
        "date": today_str,
        "time": time_label,
        "haltedCount": halted_count,
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

    return rebuild_weekly_from_daily(daily_df)


def _precompute_benchmarks():
    """Compute HS300 + equal-weight benchmarks once."""
    all_daily = CACHE["all_daily"]
    if not all_daily:
        return

    close_series = []
    for code, df in all_daily.items():
        s = df.set_index("date")["close"].astype(float).sort_index().pct_change()
        s.name = code
        close_series.append(s)
    if not close_series:
        return

    returns_df = pd.concat(close_series, axis=1).sort_index()
    eq_returns = returns_df.mean(axis=1, skipna=True).fillna(0.0)
    eq_nav_series = (1.0 + eq_returns).cumprod() * 100.0
    date_strs = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in eq_nav_series.index]

    CACHE["eq_weight_pct"] = [round(float(v), 2) for v in eq_nav_series]
    CACHE["eq_dates"] = date_strs

    try:
        hs = load_hs300_daily_cached()
        CACHE["hs300_pct"] = build_hs300_pct(hs, date_strs)
        CACHE["hs300_daily_df"] = hs
        CACHE["hs300_weekly_df"] = build_hs300_weekly(hs)
        _build_ma_trend_cache(20)
    except Exception as e:
        print(f"  [WARN] HS300 data load failed: {e}")
        CACHE["hs300_pct"] = None
        CACHE["hs300_daily_df"] = None
        CACHE["hs300_weekly_df"] = None

    # HS300 weekly DataFrame for residual momentum (reuse if available)
    if CACHE.get("hs300_weekly_df") is not None:
        CACHE["hs300_weekly"] = CACHE["hs300_weekly_df"].rename(columns={"close": "close"})
        print(f"  HS300 weekly: {len(CACHE['hs300_weekly'])} bars for residual momentum")
    else:
        CACHE["hs300_weekly"] = None


def _build_ma_trend_cache(period):
    """Build or retrieve HS300 MA trend lookup for a given period."""
    ma_cache = CACHE.get("hs300_above_ma", {})
    if period in ma_cache:
        return ma_cache[period]
    result = build_ma_trend_cache(CACHE.get("hs300_daily_df"), CACHE.get("hs300_weekly_df"), period)
    if result is None:
        return None
    ma_cache[period] = result
    CACHE["hs300_above_ma"] = ma_cache
    above_map = result.get("above", {})
    rising_map = result.get("ma_rising", {})
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


def _load_etf_metadata():
    """Load ETF metadata (AUM + top10 holdings) from disk into CACHE."""
    path = SKILL_DIR / "data" / "quant" / "etf_metadata.json"
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                CACHE["etf_metadata"] = json.load(f)
            print(f"  ETF metadata: {len(CACHE['etf_metadata'])} ETFs loaded")
        else:
            CACHE["etf_metadata"] = {}
            print("  ETF metadata: no file, skipping")
    except Exception as e:
        CACHE["etf_metadata"] = {}
        print(f"  ETF metadata: load failed ({e})")


def _precompute_heatmap_returns(lookbacks=(5, 20)):
    """Precompute N-day rolling returns for all ETFs.
    Called once at startup; subsequent requests read CACHE["heatmap"].
    Set CACHE["heatmap"] = { "5": {code: {date_str: ret}}, "20": {...} }
    Uses date column as index so pct_change aligns on calendar dates.
    """
    all_daily = CACHE.get("all_daily", {})
    if not all_daily:
        return
    result = {}
    for lb in lookbacks:
        lb_key = str(lb)
        result[lb_key] = {}
        for code, df in all_daily.items():
            # Set date as index so pct_change aligns on trading days
            close = df.set_index("date")["close"].astype(float)
            ret = close.pct_change(lb).dropna()
            # Convert to dict {date_str: return_value}
            result[lb_key][code] = {str(d): float(v) for d, v in zip(ret.index, ret.values)}
    CACHE["heatmap"] = result
    total = sum(len(v) for v in result.values())
    print(f"  Heatmap returns precomputed: {len(result)} lookbacks, {total} series")


def _weight_total_pct(params):
    return qc.weight_total_pct(params)


def _parse_universe_filter(params):
    return qc.parse_universe_filter(params)


def _validate_tuner_params(params):
    return qc.validate_tuner_params(params)


def _compute_etf_contributions(trade_log, signal_history, etf_name_map, etf_sector_map):
    """Aggregate per-ETF contribution metrics from trade log and signal history.

    Returns dict: {code: {name, sector, selectedCount, selectionRate, avgWeight,
                          avgHoldDays, firstSelected, totalPnlPct, avgTradePnl,
                          tradeCount, winRate, payoffRatio, sectorShare,
                          topCooccurrence, cooccurrenceCount, phaseRates, trend}}
    """
    total_signals = max(len(signal_history), 1)
    all_codes = set(etf_name_map.keys())  # all ETFs in universe, including never-selected
    for s in signal_history:
        for code in s.get("top6", []):
            all_codes.add(code)
    for t in trade_log:
        all_codes.add(t["code"])

    # ── Phase definitions ──
    phases = [
        ("2020-2021", "2020-01-01", "2021-12-31"),
        ("2022",      "2022-01-01", "2022-12-31"),
        ("2023",      "2023-01-01", "2023-12-31"),
        ("2024",      "2024-01-01", "2024-12-31"),
        ("2025",      "2025-01-01", "2025-12-31"),
        ("2026",      "2026-01-01", "2026-12-31"),
    ]

    # ── Per-code aggregation ──
    result = {}
    for code in sorted(all_codes):
        name = etf_name_map.get(code, code)
        sector = etf_sector_map.get(code, "")

        # --- Participation (from signal_history) ---
        selected_count = 0
        available_signals = 0
        weight_sum = 0.0
        weight_n = 0
        hold_streaks = []
        current_streak = 0
        first_selected = None

        for s in signal_history:
            top6 = s.get("top6", [])
            positions = s.get("positions", {})
            scores = s.get("scores", {})
            if code in scores:
                available_signals += 1
            date_str = str(s.get("date", ""))[:10]
            in_top6 = code in top6
            if in_top6:
                selected_count += 1
                w = positions.get(code, 0)
                weight_sum += w * 100  # convert to %
                weight_n += 1
                current_streak += 1
                if first_selected is None:
                    first_selected = date_str
            else:
                if current_streak > 0:
                    hold_streaks.append(current_streak)
                current_streak = 0
        if current_streak > 0:
            hold_streaks.append(current_streak)

        effective = max(available_signals, 1)
        selection_rate = round(selected_count / effective * 100, 1)
        avg_weight = round(weight_sum / max(weight_n, 1), 1)
        avg_hold = round(sum(hold_streaks) / max(len(hold_streaks), 1), 1)

        # --- Performance (from trade_log) ---
        code_trades = [t for t in trade_log if t["code"] == code]
        if code_trades:
            winners = [t for t in code_trades if t["pnl_pct"] > 0]
            losers = [t for t in code_trades if t["pnl_pct"] <= 0]
            total_pnl = round(sum(t["pnl_pct"] for t in code_trades), 2)
            avg_pnl = round(total_pnl / len(code_trades), 2)
            wr = round(len(winners) / len(code_trades) * 100, 1)
            aw = sum(t["pnl_pct"] for t in winners) / len(winners) if winners else 0
            al = abs(sum(t["pnl_pct"] for t in losers) / len(losers)) if losers else 0
            payoff = round(aw / al, 2) if al > 0 else 999.0
        else:
            total_pnl, avg_pnl, wr, payoff = 0.0, 0.0, 0.0, 0.0

        # --- Structural ---
        # Sector share: this ETF's selection count / total selections in its sector
        sector_total = sum(
            1 for s in signal_history
            for c in s.get("top6", [])
            if etf_sector_map.get(c, "") == sector
        )
        sector_share = round(selected_count / max(sector_total, 1) * 100, 1)

        # Co-occurrence: most common co-selected ETF
        co_occur = {}
        for s in signal_history:
            top6 = s.get("top6", [])
            if code in top6:
                for other in top6:
                    if other != code:
                        co_occur[other] = co_occur.get(other, 0) + 1
        top_co = max(co_occur, key=co_occur.get) if co_occur else ""
        top_co_name = etf_name_map.get(top_co, top_co) if top_co else ""
        top_co_n = co_occur.get(top_co, 0) if top_co else 0

        # --- Lifecycle (phase rates) ---
        phase_rates = {}
        for phase_label, p_start, p_end in phases:
            n = sum(1 for s in signal_history
                    if p_start <= str(s.get("date", ""))[:10] <= p_end)
            c = sum(1 for s in signal_history
                    if p_start <= str(s.get("date", ""))[:10] <= p_end
                    and code in s.get("top6", []))
            phase_rates[phase_label] = round(c / max(n, 1) * 100, 1) if n > 0 else 0

        # Trend: compare last 2 phases with first 2
        recent = sum(phase_rates.get(p[0], 0) for p in phases[-2:])
        early = sum(phase_rates.get(p[0], 0) for p in phases[:2])
        if recent > early + 5:
            trend = "rising"
        elif recent < early - 5:
            trend = "declining"
        else:
            trend = "stable"

        # Observation period: < 80 trading days since listing
        meta = (CACHE.get("etf_metadata") or {}).get(code, {})
        listing_str = meta.get("listing_date", "")
        trading_days = 0
        observation = False
        if listing_str:
            try:
                listing_dt = pd.Timestamp(listing_str)
                end_dt = pd.Timestamp(end_date_str) if (end_date_str := str(signal_history[-1].get("date", ""))[:10]) else None
                if end_dt:
                    trading_days = max(0, len([d for d in pd.date_range(listing_dt, end_dt) if d.weekday() < 5]))
                observation = trading_days < 80
            except Exception:
                pass

        result[code] = {
            "name": name,
            "sector": sector,
            "observation": observation,
            "tradingDays": trading_days,
            "selectedCount": selected_count,
            "availableSignals": available_signals,
            "selectionRate": selection_rate,
            "avgWeight": avg_weight,
            "avgHoldDays": avg_hold,
            "firstSelected": first_selected or "",
            "totalPnlPct": total_pnl,
            "avgTradePnl": avg_pnl,
            "tradeCount": len(code_trades),
            "winRate": wr,
            "payoffRatio": payoff,
            "sectorShare": sector_share,
            "topCooccurrence": top_co,
            "topCoName": top_co_name,
            "cooccurrenceCount": top_co_n,
            "phaseRates": phase_rates,
            "trend": trend,
        }
    return result


def run_tuner_backtest(params):
    """Tuner wrapper → unified quant_backtest.run_backtest().

    Builds config_override from frontend params, prepares preloaded data from
    CACHE, calls the shared backtest engine, and formats output for the frontend.
    """
    validation_error = _validate_tuner_params(params)
    if validation_error:
        return {"error": validation_error}

    t0 = time.time()
    from quant_backtest import run_backtest as _run_backtest

    # ── Build config_override from shared parameter contract ──
    config_override = qc.tuner_params_to_config_override(params)

    # ── Prepare preloaded data ──
    all_daily = dict(CACHE["all_daily"])
    all_weekly = dict(CACHE["all_weekly"])
    # Merge intraday cache into daily data ONLY (for execution price lookup).
    # Weekly data stays as CSV-original — never rebuild from intraday.
    # rebuild_weekly_from_daily() would shift the current week's bar date
    # forward, causing searchsorted() to skip it for prior rebalance dates
    # within the same week → different F1 value → lookahead bias.
    if CACHE.get("intraday_cache"):
        all_daily = {}
        for code in CACHE["all_daily"]:
            all_daily[code] = _get_daily_with_cache(code)
        # all_weekly stays as CSV snapshot — no intraday rebuild

    universe_filter, _universe_mode = _parse_universe_filter(params)
    if universe_filter is not None:
        all_daily = {k: v for k, v in all_daily.items() if k in universe_filter}
        all_weekly = {k: v for k, v in all_weekly.items() if k in universe_filter}

    available = len(all_daily)
    if available < 6:
        return {"error": f"Only {available} ETFs with data, need at least 6"}

    ma_trend_period = config_override["confidence"]["ma_trend_period"]
    ma_cache = _build_ma_trend_cache(ma_trend_period) or {}
    preloaded = {
        "all_daily": all_daily,
        "all_weekly": all_weekly,
        "market_regimes": CACHE.get("market_regimes", {}),
        "hs300_above_ma": ma_cache.get("above", {}),
        "hs300_ma_rising": ma_cache.get("ma_rising", {}),
    }

    # Factor precomputation and price lookup now handled inside run_backtest()

    execution_timing = config_override["position"]["execution_timing"]
    if execution_timing not in ("same_close", "next_open"):
        execution_timing = "same_close"

    # ── Call unified backtest engine ──
    return_debug = bool(params.get("debug", False))
    nav_df, signal_history, extra = _run_backtest(
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        preset="preset2",
        execution_timing=execution_timing,
        universe_filter=universe_filter,
        preloaded=preloaded,
        config_override=config_override,
        return_details=True,
        return_debug=return_debug,
    )
    total_commission = extra.get("total_commission", 0)

    if nav_df is None:
        return {"error": "Backtest produced no results"}

    elapsed = time.time() - t0
    initial_cap = 1000000.0
    final_nav_val = float(nav_df["nav"].iloc[-1])
    total_return = (final_nav_val / initial_cap - 1) * 100
    days = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days
    annual_return = ((final_nav_val / initial_cap) ** (365 / max(days, 1)) - 1) * 100 if days > 0 else 0

    cummax = nav_df["nav"].cummax()
    dd = (nav_df["nav"] - cummax) / cummax * 100
    max_drawdown = float(dd.min())

    daily_rets = nav_df["nav"].pct_change().dropna()
    if len(daily_rets) > 0 and daily_rets.std() > 0:
        sharpe = (daily_rets.mean() * 252 - 0.02) / (daily_rets.std() * np.sqrt(252))
    else:
        sharpe = 0.0

    downside = daily_rets[daily_rets < 0]
    if len(downside) > 0 and downside.std() > 0:
        sortino = (daily_rets.mean() * 252 - 0.02) / (downside.std() * np.sqrt(252))
    else:
        sortino = 0.0

    monthly_groups = nav_df.groupby(nav_df["date"].dt.to_period("M"))
    monthly_rets = monthly_groups["nav"].last().pct_change().dropna()
    monthly_win_rate = float((monthly_rets > 0).sum() / max(len(monthly_rets), 1) * 100) if len(monthly_rets) > 0 else 0.0

    # ── Per-trade win rate & payoff ratio from trade log ──
    trade_log = extra.get("trade_log", [])
    if trade_log:
        winning_trades = [t for t in trade_log if t["pnl_pct"] > 0]
        losing_trades = [t for t in trade_log if t["pnl_pct"] <= 0]
        win_rate = round(len(winning_trades) / len(trade_log) * 100, 1)
        avg_win = sum(t["pnl_pct"] for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = abs(sum(t["pnl_pct"] for t in losing_trades) / len(losing_trades)) if losing_trades else 0.0
        payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 999.0
    else:
        win_rate = 0.0
        payoff_ratio = 0.0
        avg_win = 0.0
        avg_loss = 0.0
    best_month = float(monthly_rets.max() * 100) if len(monthly_rets) > 0 else 0.0
    worst_month = float(monthly_rets.min() * 100) if len(monthly_rets) > 0 else 0.0
    calmar = annual_return / abs(max_drawdown) if abs(max_drawdown) > 0 else 0.0

    max_win_streak = 0
    max_loss_streak = 0
    current_streak = 0
    for r in daily_rets:
        if r > 0.02 / 252:
            current_streak = current_streak + 1 if current_streak > 0 else 1
            max_win_streak = max(max_win_streak, current_streak)
        elif r < -0.02 / 252:
            current_streak = current_streak - 1 if current_streak < 0 else -1
            max_loss_streak = min(max_loss_streak, current_streak)
        else:
            current_streak = 0

    yearly_groups = nav_df.groupby(nav_df["date"].dt.year)
    annual_returns = {}
    for yr, grp in yearly_groups:
        first_nav = grp["nav"].iloc[0]
        last_nav = grp["nav"].iloc[-1]
        annual_returns[str(yr)] = round((last_nav / first_nav - 1) * 100, 1)

    # Benchmarks: rebase to 100 at start, align to NAV dates
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

    hs_sliced = _rebase_slice(hs_full, eq_dates, nav_date_strs)
    eq_sliced = _rebase_slice(eq_full, eq_dates, nav_date_strs)
    # Excess return vs HS300 (both rebased to 100)
    excess_return = round((final_nav_val / initial_cap) - (hs_sliced[-1] / 100 if hs_sliced else 1), 4) * 100
    excess_return = round(excess_return, 1)

    latest_holdings = []
    if signal_history:
        last = signal_history[-1]
        etf_map = {e["code"]: e for e in CACHE["cfg"]["universe"]}
        for code in last.get("top6", [])[:6]:
            info = etf_map.get(code, {})
            latest_holdings.append({
                "code": code, "name": info.get("name", code),
                "sector": info.get("sector", ""),
                "position": round(last.get("positions", {}).get(code, 0) * 100, 1),
                "score": round(last.get("scores", {}).get(code, 0) * 100, 1),
            })

    conf_type = config_override["confidence"]["type"]
    strategy_label = {"regime": "Regime-aware", "dd_trigger": "DD Trigger",
                      "momentum_crash": "Mom Crash", "always_full": "Always 95%",
                      "ma_trend": "MA Trend"}.get(conf_type, conf_type or "unknown")

    user_start_str = params.get("start_date", "")
    user_end_str = params.get("end_date", "")
    try:
        start_dt = pd.Timestamp(user_start_str) if user_start_str else nav_df["date"].iloc[0]
        end_dt = pd.Timestamp(user_end_str) if user_end_str else nav_df["date"].iloc[-1]
    except Exception:
        start_dt = nav_df["date"].iloc[0]
        end_dt = nav_df["date"].iloc[-1]

    etf_name_map = {e["code"]: e.get("name", e["code"]) for e in CACHE["cfg"].get("universe", [])}
    etf_sector_map = {e["code"]: e.get("sector", "") for e in CACHE["cfg"].get("universe", [])}

    # Enrich detail with "action" by comparing consecutive positions
    prev_positions = {}
    enriched_history = []
    actual_rebalance_count = 0
    for s in signal_history:
        detail = s.get("detail", {})
        had_action = False
        for code, d in detail.items():
            cur_pos = d.get("position", 0)
            prev_pos = prev_positions.get(code, 0)
            if cur_pos > 0 and prev_pos == 0:
                d["action"] = "new"
                had_action = True
            elif cur_pos > 0 and prev_pos > 0 and abs(cur_pos - prev_pos) > 0.01:
                d["action"] = "adj_up" if cur_pos > prev_pos else "adj_down"
                d["delta"] = round(cur_pos - prev_pos, 1)
                had_action = True
            elif cur_pos > 0 and prev_pos > 0:
                d["action"] = "hold"
            elif cur_pos == 0 and prev_pos > 0:
                d["action"] = "out"
                had_action = True
            else:
                d["action"] = ""
        prev_positions = {code: d.get("position", 0) for code, d in detail.items()}
        if had_action:
            actual_rebalance_count += 1

        sig_date = s["date"]
        # Compute C_eff for this rebalance
        pos_cfg = config_override.get("position", {})
        base_c = float(pos_cfg.get("concentration", 2.0))
        cs_val = float(pos_cfg.get("c_sensitivity", 0.0))
        c_eff = base_c
        if cs_val > 0:
            all_scores = np.array(list(s["scores"].values()))
            top6_scores = np.array([s["scores"][c] for c in s.get("top6", []) if c in s["scores"]])
            if len(all_scores) > 5 and len(top6_scores) > 1:
                mu, sigma = float(all_scores.mean()), max(float(all_scores.std()), 0.02)
                z_top6 = (top6_scores - mu) / sigma
                disp = float(z_top6.std())
                c_mult = 1.0 + cs_val * (disp - 0.5)
                c_eff = round(base_c * max(c_mult, 0.1), 2)

        enriched_history.append({
            "date": sig_date.strftime("%Y-%m-%d") if hasattr(sig_date, "strftime") else str(sig_date)[:10],
            "signalDate": s.get("signal_date", sig_date).strftime("%Y-%m-%d") if hasattr(s.get("signal_date", sig_date), "strftime") else str(s.get("signal_date", sig_date))[:10],
            "executionDate": sig_date.strftime("%Y-%m-%d") if hasattr(sig_date, "strftime") else str(sig_date)[:10],
            "scores": s["scores"],
            "topN": s.get("top6", []),
            "top_n": s.get("top6", []),
            "positions": s["positions"],
            "detail": detail,
            "avgConfidence": round(s.get("total_target", 0) * 100, 0),
            "totalPosition": round(sum(s.get("positions", {}).values()) * 100, 1),
            "cashPct": round((1.0 - sum(s.get("positions", {}).values())) * 100, 1),
            "regime": s.get("regime", ""),
            "cEff": c_eff,
        })

    # Detect intraday estimate: last NAV date matches intraday cache date
    ic_date = CACHE.get("intraday_date")
    ic_times = []
    for v in CACHE.get("intraday_cache", {}).values():
        if v.get("time"):
            ic_times.append(v["time"])
    ic_time = ic_times[-1] if ic_times else None
    has_intraday = bool(ic_date and nav_date_strs and nav_date_strs[-1] == ic_date)

    # Write debug snapshots if requested
    if return_debug:
        import json as _json
        snaps = extra.get("debug_snapshots", [])
        debug_path = SKILL_DIR / "data" / "debug_tuner.json"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with debug_path.open("w", encoding="utf-8") as _f:
            _json.dump({"count": len(snaps), "snapshots": snaps}, _f, ensure_ascii=False, indent=2)
        print(f"DEBUG: {len(snaps)} snapshots saved → {debug_path}")

    return {
        "strategy": strategy_label,
        "etfNameMap": etf_name_map,
        "hs300": hs_sliced,
        "eqWeight": eq_sliced,
        "drawdown": [round(v, 2) for v in dd],
        "summary": {
            "totalReturn": round(total_return, 2),
            "annualReturn": round(annual_return, 2),
            "maxDrawdown": round(max_drawdown, 2),
            "sharpe": round(float(sharpe), 2),
            "sortino": round(float(sortino), 2),
            "calmar": round(float(calmar), 2),
            "excessReturn": excess_return,
            "winRate": round(win_rate, 1),
            "payoffRatio": round(payoff_ratio, 2),
            "avgWin": round(avg_win, 2) if isinstance(avg_win, (int, float)) else 0.0,
            "avgLoss": round(avg_loss, 2) if isinstance(avg_loss, (int, float)) else 0.0,
            "tradeCount": len(trade_log),
            "monthlyWinRate": round(monthly_win_rate, 1),
            "bestMonth": round(best_month, 2),
            "worstMonth": round(worst_month, 2),
            "maxWinStreak": max_win_streak,
            "maxLossStreak": abs(max_loss_streak),
            "startDate": start_dt.strftime("%Y-%m-%d") if hasattr(start_dt, "strftime") else str(start_dt)[:10],
            "endDate": end_dt.strftime("%Y-%m-%d") if hasattr(end_dt, "strftime") else str(end_dt)[:10],
            "tradingDays": len(nav_df),
            "rebalanceCount": actual_rebalance_count,
            "rebalanceDays": len(enriched_history),
            "commissionPct": round(total_commission / initial_cap * 100, 2),
            "elapsed": round(elapsed, 1),
            "initialCapital": initial_cap,
            "finalNav": round(final_nav_val, 0),
            "annualReturns": annual_returns,
            "hasIntradayEstimate": has_intraday,
            "intradayDate": ic_date if has_intraday else None,
            "intradayTime": ic_time if has_intraday else None,
            "intradayCount": len(CACHE.get("intraday_cache", {})) if has_intraday else 0,
            "haltedEtfs": [code for code, v in CACHE.get("intraday_cache", {}).items() if v.get("halted")],
        },
        "nav": {
            "dates": nav_date_strs,
            "pct": [round(float(v), 2) for v in nav_df["nav_pct"]],
        },
        "benchmarks": {
            "hs300": hs_sliced,
            "eqWeight": eq_sliced,
            "holdings": latest_holdings,
            "etfNameMap": etf_name_map,
            "etfSectorMap": etf_sector_map,
        },
        "signalHistory": enriched_history,
        "etfContributions": _compute_etf_contributions(trade_log, signal_history, etf_name_map, etf_sector_map),
    }



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
    gc.collect()
    try:
        import psutil
        mem_mb = psutil.Process().memory_info().rss / 1024 / 1024
        if mem_mb > 800:
            print(f"  [GC] Memory {mem_mb:.0f}MB > 800MB, aggressive cleanup")
            gc.collect(2)
    except Exception:
        pass
    return response

TEMPLATES_DIR = SKILL_DIR / "templates"


@app.route("/")
def index():
    return send_from_directory(TEMPLATES_DIR, "tuner.html")


@app.route("/assets/<path:filepath>")
def serve_assets(filepath):
    """Serve static assets (CSS/JS) from the skill's assets directory."""
    return send_from_directory(SKILL_DIR / "assets", filepath)


def _require_ready():
    """Return (json_error, 503) if CACHE not ready, otherwise None."""
    if not CACHE.get("ready"):
        return jsonify({"error": "Server is still loading data, please wait"}), 503
    return None


_BACKTEST_CACHE_PATH = SKILL_DIR / "data" / "quant" / "cache" / "last_backtest.json"


def _cache_version_hash():
    """Hash key source files so cached results invalidate on code change."""
    import hashlib
    h = hashlib.md5()
    for fname in ["quant_tuner.py", "quant_backtest.py", "quant_factors.py",
                  "quant_contract.py", "quant_data_utils.py"]:
        fp = SKILL_DIR / "scripts" / fname
        if fp.exists():
            h.update(fp.read_bytes())
    return h.hexdigest()[:8]


@app.route("/api/run", methods=["POST"])
def api_run():
    guard = _require_ready()
    if guard:
        return guard
    params = request.json or {}
    try:
        result = run_tuner_backtest(params)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 500
    # Save to disk cache
    try:
        cache = {"version": _cache_version_hash(), "params": params, "result": result}
        _BACKTEST_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _BACKTEST_CACHE_PATH.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, default=str)
    except Exception:
        pass
    return jsonify(result)


@app.route("/api/debug_data_state")
def api_debug_data_state():
    """Debug: show data state — CSV row counts, intraday cache status."""
    ic = CACHE.get("intraday_cache", {})
    ic_date = CACHE.get("intraday_date", "")
    # Sample first 3 ETFs
    samples = {}
    for i, (code, df) in enumerate(CACHE["all_daily"].items()):
        if i >= 3: break
        dates = df["date"].astype(str).values
        samples[code] = {"rows": len(df), "first": dates[0][:10], "last": dates[-1][:10]}
    merged_samples = {}
    if ic:
        for i, code in enumerate(CACHE["all_daily"]):
            if i >= 3: break
            df = _get_daily_with_cache(code)
            dates = df["date"].astype(str).values
            merged_samples[code] = {"rows": len(df), "first": dates[0][:10], "last": dates[-1][:10]}
    return jsonify({
        "intraday_cache_etfs": len(ic),
        "intraday_date": ic_date,
        "csv_samples": samples,
        "merged_samples": merged_samples,
    })


# ── REQ-263a: snapshot intraday cache to disk ──
SNAPSHOT_DIR = SKILL_DIR / "data" / "intraday_snapshots"

@app.route("/api/snapshot_intraday", methods=["POST"])
def api_snapshot_intraday():
    guard = _require_ready()
    if guard:
        return guard
    label = request.args.get("label", datetime.now().strftime("%H%M"))
    today_str = datetime.now().strftime("%Y-%m-%d")
    ic = CACHE.get("intraday_cache", {})
    if not ic:
        return jsonify({"ok": False, "error": "No intraday cache available"})
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{today_str}_{label}.json"
    path = SNAPSHOT_DIR / filename
    # Convert numpy/pandas types to native Python
    data = {"date": today_str, "time": label, "entries": {}}
    for code, row in ic.items():
        entry = {}
        for k, v in row.items():
            entry[k] = float(v) if hasattr(v, "item") else v
        data["entries"][code] = entry
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    return jsonify({"ok": True, "file": filename, "etfs": len(ic)})


# ── REQ-263b: backtest using saved intraday snapshot as today's close ──
@app.route("/api/backtest_with_snapshot", methods=["POST"])
def api_backtest_with_snapshot():
    guard = _require_ready()
    if guard:
        return guard
    params = request.json or {}
    snapshot_file = params.get("snapshot", "")
    if not snapshot_file:
        return jsonify({"error": "Missing 'snapshot' parameter"}), 400
    path = SNAPSHOT_DIR / snapshot_file
    if not path.exists():
        return jsonify({"error": f"Snapshot not found: {snapshot_file}"}), 404
    with path.open("r", encoding="utf-8") as f:
        snap = json.load(f)

    # Save original daily data, then patch with snapshot
    _orig_daily = dict(CACHE["all_daily"])
    import pandas as _pd
    snap_date = snap["date"]
    for code, entry in snap["entries"].items():
        if code not in _orig_daily:
            continue
        df = _orig_daily[code].copy()
        # Find or create row for snapshot date
        mask = df["date"].astype(str).str[:10] == snap_date
        if mask.any():
            idx = df[mask].index[0]
            df.at[idx, "close"] = entry.get("close", df.at[idx, "close"])
            if "volume" in entry:
                df.at[idx, "volume"] = entry["volume"]
            if "amount" in entry:
                df.at[idx, "amount"] = entry["amount"]
        CACHE["all_daily"][code] = df

    try:
        result = run_tuner_backtest(params)
    finally:
        CACHE["all_daily"] = _orig_daily
    return jsonify(result)


@app.route("/api/last_result")
def api_last_result():
    guard = _require_ready()
    if guard:
        return guard
    try:
        if _BACKTEST_CACHE_PATH.exists():
            with _BACKTEST_CACHE_PATH.open("r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("version") == _cache_version_hash():
                return jsonify({"cached": True, "params": cache.get("params", {}),
                                "result": cache.get("result", {})})
    except Exception:
        pass
    return jsonify({"cached": False})


@app.route("/api/metadata")
def api_metadata():
    guard = _require_ready()
    if guard:
        return guard
    return jsonify(CACHE.get("etf_metadata", {}))


@app.route("/api/refresh_metadata", methods=["POST"])
def api_refresh_metadata():
    guard = _require_ready()
    if guard:
        return guard
    try:
        from fetch_etf_metadata import load_universe, fetch_one, load_existing, save_metadata
        universe = load_universe()
        existing = load_existing()
        ok = fail = 0
        import time as _t
        for etf in universe:
            try:
                entry = fetch_one(etf, existing)
                existing[etf["code"]] = entry
                ok += 1
                _t.sleep(1.0)
            except Exception:
                fail += 1
        save_metadata(existing)
        CACHE["etf_metadata"] = existing
        return jsonify({"ok": True, "message": f"meta: {ok} OK, {fail} fail", "ok_count": ok, "fail_count": fail})
    except ImportError:
        return jsonify({"ok": False, "message": "fetch_etf_metadata not available"}), 500
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/param_schema")
def api_param_schema():
    """Return shared Tuner parameter schema."""
    return jsonify(qc.get_param_schema())


@app.route("/api/presets")
def api_presets():
    guard = _require_ready()
    if guard:
        return guard
    """Return strategy presets from YAML config."""
    cfg = CACHE.get("cfg") or load_config()
    return jsonify(qc.build_presets_response(cfg))


def _save_to_preset(preset_name, overrides):
    """Deep-merge overrides into a specific preset inside quant_universe.yaml.
    If the preset doesn't exist yet, auto-create it from daily_aggressive template."""
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    presets = cfg.setdefault("presets", {})
    if preset_name not in presets:
        template = presets.get("preset2", {})
        if template:
            presets[preset_name] = deepcopy(template)
            presets[preset_name]["label"] = "自定义策略"
            presets[preset_name]["description"] = "用户自定义策略。"
        else:
            raise ValueError(f"Preset '{preset_name}' not found and no template available")
    target = presets[preset_name]
    for section in ("scoring", "confidence", "position", "factors"):
        if section in overrides:
            target.setdefault(section, {}).update(overrides[section])
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


@app.route("/api/save", methods=["POST"])
def api_save():
    guard = _require_ready()
    if guard:
        return guard
    params = dict(request.json or {})
    preset_name = params.pop("_preset", None)
    validation_error = _validate_tuner_params(params)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error})
    try:
        # Build config fragment from shared parameter contract
        overrides = qc.tuner_params_to_preset_patch(params, load_config())

        if preset_name:
            _save_to_preset(preset_name, overrides)
        else:
            # Fallback: no preset selected → save to overrides file
            with OVERRIDES_PATH.open("w", encoding="utf-8") as f:
                f.write("# Quant Tuner user overrides — safe to delete to reset to defaults\n")
                yaml.dump(overrides, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        # Refresh CACHE so /api/presets returns updated config immediately
        CACHE["cfg"] = load_config()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/kline")
def api_kline():
    guard = _require_ready()
    if guard:
        return guard
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
    guard = _require_ready()
    if guard:
        return guard
    """Fetch latest data: intraday cache (pre-market) or confirmed CSV update (post-market)."""
    result = refresh_data()
    return jsonify(result)


@app.route("/api/data_status")
def api_data_status():
    """Return current data freshness: latest CSV date, intraday cache status."""
    all_daily = CACHE.get("all_daily", {})
    ic = CACHE.get("intraday_cache", {})
    ic_date = CACHE.get("intraday_date")
    ic_times = [v.get("time") for v in ic.values() if v.get("time")]
    ic_time = ic_times[-1] if ic_times else None

    csv_latest = ""
    for df in all_daily.values():
        if len(df) > 0:
            d = df["date"].iloc[-1]
            ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            if ds > csv_latest:
                csv_latest = ds

    today = datetime.now().strftime("%Y-%m-%d")
    halted_codes = [code for code, v in ic.items() if v.get("halted")]
    return jsonify({
        "ready": CACHE.get("ready", False),
        "csvLatestDate": csv_latest,
        "todayDate": today,
        "intradayCacheDate": ic_date,
        "intradayCacheTime": ic_time,
        "intradayCacheCount": len(ic),
        "isPostMarket": _is_post_market(),
        "haltedEtfs": halted_codes,
    })


@app.route("/api/etf_prices")
def api_etf_prices():
    guard = _require_ready()
    if guard:
        return guard
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

    # Source dataframe: merge intraday cache so kline-replay shows EOD-estimated data
    if freq == "weekly":
        full = _get_weekly_with_cache(code)
    else:
        full = _get_daily_with_cache(code)

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


@app.route("/api/heatmap_data")
def api_heatmap_data():
    guard = _require_ready()
    if guard:
        return guard
    """Return precomputed N-day rolling returns for all ETFs."""
    lookback = request.args.get("lookback", "20").strip()
    force = request.args.get("force", "0") == "1"

    if force or "heatmap" not in CACHE:
        _precompute_heatmap_returns()

    heatmap = CACHE.get("heatmap", {})
    if lookback not in heatmap:
        return jsonify({"error": f"Unknown lookback: {lookback}"}), 400

    data = heatmap[lookback]
    cfg = CACHE.get("cfg", {})

    # Collect all dates (union of all ETF date keys, sorted)
    all_dates = set()
    for code, ret_map in data.items():
        all_dates.update(ret_map.keys())
    dates = sorted(all_dates)

    etfs_out = []
    for entry in cfg.get("universe", []):
        code = entry["code"]
        if code not in data:
            continue
        ret_map = data[code]
        rets = [ret_map.get(d) for d in dates]  # None if date missing
        etfs_out.append({
            "code": code,
            "name": entry.get("name", code),
            "sector": entry.get("sector", ""),
            "returns": rets,
        })

    return jsonify({"lookback": int(lookback), "dates": dates, "etfs": etfs_out})


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
    _parser.add_argument("--preload-then-wait", action="store_true",
                         help="Hot-swap: preload synchronously, signal via file, then wait for old process to be killed before binding port")
    _args = _parser.parse_args()

    _hot_swap = _args.preload_then_wait

    if not _hot_swap:
        # Normal mode: ensure port is free before starting
        for _retry in range(10):
            if not is_port_in_use(TUNER_PORT):
                break
            if _retry == 0:
                print(f"Port {TUNER_PORT} in use, waiting for release...")
            time.sleep(0.1)
        else:
            if is_tuner_alive(TUNER_PORT):
                print(f"Tuner already running at http://localhost:{TUNER_PORT}")
            else:
                print(f"Port {TUNER_PORT} is in use but NOT by Tuner.")
                print(f"Another process is occupying this port. Kill it or change TUNER_PORT.")
                print(f"Hint: netstat -ano | findstr :{TUNER_PORT}")
            sys.exit(0)

    # --auto: 自动更新数据 (in hot-swap mode this runs while old process still serves)
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

    # Preload
    if _hot_swap:
        # Hot-swap: preload synchronously while old process still serves port 5179.
        # Then signal PowerShell to kill the old process by writing a marker file.
        # Wait until PowerShell deletes the marker (means old process is gone),
        # then bind the port and start Flask.
        preload()

        signal_path = SKILL_DIR / ".tuner_ready_to_bind"
        signal_path.write_text("ready", encoding="utf-8")

        for _ in range(100):  # 10s timeout waiting for PowerShell to delete signal
            if not signal_path.exists():
                break
            time.sleep(0.1)
        else:
            # PowerShell may have crashed — clean up and proceed
            if signal_path.exists():
                signal_path.unlink(missing_ok=True)

        # OS may need ~50ms to release old port after taskkill /F
        for _ in range(20):
            if not is_port_in_use(TUNER_PORT):
                break
            time.sleep(0.05)
    else:
        # Normal mode: start preload in background, Flask serves frontend immediately.
        # The frontend polls /api/data_status until CACHE["ready"] is True.
        threading.Thread(target=preload, daemon=True).start()

    print("=" * 50)
    if _hot_swap:
        print(f"Quant Tuner ready: http://localhost:{TUNER_PORT}")
    else:
        print(f"Quant Tuner: http://localhost:{TUNER_PORT}")
        print("  (Loading data in background — page will refresh when ready)")
    print("Ctrl+C to stop")
    print("=" * 50)

    if not _args.no_browser:
        try_open_browser(f"http://localhost:{TUNER_PORT}")
    app.run(host="127.0.0.1", port=TUNER_PORT, debug=False, threaded=True)
