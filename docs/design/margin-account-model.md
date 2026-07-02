# 杠杆与融资账户建模设计

> 本文承接 v3.9 杠杆能力建设。通用两融知识见 `docs/knowledge/margin-financing.md`。
>
> 设计分两阶段：Stage A 在 v3.9 上线“合成杠杆”研究与展示能力；Stage B 在 v3.10 上线更接近真实两融账户的融资/担保/强平模型。

---

## 1. 总体判断

`ma_bull_pos > 1.0` 不应被当成普通仓位参数扩围。它至少有两种语义：

```text
Stage A: synthetic_leverage
  零融资成本、无追保/强平、无真实账户约束。
  目标：快速打开 ma_bull <= 2.0 的研究空间，优化三派风险偏好。

Stage B: real_margin_account
  有融资成本、维持担保比例、追保/强平风险、账户状态序列。
  目标：把 Stage A 发现的可行杠杆策略，落到更接近真实两融账户的模型。
```

v3.9 先做 Stage A。这样能快速回答：

- 三派是否有必要突破 100%？
- 哪个主体适合更高风险预算？
- 收益改善是否只是粗暴杠杆，还是风险调整后仍有价值？
- 如果引入融资成本，理论收益大概还能剩多少？

v3.10 再做 Stage B。这样避免第一版被真实两融细节拖慢，同时给后续真实账户模型保留结构。

---

## 2. 设计原则

1. **现金账户行为不变**：默认模式仍是 cash，现有 preset 不因 v3.9 自动加杠杆。
2. **合成杠杆显式命名**：Stage A 不叫真实两融，不模拟融资成本和强平，只作为研究模型。
3. **收益与风险同屏**：任何杠杆收益都必须同时展示 exposure、尾部风险和融资成本压力估算。
4. **三派差异化风险预算**：杠杆不是全局开关，应服务多主体策略治理。
5. **Stage A 为 Stage B 留接口**：配置字段和 payload 命名要能自然扩展到真实融资账户。

---

## 3. Stage A: synthetic_leverage（v3.9）

### 3.1 目标

v3.9 上线合成杠杆研究能力：

```text
account_mode: cash / synthetic_leverage
ma_bull_pos max: 2.0
financing_cost: 0（仅作为零成本研究上限）
margin_call: 不模拟
forced_liquidation: 不模拟
```

核心模型：

```text
组合日收益 = 当日底层组合收益率 * 当日目标总仓位
```

这不是现实两融账户，只是“把仓位暴露作为收益放大器”的研究模型。

### 3.2 参数语义

新增账户配置建议：

```yaml
account:
  mode: cash                 # cash / synthetic_leverage
  max_gross_exposure: 1.0    # synthetic_leverage 可到 2.0
  financing_rate_annual: 0.0 # Stage A 不进入 NAV，只用于压力估算
  margin_model: none         # none / real_margin（Stage B）
```

Stage A 约束：

```text
cash:
  ma_bull_pos <= 1.0
  max_gross_exposure = 1.0

synthetic_leverage:
  ma_bull_pos <= 2.0
  max_gross_exposure <= 2.0
```

### 3.3 ma_bull_pos 重新定义

当前：

```text
ma_bull_pos = 牛市目标总仓位
```

Stage A 后：

```text
ma_bull_pos = 趋势上方的目标暴露
max_gross_exposure = 账户模式允许的最大暴露
actual_exposure = min(ma_state_target, max_gross_exposure)
```

`ma_bull_pos` 可以触发超过 100% 的目标暴露，但是否允许由 `account.mode` 和 `max_gross_exposure` 裁决。

### 3.4 风险闸门

Stage A 不做真实追保/强平，但必须有最小风险闸门。

#### 硬上限

```text
actual_exposure = min(target_exposure, max_gross_exposure)
```

#### 趋势门槛

只有强趋势允许超过 100%。建议第一版：

```text
if not (hs300_above_ma and hs300_ma_rising):
    actual_exposure = min(actual_exposure, 1.0)
```

#### 回撤刹车

第一版可先固定为非优化参数：

```text
if strategy_drawdown < -10%:
    actual_exposure = min(actual_exposure, 1.0)
```

后续再考虑进入优化器。

### 3.5 输出指标

Stage A 必须输出 exposure 序列和风险摘要。

