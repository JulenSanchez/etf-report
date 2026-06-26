# gam-1 参数优化报告
**日期**: 2026-06-23 19:46
**策略**: bayesian, 13 trials
**优化目标**: annual_return

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 1Y | annual_return | 197.4755 | 228.3898 | +30.9143 |
| 3Y | annual_return | 67.1239 | 71.3751 | +4.2512 |
| 6Y | annual_return | 47.1754 | 47.4673 | +0.2919 |

## Top 10（按 annual_return 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 0.0000 | 0.0000 | 0.0000 | 1.0754 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=60, w3=26, w7=14 |
| 2 | 0.0000 | 0.0000 | 0.0000 | 0.9992 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=56, w3=28, w7=16 |
| 3 | 0.0000 | 0.0000 | 0.0000 | 0.9634 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=55, w3=29, w7=16 |
| 4 | 0.0000 | 0.0000 | 0.0000 | 0.9296 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=56, w3=29, w7=15 |
| 5 | 0.0000 | 0.0000 | 0.0000 | 0.8913 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=57, w3=28, w7=15 |
| 6 | 0.0000 | 0.0000 | 0.0000 | 0.8627 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=57, w3=27, w7=16 |
| 7 | 0.0000 | 0.0000 | 0.0000 | 0.8187 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=57, w3=28, w7=15 |
| 8 | 0.0000 | 0.0000 | 0.0000 | 0.8168 | 0.0000 | concentration=4.3, f1_ema_period=4, score_band=2.8, w1=58, w3=27, w7=15 |
| 9 | 0.0000 | 0.0000 | 0.0000 | 0.7978 | 0.0000 | concentration=4.3, f1_ema_period=3, score_band=2.8, w1=63, w3=22, w7=15 |
| 10 | 0.0000 | 0.0000 | 0.0000 | 0.7720 | 0.0000 | concentration=4.3, f1_ema_period=3, score_band=2.8, w1=53, w3=32, w7=15 |

## 各周期最佳

**1Y** (2025-06-23 ~ 2026-06-23):
- Total: +228.39%  Annual: +228.39%  MDD: -17.52%
- Sharpe: 3.09  Sortino: 4.67  Calmar: 13.04
- Trades: 0/0
- Params: {"account_mode": "cash", "bias": 0.0, "c_sensitivity": 60.0, "concentration": 4.3, "conf_type": "ma_trend", "dead_zone": 17, "disc_step": 0.11, "execution_timing": "same_close", "f1_active_days": 1, "f1_ema_period": 4, "f1_sensitivity": 9.8, "f3_sensitivity": 4.29, "f3_vol_window": 36, "f7_k": 3.4200000000000004, "f7_t": 21.85, "f7_window": 20, "full_zone": 65, "ma_bear_pos": 0.73, "ma_bull_pos": 1.1300000000000001, "ma_direction_confirm": true, "ma_trend_period": 28, "max_gross_exposure": 1.4, "max_holdings": 4, "rebalance_freq": "daily", "score_band": 2.8, "w1": 60, "w3": 26, "w7": 14}

**3Y** (2023-06-24 ~ 2026-06-23):
- Total: +401.83%  Annual: +71.38%  MDD: -18.44%
- Sharpe: 1.79  Sortino: 2.83  Calmar: 3.87
- Trades: 0/0
- Params: {"account_mode": "cash", "bias": 0.0, "c_sensitivity": 60.0, "concentration": 4.3, "conf_type": "ma_trend", "dead_zone": 17, "disc_step": 0.11, "execution_timing": "same_close", "f1_active_days": 1, "f1_ema_period": 4, "f1_sensitivity": 9.8, "f3_sensitivity": 4.29, "f3_vol_window": 36, "f7_k": 3.4200000000000004, "f7_t": 21.85, "f7_window": 20, "full_zone": 65, "ma_bear_pos": 0.73, "ma_bull_pos": 1.1300000000000001, "ma_direction_confirm": true, "ma_trend_period": 28, "max_gross_exposure": 1.4, "max_holdings": 4, "rebalance_freq": "daily", "score_band": 2.8, "w1": 60, "w3": 26, "w7": 14}

**6Y** (2020-06-24 ~ 2026-06-23):
- Total: +928.43%  Annual: +47.47%  MDD: -18.44%
- Sharpe: 1.37  Sortino: 2.08  Calmar: 2.57
- Trades: 0/0
- Params: {"account_mode": "cash", "bias": 0.0, "c_sensitivity": 60.0, "concentration": 4.3, "conf_type": "ma_trend", "dead_zone": 17, "disc_step": 0.11, "execution_timing": "same_close", "f1_active_days": 1, "f1_ema_period": 4, "f1_sensitivity": 9.8, "f3_sensitivity": 4.29, "f3_vol_window": 36, "f7_k": 3.4200000000000004, "f7_t": 21.85, "f7_window": 20, "full_zone": 65, "ma_bear_pos": 0.73, "ma_bull_pos": 1.1300000000000001, "ma_direction_confirm": true, "ma_trend_period": 28, "max_gross_exposure": 1.4, "max_holdings": 4, "rebalance_freq": "daily", "score_band": 2.8, "w1": 60, "w3": 26, "w7": 14}

## Promotion 建议

**Ready to promote**: 在所有周期上，最优 trial 的优化目标不低于基线。
