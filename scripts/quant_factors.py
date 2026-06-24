"""
REQ-177 M1.1: 三因子计算模块
输入：日线 DataFrame (date, open, high, low, close, volume)
     周线 DataFrame (同上)
输出：三因子连续值

因子：
  F1: 周线 EMA 偏离度 = (close - EMA_N) / EMA_N
  F3: 自归一化量比 = vol_z = volume/60d_avg → mean(up_vol_z)/mean(down_vol_z), N日滚动
  F7: 对数收益偏离 Z-score

评分管线（连续映射版）：
  原始因子 → 连续映射函数 → [0, 1] 绝对分数 → 加权合成 → 信心函数 → 仓位分配
  不做截面标准化（percentile_rank），保留因子的绝对水平和极端性。
"""
import math
import numpy as np
import pandas as pd


def calc_ema(series: pd.Series, span: int) -> pd.Series:
    """计算 EMA"""
    return series.ewm(span=span, adjust=False).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def factor_ema_deviation(weekly_df: pd.DataFrame, ema_period: int = 16,
                         today_close: float = None) -> float:
    """
    F1: 周线 EMA 偏离度
    返回最新一周的 (close - EMA) / EMA × 100 (百分比)
    若提供 today_close，则用它替代最后一根周K的收盘价（用于F1_daily实验）
    """
    if weekly_df is None or len(weekly_df) < ema_period:
        return np.nan

    close = weekly_df["close"].astype(float)
    if today_close is not None and not np.isnan(today_close):
        close = close.copy()
        close.iloc[-1] = today_close
    ema = calc_ema(close, span=ema_period)
    deviation = (close.iloc[-1] - ema.iloc[-1]) / ema.iloc[-1] * 100
    return deviation



def factor_volume_ratio(daily_df: pd.DataFrame, window: int = 20) -> float:
    """
    F3: 方向性量比
    = mean(上涨日成交额) / mean(下跌日成交额), 最近 N 日
    返回原始比值（后续截面标准化）
    """
    if daily_df is None or len(daily_df) < window + 1:
        return np.nan

    df = daily_df.tail(window + 1).copy()
    df["change"] = df["close"].astype(float).pct_change()
    df = df.iloc[1:]  # 去掉第一行 NaN

    vol_col = "volume"
    # 如果有 amount 列优先用（成交额比成交量更有意义）
    if "amount" in df.columns:
        vol_col = "amount"

    up_days = df[df["change"] > 0]
    down_days = df[df["change"] < 0]

    if len(down_days) == 0 or down_days[vol_col].astype(float).mean() == 0:
        return 3.0 if len(up_days) > 0 else 1.0  # 全涨无跌 → 强势上限

    up_vol = up_days[vol_col].astype(float).mean() if len(up_days) > 0 else 0
    down_vol = down_days[vol_col].astype(float).mean()

    ratio = up_vol / down_vol
    return ratio


def factor_volume_ratio_normalized(daily_df: pd.DataFrame, window: int = 20,
                                   norm_window: int = 60) -> float:
    """
    F3-N (自归一化量比): 先用自身历史均值校准每日成交量，再做方向性量比。

    vol_z[t] = volume[t] / mean(volume[t-norm_window : t])
    F3-N = mean(vol_z on up days) / mean(vol_z on down days)  over `window`

    相比原 F3:
    - 停牌日量低 → vol_z < 1 → 被自身历史校准，不影响跨 ETF 比较
    - 热度日量大 → vol_z > 1 → 信号保留但不靠绝对量霸榜
    - 正常 ETF → vol_z ≈ 1.0 → F3-N ≈ 原 F3

    返回原始比值（后续截面标准化）。若历史不足 norm_window+window 天则返回 NaN。
    """
    min_days = norm_window + window + 1
    if daily_df is None or len(daily_df) < min_days:
        return np.nan

    vol_col = "volume"
    if "amount" in daily_df.columns:
        vol_col = "amount"

    df = daily_df.tail(min_days).copy()
    vol = df[vol_col].astype(float)
    close = df["close"].astype(float)

    # Rolling mean of trailing `norm_window` volume (excludes current day)
    vol_ma = vol.rolling(window=norm_window, min_periods=norm_window).mean().shift(1)
    vol_z = vol / vol_ma  # NaN where vol_ma is NaN

    chg = close.pct_change()

    # Only use the last `window` days for ratio computation
    vol_z = vol_z.iloc[-window:]
    chg = chg.iloc[-window:]

    up_mask = chg > 0
    down_mask = chg < 0

    up_z = vol_z[up_mask]
    down_z = vol_z[down_mask]

    if len(down_z) == 0 or down_z.mean() == 0:
        return 3.0 if len(up_z) > 0 else 1.0

    up_avg = up_z.mean() if len(up_z) > 0 else 0
    down_avg = down_z.mean()

    return up_avg / down_avg


