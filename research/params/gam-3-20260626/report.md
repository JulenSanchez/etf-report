# gam-3 参数优化报告
**日期**: 2026-06-26 11:39
**策略**: bayesian, 19 trials
**优化目标**: annual_return

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 6Y | annual_return | 33.5923 | 50.7715 | +17.1792 |

## Top 10（按 annual_return 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 0.0000 | 0.0000 | 0.0000 | 1.5114 | 0.0000 | concentration=11.8, f1_ema_period=9, score_band=4.1, w1=24, w3=45, w7=31 |
| 2 | 0.0000 | 0.0000 | 0.0000 | 1.4503 | 0.0000 | concentration=10.3, f1_ema_period=5, score_band=3.1, w1=24, w3=28, w7=48 |
| 3 | 0.0000 | 0.0000 | 0.0000 | 1.1213 | 0.0000 | concentration=10.1, f1_ema_period=3, score_band=4.1, w1=22, w3=46, w7=32 |
| 4 | 0.0000 | 0.0000 | 0.0000 | 1.0971 | 0.0000 | concentration=9.9, f1_ema_period=3, score_band=4.1, w1=22, w3=45, w7=33 |
| 5 | 0.0000 | 0.0000 | 0.0000 | 1.0117 | 0.0000 | concentration=13.100000000000001, f1_ema_period=3, score_band=5.6, w1=25, w3=42, w7=33 |
| 6 | 0.0000 | 0.0000 | 0.0000 | 0.9997 | 0.0000 | concentration=11.3, f1_ema_period=5, score_band=4.6, w1=25, w3=44, w7=31 |
| 7 | 0.0000 | 0.0000 | 0.0000 | 0.9705 | 0.0000 | concentration=15.3, f1_ema_period=3, score_band=5.1, w1=24, w3=41, w7=35 |
| 8 | 0.0000 | 0.0000 | 0.0000 | 0.9514 | 0.0000 | concentration=12.3, f1_ema_period=4, score_band=4.6, w1=25, w3=43, w7=32 |
| 9 | 0.0000 | 0.0000 | 0.0000 | 0.9152 | 0.0000 | concentration=10.5, f1_ema_period=3, score_band=4.1, w1=22, w3=45, w7=33 |
| 10 | 0.0000 | 0.0000 | 0.0000 | 0.8182 | 0.0000 | concentration=10.9, f1_ema_period=3, score_band=4.1, w1=21, w3=46, w7=33 |

## 各周期最佳

**6Y** (2020-06-27 ~ 2026-06-26):
- Total: +1070.71%  Annual: +50.77%  MDD: -19.72%
- Sharpe: 1.50  Sortino: 2.15  Calmar: 2.57
- Trades: 0/0
- Params: {"account_mode": "cash", "benchmarks": ["000300"], "c_sensitivity": 144.0, "concentration": 11.8, "conf_type": "ma_trend", "dead_zone": 17, "disc_step": 0.11, "execution_timing": "same_close", "f1_active_days": 1, "f1_ema_period": 9, "f1_sensitivity": 8.9, "f3_sensitivity": 5.4, "f3_vol_window": 17, "f7_k": 3.0, "f7_t": 23.0, "f7_window": 8, "full_zone": 65, "ma_bear_pos": 0.31, "ma_bull_pos": 1.6300000000000001, "ma_direction_confirm": true, "ma_trend_period": 39, "max_gross_exposure": 1.2, "max_holdings": 6, "rebalance_freq": "daily", "score_band": 4.1, "w1": 24, "w3": 45, "w7": 31}

## Promotion 建议

**Ready to promote**: 在所有周期上，最优 trial 的优化目标不低于基线。
