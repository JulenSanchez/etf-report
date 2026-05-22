# Quant System — 量化回测系统入口

本文是 `etf-report` 量化回测系统的第一入口。任何涉及 Tuner、回测引擎、因子、preset、量化数据、正式页量化板块或量化研究归档的任务，先读本文，再按任务类型跳转。

## 0. AI 首读规则

1. 先读本文，确认任务落在哪条管线。
2. 再读对应事实源，不要只凭上下文猜文件。
3. 参数、因子、回测逻辑、Tuner UI、正式页 payload 任一变更，都必须检查“变更路由表”。
4. 当前参数和资产池只以 `config/quant_universe.yaml` 为准；其他文档不得复制一份长期维护的“当前参数”。
5. Tuner 页面里的“参数原理”是用户帮助层，不是工程事实源；若与 `scripts/quant_backtest.py` 冲突，以代码和 `docs/BACKTEST_ENGINE.md` 为准。

## 1. 系统边界

量化系统分为四条边界清晰的子系统：

| 子系统 | 入口 | 职责 | 不负责 |
|---|---|---|---|
| 数据层 | `scripts/quant_data_fetcher.py` | 拉取 ETF K 线，维护 `data/quant/*.csv` | 解释策略、保存参数 |
| 回测引擎 | `scripts/quant_backtest.py` | 唯一回测计算核心，输出 NAV 与 signal history | Flask、HTML、用户交互 |
| 工坊 Tuner | `scripts/quant_tuner.py` + `templates/tuner.html` | 本地交互调参、运行回测、保存 preset | 定义真实回测逻辑 |
| 橱窗正式页 | `scripts/update_report.py` + `assets/js/quant-main.js` | 生成并渲染静态量化结果 | 交互调参、写回 YAML |
| 研究归档 | `research/` | 保存实验、证据、promotion 记录 | 作为当前参数事实源 |

## 2. 当前架构图

```text
config/quant_universe.yaml
  ├─ universe: ETF 池
  └─ presets: 当前策略参数

scripts/quant_data_fetcher.py
  └─ data/quant/*.csv

scripts/quant_backtest.py  ← 唯一回测引擎
  ├─ CLI 直接调用
  ├─ scripts/quant_tuner.py       ← 工坊：Flask + Tuner UI
  └─ scripts/update_report.py ← 橱窗：assets/js/quant_payload.js
     scripts/quant_build_payload.py 是兼容 wrapper，内部调用 update_report 路径

assets/js/quant_payload.js
  └─ index.html + assets/js/quant-main.js
```

## 3. 事实源优先级

| 问题 | 第一事实源 | 第二事实源 |
|---|---|---|
| 当前 ETF 池 / preset 参数 | `config/quant_universe.yaml` | `research/params/README.md` 只看来源证据 |
| 回测实际计算过程 | `scripts/quant_backtest.py` | `docs/BACKTEST_ENGINE.md` |
| Tuner API 与缓存 | `scripts/quant_tuner.py` | `runbooks/QUANT_RUNBOOK.md` |
| Tuner 前端控件和说明 | `templates/tuner.html` | 本文的参数契约章节 |
| 正式页量化展示 | `assets/js/quant-main.js` | `scripts/update_report.py` / `scripts/quant_build_payload.py` wrapper |
| 长任务、启动、刷新、排障 | `runbooks/QUANT_RUNBOOK.md` | `docs/01-数据源与工具生态.md` |
| 策略实验和历史结论 | `research/` | `docs/08-quant-research-memo.md` |
| ETF 贡献指标定义与分析 | `docs/ETF_CONTRIBUTION_FRAMEWORK.md` | `scripts/quant_tuner.py` `_compute_etf_contributions()` |
| 早期三因子方法论 | `docs/07-quant-methodology.md` | 仅作历史参考 |

## 4. 文件职责表

