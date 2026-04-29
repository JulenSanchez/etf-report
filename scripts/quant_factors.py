"""
REQ-177 M1.1: 三因子计算模块
输入：日线 DataFrame (date, open, high, low, close, volume)
     周线 DataFrame (同上)
输出：三因子连续值

因子：
  F1: 周线 EMA 偏离度 = (close - EMA_N) / EMA_N
  F2: 日线 RSI(14) 趋势自适应变换
  F3: 方向性量比 = mean(上涨日volume) / mean(下跌日volume), N日滚动

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


def factor_ema_deviation(weekly_df: pd.DataFrame, ema_period: int = 20) -> float:
    """
    F1: 周线 EMA 偏离度
    返回最新一周的 (close - EMA) / EMA × 100 (百分比)
    """
    if weekly_df is None or len(weekly_df) < ema_period:
        return np.nan

    close = weekly_df["close"].astype(float)
    ema = calc_ema(close, span=ema_period)
    deviation = (close.iloc[-1] - ema.iloc[-1]) / ema.iloc[-1] * 100
    return deviation


def factor_rsi_adaptive(daily_df: pd.DataFrame, rsi_period: int = 14,
                        weekly_df: pd.DataFrame = None, ema_period: int = 20,
                        rsi_window: int = 20) -> float:
    """
    F2: RSI 双通道异动检测器

    通道 1（相对）: z-score vs 近期基线
      - 检测"RSI 突然偏离自身近期均值"
      - 问题：持续趋势中，均值跟随 RSI → z ≈ 0 → 沉默

    通道 2（绝对）: RSI 距中性 50 的距离
      - 检测"RSI 处于绝对极端水平，无论趋势如何"
      - 缩放: ÷15（RSI=35 → -1.0, RSI=20 → -2.0, RSI=65 → +1.0, RSI=80 → +2.0）
      - 比 z-score 更保守，避免牛市中 RSI=65 的误触发

    合成: 取两个通道中绝对值更大的信号。
      - 趋势中 z≈0 但 RSI 极端时，绝对通道接管
      - 突然异动但绝对水平不高时，相对通道主导

    输出: z-like score, 含义与 map_f2 一致:
      << 0 → 超卖异动 → 博反弹（映射高分）
      >> 0 → 超买异动 → 逃顶（映射低分）
      ≈ 0 → 无显著异动 → 中性（死区内不投票）

    注意：weekly_df / ema_period 参数保留以维持调用兼容，新逻辑不再使用它们
    """
    if daily_df is None or len(daily_df) < rsi_period + rsi_window + 5:
        return np.nan

    close = daily_df["close"].astype(float)
    rsi_series = calc_rsi(close, rsi_period)
    current_rsi = rsi_series.iloc[-1]

    if np.isnan(current_rsi):
        return np.nan

    # 通道 1: 相对 z-score（原有设计）
    recent = rsi_series.iloc[-rsi_window:].dropna()
    if len(recent) < max(5, rsi_window // 2):
        return np.nan
    rsi_mean = recent.mean()
    rsi_std = recent.std()
    sigma_floor = 5.0
    sigma = max(rsi_std, sigma_floor) if not np.isnan(rsi_std) else sigma_floor
    rel_z = (current_rsi - rsi_mean) / sigma

    # 通道 2: 绝对 RSI 位置
    # ÷15 缩放: RSI=35 → -1.0, RSI=65 → +1.0（dead_zone=1.0 时刚好在边界）
    abs_z = (current_rsi - 50.0) / 15.0

    # 合成: 取更极端的信号
    if abs(rel_z) >= abs(abs_z):
        composite = rel_z
    else:
        composite = abs_z

    return float(np.clip(composite, -3.0, 3.0))


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


def compute_all_factors(daily_df: pd.DataFrame, weekly_df: pd.DataFrame,
                        ema_period: int = 20, rsi_period: int = 14,
                        vol_window: int = 20) -> dict:
    """
    计算一支 ETF 的全部因子 (F1-F5)
    返回 dict: {f1_ema_dev, f2_rsi_adaptive, f3_volume_ratio, f5_volatility_z}
    """
    f1 = factor_ema_deviation(weekly_df, ema_period)
    f2 = factor_rsi_adaptive(daily_df, rsi_period, weekly_df, ema_period)
    f3 = factor_volume_ratio(daily_df, vol_window)
    f5 = factor_volatility_zscore(daily_df, vol_window=20, lookback=60)
    return {
        "f1_ema_dev": f1,
        "f2_rsi_adaptive": f2,
        "f3_volume_ratio": f3,
        "f5_volatility_z": f5,
    }


def normalize_cross_section(scores: pd.Series, method: str = "percentile_rank") -> pd.Series:
    """
    [已弃用] 截面标准化：将 N 支 ETF 的原始因子值标准化到 0-100
    保留此函数仅为向后兼容，新代码应使用 map_f1 / map_f2 / map_f3 / map_f4。
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


