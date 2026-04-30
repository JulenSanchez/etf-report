"""
REQ-177 M3.1 v2: quant payload 构建脚本（多模板版）
对 3 套策略模板分别跑回测，输出统一 payload 供前端切换。

用法:
  python scripts/quant_build_payload.py
"""
import json
import math
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from quant_backtest import run_backtest

CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
TEMPLATES_PATH = SKILL_DIR / "config" / "quant_templates.yaml"
OUTPUT_PATH = SKILL_DIR / "assets" / "js" / "quant_payload.js"


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_templates():
    with TEMPLATES_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)["templates"]


def merge_config(base, override):
    """Deep merge override into base config (returns new dict)."""
    result = deepcopy(base)
    if not override:
        return result
    for key, val in override.items():
        if key in ("label", "description"):
            continue  # meta fields, not config
        if isinstance(val, dict) and key in result and isinstance(result[key], dict):
            result[key] = merge_config(result[key], val)
        else:
            result[key] = deepcopy(val)
    return result


def build_etf_name_map(cfg):
    m = {}
    for etf in cfg["universe"]:
        m[etf["code"]] = {
            "name": etf["name"],
            "sector": etf["sector"],
            "bias": etf.get("bias", False),
        }
    return m


def compute_drawdown(nav_series):
    cummax = nav_series.cummax()
    dd = (nav_series - cummax) / cummax * 100
    return [round(float(v), 2) for v in dd]


def compute_summary(nav_df, signal_count):
    initial = nav_df["nav"].iloc[0]
    final = nav_df["nav"].iloc[-1]
    total_return = (final / initial - 1) * 100
    days = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days
    annual_return = ((final / initial) ** (365 / days) - 1) * 100 if days > 0 else 0

    cummax = nav_df["nav"].cummax()
    drawdown = (nav_df["nav"] - cummax) / cummax * 100
    max_drawdown = float(drawdown.min())

    daily_returns = nav_df["nav"].pct_change().dropna()
    rf_daily = 0.02 / 252  # 2% annual risk-free

    # Sharpe
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() * 252 - 0.02) / (daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0.0

    # Sortino (downside deviation only)
    downside = daily_returns[daily_returns < rf_daily] - rf_daily
    if len(downside) > 0 and downside.std() > 0:
        sortino = (daily_returns.mean() * 252 - 0.02) / (downside.std() * np.sqrt(252))
    else:
        sortino = 0.0

    # Calmar (annual return / max drawdown)
    calmar = abs(annual_return / max_drawdown) if max_drawdown != 0 else 0.0

    # Win rate (daily)
    win_days = (daily_returns > 0).sum()
    total_days = len(daily_returns)
    win_rate = win_days / total_days * 100 if total_days > 0 else 0.0

    # Monthly returns for stats
    df = nav_df.copy()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    monthly_rets = []
    for (y, m), grp in df.groupby(["year", "month"]):
        r = (grp["nav"].iloc[-1] / grp["nav"].iloc[0] - 1) * 100
        monthly_rets.append({"year": int(y), "month": int(m), "ret": round(r, 2)})

    monthly_vals = [x["ret"] for x in monthly_rets]
    best_month = max(monthly_vals) if monthly_vals else 0.0
    worst_month = min(monthly_vals) if monthly_vals else 0.0
    win_months = sum(1 for v in monthly_vals if v > 0)
    monthly_win_rate = win_months / len(monthly_vals) * 100 if monthly_vals else 0.0

    # Annual breakdown
    annual_breakdown = []
    for y, grp in df.groupby("year"):
        yr_ret = (grp["nav"].iloc[-1] / grp["nav"].iloc[0] - 1) * 100
        annual_breakdown.append({"year": int(y), "ret": round(yr_ret, 2)})

    # Consecutive win/loss streaks
    signs = (daily_returns > 0).astype(int)
    max_win_streak = max_loss_streak = cur_win = cur_loss = 0
    for s in signs:
        if s == 1:
            cur_win += 1; cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
        else:
            cur_loss += 1; cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)

    return {
        "totalReturn": round(total_return, 2),
        "annualReturn": round(annual_return, 2),
        "maxDrawdown": round(max_drawdown, 2),
        "sharpe": round(float(sharpe), 2),
        "sortino": round(float(sortino), 2),
        "calmar": round(float(calmar), 2),
        "winRate": round(win_rate, 1),
        "monthlyWinRate": round(monthly_win_rate, 1),
        "bestMonth": round(best_month, 2),
        "worstMonth": round(worst_month, 2),
        "maxWinStreak": int(max_win_streak),
        "maxLossStreak": int(max_loss_streak),
        "annualBreakdown": annual_breakdown,
        "monthlyReturns": monthly_rets,
        "startDate": nav_df["date"].iloc[0].strftime("%Y-%m-%d"),
        "endDate": nav_df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "tradingDays": len(nav_df),
        "rebalanceCount": signal_count,
        "initialCapital": float(initial),
        "finalNav": round(float(final), 0),
    }


