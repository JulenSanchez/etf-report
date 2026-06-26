# gam-2 参数优化报告
**日期**: 2026-06-26 13:34
**策略**: bayesian, 33 trials
**优化目标**: annual_return

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 6Y | annual_return | 110.4659 | 75.2688 | -35.1971 |

## Top 10（按 annual_return 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 0.0000 | 0.0000 | 0.0000 | 0.6814 | 0.0000 | concentration=17.13, f1_ema_period=6, score_band=7.9, w1=45, w3=23, w7=32 |
| 2 | 0.0000 | 0.0000 | 0.0000 | 0.6696 | 0.0000 | concentration=17.830000000000002, f1_ema_period=6, score_band=8.4, w1=45, w3=23, w7=32 |
| 3 | 0.0000 | 0.0000 | 0.0000 | 0.6628 | 0.0000 | concentration=16.830000000000002, f1_ema_period=6, score_band=8.9, w1=45, w3=23, w7=32 |
| 4 | 0.0000 | 0.0000 | 0.0000 | 0.6554 | 0.0000 | concentration=17.13, f1_ema_period=6, score_band=8.4, w1=45, w3=23, w7=32 |
| 5 | 0.0000 | 0.0000 | 0.0000 | 0.6375 | 0.0000 | concentration=12.129999999999999, f1_ema_period=6, score_band=1.4, w1=45, w3=23, w7=32 |
| 6 | 0.0000 | 0.0000 | 0.0000 | 0.6025 | 0.0000 | concentration=17.03, f1_ema_period=6, score_band=6.9, w1=45, w3=23, w7=32 |
| 7 | 0.0000 | 0.0000 | 0.0000 | 0.6021 | 0.0000 | concentration=18.43, f1_ema_period=6, score_band=8.9, w1=45, w3=23, w7=32 |
| 8 | 0.0000 | 0.0000 | 0.0000 | 0.6010 | 0.0000 | concentration=19.63, f1_ema_period=6, score_band=8.4, w1=45, w3=23, w7=32 |
| 9 | 0.0000 | 0.0000 | 0.0000 | 0.5939 | 0.0000 | concentration=17.03, f1_ema_period=6, score_band=6.9, w1=45, w3=23, w7=32 |
| 10 | 0.0000 | 0.0000 | 0.0000 | 0.5899 | 0.0000 | concentration=17.23, f1_ema_period=6, score_band=8.9, w1=45, w3=23, w7=32 |

## 各周期最佳

**6Y** (2020-06-27 ~ 2026-06-26):
- Total: +2785.52%  Annual: +75.27%  MDD: -23.67%
- Sharpe: 1.59  Sortino: 2.40  Calmar: 3.18
- Trades: 0/0
- Params: {"account_mode": "synthetic_leverage", "benchmarks": ["000300"], "c_sensitivity": 130.04, "concentration": 17.13, "conf_type": "ma_trend", "dead_zone": 17, "disc_step": 0.0695, "execution_timing": "same_close", "f1_active_days": 1, "f1_ema_period": 6, "f1_sensitivity": 6.2, "f3_sensitivity": 3.6, "f3_vol_window": 22, "f7_k": 3.9, "f7_t": 7.0, "f7_window": 20, "full_zone": 65, "ma_bear_pos": 0.882, "ma_bull_pos": 1.124, "ma_direction_confirm": true, "ma_trend_period": 25, "max_gross_exposure": 2.0, "max_holdings": 3, "rebalance_freq": "daily", "score_band": 7.9, "w1": 45, "w3": 23, "w7": 32}

## Promotion 建议

**需人工判断**: 部分周期上最优 trial 低于基线，请检查具体数据。
