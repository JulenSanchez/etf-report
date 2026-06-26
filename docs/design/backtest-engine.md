# 回测引擎

> 回测循环、仓位分配、信心函数、成交执行。因子定义见 `docs/design/factors.md`，系统架构见 `docs/design/overview.md`。

---

## 1. 唯一回测入口

```python
scripts/quant_backtest.py::run_backtest()
```

签名：

```python
def run_backtest(
    start_date: str = "2023-01-01",
    end_date: str = None,
    initial_capital: float = 1000000.0,
    rebalance_freq: str = None,
    preset: str = None,  # None 时使用 DEFAULT_PRESET (见 quant_contract.py)
    universe_filter: list = None,
    preloaded: dict = None,
    config_override: dict = None,
    return_details: bool = False,
    return_debug: bool = False,
):
```

返回：

```python
(nav_df, signal_history, extra)
```

| 返回值 | 含义 |
|---|---|
| `nav_df` | 日度组合净值 DataFrame，含 `date/nav` 等列 |
| `signal_history` | 每个调仓日的信号、分数、目标仓位、成交口径等 |

### 默认策略

所有入口函数的 `preset` 参数默认值为 `None`，解析为 `quant_contract.py::DEFAULT_PRESET`。更改默认策略只需修改该常量，全项目自动生效。

受影响的入口：`run_backtest()`、`load_config()`、`quant_optimizer.py`、`quant_tuner.py`、`preclose_push.py`、`update_report.py`、`quant_consistency_check.py`、`quant_walkforward.py`、`pool_change.py`。
| `extra` | 附加统计，如总佣金、debug snapshots |

---

## 2. 配置加载顺序

配置来源优先级：

```text
config/quant_universe.yaml
  -> load_config(preset)
  -> config_override 覆盖 scoring / confidence / position / factors
  -> 函数参数 rebalance_freq 覆盖
  -> universe_filter 过滤 ETF 池
```

关键规则：

1. `preset` 必填，顶层 `scoring: null` 不再承载生产权重。
2. 当前生产参数以 `config/quant_universe.yaml` 的 `presets` 为准。
3. Tuner 与 update_report 不应手写参数转换，必须通过 `quant_contract.py`。
4. `config_override` 只覆盖以下四个块：

```python
{
    "scoring": {...},
    "confidence": {...},
    "position": {...},
    "factors": {...},
}
```

---

## 3. 成交口径契约

成交口径 — 统一使用信号日收盘价成交（same_close）。

```text
信号日 = 执行日
成交价字段 = close
```

```python
get_execution_date(signal_date, all_dates)
execution_price_field()
```

回归测试：

```text
tests/test_quant_backtest_execution.py
```

---

## 4. 数据加载契约

### 4.1 默认 CSV 路径

```text
data/quant/{code}_daily.csv
data/quant/{code}_weekly.csv
```

由：

```text
scripts/quant_data_fetcher.py
```

维护。

### 4.2 preloaded 模式

Tuner 会预加载 CSV 和盘中 cache，然后通过 `preloaded` 传入：

```python
{
    "all_daily": {code: daily_df},
    "all_weekly": {code: weekly_df},
    "market_regimes": {...},
    "hs300_above_ma": {...},
    "hs300_ma_rising": {...},
}
```

若 `preloaded["all_daily"]` 存在，回测引擎跳过磁盘 CSV 加载。

### 4.3 HS300 MA Trend

当 `confidence.type == "ma_trend"` 时，回测引擎需要 HS300 MA 缓存：

```text
benchmark_data.py::load_hs300_daily_cached()
benchmark_data.py::build_hs300_weekly()
benchmark_data.py::build_ma_trend_cache()
```

Tuner 可提前构建并通过 `preloaded` 注入，CLI 则由回测引擎自行加载。

### 4.4 数据架构：筛选池 vs 量化池