def factor_residual_momentum(weekly_df: pd.DataFrame,
                             hs300_weekly: pd.DataFrame,
                             reg_window: int = 12,
                             mom_window: int = 12) -> float:
    """
    残差动量因子（Residual Momentum）

    原理：原始动量混合了市场 beta 和个股 alpha。通过回归剥离市场成分，
    只保留"跑赢/跑输大盘的那部分动量"。学术研究表明残差动量比原始
    动量更稳定、换手更低（Gutierrez & Pirinsky 2007, Blitz et al. 2020）。

    计算步骤：
    1. 取最近 reg_window 周的 (ETF周收益, HS300周收益) 对
    2. 做 OLS 回归: r_etf = alpha + beta * r_hs300 + epsilon
    3. 残差 epsilon = r_etf - (alpha + beta * r_hs300)
    4. 残差动量 = 最近 mom_window 周残差的累积和

    返回：残差动量百分比（正=持续跑赢大盘，负=持续跑输）
    """
    if weekly_df is None or hs300_weekly is None:
        return np.nan
    if len(weekly_df) < reg_window + 1 or len(hs300_weekly) < reg_window + 1:
        return np.nan

    etf_close = weekly_df["close"].astype(float)
    hs300_close = hs300_weekly["close"].astype(float)

    # 计算周收益率
    etf_ret = etf_close.pct_change().dropna()
    hs300_ret = hs300_close.pct_change().dropna()

    # 对齐日期
    common_idx = etf_ret.index.intersection(hs300_ret.index)
    if len(common_idx) < reg_window:
        return np.nan

    etf_ret = etf_ret.loc[common_idx]
    hs300_ret = hs300_ret.loc[common_idx]

    # 取最近 reg_window 周
    y = etf_ret.iloc[-reg_window:].values
    x = hs300_ret.iloc[-reg_window:].values

    # OLS: r_etf = alpha + beta * r_hs300
    n = len(x)
    if n < 3:
        return np.nan
    x_mean = x.mean()
    y_mean = y.mean()
    ss_xx = ((x - x_mean) ** 2).sum()
    if ss_xx < 1e-12:
        # HS300 无波动，无法回归
        return np.nan
    beta = ((x - x_mean) * (y - y_mean)).sum() / ss_xx
    alpha = y_mean - beta * x_mean

    # 残差
    residuals = y - (alpha + beta * x)

    # 残差动量：最近 mom_window 周残差累积
    mw = min(mom_window, len(residuals))
    residual_mom = residuals[-mw:].sum() * 100  # 转百分比

    return float(residual_mom)