| 文件 | 职责 | 修改触发 |
|---|---|---|
| `config/quant_universe.yaml` | 当前 ETF 池、preset、仓位、因子参数 | 改资产池、当前策略、Tuner 保存参数 |
| `scripts/quant_factors.py` | 单因子原始值与映射函数 | 新增/修改 F1-F7 因子定义 |
| `scripts/quant_backtest.py` | 唯一回测引擎、调仓、NAV、统计 | 改回测逻辑、仓位分配、执行时点 |
| `scripts/quant_contract.py` | YAML preset ↔ Tuner params ↔ config_override 的参数契约 | 新增/修改 Tuner 参数 |
| `scripts/quant_tuner.py` | Flask API、预加载缓存、调用参数契约和回测引擎 | 改 Tuner API、缓存、保存行为 |
| `templates/tuner.html` | Tuner 控件、交互、用户帮助文案 | 改前端控件、参数说明、可视化 |
| `scripts/update_report.py` | 正式页静态 payload 生成主路径 | 改正式页量化数据结构 |
| `scripts/quant_build_payload.py` | 正式页 payload 兼容 CLI wrapper，调用 update_report 路径 | 改 payload CLI 入口 |
| `assets/js/quant_payload.js` | 生成产物：`window.__QUANT_RUNTIME__` | 由脚本生成，不手改 |
| `assets/js/quant-main.js` | 正式页量化板块渲染 | 改 index.html 量化展示 |
| `scripts/fetch_etf_metadata.py` | 拉取全部 ETF 的规模(AUM)和前十大重仓股 → `data/quant/etf_metadata.json` | 新增/移除 ETF、定期更新持仓数据 |
| `data/quant/etf_metadata.json` | ETF 元数据事实源（AUM + 成分股），Tuner 启动时加载 | 人工或脚本更新后自动生效 |
| `docs/ETF_CONTRIBUTION_FRAMEWORK.md` | ETF 贡献分析框架：指标定义、分析流程、淘汰规则 | 改贡献计算逻辑或新增指标后同步 |
| `docs/BACKTEST_ENGINE.md` | 回测引擎契约 | 改 `run_backtest()` 或核心算法后同步 |
| `runbooks/QUANT_RUNBOOK.md` | 运维和排障手册 | 改启动、刷新、长任务、数据源规则后同步 |
| `research/` | 实验记录和 promotion 证据 | 策略研究、参数优化、结论沉淀 |

## 5. 变更路由表

### 5.1 修改一个因子

必须检查：

```text
scripts/quant_factors.py
scripts/quant_backtest.py
config/quant_universe.yaml
templates/tuner.html
scripts/quant_tuner.py
docs/BACKTEST_ENGINE.md
tests/test_quant_factors.py
```

如果影响当前策略结论，还要更新：

```text
research/strategy/README.md
research/params/README.md
docs/08-quant-research-memo.md
```

### 5.2 新增一个 Tuner 参数

必须检查：

```text
templates/tuner.html                  # 控件、getParams/setParams、URL 参数
scripts/quant_contract.py              # 参数映射唯一契约
scripts/quant_tuner.py                 # /api/presets、/api/run、/api/save 接线
scripts/quant_backtest.py              # 是否消费该参数
config/quant_universe.yaml             # preset 默认值
docs/BACKTEST_ENGINE.md                # 引擎语义
tests/                                # 参数映射或引擎测试
```

新增参数时，重点防止三处映射漂移：

```text
YAML preset -> /api/presets -> 前端控件
前端控件 -> /api/run -> config_override
前端控件 -> /api/save -> YAML preset
```

### 5.3 修改回测执行逻辑

必须检查：

```text
scripts/quant_backtest.py
docs/BACKTEST_ENGINE.md
templates/tuner.html 的“参数原理”
scripts/update_report.py payload helper
scripts/quant_build_payload.py wrapper
assets/js/quant-main.js（若展示结构受影响）
tests/ 中相关回归测试
```

典型执行逻辑包括：预热、初始建仓、调仓日、执行价格、分数带、Top-N、仓位分配、交易顺序、NAV 统计。

### 5.4 修改当前 preset 或资产池

必须检查：

```text
config/quant_universe.yaml
scripts/quant_data_fetcher.py（资产池变更时）
research/params/README.md（参数来源）
research/strategy/README.md（策略线描述）
runbooks/QUANT_RUNBOOK.md（若运维摘要涉及当前策略）
templates/tuner.html（不得残留硬编码默认值）
```

### 5.5 修改正式页量化板块

必须检查：

```text
scripts/update_report.py payload helper
scripts/quant_build_payload.py wrapper
assets/js/quant_payload.js（生成结果）
assets/js/quant-main.js
index.html 的量化 DOM
docs/BACKTEST_ENGINE.md（若 payload 语义变化）
```

## 6. 参数契约

当前参数经过三层转换：

```text
config/quant_universe.yaml presets
  -> scripts/quant_contract.py 统一参数契约
  -> scripts/quant_tuner.py /api/param_schema + /api/presets
  -> templates/tuner.html 控件（schema 拉取失败不阻塞主流程）
  -> scripts/quant_tuner.py /api/run config_override
  -> scripts/quant_backtest.py run_backtest()
```