def serialize_signal_history(signal_history):
    """Serialize signal_history for JSON (Timestamp -> str)."""
    result = []
    for i, sig in enumerate(signal_history):
        result.append({
            "date": sig["date"].strftime("%Y-%m-%d"),
            "index": i,
            "scores": {k: round(float(v), 2) for k, v in sig["scores"].items()},
            "top6": sig["top6"],
            "positions": {k: round(float(v), 4) for k, v in sig["positions"].items()},
            "avgConfidence": round(float(sig["avg_confidence"]), 3),
            "totalTarget": round(float(sig["total_target"]), 3),
        })
    return result


def build_rebalance_freq(signal_history, etf_map):
    freq = {}
    total = len(signal_history)
    for sig in signal_history:
        for c in sig["top6"]:
            freq[c] = freq.get(c, 0) + 1
    result = []
    for code, count in sorted(freq.items(), key=lambda x: -x[1]):
        info = etf_map.get(code, {})
        result.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "count": count,
            "pct": round(count / total * 100, 1) if total > 0 else 0,
        })
    return result


def build_sector_distribution(signal_history, etf_map):
    if not signal_history:
        return []
    latest = signal_history[-1]
    positions = latest["positions"]
    sector_weight = {}
    for code, weight in positions.items():
        if weight <= 0:
            continue
        info = etf_map.get(code, {})
        sector = info.get("sector", "Other")
        sector_weight[sector] = sector_weight.get(sector, 0) + weight
    result = []
    for sector, w in sorted(sector_weight.items(), key=lambda x: -x[1]):
        result.append({"sector": sector, "weight": round(float(w) * 100, 1)})
    return result


def build_hs300_benchmark(nav_df):
    """Fetch HS300 and normalize to nav_df date range (100% = first date)."""
    try:
        import akshare as ak
    except ImportError:
        print("  [WARN] akshare not installed, HS300 benchmark unavailable")
        return None

    print("  Fetching HS300 daily...")
    try:
        hs = ak.stock_zh_index_daily(symbol="sh000300")
    except Exception as e:
        print(f"  [WARN] Fetch failed: {e}")
        return None

    hs["date"] = pd.to_datetime(hs["date"])
    hs = hs.sort_values("date").reset_index(drop=True)
    hs_map = dict(zip(hs["date"].dt.strftime("%Y-%m-%d"), hs["close"].astype(float)))

    nav_dates = [d.strftime("%Y-%m-%d") for d in nav_df["date"]]
    anchor = None
    for d in nav_dates:
        if d in hs_map:
            anchor = hs_map[d]
            break
    if not anchor:
        return None

    result = []
    last_val = 100.0
    for d in nav_dates:
        if d in hs_map:
            last_val = round(hs_map[d] / anchor * 100, 2)
        result.append(last_val)
    return result


def build_equal_weight_benchmark(nav_df, all_daily_data):
    """
    Compute equal-weight buy-and-hold benchmark for all 25 ETFs.
    Normalized to 100% at first valid date.
    """
    nav_dates = nav_df["date"].tolist()
    if not nav_dates:
        return None

    # Build date -> {code: close} map
    price_map = {}  # date_str -> {code: close}
    for code, df in all_daily_data.items():
        for _, row in df.iterrows():
            d = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])[:10]
            if d not in price_map:
                price_map[d] = {}
            price_map[d][code] = float(row["close"])

    # Find anchor prices (first date with data)
    nav_date_strs = [d.strftime("%Y-%m-%d") for d in nav_dates]
    anchor_prices = None
    for d in nav_date_strs:
        if d in price_map and len(price_map[d]) >= 10:
            anchor_prices = price_map[d]
            break

    if not anchor_prices:
        return None

    # Compute equal-weight portfolio value each day
    codes = list(anchor_prices.keys())
    result = []
    last_val = 100.0
    for d in nav_date_strs:
        if d in price_map:
            day_prices = price_map[d]
            total_return = 0.0
            count = 0
            for c in codes:
                if c in day_prices and c in anchor_prices and anchor_prices[c] > 0:
                    total_return += day_prices[c] / anchor_prices[c]
                    count += 1
            if count > 0:
                last_val = round(total_return / count * 100, 2)
        result.append(last_val)

    return result