```text
avg_exposure
max_exposure
days_above_100
days_above_150
days_above_180
max_daily_loss
worst_month
leverage_usage_ratio
interest_drag_estimate
```

融资成本压力估算：

```text
avg_excess_exposure = average(max(exposure - 1.0, 0))
interest_drag_estimate = avg_excess_exposure * financing_rate_annual
```

注意：`interest_drag_estimate` 不进入 Stage A NAV，只作为解释性压力视图。

### 3.6 优化目标

放开到 200% 后，不能只按 TR 排序。

建议硬过滤：

```text
MDD <= 35%
max_daily_loss <= 8%
worst_month >= -18%
```

建议排序：

```text
score = Sortino * Calmar
```

或：

```text
score = annual_return / abs(max_drawdown)
```

### 3.7 三派风险预算

Stage A 不应给三派统一上限。

```text
act-1:
  ma_bull_pos upper: 1.3 ~ 1.5
  objective: Sharpe / Sortino / Calmar

zen-1:
  ma_bull_pos upper: 1.1 ~ 1.3
  objective: low drawdown / low volatility / low turnover

gam-1:
  ma_bull_pos upper: 2.0
  objective: high AR / high Calmar with MDD gate
```

候选命名建议：

```text
act-margin-1
zen-margin-1
gam-margin-1
```

这些候选不直接覆盖现有生产 preset。

### 3.8 Tuner 展示

Tuner Stage A 新增：

```text
账户模式：cash / synthetic_leverage
最大总暴露：max_gross_exposure
融资成本压力估算：financing_rate_annual only for estimate
暴露天数分布：>100%, >150%, >180%
```

结果区新增：

```text
avg_exposure
max_exposure
days_above_100
days_above_150
days_above_180
max_daily_loss
worst_month
interest_drag_estimate
```

### 3.9 正式页展示

正式页只展示通过 promotion 的结果。若只是研究候选，不进入正式页主指标。

推荐展示：

```text
accountMode
maxGrossExposure
avgExposure
leverageContribution
interestDragEstimate
maxDailyLoss
worstMonth
daysAbove100
```

文案必须标明：

```text
Stage A 为零融资成本合成杠杆模型，不代表真实两融账户收益。
```

---

## 4. Stage B: real_margin_account（v3.10）

### 4.1 目标

v3.10 在 Stage A 的账户字段基础上，引入真实两融账户近似模型：

```text
融资负债
融资利息逐日计提
担保品折算率
维持担保比例
追保标记
强平风险标记
```

### 4.2 AccountConfig

```yaml
account:
  mode: real_margin
  max_gross_exposure: 1.5
  financing_rate_annual: 0.06
  collateral_haircut: 1.0
  maintenance_ratio_warning: 1.5
  maintenance_ratio_liquidation: 1.3
  leverage_volatility_brake:
    enabled: true
    lookback_days: 20
    threshold: 0.25
    target_if_triggered: 1.0
  leverage_drawdown_brake:
    enabled: true
    threshold: -0.10
    target_if_triggered: 1.0
```

### 4.3 AccountState

```text
AccountState
  date
  cash
  long_market_value
  gross_exposure
  net_exposure
  net_liquidation_value
  margin_debt
  interest_accrued
  collateral_value
  maintenance_ratio
  available_buying_power
  margin_call_flag
  forced_liquidation_flag
```

关键定义：

```text
net_liquidation_value = cash + long_market_value - margin_debt
margin_debt = borrowed_cash + accrued_interest
gross_exposure = long_market_value / net_liquidation_value
collateral_value = long_market_value * collateral_haircut + max(cash, 0)
maintenance_ratio = collateral_value / margin_debt  # margin_debt > 0 时
```

### 4.4 每日回测顺序

```text
1. mark_to_market
2. accrue_interest
3. compute_signal
4. compute_raw_target_exposure
5. apply_account_cap
6. apply_risk_brakes
7. rebalance
8. check_margin_status
9. record_account_snapshot
```

### 4.5 融资成本

```text
daily_rate = financing_rate_annual / 365
interest = margin_debt * daily_rate
margin_debt += interest
interest_accrued += interest
```

### 4.6 卖出还款

```text
repay = min(sell_cash, margin_debt)
margin_debt -= repay
cash += sell_cash - repay
```

### 4.7 追保/强平

