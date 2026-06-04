# weekly_trend 参数优化报告
**日期**: 2026-05-21 13:01
**策略**: bayesian, 80 trials
**优化目标**: calmar

## 基线对比

| Period | Metric | Baseline | Best | Delta |
|--------|--------|----------|------|-------|
| 1Y | calmar | 12.3220 | 17.7375 | +5.4155 |
| 3Y | calmar | 1.5826 | 1.4055 | -0.1771 |
| 6Y | calmar | 1.4839 | 1.2190 | -0.2649 |

## Top 10（按 calmar 排序）

| Rank | calmar | sharpe | sortino | annual_return | total_return | Key Params |
|------|--------|--------|--------|--------|--------|------------|
| 1 | 1.0497 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=49, w2=1, w3=38, w7=11 |
| 2 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 3 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 4 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 5 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 6 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 7 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 8 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 9 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |
| 10 | 1.0469 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | concentration=1.5, ema_period=9, w1=52, w2=1, w3=34, w7=12 |

## 各周期最佳

**1Y** (2025-05-21 ~ 2026-05-21):
- Total: +188.65%  Annual: +189.49%  MDD: -10.21%
- Sharpe: 3.30  Sortino: 5.26  Calmar: 18.56
- Trades: 53/53
- Params: {"concentration": 1.5, "conf_type": "momentum_crash", "ema_period": 9, "max_holdings": 3, "score_band": 0, "w1": 52, "w2": 1, "w3": 34, "w4": 1, "w6": 0, "w7": 12}

**3Y** (2023-05-22 ~ 2026-05-21):
- Total: +90.32%  Annual: +23.95%  MDD: -14.31%
- Sharpe: 1.29  Sortino: 1.83  Calmar: 1.67
- Trades: 154/155
- Params: {"concentration": 0.7, "conf_type": "regime", "ema_period": 9, "max_holdings": 3, "score_band": 2, "w1": 52, "w2": 1, "w3": 34, "w4": 1, "w6": 0, "w7": 12}

**6Y** (2020-05-22 ~ 2026-05-21):
- Total: +650.67%  Annual: +39.95%  MDD: -29.59%
- Sharpe: 1.19  Sortino: 1.83  Calmar: 1.35
- Trades: 306/309
- Params: {"concentration": 0.7, "conf_type": "ma_trend", "ema_period": 9, "max_holdings": 3, "score_band": 0, "w1": 52, "w2": 1, "w3": 34, "w4": 1, "w6": 0, "w7": 12}

## Promotion 建议

**需人工判断**: 部分周期上最优 trial 低于基线，请检查具体数据。