def run_template_backtest(base_cfg, template_override):
    """Run backtest with template-specific config overrides."""
    cfg = merge_config(base_cfg, template_override)

    # Patch the config into the module's expected format
    # run_backtest reads from file, so we need to temporarily override
    # Instead, we'll call the internal logic directly with params
    from quant_backtest import run_backtest as _run

    # Monkey-patch load_config to return our merged config
    import quant_backtest
    original_load = quant_backtest.load_config
    quant_backtest.load_config = lambda: cfg
    try:
        nav_df, signal_history = _run()
    finally:
        quant_backtest.load_config = original_load

    return nav_df, signal_history


def build_latest_signal(all_daily_data, all_weekly_data, base_cfg, etf_map):
    """
    M4.2: 基于最新日线数据计算今日收盘后的目标仓位建议。
    与回测中的周度调仓逻辑一致，但使用最新数据（而非回测历史）。
    """
    from quant_factors import compute_all_factors, map_f1, map_f2, map_f3, map_f4, confidence_function

    cfg = base_cfg
    weights = cfg["scoring"]["weights"]
    bias_bonus = cfg["scoring"]["bias_bonus"]
    sensitivity = cfg["scoring"].get("sensitivity", {})
    f1_sens = sensitivity.get("f1", 8.0)
    f3_sens = sensitivity.get("f3", 1.5)
    dead_zone = cfg["confidence"]["dead_zone"]
    full_zone = cfg["confidence"]["full_zone"]
    max_holdings = cfg["position"]["max_holdings"]
    step = cfg["position"]["discretize_step"]
    factor_cfg = cfg["factors"]

    # bias_map 使用 0-1 尺度
    bias_map = {e["code"]: bias_bonus / 100.0 for e in cfg["universe"] if e.get("bias")}

    # Compute factors for all ETFs using latest data
    factors_data = {}
    prices_today = {}
    latest_date = None

    for code in all_daily_data:
        daily_df = all_daily_data[code]
        weekly_df = all_weekly_data.get(code)

        if daily_df is None or len(daily_df) < 30:
            continue
        if weekly_df is None or len(weekly_df) < factor_cfg["ema"]["period_weeks"]:
            continue

        factors = compute_all_factors(
            daily_df, weekly_df,
            ema_period=factor_cfg["ema"]["period_weeks"],
            rsi_period=factor_cfg["rsi"]["period_days"],
            vol_window=factor_cfg["volume_ratio"]["window_days"],
        )

        if any(np.isnan(v) for v in factors.values()):
            continue

        factors_data[code] = factors
        prices_today[code] = float(daily_df["close"].iloc[-1])

        if latest_date is None:
            latest_date = daily_df["date"].iloc[-1]
            if hasattr(latest_date, "strftime"):
                latest_date = latest_date.strftime("%Y-%m-%d")
            else:
                latest_date = str(latest_date)[:10]

    if len(factors_data) < max_holdings:
        return None

    # 连续映射 + 合成
    factors_df = pd.DataFrame(factors_data).T
    mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
    mapped_f2 = factors_df["f2_rsi_adaptive"].apply(map_f2)
    mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

    w1 = weights.get("ema_deviation", 0.30)
    w2 = weights.get("rsi_adaptive", 0.25)
    w3 = weights.get("volume_ratio", 0.30)
    w4 = weights.get("valuation", 0.15)

    composite = mapped_f1 * w1 + mapped_f2 * w2 + mapped_f3 * w3

    # F4 估值因子 (REQ-178): 低估值 = 高分
    if w4 > 0:
        try:
            from valuation_engine import ValuationEngine
            from valuation_fetcher import evaluate_all_etfs
            engine = ValuationEngine()
            val_results = evaluate_all_etfs(engine)
            # 构建估值分数: 100 - percentile (低估值得高分)
            val_scores = {}
            for code in factors_df.index:
                if code in val_results and val_results[code].get("percentile") is not None:
                    val_scores[code] = 100.0 - val_results[code]["percentile"]
                else:
                    val_scores[code] = 50.0  # 无数据给中性分
            f4_series = pd.Series(val_scores)
            mapped_f4 = f4_series.apply(map_f4)
            composite = composite + mapped_f4 * w4
        except Exception:
            pass  # 估值引擎异常时降级为三因子

    for code, bonus in bias_map.items():
        if code in composite.index:
            composite[code] += bonus

    # Top-N selection + confidence + position
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

    # Build result — composite is in [0, 1], display as percentage
    holdings = []
    for code in top_n.index:
        info = etf_map.get(code, {})
        holdings.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "bias": info.get("bias", False),
            "score": round(float(composite[code]) * 100, 2),
            "confidence": round(float(confidences[code]), 3),
            "position": round(float(target_positions.get(code, 0)) * 100, 1),
            "price": round(prices_today.get(code, 0), 3),
        })

    # All scores for context
    all_scores = []
    for code in composite.sort_values(ascending=False).index:
        info = etf_map.get(code, {})
        all_scores.append({
            "code": code,
            "name": info.get("name", code),
            "score": round(float(composite[code]) * 100, 2),
            "inTop": code in top_n.index,
        })

    return {
        "date": latest_date,
        "avgConfidence": round(float(avg_conf), 3),
        "totalTarget": round(float(total_target) * 100, 1),
        "cashTarget": round((1 - float(total_target)) * 100, 1),
        "maxHoldings": max_holdings,
        "holdings": holdings,
        "allScores": all_scores,
    }