```text
if maintenance_ratio < maintenance_ratio_warning:
    margin_call_flag = true

if maintenance_ratio < maintenance_ratio_liquidation:
    forced_liquidation_flag = true
```

第一版可以只标记风险，不真实模拟券商强平卖出；若要模拟，必须单独开需求。

---

## 5. 分阶段需求拆解建议

### v3.9 Stage A

1. 合成杠杆账户模式与 exposure 引擎。
2. 杠杆风险指标与融资成本压力估算。
3. Tuner 合成杠杆参数与结果展示。
4. 三派合成杠杆参数优化与 promotion 裁决。
5. 正式页杠杆摘要展示。

### v3.10 Stage B

1. 真实融资负债与利息计提。
2. AccountState 序列与维持担保比例。
3. 追保/强平风险标记。
4. real_margin Tuner 展示。
5. Stage A 候选在 real_margin 下复核。

---

## 6. Stage A 验收标准（v3.9）

1. cash 模式与当前回测结果保持一致。
2. synthetic_leverage 模式支持 `ma_bull_pos <= 2.0`。
3. 输出 exposure 序列和风险摘要。
4. 输出融资成本压力估算，但不进入 NAV。
5. Tuner 可选择 synthetic_leverage 并展示风险指标。
6. 三派至少各产出一个 margin 候选报告。
7. 全量测试通过：

```bash
python -m pytest tests -q
```

---

## 7. Stage B 验收标准（v3.10）

1. real_margin 模式支持融资负债。
2. 融资利息逐日计提并进入 NAV。
3. ~~输出 AccountState 序列。~~（已取消，见 §8）
4. ~~输出维持担保比例、追保、强平风险标记。~~（已取消，见 §8）
5. Stage A 候选在真实融资成本下完成复核。
6. 全量测试通过：

```bash
python -m pytest tests -q
```

---

## 8. 追保/强平在当前模型下不会触发（2026-07-02）

### 结论

在当前 Tuner 模型的参数空间内（`max_gross_exposure ≤ 2.0`、标的为高流动性 A 股行业 ETF、有回撤刹车保护），**维持担保比例永远不会降到追保线（1.5）以下，追保标记和强平标记是"不会亮的灯"**。因此 Stage B 不再单独实现 maintenance_ratio 追踪和 margin_call/forced_liquidation 标记。

### 推导

以极端情况为例：初始资金 100，满仓 2.0x（hv=200, debt=100）：

```
维持担保比例 = 持仓市值 / 融资负债 = 200 / 100 = 2.0
追保线 1.5 → hv 需跌到 150，即 -25%
强平线 1.3 → hv 需跌到 130，即 -35%
```

在发生 -25% 回撤之前，已有三层防护先行拦截：

1. **回撤刹车**（`momentum_crash_confidence`）：NAV 两天跌 -3% 即把仓位压到 20%，单日跌停完全轮不到 margin call 触发。
2. **趋势刹车**（`ma_trend` confidence）：MA 转熊即把目标仓位砍到 `ma_bear_pos`（典型 0.3~0.6），暴露从 2.0x 退到 1.0x 以下。
3. **A 股 ETF ±10% 涨跌停**：即使无刹车、单日跌停（-10%），ratio 只从 2.0 降到 1.8，仍远离 1.5。需要连续两天跌停才触及追保线，但第一天刹车已触发。

更温和的场景（如 gam-0 的 ma_bull=1.58）：

```
hv = 158, debt = 58, ratio = 158/58 ≈ 2.72
单日 -10% → hv=142.2, ratio=2.45  仍然非常安全
```

### 适用范围

此结论的假设：

| 条件 | 当前模型 | 突破后需重新评估 |
|------|---------|----------------|
| `max_gross_exposure` | ≤ 2.0 | > 2.5 时 margin 压力非线性增长 |
| 标的 | A 股行业 ETF | 个股/跨境 ETF（无涨跌停或流动性差） |
| 回撤刹车 | 开启 | 关闭或弱化时 |
| 调仓频率 | 每周 | 月频或更低时（回撤积累窗口更长） |
| 担保品折算率 | 1.0（ETF） | < 0.7 时（如个股） |

若未来参数空间突破上述任一条件，应重新评估是否需要实现 maintenance_ratio 追踪，届时重新激活 REQ-340。