def compute_all_factors(daily_df: pd.DataFrame, weekly_df: pd.DataFrame,
                        ema_period: int = 20,
                        vol_window: int = 20,
                        hs300_weekly: pd.DataFrame = None,
                        residual_reg_window: int = 12,
                        residual_mom_window: int = 12,
                        f7_window: int = 20,
                        f7_lookback: int = 250,
                        f7_min_days: int = 60,
                        f7_sigma_floor: float = 0.01) -> dict:
    """
    计算一支 ETF 的全部因子
    返回 dict: {f1_ema_dev, f3_volume_ratio (自归一化),
                f5_volatility_z, f1_residual_mom, f7_log_return_dev}
    """
    f1 = factor_ema_deviation(weekly_df, ema_period)
    f3 = factor_volume_ratio_normalized(daily_df, vol_window, norm_window=60)
    if np.isnan(f3):
        f3 = factor_volume_ratio(daily_df, vol_window)
    f5 = factor_volatility_zscore(daily_df, vol_window=20, lookback=60)
    f1r = factor_residual_momentum(weekly_df, hs300_weekly,
                                   reg_window=residual_reg_window,
                                   mom_window=residual_mom_window)
    f7 = factor_log_return_deviation(daily_df, window=f7_window,
                                      lookback=f7_lookback,
                                      min_days=f7_min_days,
                                      sigma_floor=f7_sigma_floor)
    return {
        "f1_ema_dev": f1,
        "f3_volume_ratio": f3,
        "f5_volatility_z": f5,
        "f1_residual_mom": f1r,
        "f7_log_return_dev": f7,
    }


def normalize_cross_section(scores: pd.Series, method: str = "percentile_rank") -> pd.Series:
    """
    [已弃用] 截面标准化：将 N 支 ETF 的原始因子值标准化到 0-100
    保留此函数仅为向后兼容，新代码应使用连续映射函数。
    """
    if method == "percentile_rank":
        return scores.rank(pct=True) * 100
    elif method == "z_score":
        mean, std = scores.mean(), scores.std()
        if std == 0:
            return pd.Series(50.0, index=scores.index)
        z = (scores - mean) / std
        return np.clip((z + 3) / 6 * 100, 0, 100)
    elif method == "min_max":
        min_val, max_val = scores.min(), scores.max()
        if max_val == min_val:
            return pd.Series(50.0, index=scores.index)
        return (scores - min_val) / (max_val - min_val) * 100
    else:
        raise ValueError(f"Unknown normalization method: {method}")


# ============================================================
# 连续映射函数（替代截面标准化）
# 每个因子独立映射到 [0, 1] 的绝对分数，保留原始数据的连续性和极端性。
# ============================================================

def map_f1(ema_dev_pct: float, sensitivity: float = 8.0) -> float:
    """
    F1 EMA 偏离度 → sigmoid 映射
    ema_dev_pct: 偏离度百分比，如 +5.2 或 -3.8
    sensitivity: sigmoid 响应尺度，越小越敏感（默认8，即±8%偏离对应~0.27/0.73）

    特性：
      ema_dev = 0 → 0.5（恰好在均线）
      ema_dev = +sensitivity → ~0.73（高于均线）
      ema_dev = -sensitivity → ~0.27（低于均线）
      极端偏离自然饱和，不会无限增长
    """
    if np.isnan(ema_dev_pct):
        return np.nan
    return 1.0 / (1.0 + math.exp(-ema_dev_pct / sensitivity))


def map_f1_residual(residual_mom_pct: float, sensitivity: float = 5.0) -> float:
    """
    残差动量 → sigmoid 映射
    residual_mom_pct: 残差动量百分比，如 +3.5 或 -2.1
    sensitivity: sigmoid 响应尺度（默认5，即±5%残差动量对应~0.27/0.73）

    与 map_f1 共享 sigmoid 结构，但 sensitivity 更小：
    残差动量的典型量级比 EMA 偏离度小（已剥离 beta），需要更敏感的映射。
    正残差=持续跑赢→高分，负残差=持续跑输→低分。
    """
    if np.isnan(residual_mom_pct):
        return np.nan
    return 1.0 / (1.0 + math.exp(-residual_mom_pct / sensitivity))


