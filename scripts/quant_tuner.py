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
import io
import json
import socket
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_factors import compute_all_factors, map_f1, map_f2, map_f3, map_f4, map_f5, confidence_function, calc_ema, calc_rsi
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

    events_by_code = _load_corporate_action_events()
    cleaned_count = 0

    for etf in cfg["universe"]:
        code = etf["code"]
        daily, weekly = load_etf_data(code)
        if daily is None:
            continue

        # Apply share-split / share-change cleaning when events exist for this code
        events = events_by_code.get(code) or []
        if events:
            cleaning_input = _df_to_cleaning_input(daily)
            cleaned = run_data_cleaning_pipeline(cleaning_input, events)
            daily = _apply_cleaning_to_df(daily, cleaned)
            # Rebuild weekly from cleaned daily (避免跨拆分周的 weekly CSV 失真)
            weekly = _rebuild_weekly_from_daily(daily)
            cleaned_count += 1

        CACHE["all_daily"][code] = daily
        CACHE["all_weekly"][code] = weekly

    print(f"  Loaded {len(CACHE['all_daily'])}/{len(cfg['universe'])} ETFs")
    if cleaned_count:
        print(f"  Cleaned {cleaned_count} ETF(s) for share-split events: {[c for c in events_by_code if c in CACHE['all_daily']]}")

    # Precompute benchmarks
    _precompute_benchmarks()

    # Precompute F4 valuation scores from local CSV (no network)
    _precompute_valuation_scores()

    # Load market regimes for F4 regime-aware mapping
    _load_market_regimes()

    print("Preload complete.\n")


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
    start_dt = pd.Timestamp("2023-01-01")
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
        "rsi_adaptive": params["w2"] / 100.0,
        "volume_ratio": params["w3"] / 100.0,
        "valuation": params["w4"] / 100.0,
        "volatility": params.get("w5", 0) / 100.0,
    }
    cfg["scoring"]["bias_bonus"] = params["bias"]
    cfg["confidence"]["type"] = params.get("conf_type", "quadratic")
    cfg["confidence"]["dead_zone"] = params["dead_zone"] / 100.0
    cfg["confidence"]["full_zone"] = params["full_zone"] / 100.0
    cfg["position"]["max_holdings"] = params["max_holdings"]
    cfg["position"]["discretize_step"] = params.get("disc_step", 5) / 100.0
    cfg["factors"]["ema"]["period_weeks"] = params.get("ema_period", 20)
    cfg["factors"]["rsi"]["period_days"] = params.get("rsi_period", 14)
    cfg["factors"]["volume_ratio"]["window_days"] = params.get("vol_window", 20)
    cfg["scoring"]["sensitivity"] = {
        "f1": params.get("f1_sensitivity", 8.0),
        "f3": params.get("f3_sensitivity", 1.0),
        "f2_dead_zone": params.get("f2_dead_zone", 1.5),
    }

    weights = cfg["scoring"]["weights"]
    bias_bonus = cfg["scoring"]["bias_bonus"]
    sensitivity = cfg["scoring"].get("sensitivity", {})
    f1_sens = sensitivity.get("f1", 8.0)
    f3_sens = sensitivity.get("f3", 1.0)
    f2_dz = sensitivity.get("f2_dead_zone", 1.5)
    dead_zone = cfg["confidence"]["dead_zone"]
    full_zone = cfg["confidence"]["full_zone"]
    max_holdings = cfg["position"]["max_holdings"]
    step = cfg["position"]["discretize_step"]
    factor_cfg = cfg["factors"]

    # bias_bonus 从 UI 的 0-12 整数尺度映射到 0-1 的综合分尺度
    bias_map = {e["code"]: bias_bonus / 100.0 for e in cfg["universe"] if e.get("bias")}

    all_daily = CACHE["all_daily"]
    all_weekly = CACHE["all_weekly"]

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

    rebalance_dates = get_rebalance_dates(all_dates)
    if len(rebalance_dates) == 0:
        return {"error": "Not enough data in selected range"}

    # --- Backtest loop ---
    portfolio = {}
    cash = 1000000.0
    initial_capital = cash
    signal_history = []  # only records visible (post-warmup) rebalances
    last_targets_dict = {}  # tracks prev rebalance's targets across warmup boundary

    for rb_date in rebalance_dates:
        factors_data = {}
        prices_today = {}

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
            )
            if any(np.isnan(v) for v in factors.values()):
                continue

            factors_data[code] = factors
            prices_today[code] = float(daily_slice["close"].iloc[-1])

        if len(factors_data) < max_holdings:
            continue

        factors_df = pd.DataFrame(factors_data).T
        mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
        mapped_f2 = factors_df["f2_rsi_adaptive"].apply(lambda v: map_f2(v, f2_dz))
        mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

        w1 = weights.get("ema_deviation", 0.30)
        w2 = weights.get("rsi_adaptive", 0.25)
        w3 = weights.get("volume_ratio", 0.30)
        w4 = weights.get("valuation", 0.15)
        w5 = weights.get("volatility", 0.0)

        composite = mapped_f1 * w1 + mapped_f2 * w2 + mapped_f3 * w3

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

        top_n = composite.nlargest(max_holdings)
        confidences = top_n.apply(lambda s: confidence_function(s, dead_zone, full_zone))

        if top_n.sum() > 0:
            relative_weights = top_n / top_n.sum()
        else:
            relative_weights = pd.Series(0.0, index=top_n.index)

        avg_conf = confidences.mean()
        total_target = min(0.95, avg_conf * 1.2)
        target_positions = relative_weights * total_target
        target_positions = (target_positions / step).round() * step
        target_positions = target_positions.clip(lower=0)

        # Snapshot previous targets BEFORE executing trades (for action diff)
        prev_targets = last_targets_dict

        # Execute trades
        holdings_value = sum(portfolio.get(c, 0) * prices_today.get(c, 0) for c in portfolio)
        total_value = cash + holdings_value
        target_codes = set(target_positions.index)

        for code in list(portfolio.keys()):
            if code not in target_codes or target_positions.get(code, 0) == 0:
                if code in prices_today:
                    cash += portfolio[code] * prices_today[code]
                del portfolio[code]

        for code in target_codes:
            target_value = total_value * target_positions[code]
            current_value = portfolio.get(code, 0) * prices_today.get(code, 0)
            diff = target_value - current_value
            if code not in prices_today or prices_today[code] == 0:
                continue
            if diff > 0:
                buy_shares = min(diff, cash) / prices_today[code]
                portfolio[code] = portfolio.get(code, 0) + buy_shares
                cash -= buy_shares * prices_today[code]
            elif diff < -step * total_value:
                sell_shares = min(-diff / prices_today[code], portfolio.get(code, 0))
                portfolio[code] = portfolio.get(code, 0) - sell_shares
                cash += sell_shares * prices_today[code]
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
            conf = float(confidences.get(code, 0)) if is_top else 0.0
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
        if rb_date >= user_start:
            signal_history.append({
                "date": rb_date,
                "scores": composite.to_dict(),
                "top_n": list(top_n.index),
                "positions": target_positions.to_dict(),
                "detail": etf_detail,
                "avg_confidence": round(float(avg_conf) * 100, 0),
                "total_position": round(actual_total_pos * 100, 1),
                "cash_pct": round((1.0 - actual_total_pos) * 100, 1),
                "regime": market_regime,
            })

    # --- Compute daily NAV (only over user-visible range) ---
    portfolio2 = {}
    cash2 = initial_capital
    sig_idx = 0
    nav_records = []

    visible_dates = all_dates[all_dates >= user_start]

    for date in visible_dates:
        if sig_idx < len(signal_history) and date >= signal_history[sig_idx]["date"]:
            sig = signal_history[sig_idx]
            sig_idx += 1

            prices_now = {}
            for code in all_daily:
                df = all_daily[code]
                mask = df["date"] <= date
                if mask.sum() > 0:
                    prices_now[code] = float(df.loc[mask, "close"].iloc[-1])

            hv = sum(portfolio2.get(c, 0) * prices_now.get(c, 0) for c in portfolio2)
            tv = cash2 + hv
            target_codes = set(sig["positions"].keys())

            for code in list(portfolio2.keys()):
                if code not in target_codes or sig["positions"].get(code, 0) == 0:
                    if code in prices_now:
                        cash2 += portfolio2[code] * prices_now[code]
                    portfolio2.pop(code, None)

            for code in target_codes:
                tgt = tv * sig["positions"][code]
                cur = portfolio2.get(code, 0) * prices_now.get(code, 0)
                diff = tgt - cur
                if code not in prices_now or prices_now[code] == 0:
                    continue
                if diff > 0:
                    shares = min(diff, cash2) / prices_now[code]
                    portfolio2[code] = portfolio2.get(code, 0) + shares
                    cash2 -= shares * prices_now[code]
                elif diff < -0.05 * tv:
                    shares = min(-diff / prices_now[code], portfolio2.get(code, 0))
                    portfolio2[code] = portfolio2.get(code, 0) - shares
                    cash2 += shares * prices_now[code]

        prices_now = {}
        for code in all_daily:
            df = all_daily[code]
            mask = df["date"] <= date
            if mask.sum() > 0:
                prices_now[code] = float(df.loc[mask, "close"].iloc[-1])

        hv = sum(portfolio2.get(c, 0) * prices_now.get(c, 0) for c in portfolio2)
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

    return {
        "summary": {
            "totalReturn": round(total_return, 2),
            "annualReturn": round(annual_return, 2),
            "maxDrawdown": round(max_drawdown, 2),
            "sharpe": round(float(sharpe), 2),
            "sortino": round(float(sortino), 2),
            "calmar": round(float(calmar), 2),
            "winRate": round(win_rate, 1),
            "rebalanceCount": len(signal_history),
            "elapsed": round(elapsed, 1),
            "startDate": user_start.strftime("%Y-%m-%d"),
            "endDate": user_end.strftime("%Y-%m-%d"),
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


# ============================================================
# Flask app
# ============================================================
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

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
    for key, p in presets.items():
        w = p.get("scoring", {}).get("weights", {})
        result[key] = {
            "label": p.get("label", key),
            "description": p.get("description", ""),
            "w1": int(w.get("ema_deviation", 0.30) * 100),
            "w2": int(w.get("rsi_adaptive", 0.25) * 100),
            "w3": int(w.get("volume_ratio", 0.30) * 100),
            "w4": int(w.get("valuation", 0.15) * 100),
            "bias": p.get("scoring", {}).get("bias_bonus", 4.0),
            "conf_type": p.get("confidence", {}).get("type", "quadratic"),
            "dead_zone": p.get("confidence", {}).get("dead_zone", 25),
            "full_zone": p.get("confidence", {}).get("full_zone", 65),
            "max_holdings": p.get("position", {}).get("max_holdings", 6),
            "disc_step": int(p.get("position", {}).get("discretize_step", 0.05) * 100),
            "ema_period": p.get("factors", {}).get("ema", {}).get("period_weeks", 20),
            "rsi_period": p.get("factors", {}).get("rsi", {}).get("period_days", 14),
            "vol_window": p.get("factors", {}).get("volume_ratio", {}).get("window_days", 20),
            "f1_sensitivity": p.get("scoring", {}).get("sensitivity", {}).get("f1", 8.0),
            "f3_sensitivity": p.get("scoring", {}).get("sensitivity", {}).get("f3", 1.0),
            "f2_dead_zone": p.get("scoring", {}).get("sensitivity", {}).get("f2_dead_zone", 1.5),
        }
    return jsonify(result)


@app.route("/api/save", methods=["POST"])
def api_save():
    params = request.json
    try:
        cfg = load_config()
        cfg["scoring"]["weights"] = {
            "ema_deviation": params["w1"] / 100.0,
            "rsi_adaptive": params["w2"] / 100.0,
            "volume_ratio": params["w3"] / 100.0,
            "valuation": params["w4"] / 100.0,
        }
        cfg["scoring"]["bias_bonus"] = float(params["bias"])
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
    if is_port_in_use(TUNER_PORT):
        if is_tuner_alive(TUNER_PORT):
            print(f"Tuner already running at http://localhost:{TUNER_PORT}")
        else:
            print(f"Port {TUNER_PORT} is in use but NOT by Tuner.")
            print(f"Another process is occupying this port. Kill it or change TUNER_PORT.")
            print(f"Hint: netstat -ano | findstr :{TUNER_PORT}")
        sys.exit(0)

    preload()
    print("=" * 50)
    print(f"Quant Tuner ready: http://localhost:{TUNER_PORT}")
    print("Open in browser: http://localhost:" + str(TUNER_PORT))
    print("Ctrl+C to stop")
    print("=" * 50)

    app.run(host="127.0.0.1", port=TUNER_PORT, debug=False)
