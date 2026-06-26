# gam-2 参数优化报告
**日期**: 2026-06-26 11:44
**策略**: bayesian, 22 trials
**优化目标**: annual_return

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 6Y | annual_return | 46.8490 | 60.8861 | +14.0371 |

## Top 10（按 annual_return 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 0.0000 | 0.0000 | 0.0000 | 1.2996 | 0.0000 | concentration=11.5, f1_ema_period=6, score_band=0.6, w1=45, w3=23, w7=32 |
| 2 | 0.0000 | 0.0000 | 0.0000 | 1.2978 | 0.0000 | concentration=12.2, f1_ema_period=6, score_band=1.1, w1=44, w3=24, w7=32 |
| 3 | 0.0000 | 0.0000 | 0.0000 | 1.0885 | 0.0000 | concentration=14.7, f1_ema_period=6, score_band=0.6, w1=43, w3=25, w7=32 |
| 4 | 0.0000 | 0.0000 | 0.0000 | 1.0763 | 0.0000 | concentration=9.6, f1_ema_period=6, score_band=0.6, w1=45, w3=23, w7=32 |
| 5 | 0.0000 | 0.0000 | 0.0000 | 1.0418 | 0.0000 | concentration=9.1, f1_ema_period=7, score_band=1.1, w1=38, w3=29, w7=33 |
| 6 | 0.0000 | 0.0000 | 0.0000 | 1.0417 | 0.0000 | concentration=9.0, f1_ema_period=7, score_band=0.6, w1=45, w3=23, w7=32 |
| 7 | 0.0000 | 0.0000 | 0.0000 | 1.0177 | 0.0000 | concentration=9.0, f1_ema_period=6, score_band=0.6, w1=45, w3=22, w7=33 |
| 8 | 0.0000 | 0.0000 | 0.0000 | 1.0135 | 0.0000 | concentration=11.2, f1_ema_period=6, score_band=0.6, w1=40, w3=27, w7=33 |
| 9 | 0.0000 | 0.0000 | 0.0000 | 0.9785 | 0.0000 | concentration=9.1, f1_ema_period=7, score_band=0.6, w1=45, w3=22, w7=33 |
| 10 | 0.0000 | 0.0000 | 0.0000 | 0.9076 | 0.0000 | concentration=9.7, f1_ema_period=7, score_band=5.6, w1=41, w3=27, w7=32 |

## 各周期最佳

**6Y** (2020-06-27 ~ 2026-06-26):
- Total: +1627.48%  Annual: +60.89%  MDD: -21.40%
- Sharpe: 1.54  Sortino: 2.35  Calmar: 2.85
- Trades: 0/0
- Params: {"account_mode": "synthetic_leverage", "benchmarks": ["000300"], "c_sensitivity": 178.0, "concentration": 11.5, "conf_type": "ma_trend", "dead_zone": 17, "disc_step": 0.07, "execution_timing": "same_close", "f1_active_days": 1, "f1_ema_period": 6, "f1_sensitivity": 6.2, "f3_sensitivity": 3.6000000000000005, "f3_vol_window": 22, "f7_k": 3.9, "f7_t": 7.0, "f7_window": 20, "full_zone": 65, "ma_bear_pos": 0.7100000000000001, "ma_bull_pos": 1.01, "ma_direction_confirm": true, "ma_trend_period": 35, "max_gross_exposure": 1.7000000000000002, "max_holdings": 3, "rebalance_freq": "daily", "score_band": 0.6, "w1": 45, "w3": 23, "w7": 32}

## Promotion 建议

**Ready to promote**: 在所有周期上，最优 trial 的优化目标不低于基线。
