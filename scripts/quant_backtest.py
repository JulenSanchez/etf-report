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

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_factors import (
    compute_all_factors, factor_exhaustion_penalty,
    map_f1, map_f3, map_f4, map_f7,
    confidence_function, regime_confidence, infer_regime_from_nav, dd_trigger_confidence, momentum_crash_confidence, ma_trend_confidence,
)
from quant_data_utils import load_etf_data as _load_etf_data, get_price_on_date as _get_price_on_date
from benchmark_data import load_hs300_daily_cached, build_hs300_weekly, build_ma_trend_cache

CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
DATA_DIR = SKILL_DIR / "data" / "quant"
OUTPUT_DIR = SKILL_DIR / "data" / "quant_results"


def load_config(preset: str = "daily_aggressive"):
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
    for block in ("scoring", "confidence", "position", "factors"):
        if block in p:
            cfg[block].update(p[block])
    for key in ("weights", "bias_bonus", "sensitivity"):
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


def get_execution_date(signal_date: pd.Timestamp, all_dates: pd.DatetimeIndex, timing: str) -> pd.Timestamp | None:
    """Return trade execution date for a signal date."""
    if timing == "next_open":
        future_dates = all_dates[all_dates > signal_date]
        return future_dates[0] if len(future_dates) else None
    return signal_date


def get_price_on_date(all_daily: dict, code: str, date: pd.Timestamp, field: str = "close") -> float | None:
    return _get_price_on_date(all_daily, code, date, field)


def _execute_rebalance(portfolio, cash, prices, suspended_codes,
                       target_positions, tradable_tv, step, commission_rate, turnover):
    """执行一次调仓：卖出→减仓→加仓。原地修改 portfolio，返回 (commission, new_cash)。"""
    commission_total = 0.0

    # 1. 全卖：不在目标范围内的
    for code in list(portfolio.keys()):
        if code in suspended_codes:
            continue
        if code not in target_positions or target_positions.get(code, 0) == 0:
            if code in prices:
                sell_value = portfolio[code] * prices[code]
                commission_total += sell_value * commission_rate
                cash += sell_value - sell_value * commission_rate
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
            sell_value = sell_shares * prices[code]
            commission_total += sell_value * commission_rate
            portfolio[code] = portfolio.get(code, 0) - sell_shares
            cash += sell_value - sell_value * commission_rate
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

        if is_last and cash > buy_threshold:
            buy_value = min(cash, max(diff, 0))
        elif diff > buy_threshold:
            buy_value = min(diff, cash)
        else:
            continue

        if buy_value > 0:
            commission_total += buy_value * commission_rate
            net_buy = buy_value - buy_value * commission_rate
            portfolio[code] = portfolio.get(code, 0) + net_buy / prices[code]
            cash -= buy_value

    return commission_total, cash


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