def map_f3(ratio: float, sensitivity: float = 1.0) -> float:
    """
    F3 方向性量比 → log+sigmoid 映射

    ratio: 上涨日成交额均值 / 下跌日成交额均值
    sensitivity: sigmoid 响应尺度（默认 1.0）

    新设计（取代旧的 1-exp(-x) 指数饱和）：
      - 先 log 变换让 ratio 的 0~10 范围更线性
      - 再 sigmoid 映射到 [0, 1]
      - 高位（ratio > 5）不再饱和锁死，能继续拉伸

    对照旧实现的差异（sensitivity=1.0）：
      ratio=0.5 → 0.34（旧:0.39）  量缩
      ratio=1.0 → 0.50（旧:0.63）  持平
      ratio=2.0 → 0.66（旧:0.86）  温和放量
      ratio=3.0 → 0.74（旧:0.95）  显著放量
      ratio=5.0 → 0.83（旧:0.99）  爆量
      ratio=10.0 → 0.91（旧:1.00） 极端爆量
    """
    if np.isnan(ratio):
        return np.nan
    if ratio <= 0:
        return 0.0

    # log1p 变换：ratio=1 → 0，ratio=2 → 0.69，ratio=10 → 2.4
    # 对 ratio<1 的区间用对称的负 log（让 ratio=0.5 ≈ -0.69）
    if ratio >= 1.0:
        log_r = math.log1p(ratio - 1)
    else:
        log_r = -math.log1p(1.0 / ratio - 1)

    return 1.0 / (1.0 + math.exp(-log_r / sensitivity))


def map_f4(val_score: float, regime: str = "choppy_range") -> float:
    """
    F4 估值因子 → regime-aware 映射

    val_score: [0, 100]（100 - 历史百分位），低估=高分
    regime: 当前市场状态（来自 detect_market_regime）

    核心设计：F4 是"价值反转"角色 ——
      - 在熊市底部/板块轮动时有效（低估值标的修复弹性大）
      - 在成长牛市/震荡市时弃权（估值与基本面脱钩）

    regime multiplier:
      bear_bottom:      1.5  → 放大（F4 最佳时刻）
      sector_rotation:  1.3  → 放大（价值股轮动中）
      choppy_range:     1.0  → 正常
      bear_trend:       0.8  → 弱化（还在跌，低估值可能继续跌）
      bull_trend:       0.3  → 几乎弃权（成长牛市，估值不重要）
    """
    if np.isnan(val_score):
        return np.nan

    base = np.clip(val_score / 100.0, 0.0, 1.0)

    regime_mult = {
        "bear_bottom":      1.5,
        "sector_rotation":  1.3,
        "choppy_range":     1.0,
        "bear_trend":       0.8,
        "bull_trend":       0.3,
    }.get(regime, 1.0)

    if regime_mult < 0.5:
        # 不利 regime：F4 弃权，输出向 0.5（中性）收缩
        return 0.5 + (base - 0.5) * regime_mult
    else:
        # 有利 regime：按 multiplier 放大 F4 影响力
        return min(1.0, base * regime_mult)


