# etf-report 系统设计

> 设计师视角：概括地、统领地描述设计原则和系统架构。可以包含具体细节，但出发点是"这个系统是什么样的，为什么这样设计"。
> 与之对照：`docs/runbook/` 是运维视角——"出问题了怎么排查，实际操作怎么做"。

## 一、系统架构

```
┌─────────────────────────────────────────────┐
│                 正式页 (index.html)           │
│         assets/js/quant-main.js              │
│         assets/js/quant_payload.js           │
└──────────────┬──────────────────────────────┘
               │ 静态 payload
┌──────────────▼──────────────────────────────┐
│           scripts/update_report.py           │
│           scripts/quant_build_payload.py     │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│              量化引擎                         │
│  ┌─────────────────────────────────────┐    │
│  │ scripts/quant_backtest.py            │    │
│  │   唯一回测引擎                        │    │
│  │   run_backtest() → (nav_df, signals) │    │
│  └─────────────────────────────────────┘    │
│  ┌──────────────┐ ┌──────────────────────┐  │
│  │ quant_factors │ │ quant_contract      │  │
│  │ 因子原始值     │ │ YAML↔Tuner↔引擎参数  │  │
│  │ 映射函数       │ │ 三层转换契约         │  │
│  └──────────────┘ └──────────────────────┘  │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│              工坊 Tuner                       │
│     scripts/quant_tuner.py (Flask :5179)     │
│     templates/tuner.html                     │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│              数据层                           │
│  config/quant_universe.yaml  (ETF池+preset)  │
│  data/quant/{code}_daily.csv (日线)          │
│  data/quant/{code}_weekly.csv (周线)         │
│  data/quant/etf_metadata.json (规模+持仓)     │
└─────────────────────────────────────────────┘
```

## 二、端到端数据流

```
拉数 → 清洗 → 预计算 → 回测 → payload → 前端
 │       │        │        │       │        │
 │       │        │        │       │        └─ tuner-ui.md / assets/js/
 │       │        │        │       └─ tuner.md (Tuner) / v1-report.md (正式页)
 │       │        │        └─ backtest-engine.md
 │       │        └─ factors.md + backtest-engine.md §12
 │       └─ data-architecture.md / tuner.md refresh_data
 └─ data-fetch.md / quant_data_fetcher.py
```

| 环节 | 输入 | 输出 | owner 文档 | 关键脚本 |
|------|------|------|----------|---------|
| 拉数 | ETF 代码 + 日期范围 | `data/quant/{code}_daily.csv` | `data-fetch.md` | `quant_data_fetcher.py` |
| 清洗 | 原始 CSV | 拆股调整后 CSV + intraday cache | `data-architecture.md` / `tuner.md` | `quant_tuner.py::refresh_data` |
| 预计算 | CSV + 参数 | 因子缓存 (pickle) | `factors.md` | `quant_backtest.py::_precompute_factors` |
| 回测 | 因子 + 参数 | `nav_df` + `signal_history` + `extra` | `backtest-engine.md` | `quant_backtest.py::run_backtest` |
| payload | 回测结果 | `quant_payload.js` / `/api/run` 响应 | `tuner.md` / `v1-report.md` | `quant_tuner.py` / `quant_build_payload.py` |
| 前端 | payload JSON | 渲染图表/表格 | `tuner-ui.md` | `templates/tuner.html` / `assets/js/` |

## 三、子系统设计

| 子系统 | 设计文档 | 核心代码 |
|--------|---------|---------|
| 因子体系（F1/F3/F7） | `factors.md` | `scripts/quant_backtest.py:_precompute_factors()` |
| 回测引擎（循环/仓位/信心/执行） | `backtest-engine.md` | `scripts/quant_backtest.py::run_backtest()` |
| 两融账户与杠杆风险 | `margin-account-model.md` | v3.9 账户层建模 |
| ETF 贡献分析 | `etf-contribution.md` | `scripts/quant_tuner.py:_compute_etf_contributions()` |
| 参数契约 | `src/etf_report/core/quant_contract.py` | 三层转换（YAML↔Tuner↔引擎） |

## 四、设计原则

### 唯一引擎

`run_backtest()` 是回测的唯一计算入口。CLI、Tuner、正式页 payload 全部通过参数组合调用同一函数。不允许任何路径复制回测逻辑。

### 参数契约

```
config/quant_universe.yaml preset
  → quant_contract.py (三层转换)
  → Tuner API / CLI / 正式页
```

所有参数映射集中在 `quant_contract.py`。新增参数必须改 contract、Tuner 控件、引擎消费、测试——四项对齐。完整生命周期（新增/修改/退役）见 [`docs/runbook/v2-quant/param-lifecycle.md`](../runbook/v2-quant/param-lifecycle.md)。

### 日调仓 + 分数带

当前所有 preset 使用日调仓（`rebalance_freq: daily`）。`score_band` 机制阻止小幅分数波动导致的频繁换仓。`same_close` 成交口径用于复盘回测。

### 三因子

当前活跃因子 F1/F3/F7。F2 已移除；F4/F5/F6 已于 2026-05~06 退役（权重=0，部分兼容代码仍保留）。

### 检查点/冻结模型（F1 抢跑）

F1 的周线 EMA 偏离通过 bitmask `f1_active_days` 控制更新频率。核心是三分支状态机：检查点（滚 EMA）、冻结（复用上一个检查点）、hold（复用上周值）。详见 `factors.md`。

## 五、运维手册

| 文档 | 内容 |
|------|------|
| `../runbook/v2-quant/overview.md` | 量化系统运维——启动、刷新、变更路由、排障 |
| `../runbook/v1-report.md` | 正式页报告工作流——生成、发布、企微推送 |
| `../runbook/release.md` | 发布门禁——验证、审计、GitHub Pages |
| `../runbook/audit.md` | 代码审计 |
| `../../scripts/health_check.py` | 健康检查入口 |

## 六、基准数据

当前稳定基线以 `plans/Board.md` 为准。ETF 池变更时必须重新跑当前基线对比，不在设计文档中复制 TR/MDD/Sharpe 等易变数字。