回测引擎只消费量化池数据。筛选工作流独立运行，不依赖量化池。数据结构、缓存文件名和 API 说明以 `docs/design/data-architecture.md` 为唯一事实源，本文不重复维护。

---

## 6. 主回测循环

主循环遍历调仓日 `rebalance_dates`。

### 6.1 调仓日

```text
rebalance_freq = daily      -> 每个交易日
rebalance_freq = W-FRI      -> 每周最后一个交易日
```

回测会额外找 `user_start` 前最后一个调仓日作为初始建仓日。

### 6.2 执行日和成交价

每个信号日先转执行日：

```python
execution_date = get_execution_date(rb_date, all_dates)
price_field = execution_price_field()
```

然后从执行日取 `open` 或 `close`。

### 6.3 因子查找

对每支 ETF：

1. 用执行日取成交价格。
2. 用信号日二分查找预计算因子数组（`searchsorted`）。
3. F1/F3/F7 任一为 NaN 则跳过该 ETF。

### 6.4 综合分

```text
composite = F1*w1 + F3*w3 + F7*w7 + bias
```

F2/F4/F5/F6 已退役，权重恒为 0。F7 NaN 时 fallback 为 0.5。

### 6.5 Top-N 与分数带

1. 先取 `composite.nlargest(max_holdings)`。
2. 若 `score_band > 0` 且已有持仓，新标的必须比被挤出标的高出 `score_band` 才能替换。
3. 初始建仓日不应用历史持仓约束。

### 6.6 总仓位

当前主线是 `ma_trend`：

```text
HS300 above MA -> ma_bull_pos
HS300 below MA -> ma_bear_pos
```

若 `ma_direction_confirm=True`：

```text
只有“价格在 MA 上/下方”和“MA 方向”一致时才切换；否则维持上次状态。
```

非 MA 趋势的信心函数（regime/dd_trigger/momentum_crash）已从 Tuner UI 移除，引擎代码保留但不推荐使用。

### 6.7 仓位分配

当前采用全池分数标准化 + softmax：

```text
z_i = (score_i - mean(all_scores)) / std(all_scores)

# 动态 C（c_sensitivity > 0 时生效）:
dispersion = std(z_top6)           # Top-6 的 z-score 离散度
c_mult = 1 + c_sensitivity × (dispersion − 0.5)
effective_c = concentration × max(c_mult, 0.1)

relative_weight_i = softmax(z_i * effective_c)
target_position_i = relative_weight_i * total_target
```

- `c_sensitivity = 0`: 禁用动态 C，所有 ETF 使用相同 concentration 参数
- `c_sensitivity = 1.0`: 离散度=0.5 时不变，强共识放大，弱共识缩小
- 无 clamp —— 天然分布在安全区间

再按 `position.discretize_step` 离散化。

### 6.8 交易执行

统一函数：

```python
_execute_rebalance(...)
```

顺序：

```text
1. 全卖：不在目标范围内的持仓
2. 减仓：仍在目标范围但目标下降
3. 加仓：目标上升，按目标仓位和成交额排序，最后一支吸收残量但不超目标
```

佣金：

```text
position.commission_rate
```

---

## 7. NAV 二次计算

主循环负责生成信号和交易历史；之后还有一次逐日 NAV 计算。

要求：

1. 二次计算必须使用同一个 `execution_price_field()`。
2. 二次计算必须复用 `_execute_rebalance()`。
3. 不允许主循环和二次计算各自维护不同的买卖逻辑。
4. 若修改成交口径、交易顺序、残量处理，必须同时确认主循环和二次计算一致。

相关测试：

```text
tests/test_quant_backtest_execution.py
tests/test_quant_consistency.py
scripts/quant_consistency_check.py
```

---

## 8. 输出契约

### 8.1 `nav_df`

至少包含：

```text
date
nav
```

`nav` 为资金曲线绝对值，初始资金默认 1,000,000。

### 8.2 `signal_history`

每个元素代表一个调仓信号，常用字段包括：