def composite_score(factors_df: pd.DataFrame, weights: dict,
                    bias_map: dict, sensitivity: dict = None,
                    norm_method: str = "continuous",
                    regime: str = None) -> pd.Series:
    """
    合成综合分（连续映射版）
    factors_df: index=ETF代码, columns=[f1_ema_dev, f3_volume_ratio, ...]
    weights: {ema_deviation: 0.30, volume_ratio: 0.30, ...}
    bias_map: {code: bonus} 如 {"512400": 0.04, "513120": 0.04, "512070": 0.04}
    sensitivity: {f1: 8.0, f3: 1.5, f7: 1.0} 映射函数参数
    norm_method: "continuous"（默认，使用映射函数）或 "percentile_rank"（旧方法，已弃用）

    返回：pd.Series，值域 [0, 1]（加 bias 后可能略超 1）
    """
    if sensitivity is None:
        sensitivity = {}

    f1_sens = sensitivity.get("f1", 8.0)
    f3_sens = sensitivity.get("f3", 1.0)

    if norm_method == "continuous":
        mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
        mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

        w1 = weights.get("ema_deviation", 0.40)
        w3 = weights.get("volume_ratio", 0.55)

        score = mapped_f1 * w1 + mapped_f3 * w3

        # F4 估值因子（如果 factors_df 中有 f4_valuation 列）
        w4 = weights.get("valuation", 0.00)
        if w4 > 0 and "f4_valuation" in factors_df.columns:
            mapped_f4 = factors_df["f4_valuation"].apply(lambda v: map_f4(v, regime or "choppy_range"))
            score = score + mapped_f4 * w4

        # F5 波动率因子（如果 factors_df 中有 f5_volatility_z 列）
        w5 = weights.get("volatility", 0.0)
        if w5 > 0 and "f5_volatility_z" in factors_df.columns:
            f5_sens = sensitivity.get("f5", 1.0)
            mapped_f5 = factors_df["f5_volatility_z"].apply(lambda v: map_f5(v, f5_sens))
            score = score + mapped_f5 * w5

        # F7 对数收益偏离因子（如果 factors_df 中有 f7_log_return_dev 列）
        w7 = weights.get("log_return_deviation", 0.0)
        if w7 > 0 and "f7_log_return_dev" in factors_df.columns:
            f7_t = sensitivity.get("f7_t", 7.0)
            f7_k = sensitivity.get("f7_k", 3.0)
            mapped_f7 = factors_df["f7_log_return_dev"].apply(lambda v: map_f7(v, t=f7_t, k=f7_k))
            # F7 NaN → 该 ETF 跳过 F7 贡献（得分为中性 0.5，即不加不减）
            mapped_f7 = mapped_f7.fillna(0.5)
            score = score + mapped_f7 * w7
    else:
        # 旧方法：截面标准化（已弃用，保留兼容）
        norm_f1 = normalize_cross_section(factors_df["f1_ema_dev"], norm_method) / 100.0
        norm_f3 = normalize_cross_section(factors_df["f3_volume_ratio"], norm_method) / 100.0

        w1 = weights.get("ema_deviation", 0.40)
        w3 = weights.get("volume_ratio", 0.55)

        score = norm_f1 * w1 + norm_f3 * w3

        w4 = weights.get("valuation", 0.00)
        if w4 > 0 and "f4_valuation" in factors_df.columns:
            norm_f4 = normalize_cross_section(factors_df["f4_valuation"], norm_method) / 100.0
            score = score + norm_f4 * w4

    # 偏好加成（0-1 尺度）
    for code, bonus in bias_map.items():
        if code in score.index:
            score[code] += bonus

    return score


def confidence_function(score: float, dead_zone: float = 0.25, full_zone: float = 0.65) -> float:
    """
    信心函数（分段平方）
    尺度：[0, 1]（与连续映射后的综合分一致）

    score < dead_zone → 0
    dead_zone <= score < full_zone → ((score - dead_zone) / (full_zone - dead_zone))²
    score >= full_zone → 1
    """
    if score < dead_zone:
        return 0.0
    elif score >= full_zone:
        return 1.0
    else:
        t = (score - dead_zone) / (full_zone - dead_zone)
        return t * t


def infer_regime_from_nav(nav_history: list, window: int = 10,
                          threshold: float = 0.05) -> str:
    """
    从组合 NAV 历史推断市场状态。

    注意：nav_history 是按 rebalance 周期采样的（周频约1次/周），
    window 单位是 rebalance 期数而非交易日。

    bull_trend: 近 window 期 NAV 上涨 ≥ threshold
    bear_trend: 近 window 期 NAV 下跌 ≥ threshold
    choppy_range: 其他
    """
    if len(nav_history) < window:
        return "choppy_range"
    recent = nav_history[-window:]
    change = (recent[-1] - recent[0]) / recent[0]
    if change >= threshold:
        return "bull_trend"
    elif change <= -threshold:
        return "bear_trend"
    return "choppy_range"