def _precompute_factors(all_daily, all_weekly, ema_period, vol_window,
                         f7_window=20, f7_lookback=250, f7_min_days=60, f7_sigma_floor=0.01,
                         f3_norm_window=60, f1_daily_ema=False, f1_daily_ma=False,
                         f2_ma_period=None, f6_rsi_thresh=80.0, f6_drop_thresh=0.025,
                         f6_vol_thresh=1.5, f6_decay_days=3, f6_base_penalty=0.15):
    '''Precompute F1/F3/F6/F7/RSI series once — O(1) lookup per rebalance date.'''
    import numpy as np
    from quant_factors import calc_ema as _ce
    out = {}
    f1_daily = f1_daily_ema or f1_daily_ma
    f2_window = f2_ma_period or (ema_period * 5)
    for code, daily_df in all_daily.items():
        weekly_df = all_weekly.get(code)
        daily_dates = daily_df["date"].values
        weekly_dates = weekly_df["date"].values if weekly_df is not None else np.array([])
        # F1: weekly EMA deviation (or daily EMA/MA if f1_daily_ema/f1_daily_ma)
        span_daily = ema_period * 5
        f1_val = np.full(len(daily_dates) if f1_daily else len(weekly_dates), np.nan, dtype=float)
        if f1_daily_ma and len(daily_df) >= span_daily:
            cd = daily_df["close"].astype(float)
            ma = cd.rolling(window=span_daily).mean()
            s = ((cd - ma) / ma * 100).astype(float).to_numpy()
            f1_val[:len(s)] = s; f1_val[:span_daily-1] = np.nan
        elif f1_daily_ema and len(daily_df) >= span_daily:
            cd = daily_df["close"].astype(float)
            ema = _ce(cd, span=span_daily)
            s = ((cd - ema) / ema * 100).astype(float).to_numpy()
            f1_val[:len(s)] = s; f1_val[:span_daily-1] = np.nan
        elif not f1_daily and weekly_df is not None and len(weekly_df) >= ema_period:
            cw = weekly_df["close"].astype(float)
            ema = _ce(cw, span=ema_period)
            s = ((cw - ema) / ema * 100).astype(float).to_numpy()
            f1_val[:len(s)] = s; f1_val[:ema_period-1] = np.nan
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
            cd = daily_df["close"].astype(float)
            lr = np.log(cd / cd.shift(1))
            cs = lr.rolling(window=f7_window).sum().values
            for i in range(len(cs)):
                v = cs[i]
                if np.isnan(v): continue
                s = 0 if i < f7_lookback else i - f7_lookback
                wv = cs[max(0, s):i]
                if len(wv) < f7_min_days: continue
                mu = np.nanmean(wv); sigma = max(np.nanstd(wv), f7_sigma_floor)
                if sigma == 0: continue
                f7_val[i] = float((v - mu) / sigma)
        # F2: daily MA deviation
        f2_val = np.full(len(daily_dates), np.nan, dtype=float)
        if len(daily_df) >= f2_window:
            cd = daily_df["close"].astype(float).to_numpy()
            ma = np.convolve(cd, np.ones(f2_window)/f2_window, mode='valid')
            dev = (cd[f2_window-1:] - ma) / ma * 100
            f2_val[f2_window-1:] = dev
        rsi_val = np.full(len(daily_dates), np.nan, dtype=float)
        if len(daily_df) >= 15:
            rsi_series = _precalc_rsi(daily_df["close"].astype(float), period=14)
            rsi_val = rsi_series.to_numpy(dtype=float)
        else:
            rsi_series = pd.Series(rsi_val, index=daily_df.index)

        # F6: momentum exhaustion penalty, aligned with factor_exhaustion_penalty()
        f6_val = np.ones(len(daily_dates), dtype=float)
        f6_decay_days = max(1, int(f6_decay_days))
        if "volume" in daily_df.columns and len(daily_df) >= 14 + vol_window + 2:
            close_f6 = daily_df["close"].astype(float)
            vol_f6 = daily_df["volume"].astype(float)
            vol_ma = vol_f6.rolling(vol_window, min_periods=5).mean()
            vol_ratio = vol_f6 / vol_ma
            ret = close_f6.pct_change()
            triggered = (
                (rsi_series.shift(1) >= f6_rsi_thresh) &
                (ret <= -f6_drop_thresh) &
                (vol_ratio >= f6_vol_thresh)
            ).fillna(False)
            for i in range(len(daily_df)):
                for offset in range(f6_decay_days):
                    idx = i - offset
                    if idx >= 0 and bool(triggered.iloc[idx]):
                        recovery = f6_base_penalty + (1.0 - f6_base_penalty) * (offset / f6_decay_days)
                        f6_val[i] = float(min(1.0, recovery))
                        break

        out[code] = {"daily_dates": daily_dates, "weekly_dates": weekly_dates,
                      "f1": f1_val, "f2": f2_val, "f3": f3_val, "f6": f6_val,
                      "f7": f7_val, "rsi": rsi_val}
    return out