```text
date / signal_date    — 信号日和实际执行日
positions             — {code: target_weight}  目标仓位
detail                — {code: {f1, f3, f7, score, z, position, price, ...}}  逐ETF因子明细
regime                — "ma_above" / "ma_below"
```

Tuner 和 payload 会把它序列化为前端可消费格式。

### 8.3 `extra`

常用字段：

```text
total_commission
debug_snapshots
trade_log        # [{code, buy_date, sell_date, buy_price, sell_price, shares, pnl_pct}, ...]
                 # FIFO 配对逐笔交易记录，含期末未平仓按最后收盘价虚拟平仓
```

---

## 9. 参数契约与 Tuner 交接

Tuner 不直接拼后端配置，必须通过 `quant_contract.py`：

```text
config/quant_universe.yaml preset
  -> quant_contract.preset_to_tuner_params()
  -> /api/presets
  -> templates/tuner.html
  -> /api/run
  -> quant_contract.tuner_params_to_config_override()
  -> run_backtest(config_override=...)
```

新增参数时必须同步：

```text
src/etf_report/core/quant_contract.py
templates/tuner.html
tests/test_quant_contract.py
docs/runbook/v2-quant/overview.md（如契约或路由变化）
```

---

## 10. 一致性守卫

### 10.1 单元测试

```bash
python -m pytest tests/test_quant_contract.py
python -m pytest tests/test_quant_backtest_execution.py
python -m pytest tests/test_quant_consistency.py
```

### 10.2 结果级一致性检查

```bash
# 检查三派 CLI vs Tuner 一致性
python scripts/quant_consistency_check.py --preset gam-1 --start 2026-05-01 --end 2026-06-01  # 赌徒1
python scripts/quant_consistency_check.py --preset zen-1 --start 2026-05-01 --end 2026-06-01  # 禅修者1
python scripts/quant_consistency_check.py --preset act-1 --start 2026-05-01 --end 2026-06-01  # 精算师1
```

检查内容：

```text
Direct preset: run_backtest(preset=...)
Tuner contract: preset -> tuner params -> config_override -> run_backtest(...)
```

若 FAIL，说明 `quant_universe.yaml`、`quant_contract.py`、`quant_tuner.py` 或 `quant_backtest.py` 出现结果级漂移。

---

## 11. 修改清单

### 11.1 修改成交口径

必须检查：

```text
execution_price_field()
get_execution_date()
run_backtest() 主循环
NAV 二次计算
(已移除)
quant_contract.py schema 与映射
tests/test_quant_backtest_execution.py
```

### 11.2 修改因子

必须检查：

```text
scripts/quant_factors.py
scripts/quant_backtest.py::_precompute_factors()
src/etf_report/core/quant_contract.py（如有参数）
templates/tuner.html（如有控件/说明）
docs/design/backtest-engine.md
tests/test_quant_factors.py
```

### 11.3 修改仓位分配

必须检查：

```text
z-score / softmax 逻辑
concentration 参数
离散化逻辑
_execute_rebalance()
NAV 二次计算
tests/test_quant_consistency.py
scripts/quant_consistency_check.py
```

### 11.4 修改 preset 或参数契约

必须检查：

```text
config/quant_universe.yaml
src/etf_report/core/quant_contract.py
scripts/quant_tuner.py
scripts/update_report.py payload helper
tests/test_quant_contract.py
tests/test_update_report.py -k "quant_preset_params or quant_payload_config_section"
```

---

## 12. 不属于本文的内容

| 内容 | 去哪里 |
|---|---|
| 系统总览、文件职责、变更路由 | `overview.md` / `../runbook/v2-quant/overview.md` |
| 启动 Tuner、刷新数据、排障 | `../runbook/v2-quant/overview.md` |
| 当前最优参数和研究结论 | `../../research/params/README.md` / `../../research/strategy/README.md` |
| 历史方法论和研究备忘 | `../../research/07-quant-methodology.md` / `../../research/08-quant-research-memo.md` |
