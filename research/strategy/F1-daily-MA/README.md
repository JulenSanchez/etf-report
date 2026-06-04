# F1 日线 MA 变体

**日期**: 2026-05-18
**状态**: 待实施

## 背景

当前 F1 使用**周线 EMA** 计算偏离度，与 F3/F7 的日频节奏不一致。周线版本更新慢（每周一次），日频调仓时 F1 值可能滞后。

## 方案

将 F1 从周线 EMA 改为日线 MA：

```
F1 = (close - MA) / MA × 100
```

- 日线 MA 周期 = 周线 EMA 周期 × 5（例如 `ema_period_weeks=5` → `ma_period_days=25`）
- 与 F3（日频量比）、F7（日频对数收益偏离）节奏对齐
- 使用 MA 而非 EMA：更直观，且计算更简单

## 参数

| 参数 | 含义 | 默认值 |
|------|------|--------|
| `f1_daily_ma` | 启用日线 MA（替代周线 EMA） | false |

配置示例：

```yaml
factors:
  ema:
    period_weeks: 5
  f1_daily_ma: true
```

## 代码改动

1. `quant_backtest.py` `_precompute_factors()`: 新增 `f1_daily_ma` 分支，用 `rolling(period_days).mean()` 替代 `calc_ema()`
2. `quant_factors.py`: 新增 `factor_ma_deviation_daily()` 函数
3. `config/quant_universe.yaml`: 在 preset 中可选 `f1_daily_ma: true`
4. `templates/tuner.html`: F1 相关提示文字更新

## 评估方法

- 在 `weekly_trend` preset 上 A/B 对比：周线 EMA vs 日线 MA
- 关注：年化收益、MDD、Calmar、换仓频率
- 预期：日线 MA 更灵敏，换仓频率可能略增，趋势跟踪更及时

## 依赖

- `_precompute_factors()` 已支持 `f1_daily_ema` 参数，新增 `f1_daily_ma` 复用同一框架
