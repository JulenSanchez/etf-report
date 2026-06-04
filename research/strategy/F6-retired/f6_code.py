# Archived from quant_factors.py on 2026-05-26
# F6: Momentum Exhaustion Penalty — deprecated in favor of F7
# See research/strategy/F6-retired/README.md for retirement evidence

def factor_exhaustion_penalty(daily_df: pd.DataFrame,
                              rsi_period: int = 14,
                              rsi_thresh: float = 80.0,
                              drop_thresh: float = 0.025,
                              vol_thresh: float = 1.5,
                              vol_window: int = 20,
                              decay_days: int = 3,
                              base_penalty: float = 0.15) -> float:
    """
    F6：动能衰竭惩罚因子（Momentum Exhaustion Penalty）

    逻辑：前一日RSI高位（≥rsi_thresh），当日出现放量下跌（跌幅≥drop_thresh
    且量比≥vol_thresh），认为动能衰竭，返回惩罚乘数 [0, 1]。
    1.0 = 无惩罚，0.0 = 最大惩罚。

    衰减：触发后惩罚按 decay_days 线性衰减恢复（防止单日假信号永久打压）。
    取最近 decay_days 内最强的一次惩罚后的剩余强度。

    返回：penalty_multiplier ∈ [0.0, 1.0]
      乘以综合分后得到惩罚后分数：score_penalized = score * penalty_multiplier
    """
    if daily_df is None or len(daily_df) < rsi_period + vol_window + 2:
        return 1.0

    df = daily_df.copy()
    df = df.sort_values("date").reset_index(drop=True)

    # RSI (use calc_rsi for consistency — Wilder's EMA, same as chart display)
    rsi = calc_rsi(df["close"], period=rsi_period)

    # 量比
    vol_ma   = df["volume"].rolling(vol_window, min_periods=5).mean()
    vol_ratio = df["volume"] / vol_ma

    # 日涨跌
    ret = df["close"].pct_change()

    # 前日RSI
    rsi_prev = rsi.shift(1)

    # 触发条件
    triggered = (
        (rsi_prev >= rsi_thresh) &
        (ret <= -drop_thresh) &
        (vol_ratio >= vol_thresh)
    )

    # 只看最近 decay_days 日内是否触发（含今日）
    n = len(df)
    window_start = max(0, n - decay_days)
    recent_triggers = triggered.iloc[window_start:]

    if not recent_triggers.any():
        return 1.0

    # 最近触发距今的天数（0=今日触发，1=昨日触发…）
    last_trigger_offset = None
    for i in range(decay_days):
        idx = n - 1 - i
        if idx >= 0 and triggered.iloc[idx]:
            last_trigger_offset = i
            break

    if last_trigger_offset is None:
        return 1.0

    # 惩罚强度：触发当日=base_penalty（最强），线性恢复到1.0
    # offset=0 → base_penalty, offset=decay_days-1 → ~0.8
    recovery = base_penalty + (1.0 - base_penalty) * (last_trigger_offset / decay_days)
    return float(min(1.0, recovery))


