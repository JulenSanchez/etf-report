# gam-1 参数优化报告
**日期**: 2026-06-16 18:07
**策略**: bayesian, 123 trials
**优化目标**: calmar

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 1Y | calmar | 9.4950 | 7.8307 | -1.6643 |
| 3Y | calmar | 3.5257 | 3.2395 | -0.2862 |
| 6Y | calmar | 1.6521 | 2.5571 | +0.9050 |

## Top 10（按 calmar 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 1.0971 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.645521362078744, ema_period=8, score_band=1.4292732319170587, w1=45, w3=32, w7=23 |
| 2 | 1.0882 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.041084259415038, ema_period=8, score_band=3.0077376464114973, w1=49, w3=29, w7=22 |
| 3 | 1.0678 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.134167119462282, ema_period=8, score_band=2.29509492464748, w1=47, w3=30, w7=23 |
| 4 | 1.0473 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.6994486994375713, ema_period=8, score_band=1.4804342190519784, w1=46, w3=33, w7=21 |
| 5 | 1.0172 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.4361667661939435, ema_period=8, score_band=2.363927593265954, w1=48, w3=31, w7=21 |
| 6 | 1.0169 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.6571292673138807, ema_period=8, score_band=1.375741385397371, w1=46, w3=31, w7=23 |
| 7 | 1.0127 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.770624379926297, ema_period=8, score_band=2.777826740491503, w1=44, w3=32, w7=24 |
| 8 | 1.0048 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.8574478482726546, ema_period=8, score_band=3.1761266416744527, w1=46, w3=32, w7=22 |
| 9 | 0.9959 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.7366555770485617, ema_period=8, score_band=1.3205695388217282, w1=43, w3=34, w7=23 |
| 10 | 0.9940 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=2.988955591492056, ema_period=8, score_band=0.9120915117218695, w1=46, w3=33, w7=21 |

## 各周期最佳

**1Y** (2025-06-16 ~ 2026-06-16):
- Total: +57.82%  Annual: +58.02%  MDD: -5.57%
- Sharpe: 3.01  Sortino: 4.79  Calmar: 10.42
- Trades: 191/244
- Params: {"bias": 0.0, "c_sensitivity": 26.79867791884616, "concentration": 2.644618683610444, "conf_type": "regime", "dead_zone": 15.028400065501256, "disc_step": 0.048933763779417216, "ema_period": 8, "execution_timing": "same_close", "f1_active_days": 1, "f1_sensitivity": 4.017984951862125, "f3_sensitivity": 0.9408654101885237, "f7_k": 3.1493731280772566, "f7_t": 8.31687621849488, "f7_window": 35, "full_zone": 68.85036471646504, "ma_bear_pos": 0.36859401461418545, "ma_bull_pos": 0.9858064113558874, "ma_direction_confirm": true, "ma_trend_period": 22, "max_holdings": 7, "rebalance_freq": "daily", "score_band": 1.3818338570578745, "vol_window": 34, "w1": 42, "w3": 35, "w7": 23}

**3Y** (2023-06-17 ~ 2026-06-16):
- Total: +202.87%  Annual: +44.83%  MDD: -13.84%
- Sharpe: 1.66  Sortino: 2.44  Calmar: 3.24
- Trades: 375/724
- Params: {"bias": 0.0, "c_sensitivity": 25.967834987962586, "concentration": 2.645521362078744, "conf_type": "ma_trend", "dead_zone": 15.40311598372697, "disc_step": 0.054158182867819836, "ema_period": 8, "execution_timing": "same_close", "f1_active_days": 1, "f1_sensitivity": 3.7917079298838936, "f3_sensitivity": 0.9186201631867055, "f7_k": 3.2674889040869535, "f7_t": 8.126702756003688, "f7_window": 35, "full_zone": 65.57628889865636, "ma_bear_pos": 0.3919038882932676, "ma_bull_pos": 0.9871332516359659, "ma_direction_confirm": true, "ma_trend_period": 20, "max_holdings": 7, "rebalance_freq": "daily", "score_band": 1.4292732319170587, "vol_window": 32, "w1": 45, "w3": 32, "w7": 23}

**6Y** (2020-06-17 ~ 2026-06-16):
- Total: +448.96%  Annual: +32.84%  MDD: -12.76%
- Sharpe: 1.34  Sortino: 2.01  Calmar: 2.57
- Trades: 585/1453
- Params: {"bias": 0.0, "c_sensitivity": 25.82115509360078, "concentration": 2.041084259415038, "conf_type": "ma_trend", "dead_zone": 17.698816882882117, "disc_step": 0.09550183785669149, "ema_period": 8, "execution_timing": "same_close", "f1_active_days": 1, "f1_sensitivity": 3.6136330166918538, "f3_sensitivity": 0.8132843347937808, "f7_k": 3.5032423736463167, "f7_t": 12.945582117668097, "f7_window": 28, "full_zone": 63.875845734452035, "ma_bear_pos": 0.46419432521967785, "ma_bull_pos": 0.9782806602897214, "ma_direction_confirm": true, "ma_trend_period": 15, "max_holdings": 7, "rebalance_freq": "daily", "score_band": 3.0077376464114973, "vol_window": 37, "w1": 49, "w3": 29, "w7": 22}

## Promotion 建议

**需人工判断**: 部分周期上最优 trial 低于基线，请检查具体数据。