def build_risk_orders(signal_history, all_daily_data, base_cfg, etf_map):
    """
    M4.1: 风控挂单计算
    基于最新一次调仓信号，计算：
    - Top-6 持仓的止盈/止损临界价（F1 逆运算）
    - 第7-8名候补的左侧买入价

    原理：F1 = (close - EMA) / EMA，是唯一直接依赖当前价格的因子。
    假设 F2(RSI)、F3(量比) 保持不变，反推 close 需要变动多少才会改变排名。

    简化方法：
    - 止损价 = 使该ETF的F1_raw下降到其当前综合分跌出Top-6所需的水平
    - 止盈价 = F1_raw上升到综合分达到满配(65分)的水平
    - 买入价(候补) = F1_raw上升到综合分进入Top-6的水平
    """
    if not signal_history:
        return None

    latest = signal_history[-1]
    scores = latest["scores"]
    top6 = latest["top6"]
    positions = latest["positions"]

    # Get the threshold: score of 7th ranked ETF (cutoff)
    sorted_codes = sorted(scores.keys(), key=lambda c: -scores[c])
    if len(sorted_codes) < 7:
        return None

    threshold_score = scores[sorted_codes[6]]  # 7th ETF's score = minimum to be in Top-6

    factor_cfg = base_cfg["factors"]
    ema_period = factor_cfg["ema"]["period_weeks"]

    orders = []

    for code in sorted_codes[:10]:  # Top-10 analysis
        if code not in all_daily_data:
            continue

        # Get current price and weekly EMA
        daily_df = all_daily_data[code]
        if len(daily_df) < 5:
            continue
        current_price = float(daily_df["close"].iloc[-1])

        # Compute current weekly EMA from daily data (resample)
        daily_df_copy = daily_df.copy()
        daily_df_copy["date"] = pd.to_datetime(daily_df_copy["date"])
        daily_df_copy = daily_df_copy.set_index("date").sort_index()
        weekly_close = daily_df_copy["close"].resample("W-FRI").last().dropna()
        if len(weekly_close) < ema_period:
            continue

        ema_val = float(weekly_close.ewm(span=ema_period, adjust=False).mean().iloc[-1])
        if ema_val <= 0:
            continue

        current_score = scores.get(code, 0)
        # Convert to percentage for display
        display_score = round(current_score * 100, 2)
        in_top6 = code in top6
        info = etf_map.get(code, {})

        order = {
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "currentPrice": round(current_price, 3),
            "ema": round(ema_val, 3),
            "currentScore": display_score,
            "inTop6": in_top6,
            "position": round(float(positions.get(code, 0)) * 100, 1),
        }

        # F1 contribution: how much the composite score changes per unit of EMA deviation
        w1 = base_cfg["scoring"]["weights"].get("ema_deviation", 0.35)

        # Score scale is [0, 1] now
        threshold_display = threshold_score * 100

        if in_top6:
            # Stop-loss: price at which score drops to threshold
            score_gap = current_score - threshold_score
            if score_gap > 0:
                # With sigmoid mapping, estimate the ema_dev change needed
                # to lose score_gap in composite: Δcomposite ≈ w1 × Δsigmoid ≈ w1 × sigmoid' × Δdev/sens
                # Approximate: use linear estimate for simplicity
                current_dev = (current_price - ema_val) / ema_val * 100
                # Score per 1% deviation ≈ w1 * sigmoid_slope / sensitivity
                # At current_dev, sigmoid slope ≈ sigmoid(x)*(1-sigmoid(x))/sensitivity
                x = current_dev / f1_sens
                sig_val = 1.0 / (1.0 + math.exp(-x))
                slope = sig_val * (1 - sig_val) / f1_sens
                score_per_pct = w1 * slope
                if score_per_pct > 0:
                    dev_drop = score_gap / score_per_pct
                    target_dev = current_dev - dev_drop * 1.5  # safety margin
                else:
                    target_dev = current_dev - 5.0  # fallback
                stop_loss_price = ema_val * (1 + target_dev / 100)
                stop_loss_price = max(stop_loss_price, current_price * 0.7)  # floor at -30%
                order["stopLoss"] = round(stop_loss_price, 3)
                order["stopLossPct"] = round((stop_loss_price / current_price - 1) * 100, 1)
            else:
                order["stopLoss"] = round(current_price * 0.95, 3)
                order["stopLossPct"] = -5.0

            # Take-profit: price at which score reaches full_zone
            full_zone = base_cfg["confidence"]["full_zone"]
            if current_score < full_zone:
                score_needed = full_zone - current_score
                current_dev = (current_price - ema_val) / ema_val * 100
                x = current_dev / f1_sens
                sig_val = 1.0 / (1.0 + math.exp(-x))
                slope = sig_val * (1 - sig_val) / f1_sens
                score_per_pct = w1 * slope
                if score_per_pct > 0:
                    dev_rise = score_needed / score_per_pct
                    target_dev = current_dev + dev_rise * 1.2
                else:
                    target_dev = current_dev + 5.0
                tp_price = ema_val * (1 + target_dev / 100)
                tp_price = min(tp_price, current_price * 1.5)  # cap at +50%
                order["takeProfit"] = round(tp_price, 3)
                order["takeProfitPct"] = round((tp_price / current_price - 1) * 100, 1)
            else:
                order["takeProfit"] = round(current_price * 1.15, 3)
                order["takeProfitPct"] = 15.0
        else:
            # Candidate: buy price to enter Top-6
            score_needed = threshold_score - current_score
            if score_needed > 0:
                current_dev = (current_price - ema_val) / ema_val * 100
                x = current_dev / f1_sens
                sig_val = 1.0 / (1.0 + math.exp(-x))
                slope = sig_val * (1 - sig_val) / f1_sens
                score_per_pct = w1 * slope
                if score_per_pct > 0:
                    dev_rise = score_needed / score_per_pct
                    target_dev = current_dev + dev_rise * 1.2
                else:
                    target_dev = current_dev + 5.0
                buy_price = ema_val * (1 + target_dev / 100)
                buy_price = min(buy_price, current_price * 1.3)  # cap at +30%
                order["buyPrice"] = round(buy_price, 3)
                order["buyPricePct"] = round((buy_price / current_price - 1) * 100, 1)
            else:
                # Already above threshold, minor push needed
                order["buyPrice"] = round(current_price * 1.02, 3)
                order["buyPricePct"] = 2.0

        orders.append(order)

    return {
        "date": latest["date"].strftime("%Y-%m-%d"),
        "thresholdScore": round(threshold_score * 100, 2),
        "orders": orders,
    }



