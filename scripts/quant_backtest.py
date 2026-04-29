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
    compute_all_factors,
    map_f1, map_f2, map_f3, map_f4,
    confidence_function,
)

CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
DATA_DIR = SKILL_DIR / "data" / "quant"
OUTPUT_DIR = SKILL_DIR / "data" / "quant_results"


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_etf_data(code: str):
    """加载一支 ETF 的日线和周线数据"""
    daily_path = DATA_DIR / f"{code}_daily.csv"
    weekly_path = DATA_DIR / f"{code}_weekly.csv"

    if not daily_path.exists() or not weekly_path.exists():
        return None, None

    daily = pd.read_csv(daily_path, parse_dates=["date"])
    weekly = pd.read_csv(weekly_path, parse_dates=["date"])
    daily = daily.sort_values("date").reset_index(drop=True)
    weekly = weekly.sort_values("date").reset_index(drop=True)
    return daily, weekly


def get_rebalance_dates(daily_dates: pd.DatetimeIndex, freq: str = "W-FRI"):
    """获取调仓日期列表（每周五）"""
    # 找出所有交易日中的周五（或最接近的最后交易日）
    dates_series = pd.Series(daily_dates).sort_values().reset_index(drop=True)
    # 按周分组，取每周最后一个交易日
    weekly_groups = dates_series.groupby(dates_series.dt.isocalendar().week.values +
                                          dates_series.dt.isocalendar().year.values * 100)
    rebalance_dates = weekly_groups.max().sort_values().values
    return pd.DatetimeIndex(rebalance_dates)


