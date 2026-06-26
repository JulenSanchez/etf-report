# gam-3 参数优化报告
**日期**: 2026-06-26 13:31
**策略**: bayesian, 43 trials
**优化目标**: annual_return

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 6Y | annual_return | 33.5923 | 65.5173 | +31.9250 |

## Top 10（按 annual_return 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 0.0000 | 0.0000 | 0.0000 | 1.9504 | 0.0000 | concentration=15.100000000000001, f1_ema_period=9, score_band=4.6, w1=24, w3=45, w7=31 |
| 2 | 0.0000 | 0.0000 | 0.0000 | 1.7797 | 0.0000 | concentration=15.2, f1_ema_period=9, score_band=4.6, w1=24, w3=45, w7=31 |
| 3 | 0.0000 | 0.0000 | 0.0000 | 1.7678 | 0.0000 | concentration=15.8, f1_ema_period=9, score_band=4.6, w1=24, w3=45, w7=31 |
| 4 | 0.0000 | 0.0000 | 0.0000 | 1.7135 | 0.0000 | concentration=14.2, f1_ema_period=9, score_band=4.1, w1=24, w3=45, w7=31 |
| 5 | 0.0000 | 0.0000 | 0.0000 | 1.7056 | 0.0000 | concentration=14.100000000000001, f1_ema_period=9, score_band=4.6, w1=24, w3=45, w7=31 |
| 6 | 0.0000 | 0.0000 | 0.0000 | 1.6755 | 0.0000 | concentration=14.5, f1_ema_period=9, score_band=5.1, w1=24, w3=45, w7=31 |
| 7 | 0.0000 | 0.0000 | 0.0000 | 1.6555 | 0.0000 | concentration=18.9, f1_ema_period=9, score_band=2.6, w1=24, w3=45, w7=31 |
| 8 | 0.0000 | 0.0000 | 0.0000 | 1.6359 | 0.0000 | concentration=16.4, f1_ema_period=9, score_band=4.1, w1=24, w3=45, w7=31 |
| 9 | 0.0000 | 0.0000 | 0.0000 | 1.6346 | 0.0000 | concentration=16.5, f1_ema_period=9, score_band=4.1, w1=24, w3=45, w7=31 |
| 10 | 0.0000 | 0.0000 | 0.0000 | 1.6264 | 0.0000 | concentration=16.7, f1_ema_period=9, score_band=4.1, w1=24, w3=45, w7=31 |

## 各周期最佳

**6Y** (2020-06-27 ~ 2026-06-26):
- Total: +1947.67%  Annual: +65.52%  MDD: -21.69%
- Sharpe: 1.52  Sortino: 2.23  Calmar: 3.02
- Trades: 0/0
- Params: {"account_mode": "synthetic_leverage", "benchmarks": ["000300"], "c_sensitivity": 100.0, "concentration": 15.100000000000001, "conf_type": "ma_trend", "dead_zone": 17, "disc_step": 0.08, "execution_timing": "same_close", "f1_active_days": 1, "f1_ema_period": 9, "f1_sensitivity": 8.9, "f3_sensitivity": 5.4, "f3_vol_window": 17, "f7_k": 3.0, "f7_t": 23.0, "f7_window": 8, "full_zone": 65, "ma_bear_pos": 0.6, "ma_bull_pos": 1.32, "ma_direction_confirm": true, "ma_trend_period": 25, "max_gross_exposure": 1.1, "max_holdings": 2, "rebalance_freq": "daily", "score_band": 4.6, "w1": 24, "w3": 45, "w7": 31}

## Promotion 建议

**Ready to promote**: 在所有周期上，最优 trial 的优化目标不低于基线。
