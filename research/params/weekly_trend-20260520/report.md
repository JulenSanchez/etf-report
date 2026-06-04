# weekly_trend 参数优化报告
**日期**: 2026-05-20 19:25
**策略**: bayesian, 100 trials
**优化目标**: calmar

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 1Y | calmar | 12.0302 | 18.4837 | +6.4535 |
| 3Y | calmar | 1.5695 | 1.8877 | +0.3182 |
| 6Y | calmar | 1.4396 | 1.4951 | +0.0555 |

## Top 10（按 calmar 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 7.2888 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=0.9440776835125876, ema_period=9, score_band=3.6031933970343863, w1=64, w2=5, w3=21, w7=10 |
| 2 | 7.1122 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=0.9362822750048153, ema_period=9, score_band=5.3809183566717484, w1=61, w2=5, w3=23, w6=2, w7=9 |
| 3 | 6.8224 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.4968285158412855, ema_period=9, score_band=8.724856391966863, w1=38, w3=37, w6=6, w7=10 |
| 4 | 6.6395 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.0294568953765657, ema_period=9, score_band=4.137276802162572, w1=64, w2=5, w3=19, w6=2, w7=10 |
| 5 | 6.3859 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=0.9357404918013608, ema_period=9, score_band=3.100881372814513, w1=55, w2=5, w3=27, w6=4, w7=9 |
| 6 | 6.3856 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=0.9219176152319082, ema_period=9, score_band=4.378100303887232, w1=54, w2=4, w3=22, w6=5, w7=11 |
| 7 | 6.2937 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.133355651960046, ema_period=9, score_band=2.4797378777638457, w1=50, w2=4, w3=31, w6=6, w7=9 |
| 8 | 6.2730 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=0.9766173390859094, ema_period=9, score_band=2.7981621326946624, w1=56, w2=5, w3=28, w6=3, w7=8 |
| 9 | 6.2551 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.034437754733813, ema_period=9, score_band=4.224930016833937, w1=62, w2=5, w3=23, w6=1, w7=9 |
| 10 | 6.0958 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.3716374188172906, ema_period=9, score_band=2.4342895152322894, w1=57, w3=22, w6=9, w7=12 |

## 各周期最佳

**1Y** (2025-05-20 ~ 2026-05-20):
- Total: +221.19%  Annual: +221.19%  MDD: -11.97%
- Sharpe: 3.22  Sortino: 4.52  Calmar: 18.48
- Trades: 48/53
- Params: {"bias": 0.0, "concentration": 0.9440776835125876, "conf_type": "momentum_crash", "dead_zone": 42.65502561120227, "disc_step": 0.14212058269938316, "ema_period": 9, "execution_timing": "same_close", "f1_sensitivity": 10.667794023937379, "f2_ma_period": 18, "f2_sensitivity": 7.167439946796204, "f3_sensitivity": 0.9395266428421519, "f6_base_penalty": 0.37019194716378234, "f6_drop_thresh": 4.3588247493991314, "f6_rsi_thresh": 65.30367843469462, "f7_k": 3.607083282873456, "f7_t": 13.201800745798382, "f7_window": 18, "full_zone": 81.00134255784612, "ma_bear_pos": 0.3808460377349717, "ma_bull_pos": 0.7736178138588685, "ma_direction_confirm": true, "ma_trend_period": 33, "max_holdings": 3, "rebalance_freq": "W-FRI", "score_band": 3.6031933970343863, "vol_window": 10, "w1": 64, "w2": 5, "w3": 21, "w4": 0, "w6": 0, "w7": 10}

**3Y** (2023-05-21 ~ 2026-05-20):
- Total: +292.04%  Annual: +57.75%  MDD: -19.95%
- Sharpe: 1.66  Sortino: 2.60  Calmar: 2.89
- Trades: 142/155
- Params: {"bias": 0.0, "concentration": 0.9968122632452181, "conf_type": "always_full", "dead_zone": 48.5798106075189, "disc_step": 0.13983429265319267, "ema_period": 9, "execution_timing": "same_close", "f1_sensitivity": 6.5074517951183655, "f2_ma_period": 24, "f2_sensitivity": 7.402649012871896, "f3_sensitivity": 1.8567249007605586, "f6_base_penalty": 0.2148652493615292, "f6_drop_thresh": 4.880130608621357, "f6_rsi_thresh": 66.00454997580479, "f7_k": 2.5337124996033564, "f7_t": 16.771499881218663, "f7_window": 23, "full_zone": 51.77154623397868, "ma_bear_pos": 0.26519772834602506, "ma_bull_pos": 0.7405833466829326, "ma_direction_confirm": true, "ma_trend_period": 32, "max_holdings": 3, "rebalance_freq": "W-FRI", "score_band": 2.184219696749824, "vol_window": 24, "w1": 46, "w2": 0, "w3": 39, "w4": 0, "w6": 4, "w7": 11}

**6Y** (2020-05-21 ~ 2026-05-20):
- Total: +910.16%  Annual: +47.03%  MDD: -26.16%
- Sharpe: 1.42  Sortino: 2.16  Calmar: 1.80
- Trades: 564/1454
- Params: {"bias": 0.0, "concentration": 0.7463190756436077, "conf_type": "always_full", "dead_zone": 20.430250189101717, "disc_step": 0.14472354033129667, "ema_period": 9, "execution_timing": "same_close", "f1_sensitivity": 2.7951534391036486, "f2_ma_period": 18, "f2_sensitivity": 5.174283369138856, "f3_sensitivity": 2.5661956313906016, "f6_base_penalty": 0.1457583621339143, "f6_drop_thresh": 5.221459040811126, "f6_rsi_thresh": 67.2731893349363, "f7_k": 2.2058434754834866, "f7_t": 18.258553552250902, "f7_window": 21, "full_zone": 56.79791032499978, "ma_bear_pos": 0.21798602247585042, "ma_bull_pos": 0.7903896272061981, "ma_direction_confirm": true, "ma_trend_period": 37, "max_holdings": 3, "rebalance_freq": "daily", "score_band": 7.105986128473728, "vol_window": 19, "w1": 38, "w2": 0, "w3": 36, "w4": 10, "w6": 5, "w7": 11}

## Promotion 建议

**Ready to promote**: 在所有周期上，最优 trial 的优化目标不低于基线。