def run_backtest(start_date: str = "2023-01-01", end_date: str = None,
                 initial_capital: float = 1000000.0,
                 rebalance_freq: str = None,
                 preset: str = "daily_aggressive",
                 execution_timing: str = None,
                 universe_filter: list = None,
                 preloaded: dict = None,
                 config_override: dict = None,
                 return_details: bool = False,
                 return_debug: bool = False):
    """
    主回测函数 — CLI 与 Tuner 共用唯一引擎。

    preloaded: 可选预加载数据字典，跳过 CSV 加载:
        {"all_daily": {code: DataFrame}, "all_weekly": {code: DataFrame},
         "market_regimes": {date: regime}, "hs300_above_ma": {date: bool}}
    config_override: 可选配置覆盖字典，在 preset 加载后应用:
        {"scoring": {...}, "confidence": {...}, "position": {...}, "factors": {...}}
    """
    cfg = load_config(preset=preset)
    if config_override:
        for section, values in config_override.items():
            if section in cfg:
                if isinstance(values, dict):
                    cfg[section].update(values)
                else:
                    cfg[section] = values
    if universe_filter:
        allowed = set(universe_filter)
        cfg["universe"] = [e for e in cfg["universe"] if e["code"] in allowed]
    universe = cfg["universe"]
    scoring_cfg = cfg["scoring"]
    confidence_cfg = cfg["confidence"]
    position_cfg = cfg["position"]
    factor_cfg = cfg["factors"]

    weights = scoring_cfg["weights"]
    bias_bonus = scoring_cfg["bias_bonus"]
    sensitivity = scoring_cfg.get("sensitivity", {})
    f1_sens = sensitivity.get("f1", 8.0)
    # rebalance_freq: 参数优先，否则读配置
    if rebalance_freq is None:
        rebalance_freq = position_cfg.get("rebalance_freq", "W-FRI")
    score_band = position_cfg.get("score_band", 0)
    if execution_timing is None:
        execution_timing = position_cfg.get("execution_timing", "next_open")
    if execution_timing not in ("same_close", "next_open"):
        execution_timing = "next_open"
    commission_rate = position_cfg.get("commission_rate", 0)
    f3_sens = sensitivity.get("f3", 1.0)
    f2_sens = sensitivity.get("f2", 8.0)
    conf_type = confidence_cfg.get("type", "regime")
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
    ma_bull_pos = confidence_cfg.get("ma_bull_pos", 0.95)
    ma_bear_pos = confidence_cfg.get("ma_bear_pos", 0.10)
    ma_trend_period = confidence_cfg.get("ma_trend_period", 26)
    ma_direction_confirm = confidence_cfg.get("ma_direction_confirm", True)
    max_holdings = position_cfg["max_holdings"]
    step = position_cfg["discretize_step"]
    concentration = position_cfg.get("concentration", 2.0)  # softmax concentration multiplier (higher=more concentrated)
    f1_daily_ema = factor_cfg.get("f1_daily_ema", False)
    f1_daily_ma = factor_cfg.get("f1_daily_ma", False)
    f2_ma_period = factor_cfg.get("f2_ma_period")
    f6_rsi_thresh   = factor_cfg.get("f6_rsi_thresh", 80.0)
    f6_drop_thresh  = factor_cfg.get("f6_drop_thresh", 0.025)
    f6_base_penalty = factor_cfg.get("f6_base_penalty", 0.15)
    f6_vol_thresh   = factor_cfg.get("f6_vol_thresh", 1.5)
    f6_decay_days   = factor_cfg.get("f6_decay_days", 3)
    # F7 params
    f7_cfg = factor_cfg.get("log_return_deviation", {})
    f7_window = f7_cfg.get("window_days", 20)
    f7_lookback = f7_cfg.get("lookback_days", 250)
    f7_min_days = f7_cfg.get("min_days", 60)
    f7_sigma_floor = f7_cfg.get("sigma_floor", 0.01)

    f7_t = sensitivity.get("f7_t", 7.0)
    f7_k = sensitivity.get("f7_k", 3.0)
    # 构建偏好 map（0-1 尺度）
    bias_map = {e["code"]: bias_bonus / 100.0 for e in universe if e.get("bias")}

    # 加载所有 ETF 数据（优先使用预加载数据）
    if preloaded and preloaded.get("all_daily"):
        all_daily = preloaded["all_daily"]
        all_weekly = preloaded.get("all_weekly", {})
        print(f"  使用预加载数据 {len(all_daily)}/{len(universe)} 支 ETF")
    else:
        print("加载数据...")
        all_daily = {}
        all_weekly = {}
        for etf in universe:
            code = etf["code"]
            daily, weekly = load_etf_data(code)
            if daily is not None:
                all_daily[code] = daily
                all_weekly[code] = weekly
        print(f"  成功加载 {len(all_daily)}/{len(universe)} 支 ETF")

    # 加载市场状态（F4 regime-aware 映射需要）
    if preloaded and preloaded.get("market_regimes"):
        market_regimes = preloaded["market_regimes"]
    else:
        regimes_path = SKILL_DIR / "data" / "market_regimes.json"
        market_regimes = {}
        if regimes_path.exists():
            try:
                with regimes_path.open("r", encoding="utf-8") as f:
                    regimes_data = json.load(f)
                market_regimes = {r["date"]: r["regime"] for r in regimes_data.get("regimes", [])}
                print(f"  市场状态: {len(market_regimes)} 天")
            except Exception as e:
                print(f"  [WARN] 加载市场状态失败: {e}")

    # Load HS300 MA trend signal for ma_trend confidence
    hs300_above_ma_map = {}
    hs300_ma_rising_map = {}
    if conf_type == "ma_trend":
        if preloaded and preloaded.get("hs300_above_ma"):
            hs300_above_ma_map = preloaded["hs300_above_ma"]
            hs300_ma_rising_map = preloaded.get("hs300_ma_rising", {})
            print(f"  HS300 MA{ma_trend_period}: {len(hs300_above_ma_map)} days preloaded")
        else:
            try:
                hs = load_hs300_daily_cached()
                weekly = build_hs300_weekly(hs)
                ma_cache = build_ma_trend_cache(hs, weekly, ma_trend_period) or {}
                hs300_above_ma_map = ma_cache.get("above", {})
                hs300_ma_rising_map = ma_cache.get("ma_rising", {})
                print(f"  HS300 MA{ma_trend_period}: {len(hs300_above_ma_map)} days loaded")
            except Exception as e:
                print(f"  [WARN] HS300 MA{ma_trend_period} failed: {e}")

    # 确定回测日期范围
    all_dates_set = set()
    for df in all_daily.values():
        all_dates_set.update(df["date"].values)
    all_dates_full = pd.DatetimeIndex(sorted(all_dates_set))

    user_start = pd.Timestamp(start_date)
    user_end = pd.Timestamp(end_date) if end_date else all_dates_full[-1]

    # Always precompute factor series and price lookup (no fast/slow path distinction)
    print("预计算因子序列...")
    factor_series = _precompute_factors(
        all_daily, all_weekly,
        factor_cfg["ema"]["period_weeks"],
        factor_cfg["volume_ratio"]["window_days"],
        f7_window=f7_window, f7_lookback=f7_lookback,
        f7_min_days=f7_min_days, f7_sigma_floor=f7_sigma_floor,
        f1_daily_ema=f1_daily_ema, f1_daily_ma=f1_daily_ma,
        f2_ma_period=f2_ma_period,
        f6_rsi_thresh=f6_rsi_thresh,
        f6_drop_thresh=f6_drop_thresh,
        f6_vol_thresh=f6_vol_thresh,
        f6_decay_days=f6_decay_days,
        f6_base_penalty=f6_base_penalty,
    )
    price_lookup = {
        code: {str(row["date"])[:10]: row for _, row in df.iterrows()}
        for code, df in all_daily.items()
    }

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

    print("\n开始回测...")
    debug_snapshots = []

    for rb_idx, rb_date in enumerate(rebalance_dates):
        # 初始建仓日：回测周期前最后一个调仓日，仅执行首次买入
        is_initial = initial_rb_date is not None and rb_date == initial_rb_date
        if is_initial:
            pass  # 执行初始建仓

        execution_date = get_execution_date(rb_date, all_dates, execution_timing)
        if execution_date is None:
            continue
        execution_price_field = "open" if execution_timing == "next_open" else "close"

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
            if row is None or execution_price_field not in row.index:
                continue
            exec_price = float(row[execution_price_field])
            amt_col = "amount" if "amount" in row.index else None
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
            f1_end = daily_end if (f1_daily_ema or f1_daily_ma) else weekly_end
            f1_val = fs["f1"][f1_end - 1] if f1_end > 0 else np.nan
            f3_val = fs["f3"][daily_end - 1] if daily_end > 0 else np.nan
            f7_val = fs["f7"][daily_end - 1] if daily_end > 0 else np.nan
            if np.isnan(f1_val) or np.isnan(f3_val):
                continue

            f6_val = fs["f6"][daily_end - 1] if daily_end > 0 and "f6" in fs else 1.0
            if np.isnan(f6_val):
                f6_val = 1.0

            f2_val = fs["f2"][daily_end - 1] if daily_end > 0 else np.nan
            factors = {
                "f1_ema_dev": f1_val, "f2_daily_ma": f2_val,
                "f3_volume_ratio": f3_val, "f4_valuation": 50.0,
                "f7_log_return_dev": f7_val, "f6_exhaustion_penalty": f6_val,
            }
            factors_data[code] = factors
            prices_today[code] = exec_price

        if len(factors_data) < max_holdings:
            continue

        # ------ 2. 连续映射 + 合成 ------
        factors_df = pd.DataFrame(factors_data).T

        mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
        mapped_f2 = factors_df["f2_daily_ma"].apply(lambda v: map_f1(v, f2_sens)).fillna(0.5)
        mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

        mapped_f7 = factors_df["f7_log_return_dev"].apply(lambda v: map_f7(v, t=f7_t, k=f7_k)).fillna(0.5)
        w1 = weights.get("ema_deviation", 0.35)
        w2 = weights.get("f2_daily_ma", 0.0)
        w3 = weights.get("volume_ratio", 0.35)
        w4 = weights.get("valuation", 0.15)
        w6 = weights.get("exhaustion_penalty", 0.0)
        w7 = weights.get("log_return_deviation", 0.0)

        composite = mapped_f1 * w1 + mapped_f2 * w2 + mapped_f3 * w3
        if w7 > 0:
            composite = composite + mapped_f7 * w7

        # F4 估值因子（regime-aware）
        rb_date_str = rb_date.strftime("%Y-%m-%d") if hasattr(rb_date, "strftime") else str(rb_date)[:10]
        hs300_above_ma = hs300_above_ma_map.get(rb_date_str, True)  # default bull if no data
        hs300_ma_rising = hs300_ma_rising_map.get(rb_date_str, True)
        market_regime = market_regimes.get(rb_date_str, "choppy_range")

        if w4 > 0 and "f4_valuation" in factors_df.columns:
            mapped_f4 = factors_df["f4_valuation"].apply(lambda v: map_f4(v, market_regime))
            composite = composite + mapped_f4 * w4

        # 偏好加成
        for code, bonus in bias_map.items():
            if code in composite.index:
                composite[code] += bonus

        # F6 动能衰竭惩罚（加法因子：f6_penalty-1 ∈ [-0.85, 0]，w6=0时无效）
        if w6 > 0 and "f6_exhaustion_penalty" in factors_df.columns:
            f6_score = factors_df["f6_exhaustion_penalty"] - 1.0
            composite = composite + f6_score * w6

        # ------ 3. Top-6 选股 + 仓位 ------
        top_n = composite.nlargest(max_holdings)

        # 分数带过滤：新标的替换被挤出持仓时，分数优势必须 > score_band
        if score_band > 0 and portfolio:
            # 理想 top_n 中已在持仓的 = 安全保留
            held_in_topn = {c: top_n[c] for c in top_n.index if c in portfolio}
            # 想入场的新标的
            want_in = [c for c in top_n.index if c not in portfolio]
            # 被挤出 top_n 的当前持仓
            ousted = {c: composite[c] for c in portfolio if c not in top_n.index and c in composite.index}

            if want_in and ousted:
                # 每个新标的检查：是否比某个被挤出者高出 > score_band
                allowed = [c for c in want_in
                           if any(composite[c] - out_score > score_band
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

        exp_scores = np.exp(z_scores * concentration)
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
            if ma_direction_confirm:
                both_agree = (hs300_above_ma == hs300_ma_rising)
                if both_agree:
                    effective_bull = hs300_above_ma  # 双条件一致→切换
                else:
                    effective_bull = prev_effective_bull  # 不一致→维持
            else:
                effective_bull = hs300_above_ma
            prev_effective_bull = effective_bull
            total_target = ma_trend_confidence(
                hs300_above_ma=effective_bull,
                bull_pos=ma_bull_pos,
                bear_pos=ma_bear_pos,
            )
            regime = "ma_above" if effective_bull else "ma_below"
        else:
            # Legacy: score-based quadratic confidence
            confidences = top_n.apply(lambda s: confidence_function(s, dead_zone, full_zone))
            disp_factor = min(1.0, score_dispersion / dispersion_threshold) if dispersion_threshold > 0 else 1.0
            breadth_factor = market_breadth ** breadth_power if breadth_power > 0 else 1.0
            avg_conf = confidences.mean() * disp_factor * breadth_factor
            total_target = min(0.95, avg_conf * 1.2)  # 上限 95%

        # 每支目标仓位
        target_positions = softmax_weights * total_target

        # 离散化（最大余数法：floor 后按余数补回，确保总和逼近 total_target）
        in_steps = target_positions / step
        floored = np.floor(in_steps)
        remainders = in_steps - floored
        total_floor = floored.sum()
        target_steps = round(total_target / step)
        deficit = int(target_steps - total_floor)
        if deficit > 0:
            # 余数最大的 deficit 个标的各补 1 step
            top_indices = remainders.nlargest(min(deficit, len(remainders))).index
            floored.loc[top_indices] += 1
        target_positions = (floored * step).clip(lower=0)

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
        comm, cash = _execute_rebalance(
            portfolio, cash, prices_today, suspended_codes,
            target_positions.to_dict(), tradable_tv, step, commission_rate, turnover_today,
        )
        total_commission += comm

        # 记录信号
        signal_history.append({
            "date": execution_date,
            "signal_date": rb_date,
            "execution_date": execution_date,
            "execution_timing": execution_timing,
            "scores": composite.to_dict(),
            "top6": list(top_n.index),
            "positions": target_positions.to_dict(),
            "avg_confidence": avg_conf,
            "total_target": total_target,
            "regime": regime,
        })
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
                "nav_before": round(float(total_value), 2),
                "cash": round(float(cash), 2),
                "holdings": {code: round(float(shares), 6) for code, shares in portfolio.items()},
                "top6": top6_snapshot,
                "all_px": all_px,
            })
        if return_details:
            # Convert to plain dicts for O(1) lookup (avoid pandas Series .get() overhead)
            _f1_d = mapped_f1.to_dict()
            _f2_d = mapped_f2.to_dict()
            _f3_d = mapped_f3.to_dict()
            _f7_d = mapped_f7.to_dict() if "f7_log_return_dev" in factors_df.columns else {}
            _comp_d = composite.to_dict()
            _pos_d = target_positions.to_dict()
            _f6_col = factors_df.get("f6_exhaustion_penalty")
            _f6_d = _f6_col.to_dict() if _f6_col is not None else {}
            _has_f7 = "f7_log_return_dev" in factors_df.columns and w7 > 0
            detail = {}
            for code in factors_df.index:
                raw_score = composite.get(code, 0)
                z = (raw_score - mu) / sigma if sigma > 0 else 0
                detail[code] = {
                    "f1": round(_f1_d.get(code, 0) * 100, 1),
                    "f2": round(_f2_d.get(code, 0.5) * 100, 1),
                    "f3": round(_f3_d.get(code, 0) * 100, 1),
                    "f6": round(_f6_d.get(code, 100.0) * 100, 1) if _f6_d else 100.0,
                    "f7": round(_f7_d.get(code, 0.5) * 100, 1) if _has_f7 else None,
                    "score": round(raw_score * 100, 1),
                    "z": round(float(z), 2),
                    "confidence": round(float(total_target) * 100, 0),
                    "position": round(_pos_d.get(code, 0) * 100, 1),
                    "price": round(float(prices_today.get(code, 0)), 3),
                }
            signal_history[-1]["detail"] = detail

        # 进度
        if (rb_idx + 1) % 20 == 0:
            nav = (cash + sum(portfolio.get(c, 0) * prices_today.get(c, 0) for c in portfolio))
            print(f"  [{rb_idx+1}/{len(rebalance_dates)}] {rb_date.strftime('%Y-%m-%d')} "
                  f"NAV={nav/initial_capital*100:.1f}% holdings={len(portfolio)}")

    # ============================================================
    # 逐日计算 NAV（从第一个调仓日到最后一个交易日）
    # ============================================================
    print("\n计算逐日 NAV...")

    # 重新跑一遍，但这次逐日记录净值
    # 简化：用调仓后的持仓，在每个交易日按收盘价计算 NAV
    # 重新回测（精确版）
    portfolio2 = {}
    cash2 = initial_capital
    signal_idx = 0
    nav_records = []
    total_commission2 = 0.0

    for date in all_dates:
        if False:  # dead code — precomputation eliminated warmup expansion
            # 慢路径预热期：执行调仓但不记录 NAV
            if signal_idx < len(signal_history) and date >= signal_history[signal_idx]["date"]:
                sig = signal_history[signal_idx]
                target_codes = set(sig["positions"].keys())
                trade_field = "open" if sig.get("execution_timing") == "next_open" else "close"
                prices = {code: get_price_on_date(all_daily, code, date, trade_field) for code in all_daily}
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

            # 获取成交价格 + 成交额：same_close 用收盘价，next_open 用执行日开盘价
            trade_field = "open" if sig.get("execution_timing") == "next_open" else "close"
            prices = {}
            turnover2 = {}
            for code in all_daily:
                p = get_price_on_date(all_daily, code, date, trade_field)
                if p is not None:
                    prices[code] = p
                # 成交额 from price_lookup row
                row2 = price_lookup.get(code, {}).get(date.strftime("%Y-%m-%d"))
                if row2 is not None and "amount" in row2.index:
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
            comm2, cash2 = _execute_rebalance(
                portfolio2, cash2, prices, suspended_codes2,
                target_positions, tradable_tv2, step, commission_rate, turnover2,
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
        nav = cash2 + hv

        nav_records.append({
            "date": date,
            "nav": nav,
            "nav_pct": nav / initial_capital * 100,
            "cash": cash2,
            "holdings": len(portfolio2),
        })

    nav_df = pd.DataFrame(nav_records)

    # ============================================================
    # 输出统计
    # ============================================================
    final_nav = nav_df["nav"].iloc[-1]
    total_return = (final_nav / initial_capital - 1) * 100
    days = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days
    annual_return = ((final_nav / initial_capital) ** (365 / days) - 1) * 100 if days > 0 else 0

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

    return nav_df, signal_history, {"total_commission": comm, "trade_count": actual_trades, "debug_snapshots": debug_snapshots}


def main():
    parser = argparse.ArgumentParser(description="REQ-177 M2.1: 量化回测引擎")
    parser.add_argument("--start", type=str, default="2023-01-01", help="回测起始日期")
    parser.add_argument("--end", type=str, default=None, help="回测结束日期")
    parser.add_argument("--execution-timing", choices=["same_close", "next_open"], default=None,
                        help="成交口径：same_close=信号日收盘成交，next_open=下一交易日开盘成交")
    parser.add_argument("--output", type=str, default=None, help="输出净值 CSV 路径")
    parser.add_argument("--preset", type=str, default="daily_aggressive",
                        help="预设配置名 (default: daily_aggressive)")
    parser.add_argument("--debug", action="store_true", dest="debug",
                        help="输出调试快照到 data/debug_cli.json")
    args = parser.parse_args()

    nav_df, signals, extra = run_backtest(
        start_date=args.start, end_date=args.end,
        execution_timing=args.execution_timing, preset=args.preset,
        return_debug=args.debug,
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
        debug_path = SKILL_DIR / "data" / "debug_cli.json"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with debug_path.open("w", encoding="utf-8") as f:
            json.dump({"count": len(snaps), "snapshots": snaps}, f, ensure_ascii=False, indent=2)
        print(f"\nDEBUG: {len(snaps)} snapshots saved → {debug_path}")


if __name__ == "__main__":
    main()
