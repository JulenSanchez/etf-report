"""
REQ-177 M2.1: 量化回测引擎
串联 M1.1 三因子模块，模拟每周调仓，输出组合净值曲线。

用法：
  python scripts/quant_backtest.py                    # 默认参数回测
  python scripts/quant_backtest.py --start 2023-01-01 # 指定起始日期
  python scripts/quant_backtest.py --output results.csv  # 输出净值CSV
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from quant_factors import (
    map_f1, map_f3, map_f4, map_f7,
    confidence_function, regime_confidence, infer_regime_from_nav, dd_trigger_confidence, momentum_crash_confidence, ma_trend_confidence, multi_benchmark_confidence,
)
from etf_report.core.quant_data_utils import load_etf_data as _load_etf_data, get_price_on_date as _get_price_on_date
from benchmark_data import load_hs300_daily_cached, build_hs300_weekly, build_ma_trend_cache, load_index_daily_cached, build_index_weekly

CONFIG_PATH = PROJECT_ROOT / "config" / "quant_universe.yaml"
DATA_DIR = PROJECT_ROOT / "data" / "quant"
OUTPUT_DIR = PROJECT_ROOT / "data" / "quant_results"


def load_config(preset: str = None):
    if preset is None:
        from etf_report.core.quant_contract import DEFAULT_PRESET
        preset = DEFAULT_PRESET
    """加载配置，并用指定 preset 覆盖顶层 scoring/confidence/position/factors。
    preset=None 将报错（顶层不再维护权重）。
    """
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if preset is None:
        raise ValueError("preset is required — top-level scoring no longer carries weights")

    if cfg.get("scoring") is None:
        cfg["scoring"] = {}

    p = cfg.get("presets", {}).get(preset)
    if p is None:
        raise ValueError(f"Preset '{preset}' not found in quant_universe.yaml")
    for block in ("scoring", "confidence", "position", "factors", "account"):
        if block in p:
            cfg[block].update(p[block])
    for key in ("weights", "sensitivity"):
        if key in p.get("scoring", {}):
            cfg["scoring"][key] = p["scoring"][key]
    return cfg


def load_etf_data(code: str):
    """加载一支 ETF 的日线和周线数据"""
    return _load_etf_data(code, DATA_DIR)


def get_rebalance_dates(daily_dates: pd.DatetimeIndex, freq: str = "W-FRI"):
    """获取调仓日期列表

    freq="W-FRI": 每周最后一个交易日（默认，兼容原有逻辑）
    freq="daily": 每个交易日都是调仓日
    """
    if freq == "daily":
        return daily_dates.sort_values()

    # 按周分组，取每周最后一个交易日
    dates_series = pd.Series(daily_dates).sort_values().reset_index(drop=True)
    weekly_groups = dates_series.groupby(dates_series.dt.isocalendar().week.values +
                                          dates_series.dt.isocalendar().year.values * 100)
    rebalance_dates = weekly_groups.max().sort_values().values
    return pd.DatetimeIndex(rebalance_dates)


def get_execution_date(signal_date: pd.Timestamp, all_dates: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Return trade execution date — always same_close (signal date = execution date)."""
    return signal_date


def execution_price_field() -> str:
    """Return price field used for trade execution — always close."""
    return "close"


def get_price_on_date(all_daily: dict, code: str, date: pd.Timestamp, field: str = "close") -> float | None:
    return _get_price_on_date(all_daily, code, date, field)


def _execute_rebalance(portfolio, cash, prices, suspended_codes,
                       target_positions, tradable_tv, step, commission_rate, turnover,
                       trade_lots=None, exec_date_str="",
                       max_gross_exposure=2.0):
    """执行一次调仓：卖出→减仓→加仓。原地修改 portfolio，返回 (commission, new_cash, trade_log)。

    允许现金为负（借款），上限为 max_gross_exposure × tradable_tv。

    trade_lots: {code: [{"buy_date", "buy_price", "shares"}, ...]}  开仓 lot 登记（原地修改）
    trade_log:  [{"code", "buy_date", "sell_date", "buy_price", "sell_price", "shares", "pnl_pct"}, ...]
    """
    commission_total = 0.0
    trade_log = []
    if trade_lots is None:
        trade_lots = {}

    def _close_lots(code, sell_price, shares_to_sell):
        """FIFO 平仓：从 code 的最老 lot 开始匹配，记录每笔平仓 P&L。返回 (平仓记录列表, 剩余待卖份额)。"""
        closed = []
        remaining = shares_to_sell
        if code not in trade_lots:
            return closed, remaining
        for lot in trade_lots[code]:
            if remaining <= 0:
                break
            matched = min(lot["shares"], remaining)
            cost = matched * lot["buy_price"] / (1.0 - commission_rate) if commission_rate < 1.0 else matched * lot["buy_price"]
            proceeds = matched * sell_price * (1.0 - commission_rate)
            pnl_pct = (proceeds / cost - 1.0) * 100.0 if cost > 0 else 0.0
            closed.append({
                "code": code, "buy_date": lot["buy_date"], "sell_date": exec_date_str,
                "buy_price": round(lot["buy_price"], 4), "sell_price": round(sell_price, 4),
                "shares": matched, "pnl_pct": round(pnl_pct, 2),
            })
            lot["shares"] -= matched
            remaining -= matched
        trade_lots[code] = [l for l in trade_lots[code] if l["shares"] > 1e-10]
        if not trade_lots[code]:
            del trade_lots[code]
        return closed, remaining

    # 1. 全卖：不在目标范围内的
    for code in list(portfolio.keys()):
        if code in suspended_codes:
            continue
        if code not in target_positions or target_positions.get(code, 0) == 0:
            if code in prices:
                sell_price = prices[code]
                sell_value = portfolio[code] * sell_price
                commission_total += sell_value * commission_rate
                cash += sell_value - sell_value * commission_rate
                closed, _ = _close_lots(code, sell_price, portfolio[code])
                trade_log.extend(closed)
            del portfolio[code]

    # 2. 减仓：仍在目标范围但需降权
    for code in target_positions:
        if code not in prices or prices[code] == 0:
            continue
        target_value = tradable_tv * target_positions[code]
        current_value = portfolio.get(code, 0) * prices.get(code, 0)
        diff = target_value - current_value
        if diff < -step * tradable_tv:
            sell_shares = -diff / prices[code]
            sell_shares = min(sell_shares, portfolio.get(code, 0))
            sell_price = prices[code]
            sell_value = sell_shares * sell_price
            commission_total += sell_value * commission_rate
            portfolio[code] = portfolio.get(code, 0) - sell_shares
            cash += sell_value - sell_value * commission_rate
            closed, _ = _close_lots(code, sell_price, sell_shares)
            trade_log.extend(closed)
            if portfolio[code] <= 0:
                del portfolio[code]

    # 3. 加仓：仓位升序，同仓位成交额升序，最后一支吸残量（不超自身目标）
    buy_order = sorted(target_positions.keys(), key=lambda c: (target_positions.get(c, 0), turnover.get(c, 0)))
    buy_threshold = step * tradable_tv * 0.5
    for i, code in enumerate(buy_order):
        if code not in prices or prices[code] == 0:
            continue
        is_last = (i == len(buy_order) - 1)
        target_value = tradable_tv * target_positions[code]
        current_value = portfolio.get(code, 0) * prices.get(code, 0)
        diff = target_value - current_value

        if is_last:
            # 最后一支吸收剩余额度
            total_hv = sum(portfolio.get(c, 0) * prices.get(c, 0) for c in portfolio)
            remaining = max_gross_exposure * tradable_tv - total_hv
            buy_value = min(max(diff, 0), remaining) if remaining > 0 else 0
        elif diff > buy_threshold:
            total_hv = sum(portfolio.get(c, 0) * prices.get(c, 0) for c in portfolio)
            remaining = max_gross_exposure * tradable_tv - total_hv
            buy_value = min(diff, remaining) if remaining > 0 else 0
        else:
            continue

        if buy_value > 0:
            commission_total += buy_value * commission_rate
            net_buy = buy_value - buy_value * commission_rate
            new_shares = net_buy / prices[code]
            portfolio[code] = portfolio.get(code, 0) + new_shares
            cash -= buy_value
            trade_lots.setdefault(code, []).append({
                "code": code,
                "buy_date": exec_date_str,
                "buy_price": round(prices[code], 4),
                "shares": new_shares,
            })

    return commission_total, cash, trade_log