def build_template_payload(nav_df, signal_history, etf_map, hs300_pct, eq_weight_pct, risk_orders, latest_signal):
    """Build one template's payload dict."""
    return {
        "summary": compute_summary(nav_df, len(signal_history)),
        "navSeries": {
            "dates": [d.strftime("%Y-%m-%d") for d in nav_df["date"]],
            "navPct": [round(float(v), 2) for v in nav_df["nav_pct"]],
            "holdings": [int(v) for v in nav_df["holdings"]],
        },
        "hs300Pct": hs300_pct,
        "eqWeightPct": eq_weight_pct,
        "drawdownSeries": compute_drawdown(nav_df["nav"]),
        "signalHistory": serialize_signal_history(signal_history),
        "rebalanceFreq": build_rebalance_freq(signal_history, etf_map),
        "sectorDistribution": build_sector_distribution(signal_history, etf_map),
        "riskOrders": risk_orders,
        "latestSignal": latest_signal,
    }


def serialize_config_for_display(cfg, template_override):
    """Extract display-friendly params for a template."""
    merged = merge_config(cfg, template_override)
    return {
        "scoring": merged.get("scoring", {}),
        "confidence": merged.get("confidence", {}),
        "position": merged.get("position", {}),
        "factors": merged.get("factors", {}),
    }