单位约定：

| 参数类型 | YAML / 引擎 | Tuner UI | 注意 |
|---|---:|---:|---|
| 权重 `w1/w2/w3/w6/w7` | 0-1 | 0-100 | UI 传入后除以 100 |
| `score_band` | 0-1 | 百分数 | 3% 在 YAML 是 `0.03` |
| `f6_drop_thresh` | 0-1 | 百分数 | 2.5% 在 YAML 是 `0.025` |
| `discretize_step` | 0-1 | 当前 UI 直接传小数 | 确认前端控件不要混用 5 与 0.05 |
| `ma_bull_pos/ma_bear_pos` | 0-1 | 0-1 | 页面展示可转百分比 |
| `f7_window` | 天数 | 天数 | 不是代码常量，来自 preset 或滑块 |
| `execution_timing` | `same_close` / `next_open` | 同左 | Tuner 和引擎必须一致支持 |

`scripts/quant_contract.py` 集中维护：

```text
preset_to_tuner_params()
tuner_params_to_config_override()
tuner_params_to_preset_patch()
validate_tuner_params()
build_presets_response()
get_param_schema()
```

## 7. API 契约

| API | 方法 | 职责 | 主要消费者 |
|---|---|---|---|
| `/` | GET | 返回 `templates/tuner.html` | 浏览器 |
| `/api/status` | GET | 返回 Tuner 是否 ready | Tuner loading |
| `/api/param_schema` | GET | 返回统一参数 schema（分组、单位、engine_path） | 前端说明 / 调试工具 / 文档校验 |
| `/api/presets` | GET | YAML preset 转前端参数 | preset cards / 控件初始化 |
| `/api/run` | POST | 前端参数转 config_override 并调用 `run_backtest()` | 运行回测 |
| `/api/save` | POST | 保存当前参数到 preset 或 override | 保存参数 |
| `/api/kline` | GET | 单 ETF K 线复盘数据 | 快照 / K 线图 |
| `/api/etf_prices` | GET | ETF 价格序列 | 辅助图表 |

## 8. 验证守卫

最小验证按变更类型选择：

| 变更 | 最小验证 |
|---|---|
| 只改文档 | 检查交叉引用路径存在，确认事实源优先级不冲突 |
| 改因子 | `pytest tests/test_quant_factors.py`，再跑一个短窗口回测 |
| 改回测引擎 | 跑 CLI 回测 + Tuner `/api/run` 同参数对比 |
| 改 Tuner 参数 | `pytest tests/test_quant_contract.py`，并确认 `/api/param_schema -> /api/presets -> UI -> /api/run -> /api/save -> /api/presets` 往返一致；如需当前策略摘要，由 AI 改参数时同步或用户显式要求更新 |
| 改参数契约/回测/Tuner 接线 | `python scripts/quant_consistency_check.py --preset daily_aggressive --start 2025-01-01 --end 2026-05-19` |
| 改正式页 payload | `python scripts/quant_build_payload.py` 后本地打开 `index.html` |
| 改资产池 | `python scripts/quant_data_fetcher.py --code <新ETF>` 或按需全量/增量更新 |

### 8.1 回测一致性工具

`quant_consistency_check.py` 用于确认同一 preset 在两条路径下结果一致：

```text
Direct preset: run_backtest(preset=...)
Tuner contract: preset -> tuner params -> config_override -> run_backtest(...)
```

常用命令：

```bash
python scripts/quant_consistency_check.py --preset daily_aggressive --start 2025-01-01 --end 2026-05-19
```

如果这里 FAIL，说明 `quant_universe.yaml`、`quant_contract.py`、`quant_tuner.py` 或 `quant_backtest.py` 之间出现结果级漂移，应先修一致性再继续调参。

## 9. 当前清理方向

已知需要持续清理的方向：

1. 历史文档中可能仍残留旧 25 支 ETF、F1-F5、旧 payload 路径等口径；若任务依赖当前状态，先回到本文和 `config/quant_universe.yaml` 核对。
2. `docs/07-quant-methodology.md` 是早期三因子方法论，不能作为当前系统事实源。
3. `templates/tuner.html` 的参数原理说明已降级为帮助层；“策略视角”类静态建议已删除。当前值以左侧滑块和参数契约表为准。
4. `scripts/quant_contract.py` 已承接 `/api/presets`、`/api/run`、`/api/save` 的核心参数映射；后续新增参数必须先改契约和测试。
5. 回测引擎测试覆盖不足，后续优先补参数映射、执行时点、分数带、仓位分配测试。