def regime_confidence(regime: str, breadth: float, clarity: float,
                      drawdown_pct: float,
                      regime_base: dict = None,
                      breadth_weight: float = 0.5,
                      clarity_threshold: float = 0.10,
                      dd_sensitivity: float = 0.5) -> float:
    """
    基于市场状态的仓位调制函数。输出 [0, 1] 代表建议总仓位比例。

    regime: bull_trend / choppy_range / bear_trend
    breadth: 市场广度 (composite > median 的比例), [0, 1]
    clarity: Top-N 分数集中度 (top_n.std()), [0, ~0.3]
    drawdown_pct: 当前回撤深度 (负数), 如 -0.12 = -12%
    regime_base: {regime_name: base_position} 映射
    breadth_weight: 广度因子权重 (0=忽略, 1=全量)
    clarity_threshold: 集中度达到此值时 clarity_factor=1.0
    dd_sensitivity: 回撤敏感度 (0=忽略回撤)
    """
    if regime_base is None:
        regime_base = {"bull_trend": 0.90, "choppy_range": 0.55, "bear_trend": 0.25}
    base = regime_base.get(regime, 0.55)

    # breadth=1 → factor=1.0, breadth=0 → factor=(1-breadth_weight)
    breadth_factor = 1.0 - breadth_weight * (1.0 - breadth)
    clarity_factor = min(1.0, clarity / clarity_threshold) if clarity_threshold > 0 else 1.0
    dd_factor = max(0.3, 1.0 + drawdown_pct * dd_sensitivity) if dd_sensitivity > 0 else 1.0

    return min(0.95, base * breadth_factor * clarity_factor * dd_factor)


def dd_trigger_confidence(drawdown_pct: float,
                          dd_trigger_level: float = -0.05,
                          dd_floor: float = 0.35,
                          dd_max: float = -0.30) -> float:
    """
    Drawdown-triggered position sizing.

    核心思想：默认满仓，只在回撤超过阈值时才减仓。
    直接对应 S2→B1（主跌段）的识别——主跌段回撤加深，
    其他阶段（B1→B2, B2→S1, S1→S2）回撤都小或为正。

    - drawdown_pct < dd_trigger_level → 开始线性减仓
    - drawdown_pct >= dd_trigger_level → 满仓 0.95
    - drawdown_pct 到 dd_max 时 → 降至 dd_floor
    """
    if drawdown_pct >= dd_trigger_level:
        return 0.95
    # 从 trigger 到 max，线性从 0.95 降到 dd_floor
    ratio = (drawdown_pct - dd_trigger_level) / (dd_max - dd_trigger_level)
    ratio = min(1.0, max(0.0, ratio))
    return 0.95 - (0.95 - dd_floor) * ratio


def momentum_crash_confidence(nav_history: list,
                               crash_window: int = 2,
                               crash_threshold: float = -0.03,
                               recovery_threshold: float = -0.01,
                               full_pos: float = 0.95,
                               crash_pos: float = 0.20,
                               recovery_pos: float = 0.70,
                               recovery_dd_level: float = -0.05) -> float:
    """
    基于NAV动量崩溃的仓位控制。

    核心思想：默认满仓，只在动量崩溃（S2）时快速减仓。

    S2 检测：近 crash_window 期 NAV 收益率 < crash_threshold → 减到 crash_pos
    B1 检测：动量企稳（2周收益 > recovery_threshold）且仍在回撤中 → 加到 recovery_pos
    回归满仓：回撤恢复到 recovery_dd_level 以上 → full_pos

    参数：
      crash_window: 动量回看期数（rebalance 周期数，2=约2周）
      crash_threshold: 2周收益率低于此值视为崩盘（S2）
      recovery_threshold: 2周收益率高于此值视为企稳（B1）
      full_pos: 正常仓位
      crash_pos: S2时仓位（地板）
      recovery_pos: B1时仓位（半仓恢复）
      recovery_dd_level: 回撤恢复到此水平以上回归满仓
    """
    if len(nav_history) < crash_window + 1:
        return full_pos

    # 2-week momentum
    momentum = (nav_history[-1] - nav_history[-crash_window]) / nav_history[-crash_window]
    # Current drawdown from peak
    peak = max(nav_history)
    current_dd = (nav_history[-1] - peak) / peak

    # S2: momentum crash → floor
    if momentum < crash_threshold:
        return crash_pos

    # B1: momentum recovering while still in drawdown
    if momentum > recovery_threshold and current_dd < recovery_dd_level:
        return recovery_pos

    # Normal: full position
    return full_pos