def count_actual_rebalances(signal_history: list) -> int:
    """Count rebalance dates where at least one ETF position actually changed.

    Uses the same action logic as the tuner's detail enrichment:
    new (0→>0), adj (|Δ|>1%), out (>0→0).  hold-only dates are NOT counted.
    """
    if not signal_history:
        return 0
    count = 0
    prev_positions = {}
    for sig in signal_history:
        cur_positions = sig.get("positions", {})
        had_change = False
        all_codes = set(prev_positions) | set(cur_positions)
        for code in all_codes:
            prev = prev_positions.get(code, 0)
            cur = cur_positions.get(code, 0)
            if (cur > 0 and prev == 0) or (cur == 0 and prev > 0) or abs(cur - prev) > 0.01:
                had_change = True
                break
        if had_change:
            count += 1
        prev_positions = dict(cur_positions)
    return count


from quant_factors import calc_rsi as _precalc_rsi

# ── Factor cache ──────────────────────────────────────────────────────
import hashlib, pickle, os as _os

def _factor_cache_key(etf_code, daily_df, weekly_df, ema_period, vol_window,
                       f7_window, f7_lookback, f7_min_days, f7_sigma_floor,
                       f1_daily_ema, f1_daily_ma, f1_active_days):
    """Per-ETF cache key from data fingerprint + factor parameters."""
    h = hashlib.sha256()
    h.update(etf_code.encode())
    h.update(str(len(daily_df)).encode())
    h.update(str(daily_df["date"].iloc[-1]).encode())
    h.update(str(daily_df["close"].iloc[-1]).encode())
    if weekly_df is not None:
        h.update(str(len(weekly_df)).encode())
        h.update(str(weekly_df["date"].iloc[-1]).encode())
    for v in [ema_period, vol_window, f7_window, f7_lookback, f7_min_days,
              f7_sigma_floor, f1_daily_ema, f1_daily_ma, f1_active_days]:
        h.update(str(v).encode())
    return f"{etf_code}_{h.hexdigest()[:12]}"

def _factor_cache_path(key):
    from pathlib import Path
    d = Path(__file__).resolve().parent.parent / "data" / "quant" / ".factor_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"fc_{key}.pickle"

def _factor_cache_load(key):
    p = _factor_cache_path(key)
    if p.exists():
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            p.unlink(missing_ok=True)
    return None

def _factor_cache_save(key, data):
    try:
        with open(_factor_cache_path(key), "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def _precompute_factors(all_daily, all_weekly, ema_period, vol_window,
                         f7_window=20, f7_lookback=250, f7_min_days=60, f7_sigma_floor=0.01,
                         f3_norm_window=60, f1_daily_ema=False, f1_daily_ma=False,
                         f1_active_days=0):
    '''Precompute F1/F3/F7/RSI series once — O(1) lookup per rebalance date.

    f1_active_days: bitmask (0-31) controlling when the current partial week is
      allowed to be used as an extra bar in the weekly EMA.
        bit 0 (1): ≥5 days (Fri)   bit 1 (2): ≥4 days (Thu)
        bit 2 (4): ≥3 days (Wed)   bit 3 (8): ≥2 days (Tue)
        bit 4 (16): ≥1 day (Mon)
      0 = Base (never), 31 = Daily (any day).
      The weekly CSV contains only complete weeks — partial bars are computed
      on-the-fly from daily data.
    '''
    import numpy as np
    from quant_factors import calc_ema as _ce

    out = {}

    # Bit → offset from last trading day of the ISO week.
    # bit 0 (Fri) = 0 days before last, bit 1 (Thu) = 1 before last, etc.
    # Actual threshold = total_trading_days_in_week - offset.
    BIT_OFFSET = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}

    # Trading calendar for total-trading-days-per-week computation
    from trading_calendar import load_trading_calendar as _load_td
    _td_list = _load_td()
    _td_set = set(_td_list) if _td_list else set()

    for code, daily_df in all_daily.items():
        weekly_df = all_weekly.get(code)
        daily_dates = pd.to_datetime(daily_df["date"]).values.astype('datetime64[ns]')
        weekly_dates = pd.to_datetime(weekly_df["date"]).values.astype('datetime64[ns]') if weekly_df is not None else np.array([], dtype='datetime64[ns]')
        weekly_closes = weekly_df["close"].astype(float).values if weekly_df is not None else np.array([])

        # ── Per-ETF cache ──
        _ck = _factor_cache_key(code, daily_df, weekly_df, ema_period, vol_window,
                                f7_window, f7_lookback, f7_min_days, f7_sigma_floor,
                                f1_daily_ema, f1_daily_ma, f1_active_days)
        _cached = _factor_cache_load(_ck)
        if _cached is not None:
            out[code] = _cached
            continue

        # Precompute EMA on completed weekly closes (one-time, O(n))
        alpha = 2.0 / (ema_period + 1)
        ema_weekly = np.full(len(weekly_closes), np.nan)
        if len(weekly_closes) >= ema_period:
            cw_s = pd.Series(weekly_closes, dtype=float)
            ema_weekly = _ce(cw_s, span=ema_period).values

        # F1 per daily date. O(1) per day using EMA rolling.
        f1_val = np.full(len(daily_dates), np.nan, dtype=float)
        _daily_dt = pd.DatetimeIndex(daily_dates)
        _weekly_dt = pd.DatetimeIndex(weekly_dates)
        _daily_iso = _daily_dt.isocalendar()
        _daily_week_str = _daily_iso.week.astype(str) + "-" + _daily_iso.year.astype(str)

        # Precompute trading-day counts per ISO week from daily data.
        # More reliable than the trading calendar for historical holidays.
        _week_td_map = _daily_week_str.value_counts().to_dict()
        # Last ISO week: use actual daily-data count unless calendar says
        # there are still trading days remaining (truly incomplete week).
        _last_week = _daily_week_str.iloc[-1]
        try:
            from trading_calendar import is_trading_day as _is_td_check
            import pandas as _pd
            _today = _pd.Timestamp.now().normalize()
            _mon = _today - _pd.Timedelta(days=_today.dayofweek)
            _has_future = any(_is_td_check(_mon + _pd.Timedelta(days=i)) for i in range(7) if _mon + _pd.Timedelta(days=i) > _today)
        except Exception:
            _has_future = _today.dayofweek < 4
        if _has_future:
            # Week is truly incomplete — force 5 to prevent false checkpoint
            _week_td_map[_last_week] = 5
        # else: short but complete week (e.g. Thu before holiday Fri)
        # — keep actual daily-data count so checkpoint fires correctly

        # Per-ETF state: checkpoint value for the current ISO week, reset on week boundary.
        checkpoint_f1 = None
        prev_week = None

        for i in range(len(daily_df)):
            cur_week = _daily_week_str.iloc[i]

            # ── Week boundary: carry over last week's final F1 ──
            if cur_week != prev_week:
                checkpoint_f1 = float(f1_val[i-1]) if i > 0 and not np.isnan(f1_val[i-1]) else None
                prev_week = cur_week

            # ── Base: last complete week ──
            # Always use Monday of the current ISO week as reference.
            # The last bar strictly before Monday is the last complete week.
            iso_year, iso_week, _ = _daily_dt[i].isocalendar()
            cur_week_monday = pd.Timestamp.fromisocalendar(iso_year, iso_week, 1)
            w_end = _weekly_dt.searchsorted(cur_week_monday, side="right")
            if w_end < ema_period: continue
            w_last = w_end - 1
            base_ema = ema_weekly[w_last]
            base_close = weekly_closes[w_last]
            if np.isnan(base_ema): continue

            # ── Days elapsed in this ISO week ──
            days_in_week = int((_daily_week_str[:i+1] == cur_week).sum())

            # ── Total trading days in this ISO week (from daily data, not calendar) ──
            total_td = _week_td_map.get(cur_week, 5)

            # ── Is today a checkpoint day? ──
            # A day is a checkpoint iff its bit is enabled AND
            # days_in_week EXACTLY equals the threshold (not ">=").
            is_checkpoint = False
            if f1_active_days > 0:
                for bit_val, offset in BIT_OFFSET.items():
                    if (f1_active_days & bit_val) and (days_in_week == total_td - offset):
                        is_checkpoint = True
                        break

            # ── Unified hold / compute / freeze ──
            # All three branches use the same base (last complete week).
            if is_checkpoint:
                today_close = float(daily_df["close"].iloc[i])
                ema_now = alpha * today_close + (1 - alpha) * base_ema
                checkpoint_f1 = float((today_close - ema_now) / ema_now * 100)
                f1_val[i] = checkpoint_f1
            elif checkpoint_f1 is not None:
                f1_val[i] = checkpoint_f1
            else:
                f1_val[i] = float((base_close - base_ema) / base_ema * 100)
        # F3: self-normalized volume ratio (60d baseline → 20d up/down comparison)
        f3_val = np.full(len(daily_dates), np.nan, dtype=float)
        if len(daily_df) >= f3_norm_window + vol_window + 1:
            close_n = daily_df["close"].astype(float)
            chg_n = close_n.pct_change()
            vc_n = "amount" if "amount" in daily_df.columns else "volume"
            vol_n = daily_df[vc_n].astype(float)
            vol_ma = vol_n.rolling(f3_norm_window, min_periods=f3_norm_window).mean().shift(1)
            vol_z = vol_n / vol_ma
            up_z = vol_z.where(chg_n > 0, 0.0).rolling(vol_window, min_periods=vol_window).sum()
            dn_z = vol_z.where(chg_n < 0, 0.0).rolling(vol_window, min_periods=vol_window).sum()
            uc = (chg_n > 0).astype(int).rolling(vol_window, min_periods=vol_window).sum()
            dc = (chg_n < 0).astype(int).rolling(vol_window, min_periods=vol_window).sum()
            up_avg = up_z / uc.replace(0, np.nan)
            dn_avg = dn_z / dc.replace(0, np.nan)
            ratio = up_avg / dn_avg
            ratio = ratio.mask(dc == 0, np.where(uc > 0, 3.0, 1.0))
            f3_val = np.array(ratio.to_numpy(dtype=float))
            f3_val[:f3_norm_window + vol_window] = np.nan
        f7_val = np.full(len(daily_dates), np.nan, dtype=float)
        if len(daily_df) >= f7_window + f7_min_days:
            cd = daily_df["close"].astype(float).where(lambda s: s > 0)
            lr = np.log(cd / cd.shift(1))
            cs = lr.rolling(window=f7_window).sum()
            # Vectorized rolling z-score: O(n) vs original O(n²) Python loop
            cs_s = pd.Series(cs.values, dtype=float)
            roll_mean = cs_s.shift(1).rolling(f7_lookback, min_periods=f7_min_days).mean()
            roll_std = cs_s.shift(1).rolling(f7_lookback, min_periods=f7_min_days).std(ddof=0)
            roll_std = roll_std.clip(lower=f7_sigma_floor)
            f7_val = ((cs_s.values - roll_mean.values) / roll_std.values)
        rsi_val = np.full(len(daily_dates), np.nan, dtype=float)
        if len(daily_df) >= 15:
            rsi_series = _precalc_rsi(daily_df["close"].astype(float), period=14)
            rsi_val = rsi_series.to_numpy(dtype=float)
        else:
            rsi_series = pd.Series(rsi_val, index=daily_df.index)

        out[code] = {"daily_dates": daily_dates, "weekly_dates": weekly_dates,
                      "f1": f1_val, "f3": f3_val,
                      "f7": f7_val, "rsi": rsi_val}
        _factor_cache_save(_ck, out[code])
    return out

