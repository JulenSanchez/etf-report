# 回测引擎技术文档

> AI 可读的回测过程完整描述。修改回测逻辑前先读此文档。

## 架构

```
前端 Tuner (tuner.html)
  │ POST /api/run
  ▼
quant_tuner.py: run_tuner_backtest()
  │ 构建 config_override + preloaded
  │ 调用统一引擎
  ▼
quant_backtest.py: run_backtest()  ← 唯一回测引擎
  │ load_config(preset) + config_override
  │ 加载数据（CSV 或 preloaded）
  │ 回测主循环
  ▼
返回 (nav_df, signal_history)
  │
  ▼
Tuner 格式化为 JSON → 前端渲染
CLI 直接打印统计 → 终端输出
```

## 唯一入口

`scripts/quant_backtest.py` → `run_backtest()`

```python
def run_backtest(
    start_date,          # "2023-05-14"
    end_date=None,       # None = 至今
    preset="daily_aggressive",  # YAML preset 名
    execution_timing="same_close",  # same_close | next_open
    universe_filter=None,    # [code, ...] 或 None
    preloaded=None,          # {all_daily, all_weekly, market_regimes, hs300_above_ma}
    config_override=None,    # {scoring, confidence, position, factors}
    return_details=False,    # True = 每 ETF 因子明细
)
```

## 回测流程

### Phase 0: 配置加载

1. `load_config(preset)` 加载 `config/quant_universe.yaml`
2. `config_override` 覆盖 preset 的 scoring/confidence/position/factors
3. `universe_filter` 过滤 ETF 池

### Phase 1: 数据加载

1. 遍历 universe 中每支 ETF，加载 `data/quant/{code}_daily.csv` + `_weekly.csv`
2. 若提供 `preloaded`，跳过 CSV 加载
3. 加载 `data/market_regimes.json`（F4 估值因子）
4. 加载 HS300 日线 → 构建 MA 趋势缓存（ma_trend 信心函数）

### Phase 2: 日期范围与预热

```
可见区间: [user_start, user_end]  ← 用户选择的回测周期
预热扩展: user_start - (ema_period + 4) 周  ← 给 EMA/RSI 积累历史

调仓日 = 预热区间内所有调仓日 ∪ 可见区间内所有调仓日
```

### Phase 3: 回测主循环

对每个调仓日 `rb_date`：

**3a. 预热期处理**
- `rb_date < user_start` 且不是初始建仓日 → 跳过（仅积累因子历史）
- 最后一个预热调仓日 = **初始建仓日**：执行首次买入，不应用分数带

**3b. 因子计算**（`quant_factors.py`）
```
F1: 周线 EMA 偏离度 = (close - EMA_16周) / EMA_16周 × 100
F2: 日线 RSI(14) 自适应变换（当前权重=0，禁用）
F3: 方向性量比 = mean(上涨日成交额) / mean(下跌日成交额)，20 日滚动
F4: 估值因子（PE/PB 历史百分位，regime-aware 映射）
F6: 动能衰竭惩罚 = RSI>80 且 放量下跌>2.5% → 扣 0.15，3 日衰减
F7: 对数收益偏离 = 20日累计对数收益的 Z-score，幂函数映射
```

**3c. 连续映射**（`map_f1` ~ `map_f7`）
- 将原始因子值映射到 [0, 1] 评分空间
- F7 参数：`f7_t`（幂次，控制加速度）、`f7_k`（Z-score 阈值）

**3d. 加权合成**
```
composite = F1×w1 + F2×w2 + F3×w3 + F4×w4 + F6_penalty×w6 + F7×w7 + bias
```

**3e. Top-N 选股**
- `composite.nlargest(max_holdings)` → top_n
- 分数带过滤（score_band）：新标的替换被挤出持仓时，分数优势必须 > score_band
- 首日不应用分数带（初始建仓已在预热期完成）

**3f. 信心函数 → 总仓位**
- `ma_trend`（当前）：HS300 在周 MA 上方 → bull_pos，下方 → bear_pos
- 可选：方向确认（需 MA 方向与位置一致）
- `total_target ∈ [bear_pos, bull_pos]`

**3g. 仓位分配**
```
target_positions = relative_weights × total_target
target_positions = round(target_positions / step) × step  # 离散化到 5% 档位
```

**3h. 执行交易**
- 卖出不在 top_n 的持仓
- 买入/调整至目标仓位
- 扣除佣金（commission_rate = 0.026%）

### Phase 4: NAV 计算

- 逐日计算组合净值（收盘价 × 持仓数量 + 现金）
- **仅记录 user_start 之后的日期**
- 预热期执行调仓但不记录 NAV

### Phase 5: 统计输出

```
总收益率 = (final_nav / initial_capital - 1) × 100
年化收益率 = (final_nav / initial_capital)^(365/days) - 1
最大回撤 = min((nav - cummax) / cummax)
夏普比率 = (daily_return_mean × 252 - 0.02) / (daily_return_std × √252)
索提诺比率 = (daily_return_mean × 252 - 0.02) / (downside_std × √252)
```

## 关键设计决策

### 预热与初始建仓

- **预热期不交易的弊端**：若跳过前 N 天，回测周期 < N 天时零交易（不合理）
- **预热期全部交易的弊端**：回测起点已有持仓，用户不理解"为什么第一天已经有持仓了"
- **当前方案**：预热期仅最后一天执行**初始建仓**（按当日收盘评分买入 top-N），其余预热日仅积累因子历史。这样：
  - 回测第一天已有持仓，市场涨跌立即反映
  - 1 天回测也能看到 P&L
  - 首日持仓来源于"前一天收盘评分"，逻辑清晰

### 分数带（黏着机制）

- 初始建仓日不应用分数带（严格按评分选 top-N）
- 之后每次调仓：新标的需比被挤出者高出 score_band 才能替换
- 目的：减少频繁换仓，降低交易成本

### 离散化

使用 `round()` 而非 `floor()`：
- 0.027 → 0.05（round up）vs 0.00（floor down）
- 避免系统性地低配仓位

## 配置结构

`config/quant_universe.yaml`：
```yaml
presets:
  daily_aggressive:     # F7 策略（当前主策略）
    scoring:
      weights: {ema_deviation: 0.35, volume_ratio: 0.5, log_return_deviation: 0.15}
      sensitivity: {f7_t: 11.0, f7_k: 3.0}
    confidence: {type: ma_trend, ma_bull_pos: 1.0, ma_bear_pos: 0.3}
    position: {rebalance_freq: daily, max_holdings: 6, discretize_step: 0.05}
    factors: {log_return_deviation: {window_days: 10}}
  daily_aggressive_f6:  # F6 对照策略
    scoring:
      weights: {ema_deviation: 0.4, volume_ratio: 0.55, exhaustion_penalty: 0.05}
    ...
```

## 相关文件

| 文件 | 职责 |
|------|------|
| `scripts/quant_backtest.py` | 唯一回测引擎 |
| `scripts/quant_factors.py` | 因子计算 + 映射函数 |
| `scripts/quant_tuner.py` | Flask 服务 + 调参 UI 后端 |
| `scripts/quant_build_payload.py` | 预计算报告页数据 |
| `scripts/quant_data_fetcher.py` | ETF 数据拉取 |
| `scripts/quant_data_utils.py` | 数据加载工具 |
| `config/quant_universe.yaml` | ETF 池 + 策略 preset |
| `templates/tuner.html` | 调参 UI 前端 |