def ma_trend_confidence(hs300_above_ma: bool,
                        bull_pos: float = 0.95,
                        bear_pos: float = 0.10) -> float:
    """
    基于沪深300周线MA20趋势的仓位控制。

    极简逻辑：沪深300在周线MA20上方 → bull_pos，下方 → bear_pos。
    本质是趋势跟踪：MA20上方=多头排列=持有，下方=空头排列=离场。

    参数：
      hs300_above_ma: 当期沪深300收盘是否在周线MA20上方
      bull_pos: 趋势向上时仓位
      bear_pos: 趋势向下时仓位
    """
    return bull_pos if hs300_above_ma else bear_pos


def factor_volatility_zscore(daily_df: pd.DataFrame,
                              vol_window: int = 20,
                              lookback: int = 60) -> float:
    """
    F5: 波动率Z-score因子

    计算逻辑：
      1. 滚动波动率 = 日收益率标准差 × sqrt(252) 年化
      2. 相对Z-score = (当前波动率 - 近期均值) / 近期标准差

    交易含义：
      - z << 0：波动率显著低于近期平均水平 → 市场平静 → 高分（偏好低波）
      - z >> 0：波动率显著高于近期平均水平 → 市场动荡 → 低分（规避高波）
      - z ≈ 0：波动率正常 → 中性
    """
    if daily_df is None or len(daily_df) < lookback + vol_window + 5:
        return np.nan

    close = daily_df["close"].astype(float)
    returns = close.pct_change().dropna()

    if len(returns) < lookback + vol_window:
        return np.nan

    # 计算滚动年化波动率
    rolling_vol = returns.rolling(window=vol_window).std() * np.sqrt(252)
    rolling_vol = rolling_vol.dropna()

    if len(rolling_vol) < lookback + 1:
        return np.nan

    current_vol = rolling_vol.iloc[-1]
    hist_vol = rolling_vol.iloc[-lookback:]
    vol_mean = hist_vol.mean()
    vol_std = hist_vol.std()

    if np.isnan(current_vol) or np.isnan(vol_mean) or vol_std == 0:
        return np.nan

    z_score = (current_vol - vol_mean) / vol_std
    return float(np.clip(z_score, -3.0, 3.0))


def map_f5(vol_z: float, sensitivity: float = 1.0) -> float:
    """
    F5 波动率Z-score → sigmoid映射（反向）

    vol_z: 波动率Z-score（来自 factor_volatility_zscore）
    sensitivity: 响应尺度，默认1.0

    特性：
      vol_z = 0   → 0.5（波动率正常）
      vol_z = -1  → ~0.73（低波偏好）
      vol_z = -2  → ~0.88（显著低波）
      vol_z = +1  → ~0.27（高波规避）
      vol_z = +2  → ~0.12（显著高波）

    设计意图：低波动率时给高分（偏好持仓），高波动率时给低分（规避风险）。
    """
    if np.isnan(vol_z):
        return np.nan
    # 反向：-z，低波→高分
    return 1.0 / (1.0 + math.exp(vol_z / sensitivity))


def factor_log_return_deviation(daily_df: pd.DataFrame,
                                 window: int = 20,
                                 lookback: int = 250,
                                 min_days: int = 60,
                                 sigma_floor: float = 0.01) -> float:
    """
    F7: 对数收益偏离因子（Log Return Deviation）

    20 日累计对数收益相对 250 日历史的 Z-score 偏离度。
    连续数值因子，替代 F6（动能衰竭惩罚）的离散条件触发。

    计算：
      1. 日对数收益率 r_t = ln(close_t / close_{t-1})
      2. 20 日累计对数收益 = sum(r_t, 20d)
      3. 历史窗口 μ/σ → Z = (当前值 - μ) / σ

    短历史策略：
      - < min_days(60) → NaN（该 ETF 跳过 F7）
      - 60–250 日 → 扩展窗口（全部可用数据）+ σ 地板
      - ≥ 250 日 → 固定滚动窗口

    Z ≥ +2σ → 极端高估，低分（左侧逃顶）
    Z ≤ -2σ → 极端超跌，高分（左侧抄底）
    Z ∈ ±1σ → 中性，交还 F1/F3 主导
    """
    if daily_df is None or len(daily_df) < window + min_days:
        return np.nan

    close = daily_df["close"].astype(float).where(lambda s: s > 0)
    log_ret = np.log(close / close.shift(1))
    log_ret = log_ret.dropna()

    if len(log_ret) < window:
        return np.nan

    # 20 日累计对数收益序列
    cum_log_ret = log_ret.rolling(window=window).sum()
    cum_log_ret = cum_log_ret.dropna()

    if len(cum_log_ret) < 2:
        return np.nan

    current = cum_log_ret.iloc[-1]

    # 窗口策略
    n = len(cum_log_ret)
    if n < min_days:
        return np.nan
    elif n < lookback:
        hist = cum_log_ret  # 扩展窗口：全部可用数据
    else:
        hist = cum_log_ret.iloc[-lookback:]  # 固定滚动窗口

    mu = hist.mean()
    sigma = hist.std()
    sigma = max(sigma, sigma_floor)

    if sigma == 0:
        return 0.0

    z = (current - mu) / sigma
    return float(z)