def main():
    print("=" * 60)
    print("REQ-177 M3.1 v2: multi-template quant payload builder")
    print("=" * 60)

    # 1. Load configs
    base_cfg = load_config()
    templates = load_templates()
    etf_map = build_etf_name_map(base_cfg)
    template_ids = list(templates.keys())
    print(f"[1/4] Configs loaded: {len(etf_map)} ETFs, {len(template_ids)} templates: {template_ids}")

    # 2. Run backtests for each template
    print("[2/4] Running backtests...")
    results = {}
    first_nav_df = None

    for tid in template_ids:
        tpl = templates[tid]
        label = tpl.get("label", tid)
        print(f"\n  --- Template: {label} ({tid}) ---")
        nav_df, signal_history = run_template_backtest(base_cfg, tpl)
        if nav_df is None:
            print(f"  [ERROR] Backtest failed for {tid}")
            continue
        results[tid] = (nav_df, signal_history)
        if first_nav_df is None:
            first_nav_df = nav_df
        s = compute_summary(nav_df, len(signal_history))
        print(f"  Return: {s['totalReturn']:+.2f}% | Annual: {s['annualReturn']:+.2f}% | "
              f"MaxDD: {s['maxDrawdown']:.2f}% | Sharpe: {s['sharpe']:.2f}")

    if not results:
        print("[ERROR] No successful backtests")
        sys.exit(1)

    # 3. Fetch HS300 benchmark + compute equal-weight benchmark (once, shared)
    print("\n[3/4] Building payload...")
    hs300_pct = build_hs300_benchmark(first_nav_df)

    # Load all daily+weekly CSVs for equal-weight benchmark and latest signal
    from quant_backtest import DATA_DIR
    all_daily_data = {}
    all_weekly_data = {}
    for etf in base_cfg["universe"]:
        code = etf["code"]
        daily_path = DATA_DIR / f"{code}_daily.csv"
        weekly_path = DATA_DIR / f"{code}_weekly.csv"
        if daily_path.exists():
            df = pd.read_csv(daily_path, parse_dates=["date"])
            all_daily_data[code] = df
        if weekly_path.exists():
            df = pd.read_csv(weekly_path, parse_dates=["date"])
            all_weekly_data[code] = df
    eq_weight_pct = build_equal_weight_benchmark(first_nav_df, all_daily_data)
    print(f"  Benchmarks: HS300={'OK' if hs300_pct else 'N/A'}, EqWeight={'OK' if eq_weight_pct else 'N/A'}")

    # 4. Assemble payload
    payload_templates = {}
    payload_configs = {}

    for tid in template_ids:
        if tid not in results:
            continue
        nav_df, signal_history = results[tid]
        merged_cfg = merge_config(base_cfg, templates[tid])
        risk_orders = build_risk_orders(signal_history, all_daily_data, merged_cfg, etf_map)
        latest_signal = build_latest_signal(all_daily_data, all_weekly_data, merged_cfg, etf_map)
        payload_templates[tid] = build_template_payload(nav_df, signal_history, etf_map, hs300_pct, eq_weight_pct, risk_orders, latest_signal)
        payload_configs[tid] = serialize_config_for_display(base_cfg, templates[tid])

    # Template meta
    template_meta = {}
    for tid in template_ids:
        tpl = templates[tid]
        template_meta[tid] = {
            "label": tpl.get("label", tid),
            "description": tpl.get("description", ""),
        }

    payload = {
        "generatedAt": datetime.now().isoformat(),
        "templateMeta": template_meta,
        "templates": payload_templates,
        "config": payload_configs,
        "etfNameMap": {c: info["name"] for c, info in etf_map.items()},
    }

    # 5. Write JS
    print("[4/4] Writing payload...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(payload, ensure_ascii=False, indent=None)  # compact for size
    js_content = (
        f"// Auto-generated by quant_build_payload.py (multi-template)\n"
        f"// {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"window.__QUANT_RUNTIME__ = {json_str};\n"
    )
    OUTPUT_PATH.write_text(js_content, encoding="utf-8")
    print(f"\n  Payload written: {OUTPUT_PATH}")
    print(f"  Size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")
    print("=" * 60)


if __name__ == "__main__":
    main()