def run_backtest(start_date: str = "2023-01-01", end_date: str = None,
                 initial_capital: float = 1000000.0):
    """
    主回测函数

    逻辑：
    1. 每个调仓日（周五收盘后）计算 25 支 ETF 三因子
    2. 截面标准化 + 合成综合分
    3. Top-6 选股 + 信心函数仓位分配
    4. 下周一开盘按目标仓位调仓（简化：用周五收盘价成交）
    5. 持仓到下一个调仓日，按每日收盘价计算组合市值
    """
    cfg = load_config()
    universe = cfg["universe"]
    scoring_cfg = cfg["scoring"]
    confidence_cfg = cfg["confidence"]
    position_cfg = cfg["position"]
    factor_cfg = cfg["factors"]

    weights = scoring_cfg["weights"]
    bias_bonus = scoring_cfg["bias_bonus"]
    sensitivity = scoring_cfg.get("sensitivity", {})
    f1_sens = sensitivity.get("f1", 8.0)
    f3_sens = sensitivity.get("f3", 1.0)
    f2_dz = sensitivity.get("f2_dead_zone", 1.0)
    dead_zone = confidence_cfg["dead_zone"]
    full_zone = confidence_cfg["full_zone"]
    max_holdings = position_cfg["max_holdings"]
    step = position_cfg["discretize_step"]

    # 构建偏好 map（0-1 尺度）
    bias_map = {e["code"]: bias_bonus / 100.0 for e in universe if e.get("bias")}

    # 加载所有 ETF 数据
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

    # 确定回测日期范围
    # 用所有 ETF 的日线数据的交集确定公共日期范围
    all_dates = set()
    for code, df in all_daily.items():
        dates = set(df["date"].values)
        if not all_dates:
            all_dates = dates
        else:
            all_dates = all_dates.union(dates)

    all_dates = sorted(all_dates)
    all_dates = pd.DatetimeIndex(all_dates)

    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date) if end_date else all_dates[-1]
    all_dates = all_dates[(all_dates >= start_dt) & (all_dates <= end_dt)]

    if len(all_dates) == 0:
        print("[ERROR] 无有效交易日")
        return None

    print(f"  回测区间: {all_dates[0].strftime('%Y-%m-%d')} ~ {all_dates[-1].strftime('%Y-%m-%d')}")
    print(f"  交易日数: {len(all_dates)}")

    # 获取调仓日
    rebalance_dates = get_rebalance_dates(all_dates)
    rebalance_dates = rebalance_dates[(rebalance_dates >= start_dt) & (rebalance_dates <= end_dt)]

    # 需要至少 EMA 周期的预热期
    min_warmup_weeks = factor_cfg["ema"]["period_weeks"]
    # 从第 min_warmup_weeks 个调仓日开始才有有效信号
    if len(rebalance_dates) <= min_warmup_weeks:
        print(f"[ERROR] 调仓日数({len(rebalance_dates)})不够预热({min_warmup_weeks}周)")
        return None

    rebalance_dates = rebalance_dates[min_warmup_weeks:]
    print(f"  有效调仓日: {len(rebalance_dates)}（跳过前 {min_warmup_weeks} 周预热）")

    # ============================================================
    # 回测主循环
    # ============================================================
    portfolio = {}  # {code: shares}
    cash = initial_capital
    nav_history = []  # [{date, nav, cash, holdings_value, positions: {...}}]
    signal_history = []  # 每次调仓的打分记录

    print("\n开始回测...")

    for rb_idx, rb_date in enumerate(rebalance_dates):
        # ------ 1. 计算当日三因子 ------
        factors_data = {}
        prices_today = {}

        for code in all_daily:
            daily_df = all_daily[code]
            weekly_df = all_weekly[code]

            # 截取到调仓日为止的数据
            daily_slice = daily_df[daily_df["date"] <= rb_date]
            weekly_slice = weekly_df[weekly_df["date"] <= rb_date]

            if len(daily_slice) < 30 or len(weekly_slice) < factor_cfg["ema"]["period_weeks"]:
                continue  # 数据不足跳过

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
            # 可用 ETF 不够，跳过本次调仓
            continue

        # ------ 2. 连续映射 + 合成 ------
        factors_df = pd.DataFrame(factors_data).T

        mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
        mapped_f2 = factors_df["f2_rsi_adaptive"].apply(lambda v: map_f2(v, f2_dz))
        mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

        w1 = weights.get("ema_deviation", 0.35)
        w2 = weights.get("rsi_adaptive", 0.30)
        w3 = weights.get("volume_ratio", 0.35)
        w4 = weights.get("valuation", 0.15)

        composite = mapped_f1 * w1 + mapped_f2 * w2 + mapped_f3 * w3

        # F4 估值因子（regime-aware）
        rb_date_str = rb_date.strftime("%Y-%m-%d") if hasattr(rb_date, "strftime") else str(rb_date)[:10]
        market_regime = market_regimes.get(rb_date_str, "choppy_range")

        if w4 > 0 and "f4_valuation" in factors_df.columns:
            mapped_f4 = factors_df["f4_valuation"].apply(lambda v: map_f4(v, market_regime))
            composite = composite + mapped_f4 * w4

        # 偏好加成
        for code, bonus in bias_map.items():
            if code in composite.index:
                composite[code] += bonus

        # ------ 3. Top-6 选股 + 仓位 ------
        top_n = composite.nlargest(max_holdings)

        # 信心函数
        confidences = top_n.apply(lambda s: confidence_function(s, dead_zone, full_zone))

        # 得分加权
        if top_n.sum() > 0:
            relative_weights = top_n / top_n.sum()
        else:
            relative_weights = pd.Series(0.0, index=top_n.index)

        # 平均信心 → 总仓位水平
        avg_conf = confidences.mean()
        total_target = min(0.95, avg_conf * 1.2)  # 上限 95%

        # 每支目标仓位
        target_positions = relative_weights * total_target

        # 离散化
        target_positions = (target_positions / step).round() * step
        target_positions = target_positions.clip(lower=0)

        # ------ 4. 计算当前组合市值 ------
        holdings_value = sum(
            portfolio.get(code, 0) * prices_today.get(code, 0)
            for code in portfolio
        )
        total_value = cash + holdings_value

        # ------ 5. 调仓：卖出不在 Top-6 的，调整仓位 ------
        target_codes = set(target_positions.index)

        # 先卖出
        for code in list(portfolio.keys()):
            if code not in target_codes or target_positions.get(code, 0) == 0:
                # 全卖
                if code in prices_today:
                    sell_value = portfolio[code] * prices_today[code]
                    cash += sell_value
                del portfolio[code]

        # 调整已有持仓 + 买入新持仓
        for code in target_codes:
            target_value = total_value * target_positions[code]
            current_value = portfolio.get(code, 0) * prices_today.get(code, 0)
            diff = target_value - current_value

            if code not in prices_today or prices_today[code] == 0:
                continue

            if diff > 0:
                # 买入
                buy_shares = diff / prices_today[code]
                if cash >= diff:
                    portfolio[code] = portfolio.get(code, 0) + buy_shares
                    cash -= diff
                else:
                    # 现金不足，买能买的
                    buy_shares = cash / prices_today[code]
                    portfolio[code] = portfolio.get(code, 0) + buy_shares
                    cash = 0
            elif diff < -step * total_value:
                # 卖出（超过一个档位才卖，避免微调）
                sell_shares = -diff / prices_today[code]
                sell_shares = min(sell_shares, portfolio.get(code, 0))
                portfolio[code] = portfolio.get(code, 0) - sell_shares
                cash += sell_shares * prices_today[code]
                if portfolio[code] <= 0:
                    del portfolio[code]

        # 记录信号
        signal_history.append({
            "date": rb_date,
            "scores": composite.to_dict(),
            "top6": list(top_n.index),
            "positions": target_positions.to_dict(),
            "avg_confidence": avg_conf,
            "total_target": total_target,
        })

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

    for date in all_dates:
        # 检查是否是调仓日
        if signal_idx < len(signal_history) and date >= signal_history[signal_idx]["date"]:
            # 执行调仓
            sig = signal_history[signal_idx]
            target_positions = sig["positions"]
            target_codes = set(target_positions.keys())

            # 获取当日价格
            prices = {}
            for code in all_daily:
                df = all_daily[code]
                row = df[df["date"] == date]
                if len(row) > 0:
                    prices[code] = float(row["close"].iloc[0])

            # 当前总值
            hv = sum(portfolio2.get(c, 0) * prices.get(c, 0) for c in portfolio2)
            tv = cash2 + hv

            # 卖出
            for code in list(portfolio2.keys()):
                if code not in target_codes or target_positions.get(code, 0) == 0:
                    if code in prices:
                        cash2 += portfolio2[code] * prices[code]
                    del portfolio2[code]

            # 重新计算 total value
            hv = sum(portfolio2.get(c, 0) * prices.get(c, 0) for c in portfolio2)
            tv = cash2 + hv

            # 买入调整
            for code in target_codes:
                if code not in prices or prices[code] == 0:
                    continue
                target_value = tv * target_positions[code]
                current_value = portfolio2.get(code, 0) * prices.get(code, 0)
                diff = target_value - current_value

                if diff > 0 and cash2 >= diff:
                    shares = diff / prices[code]
                    portfolio2[code] = portfolio2.get(code, 0) + shares
                    cash2 -= diff
                elif diff < 0:
                    sell_shares = -diff / prices[code]
                    sell_shares = min(sell_shares, portfolio2.get(code, 0))
                    portfolio2[code] = portfolio2.get(code, 0) - sell_shares
                    cash2 += sell_shares * prices[code]
                    if portfolio2.get(code, 0) <= 0:
                        portfolio2.pop(code, None)

            signal_idx += 1

        # 计算当日 NAV
        prices = {}
        for code in all_daily:
            df = all_daily[code]
            row = df[df["date"] == date]
            if len(row) > 0:
                prices[code] = float(row["close"].iloc[0])

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

    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)
    print(f"  回测区间:    {nav_df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {nav_df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"  交易日数:    {len(nav_df)}")
    print(f"  调仓次数:    {len(signal_history)}")
    print(f"  总收益率:    {total_return:+.2f}%")
    print(f"  年化收益率:  {annual_return:+.2f}%")
    print(f"  最大回撤:    {max_drawdown:.2f}%")
    print(f"  夏普比率:    {sharpe:.2f}")
    print(f"  最终 NAV:    {final_nav:,.0f} (初始 {initial_capital:,.0f})")
    print(f"  最终持仓数:  {nav_df['holdings'].iloc[-1]}")
    print("=" * 60)

    return nav_df, signal_history


def main():
    parser = argparse.ArgumentParser(description="REQ-177 M2.1: 量化回测引擎")
    parser.add_argument("--start", type=str, default="2023-01-01", help="回测起始日期")
    parser.add_argument("--end", type=str, default=None, help="回测结束日期")
    parser.add_argument("--output", type=str, default=None, help="输出净值 CSV 路径")
    args = parser.parse_args()

    nav_df, signals = run_backtest(start_date=args.start, end_date=args.end)

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


if __name__ == "__main__":
    main()