def map_f7(z_score: float, t: float = 7.0, k: float = 3.0) -> float:
    """
    F7 Z-score -> 分段映射：|Z|≤k 幂函数，|Z|>k 切线线性外延。

    z_score: 对数收益偏离 Z-score
    t: 幂次（≥1），控制两端加速程度，默认 7
    k: 标准差倍数阈值 / 切线切换点，默认 3.0

    特性（t=11, k=3）：
      Z =  0   → 0.50（中性）
      Z = +3   → 0.00（幂函数边界）
      Z = -3   → 1.00（幂函数边界）
      Z = +9   → -11.0（切线外延，约 −1.65 对 composite 的贡献）
      Z = -9   → +12.0（切线外延）

    设计决策：
      |Z| ≤ k：幂函数 (z/k)^t，在 ±kσ 附近加速，提供非线性区分
      |Z| > k：切线 f(z) = f(k) + f'(k)·(z−k)，保持线性区分但截断爆炸增长
      切线斜率 = −t/(2k)，一阶连续，在切换点平滑过渡
    """
    if np.isnan(z_score):
        return np.nan
    abs_z = abs(z_score)
    if abs_z <= k:
        ratio = abs_z / k
        powered = math.copysign(1.0, z_score) * (ratio ** t)
        return 0.5 + 0.5 * (-powered)
    else:
        slope = -t / (2.0 * k)
        if z_score > 0:
            return slope * (z_score - k)
        else:
            return 1.0 + slope * (z_score + k)

def allocate_positions(scores: pd.Series, max_holdings: int = 6,
                       dead_zone: float = 0.25, full_zone: float = 0.65,
                       step: float = 0.05) -> pd.Series:
    """
    从综合分到仓位分配
    尺度：综合分 [0, 1]，dead_zone/full_zone [0, 1]

    1. Top-N 选股
    2. 得分加权
    3. × 信心函数
    4. 离散化到 step 档位
    """
    # Top-N
    top = scores.nlargest(max_holdings)

    # 信心系数
    confidence = top.apply(lambda s: confidence_function(s, dead_zone, full_zone))

    # 得分加权（相对权重）
    if top.sum() == 0:
        relative_weight = pd.Series(0.0, index=top.index)
    else:
        relative_weight = top / top.sum()

    # 缩放因子：平均信心 × 1.2，上限 95%
    avg_confidence = confidence.mean()
    scale = min(0.95, avg_confidence * 1.2)
    position = relative_weight * scale

    # Floor-discretize: always round down, then fill gap to highest-score ETFs
    position = (position / step).apply(math.floor) * step
    position = position.clip(lower=0)

    # Fill gap: distribute remaining steps to ETFs with highest scores
    disc_sum = position.sum()
    if disc_sum < scale - step * 0.01:
        gap_steps = round((scale - disc_sum) / step)
        if gap_steps > 0:
            # top.index is already sorted by score (nlargest)
            top_up = position.index[:min(gap_steps, len(position))]
            for code in top_up:
                position[code] += step

    return position
