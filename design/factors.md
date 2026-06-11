# 因子体系

> 回测引擎使用的因子定义、计算公式、映射逻辑。引擎机制见 ，系统架构见 。

---

## 5. 因子契约

当前主回测使用预计算路径：

```python
_precompute_factors(...)
```

主循环不再每次现场重算完整因子，而是按调仓日二分查找预计算序列。

### 5.1 F1 — EMA 偏离

默认形态：周线 EMA 偏离。**周线数据来自 CSV 快照，不合并 intraday cache。**

```text
F1_raw = (close - EMA_N) / EMA_N * 100
F1 = map_f1(F1_raw, sensitivity.f1)
```

### F1 抢跑机制

#### 统一公式

F1 在任何时刻 t 都有唯一定义：

```
F1(t) = (price(t) − EMA_rolled) / EMA_rolled × 100

其中 EMA_rolled = α × price(t) + (1−α) × EMA_last_week
      EMA_last_week = 最近完整周的 EMA 值（来自 CSV）
```

**保持态和计算态不是两套逻辑——它们共用同一个公式。唯一的区别是 price(t) 的值：**

| 状态 | price(t) | 效果 |
|------|---------|------|
| 保持态 | 冻结：= 上次检查点的 close（常量） | F1 = 常值，平线 |
| 计算态 | 解冻：= 当前市场价（随时间变化） | F1 随价格波动 |

所以"抢跑"的本质是：**什么时候把 price(t) 从常量解冻为市价。**

#### 检查点

每周五 15:10，CSV 更新，产生一个新检查点。但注意：15:10 在收盘（15:00）之后。因此：

- 周五收盘时刻，新检查点还不存在，无论是基态还是抢跑态都拿不到
- 周一开盘时刻，新检查点已经存在
- 检查点是计算态的收敛目标：计算态在 t_checkpoint 时刻用 checkpoint_close 算出的 F1 = 检查点值（因为 price = close，EMA_rolled = EMA_of_that_week）

#### 参数 `f1_active_days`（bitmask 0-31）

控制在**哪些开盘时刻**允许解冻 price(t)。每位对应一个时点：

| bit | 值 | 解冻时点 | 标签 |
|-----|----|---------|------|
| 0 | 1 | 本周最后一个交易日开盘 | 周五 |
| 1 | 2 | 倒数第2个交易日开盘 | 周四 |
| 2 | 4 | 倒数第3个交易日开盘 | 周三 |
| 3 | 8 | 倒数第4个交易日开盘 | 周二 |
| 4 | 16 | 倒数第5个交易日开盘 | 周一 |

"最后一个交易日"由交易日历确定——假日周自动适配（如周四为最后交易日时 bit 0 控制周四开盘）。常用值：0=Base、1=Friday、31=Daily。

#### 三种模式 → 检查点/冻结模型

旧的三模式（Base/Friday/Daily）已被统一的**检查点/冻结点**状态机替代：

| 模式 | bitmask | 行为 |
|------|---------|------|
| Base | 0 | 全周 hold 上周 F1，周末跳到新一周的已完成 bar |
| 周五 | 1 | 周一~四 hold，周五检查点滚 EMA |
| 周二+周五 | 9 | 周一 hold，周二检查点，周三~四冻结，周五检查点 |
| 每日 | 31 | 每天检查点，中间不冻结 |

**检查点日**：bitmask 中对应位被选中 AND `days_in_week == threshold`（精确等于，不是 `>=`）。只有门槛日当天才创建检查点。

**冻结**：两个检查点之间的所有交易日复用上一个检查点的 F1 值，不做任何 EMA 滚动。

#### 计算实现（`_precompute_factors`）

1. 在周线 CSV 上预计算 EMA 序列（一次性，所有 ISO 周）
2. 对每个日线日期 D：
   - 参考点永远 = 本周一 → base 永远是上周最后一个完整周 bar
   - `total_td` 从日线数据直接统计（不依赖交易日历，避免节假日数据缺失）
3. 按检查点/冻结/hold 统一三分支：
   - **检查点** → `EMA_now = α × price(D) + (1-α) × base_EMA`，F1 = (price-EMA)/EMA，保存为 checkpoint_f1
   - **冻结** → 复用本周期最近一个 checkpoint 的 F1
   - **Hold** → 复用 base bar 的 F1（本周尚无检查点）

> 注：检查点日滚 EMA 的结果与已完成周线 bar 的 EMA 数学等价（EMA 定义：EMA_W = α × close_W + (1-α) × EMA_{W-1}）。无需 `week_already_in_base` 分支。

#### 为什么 hold 通常优于周中抢跑

F1 是周线信号，信息粒度以"周"为单位。周中抢跑用不完整信息（1/5 ~ 4/5）做估计，得到的是**有偏的近似值**——不是"错"，是噪声大。

hold 的效果不是"规避假信号"，而是**信息质量保护**：在信息不够的时候，宁可用上周的完整 5/5 值，也不用一个高噪声近似去干扰 F3/F7 的日线判断。

这引出一个可测试的假说：**周五是唯一一个在不牺牲完整度（5/5）的前提下提升新鲜度的检查点。**周五收盘时 F1 已经收敛到无偏值，同时比等 CSV 更新快一个周末。当前所有 preset 只勾周五，TR 显著高于其他模式——与这个假说一致。

bitmask 机制将信息完整度门槛暴露为可调参数。不同模式（周二+周五、每日等）的信息质量差异可以通过 6y 回测实证对比，无需理论推测。

#### 与旧实现的区别

| | 旧 (v3.5.0) | 新 (v3.6.0) |
|---|---|---|
| 检查点判定 | `days_in_week >= threshold` | `days_in_week == threshold` |
| 中间日 | 重新滚 EMA（自由移动） | 冻结（复用上一个检查点） |
| w_end 参考点 | Base=周一, 非Base=今日（不对称） | 永远=周一（统一） |
| total_td 来源 | 交易日历（缺历史假期） | 日线数据直接统计 |
| week_already_in_base | 存在（实现细节混入策略） | 已移除 |

### 5.2 F3 — 自归一化方向性量比

```text
vol_z[t] = volume_or_amount[t] / trailing_mean(volume_or_amount)
F3_raw = mean(vol_z on up days) / mean(vol_z on down days)
F3 = map_f3(F3_raw, sensitivity.f3)
```

历史不足时可能回退或产生 NaN，具体以 `quant_backtest.py::_precompute_factors()` 为准。

### 5.3 F7 — 对数收益偏离

```text
log_return = ln(close[t] / close[t-1])
cum_N = rolling_sum(log_return, window_days)
Z = (cum_N - rolling_mean(cum_N, lookback)) / rolling_std(cum_N, lookback)
F7 = map_f7(Z, t=f7_t, k=f7_k)
```

Z > 0 表示近期累计收益高于历史均值（趋势强），Z < 0 表示低于（超跌）。
`f7_t` 控制陡度，`f7_k` 控制阈值。NaN 时 fallback 为 0.5。

### 5.4 已退役因子

F2(日线 MA)、F4(估值)、F5(波动率)、F6(动能衰竭) 已于 2026-05~06 正式清退。
代码保留（权重=0），不参与综合分。详见 `research/strategy/2026-05-28-research-archive.md`。

---
