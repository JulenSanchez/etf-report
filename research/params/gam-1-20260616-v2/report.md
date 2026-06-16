# gam-1 参数优化报告
**日期**: 2026-06-16 20:02
**策略**: bayesian, 100 trials
**优化目标**: calmar

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 1Y | calmar | 9.4950 | 13.4981 | +4.0031 |
| 3Y | calmar | 3.5257 | 4.6303 | +1.1046 |
| 6Y | calmar | 1.6521 | 2.9618 | +1.3097 |

## Top 10（按 calmar 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 1.5092 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.166466352452992, ema_period=5, score_band=1.3797466379897891, w1=48, w3=35, w7=17 |
| 2 | 1.3571 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.561616011091248, ema_period=5, score_band=1.0616773774143962, w1=47, w3=35, w7=18 |
| 3 | 1.3160 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.5698761934490166, ema_period=5, score_band=1.0291403384096574, w1=48, w3=35, w7=17 |
| 4 | 1.3011 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.5333831431308336, ema_period=5, score_band=0.8580090218998944, w1=48, w3=34, w7=18 |
| 5 | 1.2948 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=4.006186469650313, ema_period=5, score_band=1.616092236385071, w1=46, w3=36, w7=18 |
| 6 | 1.2887 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.565784296358837, ema_period=5, score_band=0.883841274612567, w1=48, w3=34, w7=18 |
| 7 | 1.2870 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.8544956248232873, ema_period=5, score_band=1.2836245568430638, w1=47, w3=35, w7=18 |
| 8 | 1.2795 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=4.07382233166887, ema_period=5, score_band=1.728081013399647, w1=47, w3=35, w7=18 |
| 9 | 1.2788 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.507202516568979, ema_period=5, score_band=1.100938802438349, w1=49, w3=34, w7=17 |
| 10 | 1.2668 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=3.9718238888656074, ema_period=5, score_band=1.3859827626871495, w1=48, w3=35, w7=17 |

## 各周期最佳

**1Y** (2025-06-16 ~ 2026-06-16):
- Total: +157.78%  Annual: +158.45%  MDD: -11.69%
- Sharpe: 3.03  Sortino: 4.56  Calmar: 13.56
- Trades: 95/244
- Params: {"bias": 0.0, "c_sensitivity": 26.33945816253704, "concentration": 3.8544956248232873, "conf_type": "ma_trend", "dead_zone": 43.710320489303285, "disc_step": 0.08384484236820683, "ema_period": 5, "execution_timing": "same_close", "f1_active_days": 1, "f1_sensitivity": 11.66298401913012, "f3_sensitivity": 2.9637067217670987, "f7_k": 3.7006951877320637, "f7_t": 7.3423199099380545, "f7_window": 32, "full_zone": 75.85334994711177, "ma_bear_pos": 0.1844288516037699, "ma_bull_pos": 0.8622102209962137, "ma_direction_confirm": false, "ma_trend_period": 38, "max_holdings": 3, "rebalance_freq": "daily", "score_band": 1.2836245568430638, "vol_window": 46, "w1": 47, "w3": 35, "w7": 18}

**3Y** (2023-06-17 ~ 2026-06-16):
- Total: +295.19%  Annual: +58.30%  MDD: -12.59%
- Sharpe: 1.82  Sortino: 2.78  Calmar: 4.63
- Trades: 379/724
- Params: {"bias": 0.0, "c_sensitivity": 36.271405217495534, "concentration": 3.166466352452992, "conf_type": "ma_trend", "dead_zone": 45.8022087165049, "disc_step": 0.05317517802792334, "ema_period": 5, "execution_timing": "same_close", "f1_active_days": 1, "f1_sensitivity": 9.15060438392048, "f3_sensitivity": 2.5733280034371044, "f7_k": 3.229925574145631, "f7_t": 4.9150826732765065, "f7_window": 34, "full_zone": 79.27456002521674, "ma_bear_pos": 0.5353222327697073, "ma_bull_pos": 0.9007865615444949, "ma_direction_confirm": false, "ma_trend_period": 39, "max_holdings": 4, "rebalance_freq": "daily", "score_band": 1.3797466379897891, "vol_window": 39, "w1": 48, "w3": 35, "w7": 17}

**6Y** (2020-06-17 ~ 2026-06-16):
- Total: +696.48%  Annual: +41.34%  MDD: -13.96%
- Sharpe: 1.46  Sortino: 2.17  Calmar: 2.96
- Trades: 709/1453
- Params: {"bias": 0.0, "c_sensitivity": 36.271405217495534, "concentration": 3.166466352452992, "conf_type": "ma_trend", "dead_zone": 45.8022087165049, "disc_step": 0.05317517802792334, "ema_period": 5, "execution_timing": "same_close", "f1_active_days": 1, "f1_sensitivity": 9.15060438392048, "f3_sensitivity": 2.5733280034371044, "f7_k": 3.229925574145631, "f7_t": 4.9150826732765065, "f7_window": 34, "full_zone": 79.27456002521674, "ma_bear_pos": 0.5353222327697073, "ma_bull_pos": 0.9007865615444949, "ma_direction_confirm": false, "ma_trend_period": 39, "max_holdings": 4, "rebalance_freq": "daily", "score_band": 1.3797466379897891, "vol_window": 39, "w1": 48, "w3": 35, "w7": 17}

## Promotion 建议

**Ready to promote**: 在所有周期上，最优 trial 的优化目标不低于基线。