def map_f2(rsi_z: float, dead_zone: float = 1.0) -> float:
    """
    F2 RSI 异动 → 死区+饱和映射

    rsi_z: RSI 偏离 z-score（来自 factor_rsi_adaptive）
    dead_zone: 死区半宽，|z| < dead_zone 时输出 0.5（中性，不投票）

    特性：
      |z| < dead_zone   → 0.5 (中性，让 F1/F4 主导)
      z << -dead_zone   → 趋向 1.0 (博反弹，鼓励买入)
      z >>  dead_zone   → 趋向 0.0 (逃顶，鼓励卖出)

    饱和速度：z 超过死区后 1 个 sigma → 输出约 0.85/0.15；2 sigma → 约 0.94/0.06

    设计意图：让 F2 在 ETF "自身热度涌现" 时输出极值，平时沉默。
    """
    if np.isnan(rsi_z):
        return np.nan

    if abs(rsi_z) < dead_zone:
        return 0.5

    # 死区外的"超出量"
    overshoot = abs(rsi_z) - dead_zone

    # 用 1 - exp(-x) 饱和函数，决定偏离 0.5 的幅度
    # overshoot=1.0 → magnitude≈0.63；overshoot=2.0 → magnitude≈0.86
    magnitude = 1.0 - math.exp(-overshoot)

    if rsi_z < 0:
        return 0.5 + 0.5 * magnitude  # 博反弹，向 1.0 趋近
    return 0.5 - 0.5 * magnitude      # 逃顶，向 0.0 趋近


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
        # 跟 F2 死区思想一致：沉默 ≠ 反对，沉默 = 弃权
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
    factors_df: index=ETF代码, columns=[f1_ema_dev, f2_rsi_adaptive, f3_volume_ratio]
    weights: {ema_deviation: 0.30, rsi_adaptive: 0.25, volume_ratio: 0.30, valuation: 0.15}
    bias_map: {code: bonus} 如 {"512400": 0.04, "513120": 0.04, "512070": 0.04}
    sensitivity: {f1: 8.0, f3: 1.5} 映射函数参数
    norm_method: "continuous"（默认，使用映射函数）或 "percentile_rank"（旧方法，已弃用）

    返回：pd.Series，值域 [0, 1]（加 bias 后可能略超 1）
    """
    if sensitivity is None:
        sensitivity = {}

    f1_sens = sensitivity.get("f1", 8.0)
    f3_sens = sensitivity.get("f3", 1.0)

    if norm_method == "continuous":
        # 连续映射：每个因子独立映射到 [0, 1] 的绝对分数
        mapped_f1 = factors_df["f1_ema_dev"].apply(lambda v: map_f1(v, f1_sens))
        mapped_f2 = factors_df["f2_rsi_adaptive"].apply(map_f2)
        mapped_f3 = factors_df["f3_volume_ratio"].apply(lambda v: map_f3(v, f3_sens))

        w1 = weights.get("ema_deviation", 0.30)
        w2 = weights.get("rsi_adaptive", 0.25)
        w3 = weights.get("volume_ratio", 0.30)

        score = mapped_f1 * w1 + mapped_f2 * w2 + mapped_f3 * w3

        # F4 估值因子（如果 factors_df 中有 f4_valuation 列）
        w4 = weights.get("valuation", 0.15)
        if w4 > 0 and "f4_valuation" in factors_df.columns:
            mapped_f4 = factors_df["f4_valuation"].apply(lambda v: map_f4(v, regime or "choppy_range"))
            score = score + mapped_f4 * w4

        # F5 波动率因子（如果 factors_df 中有 f5_volatility_z 列）
        w5 = weights.get("volatility", 0.0)
        if w5 > 0 and "f5_volatility_z" in factors_df.columns:
            f5_sens = sensitivity.get("f5", 1.0)
            mapped_f5 = factors_df["f5_volatility_z"].apply(lambda v: map_f5(v, f5_sens))
            score = score + mapped_f5 * w5
    else:
        # 旧方法：截面标准化（已弃用，保留兼容）
        norm_f1 = normalize_cross_section(factors_df["f1_ema_dev"], norm_method) / 100.0
        norm_f2 = normalize_cross_section(factors_df["f2_rsi_adaptive"], norm_method) / 100.0
        norm_f3 = normalize_cross_section(factors_df["f3_volume_ratio"], norm_method) / 100.0

        w1 = weights.get("ema_deviation", 0.30)
        w2 = weights.get("rsi_adaptive", 0.25)
        w3 = weights.get("volume_ratio", 0.30)

        score = norm_f1 * w1 + norm_f2 * w2 + norm_f3 * w3

        w4 = weights.get("valuation", 0.15)
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

    与F2的区别：
      - F2检测RSI异动（价格动量异常）
      - F5检测波动率异动（价格振幅异常）
      - 两者互补：高RSI不一定高波动，高波动不一定高RSI
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

    # 离散化到 step
    position = (position / step).round() * step
    position = position.clip(lower=0)

    return position