def run_backtest(start_date: str = "2023-01-01", end_date: str = None,
                 initial_capital: float = 1000000.0,
                 rebalance_freq: str = None,
                 preset: str = None,
                 universe_filter: list = None,
                 preloaded: dict = None,
                 config_override: dict = None,
                 return_details: bool = False,
                 return_debug: bool = False,
                 return_data: bool = False,
                 progress_callback=None,
                 all_daily_exec: dict = None):
    """
    主回测函数 — CLI 与 Tuner 共用唯一引擎。

    preloaded: 可选预加载数据字典，跳过 CSV 加载:
        {"all_daily": {code: DataFrame}, "all_weekly": {code: DataFrame},
         "market_regimes": {date: regime}, "hs300_above_ma": {date: bool}}
    config_override: 可选配置覆盖字典，在 preset 加载后应用:
        {"scoring": {...}, "confidence": {...}, "position": {...}, "factors": {...}}
    all_daily_exec: 可选执行价格查询专用数据（含 intraday 合并），
        因子计算仍使用 preloaded["all_daily"]（CSV 原始数据）。
        不传时默认等于 all_daily（向后兼容）。
    """
    def _deep_merge(base, override):
        for k, v in override.items():
            if k in base and isinstance(v, dict) and isinstance(base[k], dict):
                _deep_merge(base[k], v)
            else:
                base[k] = v

    cfg = load_config(preset=preset)
    if config_override:
        for section, values in config_override.items():
            if section in cfg:
                if isinstance(values, dict) and isinstance(cfg.get(section), dict):
                    _deep_merge(cfg[section], values)
                else:
                    cfg[section] = values
    if universe_filter is not None:
        # Explicit filter: use exactly the codes provided (empty = no ETFs)
        allowed = set(universe_filter)
        cfg["universe"] = [e for e in cfg["universe"] if e["code"] in allowed]
    else:
        # Default: only active ETFs (active != false)
        cfg["universe"] = [e for e in cfg["universe"] if e.get("active", True)]
    universe = cfg["universe"]
    scoring_cfg = cfg["scoring"]
    confidence_cfg = cfg["confidence"]
    position_cfg = cfg["position"]
    factor_cfg = cfg["factors"]
    account_cfg = cfg.get("account", {})
    from etf_report.core.quant_contract import load_defaults
    _df = load_defaults()
    max_gross_exposure = account_cfg.get("max_gross_exposure", _df["account"]["max_gross_exposure"])
    financing_rate_annual = account_cfg.get("financing_rate_annual", 0.0)
    daily_financing_rate = financing_rate_annual / 360.0 if financing_rate_annual > 0 else 0.0

    weights = scoring_cfg["weights"]
    sensitivity = scoring_cfg.get("sensitivity", {})
    f1_sens = sensitivity.get("f1", _df["scoring"]["sensitivity"]["f1"])
    if rebalance_freq is None:
        rebalance_freq = position_cfg.get("rebalance_freq", _df["position"]["rebalance_freq"])
    band = position_cfg.get("band", _df["position"]["band"])
    band_sensitivity = position_cfg.get("band_sensitivity", _df["position"].get("band_sensitivity", 0.0))
    # Dynamic band config (fixed params, not optimizable)
    _dyn_cfg = position_cfg.get("dynamic_band", _df["position"].get("dynamic_band", {}))
    _dyn_enabled = bool(band_sensitivity > 0)
    _dyn_fast = _dyn_cfg.get("fast_span", 4)
    _dyn_slow = _dyn_cfg.get("slow_span", 12)
    _dyn_floor = _dyn_cfg.get("floor", 0.015)
    _dyn_ceiling = _dyn_cfg.get("ceiling", 0.045)
    # Dispersion EMA state (initialized per-backtest-run, not per-signal)
    _disp_history = []  # list of (dispersion, date_str) tuples
    commission_rate = position_cfg.get("commission_rate", _df["position"]["commission_rate"])
    f3_sens = sensitivity.get("f3", _df["scoring"]["sensitivity"]["f3"])
    conf_type = confidence_cfg.get("type", _df["confidence"]["type"])
    # dead_zone/full_zone 在 YAML 中为百分制(如 25/65)，需转为 [0,1]
    dead_zone = confidence_cfg["dead_zone"] / 100.0
    full_zone = confidence_cfg["full_zone"] / 100.0
    dispersion_threshold = confidence_cfg.get("dispersion_threshold", 0.0)  # 0=关闭
    breadth_power = confidence_cfg.get("breadth_power", 0.0)  # 0=关闭
    regime_base_cfg = confidence_cfg.get("regime_base", {"bull_trend": 0.90, "choppy_range": 0.55, "bear_trend": 0.25})
    regime_window = confidence_cfg.get("regime_window", 40)
    regime_threshold = confidence_cfg.get("regime_threshold", 0.08)
    breadth_weight = confidence_cfg.get("breadth_weight", 0.5)
    clarity_threshold = confidence_cfg.get("clarity_threshold", 0.10)
    dd_sensitivity = confidence_cfg.get("dd_sensitivity", 0.5)
    dd_trigger_level = confidence_cfg.get("dd_trigger_level", -0.05)
    dd_floor = confidence_cfg.get("dd_floor", 0.35)
    crash_window = confidence_cfg.get("crash_window", 2)
    crash_threshold = confidence_cfg.get("crash_threshold", -0.03)
    recovery_threshold = confidence_cfg.get("recovery_threshold", -0.01)
    crash_pos = confidence_cfg.get("crash_pos", 0.20)
    recovery_pos = confidence_cfg.get("recovery_pos", 0.70)
    recovery_dd_level = confidence_cfg.get("recovery_dd_level", -0.05)
    ma_bull_pos = confidence_cfg.get("ma_bull_pos", _df["confidence"]["ma_bull_pos"])
    ma_bear_pos = confidence_cfg.get("ma_bear_pos", _df["confidence"]["ma_bear_pos"])
    ma_trend_period = confidence_cfg.get("ma_trend_period", _df["confidence"]["ma_trend_period"])
    ma_direction_confirm = confidence_cfg.get("ma_direction_confirm", _df["confidence"]["ma_direction_confirm"])
    benchmarks = confidence_cfg.get("benchmarks", _df["confidence"]["benchmarks"])
    if isinstance(benchmarks, str):
        benchmarks = [benchmarks]
    use_multi_benchmark = len(benchmarks) > 1
    max_holdings = position_cfg["max_holdings"]
    step = position_cfg["discretize_step"]
    concentration = position_cfg.get("concentration", 2.0)  # softmax concentration multiplier (higher=more concentrated)
    c_sensitivity = position_cfg.get("c_sensitivity", 0.0)  # dynamic C sensitivity: c_mult = 1 + sens×(disp−0.5), 0=static
    f1_daily_ema = factor_cfg.get("f1_daily_ema", False)
    f1_daily_ma = factor_cfg.get("f1_daily_ma", False)
    f1_active_days = factor_cfg.get("f1_active_days", _df["factors"]["f1_active_days"])
    # F7 params
    f7_cfg = factor_cfg.get("log_return_deviation", {})
    f7_window = f7_cfg.get("window_days", 20)
    f7_lookback = f7_cfg.get("lookback_days", 250)
    f7_min_days = f7_cfg.get("min_days", 60)
    f7_sigma_floor = f7_cfg.get("sigma_floor", 0.01)

    f7_t = sensitivity.get("f7_t", 7.0)
    f7_k = sensitivity.get("f7_k", 3.0)

    # 加载所有 ETF 数据（优先使用预加载数据）
    if preloaded and preloaded.get("all_daily"):
        all_daily = preloaded["all_daily"]
        all_weekly = preloaded.get("all_weekly", {})
        print(f"  使用预加载数据 {len(all_daily)}/{len(universe)} 支 ETF")
    else:
        print("加载数据...")
        if progress_callback:
            progress_callback(0, 100, "加载数据")
        all_daily = {}
        all_weekly = {}
        n_etfs = len(universe)
        for i, etf in enumerate(universe):
            code = etf["code"]
            daily, weekly = load_etf_data(code)
            if daily is not None:
                all_daily[code] = daily
                all_weekly[code] = weekly
            if progress_callback and i % 10 == 9:
                progress_callback(int(i / max(n_etfs,1) * 3), 100, "加载数据")
        print(f"  成功加载 {len(all_daily)}/{len(universe)} 支 ETF")

    # 加载市场状态（F4 regime-aware 映射需要）
    if preloaded and preloaded.get("market_regimes"):
        market_regimes = preloaded["market_regimes"]
    else:
        regimes_path = PROJECT_ROOT / "data" / "market_regimes.json"
        market_regimes = {}
        if regimes_path.exists():
            try:
                with regimes_path.open("r", encoding="utf-8") as f:
                    regimes_data = json.load(f)
                market_regimes = {r["date"]: r["regime"] for r in regimes_data.get("regimes", [])}
                print(f"  市场状态: {len(market_regimes)} 天")
            except Exception as e:
                print(f"  [WARN] 加载市场状态失败: {e}")

    # Load benchmark MA trend caches for ma_trend confidence
    benchmark_above_maps = {}
    benchmark_rising_maps = {}
    if conf_type == "ma_trend":
        for idx_code in benchmarks:
            try:
                daily = load_index_daily_cached(idx_code)
                weekly = build_index_weekly(daily)
                cache = build_ma_trend_cache(daily, weekly, ma_trend_period) or {}
                benchmark_above_maps[idx_code] = cache.get("above", {})
                benchmark_rising_maps[idx_code] = cache.get("ma_rising", {})
                print("  {} MA{}: {} days loaded".format(
                    idx_code, ma_trend_period, len(benchmark_above_maps[idx_code])))
            except Exception as e:
                print("  [WARN] {} MA{} failed: {}".format(idx_code, ma_trend_period, e))
                # Fallback: empty maps (always vote bull)
                benchmark_above_maps[idx_code] = {}
                benchmark_rising_maps[idx_code] = {}

    # 确定回测日期范围
    all_dates_set = set()
    for df in all_daily.values():
        all_dates_set.update(df["date"].values)
    all_dates_full = pd.DatetimeIndex(sorted(all_dates_set))

    user_start = pd.Timestamp(start_date)
    user_end = pd.Timestamp(end_date) if end_date else all_dates_full[-1]

    # ── Execution price data (may include intraday) ──
    if all_daily_exec is None:
        all_daily_exec = all_daily

    # Always precompute factor series and price lookup (no fast/slow path distinction)
    if progress_callback:
        progress_callback(3, 100, "因子预计算")
    print("预计算因子序列...")
    factor_series = _precompute_factors(
        all_daily, all_weekly,
        factor_cfg["ema"]["period_weeks"],
        factor_cfg["volume_ratio"]["window_days"],
        f7_window=f7_window, f7_lookback=f7_lookback,
        f7_min_days=f7_min_days, f7_sigma_floor=f7_sigma_floor,
        f1_daily_ema=f1_daily_ema, f1_daily_ma=f1_daily_ma,
        f1_active_days=f1_active_days,
    )
    price_lookup = {}
    for code, df in all_daily_exec.items():
        dates = df["date"].astype(str).str[:10].tolist()
        rows = df.to_dict('records')
        price_lookup[code] = dict(zip(dates, rows))

    # Find initial trade date: last rebalance date before user_start
    all_dates_full_reb = get_rebalance_dates(
        all_dates_full[all_dates_full >= all_dates_full.min()],
        freq=rebalance_freq)
    warmup_rb = all_dates_full_reb[all_dates_full_reb < user_start]
    initial_rb_date = warmup_rb[-1] if len(warmup_rb) > 0 else None

    all_dates = all_dates_full[(all_dates_full >= user_start) & (all_dates_full <= user_end)]

    if len(all_dates) == 0:
        print("[ERROR] 无有效交易日")
        return None

    rebalance_dates = get_rebalance_dates(all_dates, freq=rebalance_freq)
    if initial_rb_date is not None and initial_rb_date < user_start:
        rebalance_dates = pd.DatetimeIndex([initial_rb_date] + list(rebalance_dates))

    print(f"  回测区间: {user_start.strftime('%Y-%m-%d')} ~ {user_end.strftime('%Y-%m-%d')}")
    print(f"  交易日数: {len(all_dates)}")
    print(f"  调仓频率: {rebalance_freq}")
    print(f"  调仓日: {len(rebalance_dates)}（含初始建仓 {1 if initial_rb_date is not None and initial_rb_date < user_start else 0}）")

    # ============================================================
    # 回测主循环
    # ============================================================
    portfolio = {}
    cash = initial_capital
    total_commission = 0.0
    nav_history = []
    signal_history = []
    nav_peak_nav = initial_capital
    regime = "choppy_range"
    nav_list_bt = []
    prev_effective_bull = True
    prev_index_votes = {}  # {code: bool} per-index previous vote, initial empty→default bull
    trade_lots = {}       # {code: [{"buy_date","buy_price","shares"}, ...]}
    all_trade_log = []    # accumulated closed trades from each rebalance

    print("\n开始回测...")
    debug_snapshots = []

    total_rb = len(rebalance_dates)
    # ── Dynamic progress segments (REQ-343): allocate % by measured cost ──
    # I/O phases (加载数据 + 因子预计算) use fixed 0-5%.
    # Pass 1 vs Pass 2 split dynamically: Pass 2 daily iteration ~2.5× Pass 1.
    _n_days_prog = len(all_dates)
    _cost_reb = 1.0
    _cost_day = 2.5
    _total_work = total_rb * _cost_reb + _n_days_prog * _cost_day
    _prog_io_end  = 5  # fixed for I/O phases
    _prog_pass1_end  = _prog_io_end + max(1, int(total_rb * _cost_reb * (100 - _prog_io_end) / _total_work))
    # _prog_pass1_end → 100 is Pass 2

    for rb_idx, rb_date in enumerate(rebalance_dates):
        # 初始建仓日：回测周期前最后一个调仓日，仅执行首次买入
        is_initial = initial_rb_date is not None and rb_date == initial_rb_date
        if is_initial:
            pass  # 执行初始建仓
        if progress_callback:
            # Fire every iteration for short runs (<200), every 5 for long runs
            cb_every = 1 if total_rb < 200 else 5
            if rb_idx % cb_every == 0:
                pct = _prog_io_end + int(rb_idx / max(total_rb, 1) * (_prog_pass1_end - _prog_io_end))
                progress_callback(pct, 100, "回测中")

        execution_date = get_execution_date(rb_date, all_dates)
        if execution_date is None:
            continue
        price_field = execution_price_field()

        # ------ 1. 查找当日因子（全部预计算，O(log n) 二分查找）------
        factors_data = {}
        prices_today = {}
        turnover_today = {}  # 成交额，用于买入排序
        rb_np = np.datetime64(rb_date)
        exec_key = execution_date.strftime("%Y-%m-%d")

        for code in all_daily:
            daily_df = all_daily[code]

            # Price & turnover: O(1) from precomputed lookup
            row = price_lookup.get(code, {}).get(exec_key)
            if row is None or price_field not in row:
                continue
            exec_price = float(row[price_field])
            amt_col = "amount" if "amount" in row else None
            if amt_col:
                turnover_today[code] = float(row[amt_col])

            # Factors: O(log n) binary search in precomputed arrays
            fs = factor_series.get(code)
            if fs is None:
                continue
            daily_end = np.searchsorted(fs["daily_dates"], rb_np, side="right")
            weekly_end = np.searchsorted(fs["weekly_dates"], rb_np, side="right")
            if daily_end < 30 or weekly_end < factor_cfg["ema"]["period_weeks"]:
                continue
            f1_end = daily_end  # F1 is always per daily date now
            f1_val = fs["f1"][f1_end - 1] if f1_end > 0 else np.nan
            f3_val = fs["f3"][daily_end - 1] if daily_end > 0 else np.nan
            f7_val = fs["f7"][daily_end - 1] if daily_end > 0 else np.nan
            if np.isnan(f1_val) or np.isnan(f3_val):
                continue

            factors = {
                "f1_ema_dev": f1_val,
                "f3_volume_ratio": f3_val, "f4_valuation": 50.0,
                "f7_log_return_dev": f7_val,
            }
            factors_data[code] = factors
            prices_today[code] = exec_price

        if len(factors_data) < max_holdings:
            continue

        # ------ 2. 连续映射 + 合成 ------
        factors_df = pd.DataFrame(factors_data).T

        mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
        mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

        mapped_f7 = factors_df["f7_log_return_dev"].apply(lambda v: map_f7(v, t=f7_t, k=f7_k)).fillna(0.5)
        w1 = weights.get("ema_deviation", 0.35)
        w3 = weights.get("volume_ratio", 0.35)
        w4 = weights.get("valuation", 0.15)
        w7 = weights.get("log_return_deviation", 0.0)

        composite = mapped_f1 * w1 + mapped_f3 * w3
        if w7 > 0:
            composite = composite + mapped_f7 * w7

        # F4 估值因子（regime-aware）
        rb_date_str = rb_date.strftime("%Y-%m-%d") if hasattr(rb_date, "strftime") else str(rb_date)[:10]

        # Multi-benchmark voting (or single HS300 for backward compat)
        _benchmark_votes = []
        for idx_code in benchmarks:
            _above = benchmark_above_maps.get(idx_code, {}).get(rb_date_str, True)
            _rising = benchmark_rising_maps.get(idx_code, {}).get(rb_date_str, True)
            _benchmark_votes.append({"code": idx_code, "above": _above, "rising": _rising})

        _single_bm = benchmarks[0] if benchmarks else "000300"
        hs300_above_ma = benchmark_above_maps.get(_single_bm, {}).get(rb_date_str, True)
        hs300_ma_rising = benchmark_rising_maps.get(_single_bm, {}).get(rb_date_str, True)
        market_regime = market_regimes.get(rb_date_str, "choppy_range")

        if w4 > 0 and "f4_valuation" in factors_df.columns:
            mapped_f4 = factors_df["f4_valuation"].apply(lambda v: map_f4(v, market_regime))
            composite = composite + mapped_f4 * w4

        # ------ 3. Top-6 选股 + 仓位 ------
        top_n = composite.nlargest(max_holdings)

        # Dynamic B: compute dispersion from z-scores, then effective_band
        # (Must be BEFORE band filtering, which uses effective_band)
        if _dyn_enabled:
            _mu = composite.mean()
            _sigma = max(composite.std(), 0.02)
            _z = (top_n.values - _mu) / _sigma
            _disp = max(float(_z.std()), 0.0)
            _disp_history.append(_disp)
            if len(_disp_history) > _dyn_slow * 2:
                _disp_history.pop(0)
            if len(_disp_history) >= _dyn_slow:
                _alpha_fast = 2.0 / (_dyn_fast + 1)
                _alpha_slow = 2.0 / (_dyn_slow + 1)
                _ema_fast = _disp_history[0]
                _ema_slow = _disp_history[0]
                for _d in _disp_history[1:]:
                    _ema_fast = _alpha_fast * _d + (1 - _alpha_fast) * _ema_fast
                    _ema_slow = _alpha_slow * _d + (1 - _alpha_slow) * _ema_slow
                _trend = (_ema_fast - _ema_slow) / max(_ema_slow, 0.01)
                effective_band = band - band_sensitivity * _trend
                effective_band = max(_dyn_floor, min(_dyn_ceiling, effective_band))
            else:
                effective_band = band
        else:
            effective_band = band

        # 分数带过滤：新标的替换被挤出持仓时，分数优势必须 > effective_band
        if effective_band > 0 and portfolio:
            # 理想 top_n 中已在持仓的 = 安全保留
            held_in_topn = {c: top_n[c] for c in top_n.index if c in portfolio}
            # 想入场的新标的
            want_in = [c for c in top_n.index if c not in portfolio]
            # 被挤出 top_n 的当前持仓
            ousted = {c: composite[c] for c in portfolio if c not in top_n.index and c in composite.index}

            if want_in and ousted:
                # 每个新标的检查：是否比某个被挤出者高出 > effective_band
                allowed = [c for c in want_in
                           if any(composite[c] - out_score > effective_band
                                  for out_score in ousted.values())]
            else:
                allowed = want_in  # 无 ousted 时全部放行

            # 组合：安全保留 + 允许入场 + 未被替换的 ousted
            merged = dict(held_in_topn)
            for c in allowed:
                merged[c] = top_n[c]
            for c, s in ousted.items():
                if c not in merged:
                    merged[c] = s
            top_n = pd.Series(merged).nlargest(max_holdings)

        # 信心函数
        avg_conf = 0.0  # 默认值，legacy分支会覆盖
        score_dispersion = top_n.std()
        market_breadth = (composite > composite.median()).sum() / max(len(composite), 1)

        # Z-score 标准化 → softmax 仓位分配
        # 用全池子的均值和标准差，不是只对 top-6
        mu = composite.mean()
        sigma = max(composite.std(), 0.02)  # floor 防全同分数时除零
        z_scores = (top_n.values - mu) / sigma

        # Dynamic C: c_mult = 1 + sensitivity × (dispersion − 0.5)
        dispersion = max(float(z_scores.std()), 0.0)
        if c_sensitivity > 0:
            c_mult = 1.0 + c_sensitivity * (dispersion - 0.5)
            effective_c = concentration * max(c_mult, 0.1)  # floor to prevent zero
        else:
            effective_c = concentration

        exp_scores = np.exp(z_scores * effective_c)
        softmax_w = exp_scores / exp_scores.sum()
        softmax_weights = pd.Series(softmax_w, index=top_n.index)

        # Update NAV tracking for regime inference
        holdings_value_bt = sum(portfolio.get(c, 0) * prices_today.get(c, 0) for c in portfolio)
        current_nav_bt = cash + holdings_value_bt
        nav_peak_nav = max(nav_peak_nav, current_nav_bt)
        current_dd = (current_nav_bt - nav_peak_nav) / nav_peak_nav
        nav_list_bt.append(current_nav_bt)

        if conf_type == "regime":
            # Market-state driven position sizing
            regime = infer_regime_from_nav(nav_list_bt, regime_window, regime_threshold)
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
            total_target = dd_trigger_confidence(
                drawdown_pct=current_dd,
                dd_trigger_level=dd_trigger_level,
                dd_floor=dd_floor,
            )
            regime = "dd_trigger"
        elif conf_type == "momentum_crash":
            total_target = momentum_crash_confidence(
                nav_history=nav_list_bt,
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
            total_target = 0.95
            regime = "always_full"
        elif conf_type == "ma_trend":
            if use_multi_benchmark:
                total_target, regime, _vote_details, prev_index_votes = multi_benchmark_confidence(
                    benchmark_votes=_benchmark_votes,
                    bull_pos=ma_bull_pos,
                    bear_pos=ma_bear_pos,
                    direction_confirm=ma_direction_confirm,
                    prev_bull=prev_effective_bull,
                    prev_index_votes=prev_index_votes,
                )
                effective_bull = (regime == "ma_above")
                prev_effective_bull = effective_bull
                benchmark_vote_details = _vote_details
            else:
                # Single HS300 — backward compatible
                if ma_direction_confirm:
                    both_agree = (hs300_above_ma == hs300_ma_rising)
                    if both_agree:
                        effective_bull = hs300_above_ma
                    else:
                        effective_bull = prev_effective_bull
                else:
                    effective_bull = hs300_above_ma
                prev_effective_bull = effective_bull
                total_target = ma_trend_confidence(
                    hs300_above_ma=effective_bull,
                    bull_pos=ma_bull_pos,
                    bear_pos=ma_bear_pos,
                )
                regime = "ma_above" if effective_bull else "ma_below"
                benchmark_vote_details = None
        else:
            # Legacy: score-based quadratic confidence
            confidences = top_n.apply(lambda s: confidence_function(s, dead_zone, full_zone))
            disp_factor = min(1.0, score_dispersion / dispersion_threshold) if dispersion_threshold > 0 else 1.0
            breadth_factor = market_breadth ** breadth_power if breadth_power > 0 else 1.0
            avg_conf = confidences.mean() * disp_factor * breadth_factor
            total_target = min(0.95, avg_conf * 1.2)  # 上限 95%

        # 目标仓位
        actual_exposure = min(total_target, max_gross_exposure)
        target_positions = softmax_weights * actual_exposure

        # 离散化（最大余数法：floor 后按余数补回，残量补给最大持仓者）
        in_steps = target_positions / step
        floored = np.floor(in_steps)
        remainders = in_steps - floored
        total_floor = floored.sum()
        target_steps = round(total_target / step)
        deficit = int(target_steps - total_floor)
        if deficit > 0:
            top_indices = remainders.nlargest(min(deficit, len(remainders))).index
            floored.loc[top_indices] += 1
        target_positions = (floored * step).clip(lower=0)
        leftover = total_target - target_positions.sum()
        if leftover > 0:
            max_idx = target_positions.idxmax()
            if not pd.isna(max_idx):
                target_positions[max_idx] += leftover
        elif leftover < 0:
            # discretization rounding pushed total above target: clip largest position
            excess = -leftover
            max_idx = target_positions.idxmax()
            if not pd.isna(max_idx):
                target_positions[max_idx] = max(0.0, target_positions[max_idx] - excess)

        # Fallback: fill missing prices for held ETFs with most recent available close.
        # ETFs whose price comes from fallback (not from today's data) are treated as
        # suspended: they are valued at last-known price but cannot be bought or sold.
        suspended_codes = set()
        for code in list(portfolio.keys()):
            if code not in prices_today:
                df = all_daily.get(code)
                if df is not None:
                    past = df[df["date"] < rb_date]
                    if len(past) > 0:
                        prices_today[code] = float(past["close"].iloc[-1])
                        suspended_codes.add(code)

        # ------ 4. 计算当前组合市值 ------
        holdings_value = sum(
            portfolio.get(code, 0) * prices_today.get(code, 0)
            for code in portfolio
        )
        total_value = cash + holdings_value

        # Tradable value excludes suspended holdings (can't sell them)
        frozen_value = sum(
            portfolio.get(code, 0) * prices_today.get(code, 0)
            for code in suspended_codes
        )
        tradable_tv = total_value - frozen_value

        # ------ 5. 调仓 ------
        comm, cash, trade_log = _execute_rebalance(
            portfolio, cash, prices_today, suspended_codes,
            target_positions.to_dict(), tradable_tv, step, commission_rate, turnover_today,
            trade_lots=trade_lots, exec_date_str=exec_key,
            max_gross_exposure=max_gross_exposure,
        )
        total_commission += comm
        all_trade_log.extend(trade_log)

        # 记录信号
        signal_entry = {
            "date": execution_date,
            "signal_date": rb_date,
            "execution_date": execution_date,
            "execution_timing": "same_close",
            "scores": composite.to_dict(),
            "top6": list(top_n.index),
            "positions": target_positions.to_dict(),
            "avg_confidence": avg_conf,
            "total_target": total_target,
            "actual_exposure": actual_exposure,
            "regime": regime,
        }
        if conf_type == "ma_trend" and benchmark_vote_details is not None:
            signal_entry["benchmark_votes"] = benchmark_vote_details
        else:
            signal_entry["hs300_above_ma"] = bool(hs300_above_ma)
        signal_history.append(signal_entry)
        if return_debug:
            top6_snapshot = []
            for code in top_n.index:
                top6_snapshot.append({
                    "code": code,
                    "score": round(float(top_n[code]), 4),
                    "softmax_w": round(float(softmax_weights[code]), 4),
                    "position": round(float(target_positions[code]), 4),
                    "px": round(float(prices_today.get(code, 0)), 3),
                })
            # Capture ALL prices (not just top6) to detect sells at different px
            all_px = {}
            for code in set(list(portfolio.keys()) + list(target_positions.index)):
                px = prices_today.get(code, 0)
                if px > 0:
                    all_px[code] = round(float(px), 3)
            debug_snapshots.append({
                "idx": rb_idx,
                "signal_date": rb_date.strftime("%Y-%m-%d"),
                "execution_date": execution_date.strftime("%Y-%m-%d"),
                "regime": regime,
                "total_target": round(float(total_target), 4),
                "mu": round(float(mu), 4),
                "sigma": round(float(sigma), 4),
                "hs300_above_ma": bool(hs300_above_ma),
                "hs300_ma_rising": bool(hs300_ma_rising) if conf_type == "ma_trend" else True,
                "benchmark_votes": benchmark_vote_details if conf_type == "ma_trend" and benchmark_vote_details is not None else None,
                "nav_before": round(float(total_value), 2),
                "cash": round(float(cash), 2),
                "holdings": {code: round(float(shares), 6) for code, shares in portfolio.items()},
                "top6": top6_snapshot,
                "all_px": all_px,
            })
        if return_details:
            # Convert to plain dicts for O(1) lookup (avoid pandas Series .get() overhead)
            _f1_d = mapped_f1.to_dict()
            _f3_d = mapped_f3.to_dict()
            _f7_d = mapped_f7.to_dict() if "f7_log_return_dev" in factors_df.columns else {}
            _comp_d = composite.to_dict()
            _pos_d = target_positions.to_dict()
            _has_f7 = "f7_log_return_dev" in factors_df.columns and w7 > 0
            # Raw factor values for attribution (REQ-233)
            _f1_raw = factors_df["f1_ema_dev"].to_dict()
            _f3_raw = factors_df["f3_volume_ratio"].to_dict()
            _f7_raw = factors_df["f7_log_return_dev"].to_dict() if _has_f7 else {}
            detail = {}
            for code in factors_df.index:
                raw_score = composite.get(code, 0)
                z = (raw_score - mu) / sigma if sigma > 0 else 0
                detail[code] = {
                    "f1": round(_f1_d.get(code, 0) * 100, 1),
                    "f3": round(_f3_d.get(code, 0) * 100, 1),
                    "f7": round(_f7_d.get(code, 0.5) * 100, 1) if _has_f7 else None,
                    "score": round(raw_score * 100, 1),
                    "z": round(float(z), 2),
                    "confidence": round(float(total_target) * 100, 0),
                    "position": round(_pos_d.get(code, 0) * 100, 1),
                    "price": round(float(prices_today.get(code, 0)), 3),
                    "f1_raw": round(float(_f1_raw.get(code, 0)), 2),
                    "f3_raw": round(float(_f3_raw.get(code, 1.0)), 2),
                    "f7_raw": round(float(_f7_raw.get(code, 0)), 2) if _has_f7 else None,
                }
            signal_history[-1]["detail"] = detail

        # 进度
        if (rb_idx + 1) % 20 == 0:
            nav = (cash + sum(portfolio.get(c, 0) * prices_today.get(c, 0) for c in portfolio))
            print(f"  [{rb_idx+1}/{len(rebalance_dates)}] {rb_date.strftime('%Y-%m-%d')} "
                  f"NAV={nav/initial_capital*100:.1f}% holdings={len(portfolio)}")

    # ── Close remaining open lots at last available close price ──
    if trade_lots:
        last_close = {}
        for code in all_daily_exec:
            df = all_daily_exec[code]
            if len(df) > 0:
                last_close[code] = float(df["close"].iloc[-1])
        final_date = str(all_dates[-1])[:10] if len(all_dates) > 0 else exec_key
        for code, lots in trade_lots.items():
            sell_price = last_close.get(code)
            if sell_price is None or sell_price <= 0:
                continue
            for lot in lots:
                cost = lot["shares"] * lot["buy_price"] / (1.0 - commission_rate) if commission_rate < 1.0 else lot["shares"] * lot["buy_price"]
                proceeds = lot["shares"] * sell_price * (1.0 - commission_rate)
                pnl_pct = (proceeds / cost - 1.0) * 100.0 if cost > 0 else 0.0
                all_trade_log.append({
                    "code": code, "buy_date": lot["buy_date"], "sell_date": final_date,
                    "buy_price": lot["buy_price"], "sell_price": round(sell_price, 4),
                    "shares": lot["shares"], "pnl_pct": round(pnl_pct, 2),
                })

    # ============================================================
    # 逐日计算 NAV（从第一个调仓日到最后一个交易日）
    # ============================================================
    if progress_callback:
        progress_callback(_prog_pass1_end, 100, "计算净值")
    print("\n计算逐日 NAV...")

    # 重新跑一遍，但这次逐日记录净值
    # 简化：用调仓后的持仓，在每个交易日按收盘价计算 NAV
    # 重新回测（精确版）
    portfolio2 = {}
    cash2 = initial_capital
    signal_idx = 0
    nav_records = []
    total_commission2 = 0.0
    total_interest2 = 0.0
    current_exposure = 0.0

    n_dates = len(all_dates)
    _cb_every_nav = max(1, n_dates // 50)  # ~50 updates per run, at least every iteration
    for di, date in enumerate(all_dates):
        if progress_callback and di % _cb_every_nav == 0:
            progress_callback(_prog_pass1_end + int(di / max(n_dates, 1) * (100 - _prog_pass1_end)), 100, "计算净值")
        if False:  # dead code — precomputation eliminated warmup expansion
            # 慢路径预热期：执行调仓但不记录 NAV
            if signal_idx < len(signal_history) and date >= signal_history[signal_idx]["date"]:
                sig = signal_history[signal_idx]
                target_codes = set(sig["positions"].keys())
                trade_field = "close"
                prices = {code: get_price_on_date(all_daily_exec, code, date, trade_field) for code in all_daily}
                prices = {k: v for k, v in prices.items() if v is not None}
                hv = sum(portfolio2.get(c, 0) * prices.get(c, 0) for c in portfolio2)
                tv = cash2 + hv
                for code in list(portfolio2.keys()):
                    if code not in target_codes or sig["positions"].get(code, 0) == 0:
                        if code in prices:
                            cash2 += portfolio2[code] * prices[code]
                        del portfolio2[code]
                for code in target_codes:
                    if code not in prices or prices[code] == 0: continue
                    target_value = tv * sig["positions"][code]
                    current_value = portfolio2.get(code, 0) * prices.get(code, 0)
                    diff = target_value - current_value
                    if diff > 0 and cash2 >= diff:
                        portfolio2[code] = portfolio2.get(code, 0) + diff / prices[code]
                        cash2 -= diff
                    elif diff < 0:
                        sell_shares = min(-diff / prices[code], portfolio2.get(code, 0))
                        portfolio2[code] = portfolio2.get(code, 0) - sell_shares
                        cash2 += sell_shares * prices[code]
                        if portfolio2.get(code, 0) <= 0: portfolio2.pop(code, None)
                signal_idx += 1
            continue

        # 检查是否是调仓日——while确保同一天可以处理多个信号
        while signal_idx < len(signal_history) and date >= signal_history[signal_idx]["date"]:
            # 执行调仓
            sig = signal_history[signal_idx]
            target_positions = sig["positions"]
            current_exposure = sig.get("actual_exposure", sig.get("total_target", 0))

            # 获取成交价格 — O(1) from precomputed price_lookup dict
            trade_field = "close"
            prices = {}
            turnover2 = {}
            date_str = date.strftime("%Y-%m-%d")
            for code in all_daily:
                row2 = price_lookup.get(code, {}).get(date_str)
                if row2 is not None:
                    prices[code] = float(row2[trade_field])
                    if "amount" in row2:
                        turnover2[code] = float(row2["amount"])

            # Fallback: fill missing prices for held ETFs with most recent available close.
            # ETFs whose price comes from fallback (not from today's data) are treated as
            # suspended: they are valued at last-known price but cannot be bought or sold.
            suspended_codes2 = set()
            for code in list(portfolio2.keys()):
                if code not in prices:
                    df = all_daily.get(code)
                    if df is not None:
                        past = df[df["date"] < date]
                        if len(past) > 0:
                            prices[code] = float(past["close"].iloc[-1])
                            suspended_codes2.add(code)

            # 当前总值
            hv = sum(portfolio2.get(c, 0) * prices.get(c, 0) for c in portfolio2)
            tv = cash2 + hv

            # Tradable value excludes suspended holdings
            frozen_value2 = sum(
                portfolio2.get(c, 0) * prices.get(c, 0)
                for c in suspended_codes2
            )
            tradable_tv2 = tv - frozen_value2

            # 执行调仓
            comm2, cash2, _ = _execute_rebalance(
                portfolio2, cash2, prices, suspended_codes2,
                target_positions, tradable_tv2, step, commission_rate, turnover2,
                max_gross_exposure=max_gross_exposure,
            )
            total_commission2 += comm2

            signal_idx += 1

        # 计算当日 NAV
        prices = {}
        for code in all_daily:
            df = all_daily[code]
            row = df[df["date"] == date]
            if len(row) > 0:
                prices[code] = float(row["close"].iloc[0])

        # Fallback: fill missing prices for held ETFs with most recent available close
        for code in list(portfolio2.keys()):
            if code not in prices:
                df = all_daily.get(code)
                if df is not None:
                    past = df[df["date"] < date]
                    if len(past) > 0:
                        prices[code] = float(past["close"].iloc[-1])

        hv = sum(portfolio2.get(c, 0) * prices.get(c, 0) for c in portfolio2)

        # ── Financing cost: daily interest on borrowed cash (negative cash = borrowing) ──
        if cash2 < 0 and daily_financing_rate > 0:
            interest_today = -cash2 * daily_financing_rate
            cash2 -= interest_today
            total_interest2 += interest_today

        nav = cash2 + hv

        nav_records.append({
            "date": date,
            "nav": nav,
            "nav_pct": nav / initial_capital * 100,
            "cash": cash2,
            "holdings": len(portfolio2),
            "exposure": current_exposure,
            "total_interest_accrued": round(total_interest2, 2),
        })

    if progress_callback:
        progress_callback(100, 100, "计算净值")
    nav_df = pd.DataFrame(nav_records)

    # ============================================================
    # 输出统计
    # ============================================================
    final_nav = nav_df["nav"].iloc[-1]
    start_nav = nav_df["nav"].iloc[0]
    total_return = (final_nav / start_nav - 1) * 100
    days = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days
    annual_return = ((final_nav / start_nav) ** (365 / days) - 1) * 100 if days > 0 else 0

    # 最大回撤
    cummax = nav_df["nav"].cummax()
    drawdown = (nav_df["nav"] - cummax) / cummax * 100
    max_drawdown = drawdown.min()

    # 夏普比率（年化，假设无风险利率 2%）
    daily_returns = nav_df["nav"].pct_change().dropna()
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() * 252 - 0.02) / (daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0

    # 索提诺比率（只惩罚下行波动）
    downside = daily_returns[daily_returns < 0]
    if len(downside) > 0 and downside.std() > 0:
        sortino = (daily_returns.mean() * 252 - 0.02) / (downside.std() * np.sqrt(252))
    else:
        sortino = 0

    actual_trades = count_actual_rebalances(signal_history)

    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)
    print(f"  回测区间:    {nav_df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {nav_df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"  交易日数:    {len(nav_df)}")
    print(f"  调仓次数:    {actual_trades} / {len(signal_history)}（实际换仓 / 总调仓日）")
    print(f"  总收益率:    {total_return:+.2f}%")
    print(f"  年化收益率:  {annual_return:+.2f}%")
    print(f"  最大回撤:    {max_drawdown:.2f}%")
    print(f"  夏普比率:    {sharpe:.2f}")
    print(f"  索提诺比率:  {sortino:.2f}")
    print(f"  最终 NAV:    {final_nav:,.0f} (初始 {initial_capital:,.0f})")
    print(f"  最终持仓数:  {nav_df['holdings'].iloc[-1]}")
    comm = total_commission2  # from second-pass NAV loop (matches returned NAV curve)
    if comm > 0:
        print(f"  交易佣金:    {comm:,.0f} ({comm/initial_capital*100:.2f}% 本金)")
    print("=" * 60)

    # 杠杆风险指标
    exposure_series = nav_df["exposure"].values
    avg_exposure = float(np.mean(exposure_series)) if len(exposure_series) > 0 else 0.0
    max_exposure = float(np.max(exposure_series)) if len(exposure_series) > 0 else 0.0
    days_above_100 = int(np.sum(exposure_series > 1.0))
    days_above_150 = int(np.sum(exposure_series > 1.5))
    days_above_180 = int(np.sum(exposure_series > 1.8))
    avg_excess = float(np.mean(np.maximum(exposure_series - 1.0, 0)))
    daily_rets = nav_df["nav"].pct_change().fillna(0).values
    max_daily_loss = float(np.min(daily_rets)) * 100 if len(daily_rets) > 0 else 0.0
    financing_rate = account_cfg.get("financing_rate_annual", 0.06)
    interest_drag = avg_excess * financing_rate

    # Leverage contribution: estimate what return would be without leverage
    unlevered_rets = []
    for i in range(len(daily_rets)):
        exp = exposure_series[i] if i < len(exposure_series) else 1.0
        if exp > 1.0:
            unlevered_rets.append(daily_rets[i] / exp)
        else:
            unlevered_rets.append(daily_rets[i])
    unlevered_nav = 1.0
    for r in unlevered_rets:
        unlevered_nav *= (1.0 + r)
    unlevered_total_return = (unlevered_nav - 1.0) * 100
    leverage_contribution = total_return - unlevered_total_return

    result_extra = {
        "total_commission": comm, "trade_count": actual_trades,
        "debug_snapshots": debug_snapshots, "trade_log": all_trade_log,
        "exposure_series": exposure_series.tolist(),
        "exposure_summary": {
            "avg_exposure": round(avg_exposure, 4),
            "max_exposure": round(max_exposure, 4),
            "days_above_100": days_above_100,
            "days_above_150": days_above_150,
            "days_above_180": days_above_180,
            "max_daily_loss_pct": round(max_daily_loss, 2),
            "interest_drag_estimate": round(interest_drag * 100, 2),
            "total_interest_accrued": round(total_interest2, 2),
            "total_interest_accrued_pct": round(total_interest2 / initial_capital * 100, 4) if initial_capital > 0 else 0,
            "leverage_contribution_pct": round(leverage_contribution, 2),
            "unlevered_total_return_pct": round(unlevered_total_return, 2),
        },
        "sortino": round(sortino, 4),
        "sharpe": round(sharpe, 4),
        "annual_return": round(annual_return, 2),
        "max_drawdown": round(max_drawdown, 2),
    }
    if return_data:
        result_extra["all_daily"] = all_daily
    return nav_df, signal_history, result_extra


def main():
    parser = argparse.ArgumentParser(description="REQ-177 M2.1: 量化回测引擎")
    parser.add_argument("--start", type=str, default="2023-01-01", help="回测起始日期")
    parser.add_argument("--end", type=str, default=None, help="回测结束日期")
    parser.add_argument("--execution-timing", choices=["same_close"], default=None,
                        help="(已废弃，仅保留兼容性)")
    parser.add_argument("--output", type=str, default=None, help="输出净值 CSV 路径")
    parser.add_argument("--preset", type=str, default=None,
                        help="预设配置名 (default: zen-1)")
    parser.add_argument("--debug", action="store_true", dest="debug",
                        help="输出调试快照到 data/debug_cli.json")
    parser.add_argument("--universe", type=str, default=None,
                        help="ETF 筛选列表（逗号分隔，不传=仅 active ETF）")
    args = parser.parse_args()

    universe_filter = None
    if args.universe is not None:
        universe_filter = [c.strip() for c in args.universe.split(",") if c.strip()] if args.universe else []

    nav_df, signals, extra = run_backtest(
        start_date=args.start, end_date=args.end,
        preset=args.preset,
        return_debug=args.debug,
        universe_filter=universe_filter,
    )

    if nav_df is not None and args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        nav_df.to_csv(output_path, index=False)
        print(f"\n净值曲线已保存: {output_path}")
    elif nav_df is not None:
        # 默认保存
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / "backtest_nav.csv"
        nav_df.to_csv(output_path, index=False)
        print(f"\n净值曲线已保存: {output_path}")

    if args.debug and nav_df is not None:
        snaps = extra.get("debug_snapshots", [])
        debug_path = PROJECT_ROOT / "data" / "debug_cli.json"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with debug_path.open("w", encoding="utf-8") as f:
            json.dump({"count": len(snaps), "snapshots": snaps}, f, ensure_ascii=False, indent=2)
        print(f"\nDEBUG: {len(snaps)} snapshots saved → {debug_path}")


if __name__ == "__main__":
    main()
