# 量化运维手册

> 系统设计见 `../../architecture.md`，因子/引擎细节见 `../../architecture/design/`。

---

## 一、系统边界与文件职责

## 1. 系统边界

量化系统分为四条边界清晰的子系统：

| 子系统 | 入口 | 职责 | 不负责 |
|---|---|---|---|
| 数据层 | `scripts/quant_data_fetcher.py` | 拉取 ETF K 线，维护 `data/quant/*.csv` | 解释策略、保存参数 |
| 回测引擎 | `scripts/quant_backtest.py` | 唯一回测计算核心，输出 NAV 与 signal history | Flask、HTML、用户交互 |
| 工坊 Tuner | `scripts/quant_tuner.py` + `templates/tuner.html` | 本地交互调参、运行回测、保存 preset | 定义真实回测逻辑 |
| 橱窗正式页 | `scripts/update_report.py` + `assets/js/quant-main.js` | 生成并渲染静态量化结果 | 交互调参、写回 YAML |
| 研究归档 | `research/` | 保存实验、证据、promotion 记录 | 作为当前参数事实源 |
| **池管理** | `docs/ops/pool-change.md` | ETF 池批量新增/移除 SOP（跨筛选+量化） | 筛选规则本身（见 `scripts/scan_etf_universe.py`） |

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
| 回测实际计算过程 | `scripts/quant_backtest.py` | `../../architecture/design/backtest-engine.md` |
| Tuner API 与缓存 | `scripts/quant_tuner.py` | `docs/ops/quant/overview.md` |
| Tuner 前端控件和说明 | `templates/tuner.html` | 本文的参数契约章节 |
| 正式页量化展示 | `assets/js/quant-main.js` | `scripts/update_report.py` / `scripts/quant_build_payload.py` wrapper |
| 长任务、启动、刷新、排障 | `docs/ops/quant/overview.md` | `docs/01-数据源与工具生态.md` |
| 策略实验和历史结论 | `research/` | `research/08-quant-research-memo.md` |
| ETF 贡献指标定义与分析 | `../../architecture/design/etf-contribution.md` | `scripts/quant_tuner.py` `_compute_etf_contributions()` |
| 早期三因子方法论 | `research/07-quant-methodology.md` | 仅作历史参考 |

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
| `scripts/fetch_etf_metadata.py` | 拉取全部 ETF 的基金规模(AUM)和前十大重仓股 → `data/quant/etf_metadata.json` | 新增/移除 ETF、定期更新持仓数据 |
| `data/quant/etf_metadata.json` | ETF 元数据事实源（基金规模 + 成分股），Tuner 启动时加载 | 人工或脚本更新后自动生效 |
| `../../architecture/design/etf-contribution.md` | ETF 贡献分析框架：指标定义、分析流程、淘汰规则 | 改贡献计算逻辑或新增指标后同步 |
| `../../architecture/design/backtest-engine.md` | 回测引擎契约 | 改 `run_backtest()` 或核心算法后同步 |
| `docs/ops/quant/overview.md` | 运维和排障手册 | 改启动、刷新、长任务、数据源规则后同步 |
| `tests/test_quant_backtest_core.py` | 回测引擎结构、preset 差异、universe_filter、execution_timing 测试 | 改 `run_backtest()` 语义后同步 |
| `tests/test_quant_data_cache.py` | 共享数据缓存加载、cache key、结果读写 | 改 `quant_data_cache.py` 后同步 |
| `research/` | 实验记录和 promotion 证据 | 策略研究、参数优化、结论沉淀 |

---

## 二、变更路由

## 5. 变更路由表

**改动前先建基准。** 策略逻辑/参数/因子变更前，保存各 preset 的 NAV 序列、关键指标、ETF 因子样本。改动后对比确认无意外漂移。基准工具见 REQ-275。

### 5.1 修改一个因子

必须检查：

```text
scripts/quant_factors.py
scripts/quant_backtest.py
config/quant_universe.yaml
templates/tuner.html
scripts/quant_tuner.py
../../architecture/design/backtest-engine.md
tests/test_quant_factors.py
```

如果影响当前策略结论，还要更新：

```text
research/strategy/README.md
research/params/README.md
research/08-quant-research-memo.md
```

### 5.2 新增一个 Tuner 参数

必须检查：

```text
templates/tuner.html                  # 控件、getParams/setParams、URL 参数
templates/tuner.html                  # 导览 guide 块（guide-pos / guide-pipeline / guide-contract）同步更新
scripts/quant_contract.py              # 参数映射唯一契约（preset_to_tuner_params / tuner_params_to_config_override / PARAM_BOUNDS / get_param_schema）
scripts/quant_tuner.py                 # /api/presets、/api/run、/api/save 接线
scripts/quant_backtest.py              # 是否消费该参数
config/quant_universe.yaml             # preset 默认值
../../architecture/design/backtest-engine.md                # 引擎语义
tests/                                # 参数映射或引擎测试
```

新增参数时，重点防止五处映射漂移：

```text
YAML preset -> /api/presets -> 前端控件
前端控件 -> /api/run -> config_override
前端控件 -> /api/save -> YAML preset
导览 guide 块（guide-pos / guide-pipeline / guide-contract）与控件/引擎同步
参数契约 schema（get_param_schema / PARAM_BOUNDS）与控件/引擎同步
```

### 5.3 修改回测执行逻辑

必须检查：

```text
scripts/quant_backtest.py
../../architecture/design/backtest-engine.md
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
docs/ops/quant/overview.md（若运维摘要涉及当前策略）
templates/tuner.html（不得残留硬编码默认值）
```

#### ETF 增/删/替 标准流程

##### 核心原则

1. **逐支执行**：改一个池配置文件条目 = 一次替换。要么完成（验证通过），要么回退（恢复旧条目）。不允许多支替换混在一起跑一次验证。
2. **基线先于改动**：改池配置文件前必须先保存当前精算师和赌徒的 6 年指标快照（总收益率/AR/Sharpe/Calmar/最大回撤）。没有基线不动配置。
3. **同池验证**：A/B 对比必须在 ETF 数量完全相同的池上运行。严禁用 `universe_filter` 做 A/B 对比（它会 silently 丢弃不在 YAML 中的代码，导致两池 ETF 数量不同）。
4. **数据交叉验证**：同指数/同赛道替换，必须检查新旧 ETF 在重叠日期上的价格比值稳定性。比值跳变 >5% 视为数据异常，必须排查。
5. **验证标准**：替换后精算师和赌徒的 6 年总收益率不得低于替换前基线的 95%。任一跌破 → 回退。

##### 增（新 ETF 入池）

1. **事实确认**：AKShare 核验代码、全称、市场、类型、上市日期。
2. **拉取 K 线**：`python scripts/quant_data_fetcher.py --code <code>`，确认日线 ≥ 250 行。
3. **更新元数据**：`python scripts/fetch_etf_metadata.py`，确认 top10 持仓已写入。
4. **原子新增**：编辑 `config/quant_universe.yaml`，在对应 sector 下插入新条目。
5. **回测验证**：跑 6 年 + smoke test（精算师 + 赌徒），确认无报错、总收益率无意外漂移。
6. **收口**：确认 Tuner 加载正常、`scan_etf_universe.py` 识别新 ETF。

##### 删（ETF 退池）

1. **事实确认**：确认退池原因（清盘/规模过小/数据不可用/策略淘汰）。
2. **保存基准**：删前跑一次 6y 全 preset 快照。
3. **原子删除**：编辑 `config/quant_universe.yaml`，删除对应条目。
4. **回测验证**：跑 6y 确认无报错，记录 TR 变化。
5. **收口**：全项目 `grep` 旧代码残留；Tuner 加载正常。

##### 替（旧换新）

> ⛔ **执行前强制自检（逐条确认后才能动手）**：
> 1. 旧/新 ETF 是否跟踪同一指数或属于同一赛道？（不是同一赛道 → 不替换，修分组）
> 2. 我是否已读完下方 9 个步骤？
> 3. 我之前是否跳过过任何一步？（如果是 → 先补上）
> 4. 我是否准备用 `yaml.dump` 编辑 YAML？（如果是 → 停下来，用文本替换）
> 5. 替换完成后我会重建周线并验证吗？

**这是唯一正确的 A/B 对比流程。禁止跳步。**

1. **保存基线**：改池配置文件前，跑一次当前池 6 年全策略（至少精算师+赌徒），记录总收益率/AR/Sharpe/Calmar/最大回撤。保存到 `_working/etf_replace_baseline_<旧code>_<新code>.json`。

2. **事实确认**：AKShare 核验旧/新 ETF 代码、全称、市场、类型、跟踪指数。确认两者跟踪同一指数或同一赛道。记录映射。

3. **静默拉取**：拉取新 ETF K 线。必须满足：
   - 日线行数 ≥ 旧 ETF 日线行数（数据覆盖不能缩水）
   - 重叠日期 ≥ 旧 ETF 日期的 95%（不能有大量缺失）
   - 单日涨跌幅 > 15% 的天数 = 0（排除数据源错误/异常拆分）
   - 上市时间显著晚于旧 ETF 的不替换，保留旧标的

4. **静默拉元数据**：`python scripts/fetch_etf_metadata.py`，确认新 ETF 的 top10 持仓已写入。

5. **数据交叉验证**（同指数替换必做）：
   - 加载新旧 ETF 日线 CSV，找出重叠日期
   - 计算每日价格比值 `ratio = new_close / old_close`
   - 比值应满足：`std(ratio) / mean(ratio) < 3%`
   - 不满足 → **中止替换，排查原因**
   - 将交叉验证结果写入基准文件

6. **原子替换**：编辑 `config/quant_universe.yaml`，删除旧条目、插入新条目。
   - `market` 字段以 AKShare 实际数据为准（新旧可能不同，如 sz↔sh）
   - `name` 使用短名（≤6 字，去掉"ETF"和基金公司后缀），保持与池内其他 ETF 一致的命名风格
   - **必须保留 YAML 文件头部的注释**（字段说明等），禁止用 `yaml.dump` 覆盖全文件
   - 若修改过程中误清注释，用 `git checkout` 恢复后重新编辑

7. **重建周线**：新 ETF 拉完日线后必须运行 `rebuild_weekly_from_daily()` 生成周线 CSV。步骤 3 已拉取日线，此步确保周线存在。

8. **同池回测验证**（不可跳过，不可用 universe_filter 替代）：
   - 直接跑替换后全池 6 年（精算师 + 赌徒），不需要 universe_filter
   - 对比步骤 1 的基线快照
   - **验证标准**（全部满足才算通过）：
     - 精算师和赌徒的 6 年总收益率 ≥ 基线的 95%
     - 最大回撤恶化 ≤ 2 个百分点（如基线 -18% → 替换后不得低于 -20%）
     - AR/Sharpe/Calmar 无异常恶化
   - 任一 preset 任一条件不满足 → **立即回退 YAML，恢复旧条目**

9. **收口**：
   - `grep` 旧代码在项目中的残留
   - 确认 Tuner 加载正常（`/api/presets` 返回 45 支）
   - 确认 `scan_etf_universe.py` 识别新 ETF
   - **写入替换记录**到 `research/promoted/YYYY-MM-DD_<名称>_替换.md`，记录：替换原因、新旧对比、回测指标变化
   - 将基准文件从 `_working/` 移到 `research/promoted/`

##### 回退（替换失败时）

1. **确认失败原因**：检查步骤 5（交叉验证）或步骤 8（回测验证）的具体失败项。
2. **原子回退**：编辑 `config/quant_universe.yaml`，恢复旧条目的 code/name/market。使用 `git checkout` 兜底。
3. **验证回退**：跑一次 6 年确认总收益率回到替换前基线（偏差 < 1%）。
4. **记录**：在 `research/promoted/` 中记录回退决定和原因（如"513350 标普油气：数据交叉验证失败，比值跳变 9.14%"）。
5. **清理**：可选删除新 ETF 的日线/周线 CSV（保留也可，供后续再次评估）。
6. **重要**：回退后必须确认定时任务（preclose_push）和 Tuner 都能正常工作。

##### 多支替换

**一次只替换一支。** 多支替换必须串行，每支独立走完整「替」流程。前一支持续验证通过才能开始下一支。严禁 3 支一起改然后跑一次回测。

### 5.5 修改正式页量化板块

必须检查：

```text
scripts/update_report.py payload helper
scripts/quant_build_payload.py wrapper
assets/js/quant_payload.js（生成结果）
assets/js/quant-main.js
index.html 的量化 DOM
../../architecture/design/backtest-engine.md（若 payload 语义变化）
```

### 5.6 废弃一个 Tuner 参数或因子

走 §5.2 的逆向流程，从所有映射层中移除：

```text
templates/tuner.html                  # 移除控件、getParams/setParams、导览 guide 块
scripts/quant_contract.py              # 移除 schema 条目、PARAM_BOUNDS、preset_to_tuner_params
scripts/quant_tuner.py                 # 若 /api/save 涉及该参数
scripts/quant_backtest.py              # 若引擎消费该参数（权重归零即可，不删逻辑）
config/quant_universe.yaml             # 所有 preset 中移除该参数
../../architecture/design/backtest-engine.md                # 移除相关章节
tests/                                # 更新引用
```

**最后一步——确认零残留**：用被移除的参数名/ID/关键字对全项目做 grep，确保所有文件中不再有活动引用。F6 清退时漏掉这一步，导致 `$id('w6')` 等 JS 引用残留在 `getParams`/`setParams`/`getWeightTotal` 中，运行时 `parseInt(null)`=NaN 使权重校验失败，回测按钮被禁用。

```bash
grep -rn 'w6\|f6_\|F6' templates/ scripts/ config/ docs/ --include='*.html' --include='*.py' --include='*.yaml' --include='*.md'
```

**分支选择**：

| 情况 | 动作 |
|------|------|
| 纯实验，无证据价值 | 直接删除所有痕迹 |
| 有对比数据，可作为历史参考 | 代码保留（加 `# DEPRECATED` 注释），研究数据归档到 `research/strategy/{name}-retired/`，在 `research/strategy/README.md` 的 Tried & Failed 中记录 |
| 被新因子替代 | 同"有对比数据"，额外在废弃因子的代码注释中注明替代者 |

F6（动能衰竭惩罚）是典型的"被新因子替代 + 有对比数据"案例：F7 在组合策略中综合表现更优，代码保留，研究归档，UI/契约/schema 全部移除。详见 research/strategy/2026-05-28-research-archive.md。

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
| 权重 `w1/w3/w7` | 0-1 | 0-100 | UI 传入后除以 100 |
| `score_band` | 0-1 | 百分数 | 3% 在 YAML 是 `0.03` |
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

---

## 三、API 契约

## 7. API 契约

| API | 方法 | 职责 | 主要消费者 |
|---|---|---|---|
| `/` | GET | 返回 `templates/tuner.html` | 浏览器 |
| `/api/data_status` | GET | 返回 Tuner ready 状态 / 数据新鲜度 | Tuner loading |
| `/api/param_schema` | GET | 返回统一参数 schema（分组、单位、engine_path） | 前端说明 / 调试工具 / 文档校验 |
| `/api/presets` | GET | YAML preset 转前端参数 | preset cards / 控件初始化 |
| `/api/run` | POST | 前端参数转 config_override 并调用 `run_backtest()` | 运行回测 |
| `/api/save` | POST | 保存当前参数到 preset 或 override | 保存参数 |
| `/api/kline` | GET | 单 ETF K 线复盘数据 | 快照 / K 线图 |
| `/api/etf_prices` | GET | ETF 价格序列 | 辅助图表 |

---

## 四、验证守卫与一致性检查

## 8. 验证守卫

最小验证按变更类型选择：

| 变更 | 最小验证 |
|---|---|
| 只改文档 | 检查交叉引用路径存在，确认事实源优先级不冲突 |
| 改因子 | `pytest tests/test_quant_factors.py`，再跑一个短窗口回测 |
| 改回测引擎 | 跑 CLI 回测 + Tuner `/api/run` 同参数对比；`pytest tests/test_quant_backtest_core.py` |
| 改 Tuner 参数 | `pytest tests/test_quant_contract.py`，并确认 `/api/param_schema -> /api/presets -> UI -> /api/run -> /api/save -> /api/presets` 往返一致；如需当前策略摘要，由 AI 改参数时同步或用户显式要求更新 |
| 改参数契约/回测/Tuner 接线 | `python scripts/quant_consistency_check.py --preset zen-1 --start 2025-01-01 --end 2026-05-19` |
| 改正式页 payload | `python scripts/quant_build_payload.py` 后本地打开 `index.html` |
| 改资产池 | `python scripts/quant_data_fetcher.py --code <新ETF>` 或按需全量/增量更新 |
| 改数据缓存/并行模块 | `pytest tests/test_quant_data_cache.py` |

### 8.1 回测一致性工具

`quant_consistency_check.py` 用于确认同一 preset 在两条路径下结果一致：

```text
Direct preset: run_backtest(preset=...)
Tuner contract: preset -> tuner params -> config_override -> run_backtest(...)
```

常用命令：

```bash
python scripts/quant_consistency_check.py --preset zen-1 --start 2025-01-01 --end 2026-05-19
```

如果这里 FAIL，说明 `quant_universe.yaml`、`quant_contract.py`、`quant_tuner.py` 或 `quant_backtest.py` 之间出现结果级漂移，应先修一致性再继续调参。

## 9. 当前清理方向

已知需要持续清理的方向：

1. 历史文档中可能仍残留旧 25 支 ETF、F1-F5、旧 payload 路径等口径；若任务依赖当前状态，先回到本文和 `config/quant_universe.yaml` 核对。
2. `research/07-quant-methodology.md` 是早期三因子方法论，不能作为当前系统事实源。
3. `templates/tuner.html` 的参数原理说明已降级为帮助层；“策略视角”类静态建议已删除。当前值以左侧滑块和参数契约表为准。
4. `scripts/quant_contract.py` 已承接 `/api/presets`、`/api/run`、`/api/save` 的核心参数映射；后续新增参数必须先改契约和测试。
5. 回测引擎测试覆盖不足，后续优先补参数映射、执行时点、分数带、仓位分配测试。

---

## 五、运维操作

---|---|
| `ready` | Tuner 是否已完成预加载 |
| `csvLatestDate` | `data/quant/*.csv` 最新日期 |
| `intradayCacheDate` | 盘中实时缓存日期 |
| `intradayCacheCount` | 盘中缓存 ETF 数量 |

### 1.4 刷新量化数据

```bash
python scripts/quant_data_fetcher.py              # 增量更新，默认选择
python scripts/quant_data_fetcher.py --code 512400 # 只更新单支 ETF
python scripts/quant_data_fetcher.py --full        # 全量重拉，谨慎使用
```

### 1.5 强制重拉特定日期数据

当怀疑某几天的 CSV 数据有问题（如盘中价被错误写入），先删后拉：

```bash
# 预览（不执行）
python scripts/strip_csv_dates.py --dry-run 2026-06-01 2026-06-02

# 删除 6/1~6/2 的行
python scripts/strip_csv_dates.py 2026-06-01 2026-06-02

# 然后刷新
# 在 Tuner 页面点「刷新数据」或 POST /api/refresh_data
```

原理：`refresh_data` 发现 CSV 缺数据 → 自动走增量拉取路径补全。

### 1.6 跑一致性检查

```bash
python scripts/quant_consistency_check.py --preset act-1 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset zen-1 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset gam-1 --start 2025-01-01 --end 2026-05-19
```

一致性检查对比：

```text
Direct preset: run_backtest(preset=...)
Tuner contract: preset -> tuner params -> config_override -> run_backtest(...)
```

如果 FAIL，先修一致性，再继续调参或发布。

---

## 2. 日常运维流程

### 2.1 盘后调参前

1. 更新量化 CSV：
   ```bash
   python scripts/quant_data_fetcher.py
   ```
2. 启动 Tuner：
   ```bash
   python scripts/quant_tuner.py
   ```
3. 打开：
   ```text
   http://localhost:5179
   ```
4. 检查右侧“参数原理 → 参数契约”：应显示 `schema v1 · ... params`。
5. 检查 `/api/data_status`，确认数据日期符合预期。

### 2.2 调参后保存参数

1. 在 Tuner 页面点击“保存参数”。
2. 参数会写入 `config/quant_universe.yaml` 的目标 preset。
3. 立刻运行：
   ```bash
   python scripts/quant_consistency_check.py --preset zen-1 --start 2025-01-01 --end 2026-05-19
   ```
4. 如参数作为研究结论沉淀，更新：
   ```text
   research/params/README.md
   research/strategy/README.md
   ```

### 2.3 改回测逻辑后

必须至少执行：

```bash
python -m pytest tests/test_quant_contract.py tests/test_quant_backtest_execution.py tests/test_quant_consistency.py tests/test_quant_backtest_core.py tests/test_quant_data_cache.py
python scripts/quant_consistency_check.py --preset zen-1 --start 2025-01-01 --end 2026-05-19
```

若改动影响 `run_backtest()` 的语义，同时更新：

```text
../../architecture/design/backtest-engine.md
docs/ops/quant/overview.md（如变更路由或契约变化）
```

---

## 3. 数据管线运维

### 3.1 文件位置

| 数据 | 路径 | 说明 |
|---|---|---|
| ETF 日线 | `data/quant/{code}_daily.csv` | date/open/close/high/low/volume/amount |
| ETF 周线 | `data/quant/{code}_weekly.csv` | 由日线重建或数据源拉取 |
| 市场状态 | `data/market_regimes.json` | 部分因子/历史逻辑会消费 |
| 估值历史 | `data/valuation_history/` | F4 估值相关 |
| 正式页 payload | `assets/js/quant_payload.js` | `window.__QUANT_RUNTIME__` |

### 3.2 当前数据源

量化 K 线：腾讯财经 fqkline API，前复权。  
脚本：`scripts/quant_data_fetcher.py`

已知约束：

- 有请求频率限制。
- 增量更新优先，少用 `--full`。
- `amount` 可能为估算值：`close * volume * 100`。
- 收盘后有冷却期，避免拿到未完成 K 线。

### 3.3 收盘冷却期

当前量化管线：

```text
MARKET_CLOSE_HOUR = 15
COOL_OFF_MINUTES = 10
```

含义：15:10 后才允许把当天 K 线视为已确认数据。盘中数据只进 Tuner 的 intraday cache，不写入 CSV。

### 3.4 盘中 intraday cache

Tuner 盘中会把新浪实时行情临时合并进内存：

```text
CACHE["intraday_cache"]
```

规则：

- 只在内存中存在。
- 不写入 `data/quant/*.csv`。
- 收盘后 CSV 更新成功会清空 cache。
- 回测、K 线 API、热力图读取时通过 Tuner 内部合并视图使用。

---

## 4. Tuner 运维

### 4.1 主要 API

| API | 用途 |
|---|---|
| `/` | Tuner 页面 |
| `/api/data_status` | 数据新鲜度 / Tuner ready 状态 |
| `/api/param_schema` | 参数契约 schema |
| `/api/presets` | 从 `quant_universe.yaml` 读取 preset 并转为前端参数 |
| `/api/run` | 提交当前参数并运行回测 |
| `/api/save` | 保存当前参数到 preset |
| `/api/kline` | 单 ETF K 线复盘数据 |
| `/api/etf_prices` | ETF 价格序列 |
| `/api/heatmap_data` | 涨跌热力图数据 |

### 4.2 参数契约

参数转换统一由：

```text
scripts/quant_contract.py
```

负责：

```text
preset_to_tuner_params()
tuner_params_to_config_override()
tuner_params_to_preset_patch()
validate_tuner_params()
get_param_schema()
```

新增或修改 Tuner 参数时，不要只改 HTML。必须同步：

```text
scripts/quant_contract.py
templates/tuner.html
tests/test_quant_contract.py
docs/ops/quant/overview.md（如契约说明变化）
```

### 4.3 端口冲突

默认端口：

```text
5179
```

如页面打不开：

1. 访问 `/api/data_status` 判断服务是否在线。
2. 如端口被旧进程占用，使用：
   ```bash
   python scripts/kill_tuner.py
   ```
3. 重新启动 `python scripts/quant_tuner.py`。

---

## 5. 正式页 payload 运维

正式页读取：

```text
assets/js/quant_payload.js
```

由以下路径生成：

```text
update_report.py -> generate_quant_baseline_payload()
```

当前实现：

1. 从 `config/quant_universe.yaml` 读取 `zen-1`。
2. 通过 `quant_contract.py` 转为 Tuner 参数。
3. 调用 Tuner `/api/run` 生成 1 年 / 3 年回测结果。
4. 写入 `assets/js/quant_payload.js`。

注意：

- 不要手改 `assets/js/quant_payload.js`。
- 如果 Tuner 没启动，payload 可能为空或沿用旧文件，需看日志。
- 正式页展示逻辑在 `assets/js/quant-main.js`。
- 若 payload 参数展示异常，优先检查 `quant_contract.py` 和 `update_report.py` 的 helper 测试。

---

## 6. 长任务规则

### 6.1 使用统一优化器 `quant_optimizer.py`

推荐使用统一优化器代替手工 sweep 脚本。支持三种搜索策略：

```bash
# 网格搜索（小空间穷举）
python scripts/quant_optimizer.py --preset zen-1 --strategy grid \
  --params "w1=30,40,50 w3=30,40,50 score_band=0,1,2,3" --periods 1Y,3Y

# 随机搜索（大空间探索）
python scripts/quant_optimizer.py --preset zen-1 --strategy random \
  --n-trials 200 --seed 42 --periods 1Y,3Y,6Y

# 贝叶斯优化（智能搜索，需 optuna）
python scripts/quant_optimizer.py --preset zen-1 --strategy bayesian \
  --n-trials 100 --auto-bounds --periods 1Y,3Y,6Y

# 续跑
python scripts/quant_optimizer.py ... --resume
```

输出目录：`research/params/{preset}-{date}/`，含 `results.json`、`report.md`、`checkpoint.json`、`log.txt`。

参数空间由 `scripts/quant_contract.py` 的 `PARAM_BOUNDS` 统一定义，`--auto-bounds` 从 preset 当前值自动推导搜索范围。

### 6.2 后台运行（推荐）

```powershell
Start-Process -FilePath "python" `
  -ArgumentList "scripts\quant_optimizer.py --preset zen-1 --strategy bayesian --n-trials 150 --auto-bounds --periods 1Y,3Y,6Y" `
  -WorkingDirectory "<项目根目录>"
```

完成后检查 `research/params/{preset}-{date}/report.md` 查看结论。

### 6.3 旧式批量搜索注意事项（仅用于兼容旧脚本）

- 每批组合数不要太大。
- 每个 combo 及时写 checkpoint。
- 输出 CSV/JSON 到 `data/param_search/` 或对应 `research/` 目录。
- 跑完后把结论写入 `research/params/README.md` 或对应研究目录。

---

## 7. 故障排查

> **诊断第一原则**：出现异常时先看浏览器 Console（F12）或终端错误信息，不要猜进程/网络/缓存。

### 症状索引

#### Tuner 前端

| 症状 | 可能原因 | 检查方法 | 关联 Bug |
|------|---------|---------|---------|
| 启动后一直”正在加载量化数据...” | JS 初始化抛异常，阻塞后续逻辑 | F12 → Console 看第一个红色错误 | BUG-033 |
| 回测按钮被禁用/灰掉 | 权重校验失败（`parseInt(null)`=NaN），常见于废弃参数残留 | 检查 `getWeightTotal` 是否返回 NaN；全项目 grep 废弃参数名 | F6 清退 |
| 回测结果与 CLI 不一致 | `set()` 迭代顺序非确定 → 买入顺序不同 → 现金分配不同 | 对比 CLI/Tuner 第一个调仓日的持仓排序 | BUG-024 |
| 滑块拖不动/锁死在 0% 或 100% | `range input` 无 `step` 属性时浏览器默认 step=1 | 检查滑块元素是否有 `step=”any”` | BUG-027 |
| 预设卡片不显示/报错 | `renderPresetCards()` 某个 school 缺字段 | 检查 `SCHOOLS` 数组每个元素是否都有 `target`/`constraint` | BUG-033 |
| 标的池勾选不生效 | `getUniverseParam()` 全选时发空串 → 后端解为”全池”而非”默认池” | 检查请求 payload 中 `universe` 字段是空串还是 code 列表 | REQ-289 |

#### 回测数据

| 症状 | 可能原因 | 检查方法 | 关联 Bug |
|------|---------|---------|---------|
| 同一策略周五 vs 周一回测结果不同 | F1 跨周冻结失效：周边界 `checkpoint_f1=None` | 对比上周五和本周一的 `f1_val` | BUG-032 |
| 全量重拉 CSV 后回测指标漂移 | 数据源变化 + 管线重构导致旧基线不可比 | 对比新旧 CSV 的 bar 数量、最后一行日期、close 值 | BUG-030 |
| 某 ETF 不参与因子计算 | CSV 数据不完整（full fetch 分页丢中间页） | `wc -l data/quant/{code}_daily.csv`，对比预期行数 | BUG-028 |
| 周一~周四的 MA 信号异常好 | lookahead bias：`merge_asof(direction=”forward”)` 用了未来数据 | 检查周二时 `hs300_above_ma` 是否已包含周五的 MA 值 | BUG-025 |
| 回测持仓数始终不满 / 熊市现金异常消耗 | 残量回收第二 pass 用了不同变量名漏修 | 检查熊市时 `cash` 是否被花光 | BUG-026 |
| 周线 bar 日期错位（周一出现 incomplete week bar） | `rebuild_weekly_from_daily` 未排除本周未完成周 | 检查周线 CSV 最后一周的 `week` 列是否为当前 `iso_year-iso_week` | — |

#### 筛选流

| 症状 | 可能原因 | 检查方法 | 关联 Bug |
|------|---------|---------|---------|
| 盘中拉数据导致筛选排序失真 | 非交易时段用了 `--force-refresh`，或盘中数据不完整 | 检查 `history_days.json` 缓存时间戳 | — |
| 刚上市 ETF 虚高打分进入筛选 | `_est_listing_date()` 前缀推测法已删除 | 确认使用 Sina API `history_days` | — |
| HK ETF 被豁免 O2 重叠淘汰 | `EXEMPT_PREFIXES` 曾包含 `'HK-'` | 检查 `EXEMPT_PREFIXES` 常量 | — |

#### Tuner 后端

| 症状 | 可能原因 | 检查方法 |
|------|---------|---------|
| 页面打不开 | 端口被旧进程占用 | `netstat -ano \| findstr 5179`，`python scripts/kill_tuner.py` |
| `/api/presets` 返回 ETF 数量不对 | 另一个仓库的 Tuner 占用了 5179 端口 | 确认只有一个 LISTENING 进程 |
| `yaml.dump` 改写了 config 格式 | `pool_change.py` 或 `/api/save` 用 `yaml.dump` 写回 | `git diff config/quant_universe.yaml` |
| Tuner 启动慢 / preload 卡住 | 某 ETF CSV 缺失或损坏 | 检查 Tuner 终端输出，找到卡在哪个 ETF |

### 诊断流程

**Tuner 前端异常**：
```
白屏 / loading 不消失 → F12 Console 看第一个红色错误
  → 通常是 JS 语法错误 / 字段缺失 / 异步初始化顺序问题
```

**回测结果异常**：
```
指标突变 / 持仓不对
  → 先确认 CLI 和 Tuner 结果是否一致（排除 Tuner 层）
  → 缩小范围：单 ETF → 小池 → 全池
  → 对比中间变量：F1 → 因子得分 → 排名 → 持仓权重
  → 定位到具体计算步骤后修
```

**数据异常**：
```
CSV 行数不对 / 数据缺失
  → 检查文件大小和行数
  → 对比同 ETF 在 stable 和 main 仓库的数据
  → 确认 fetch 来源
```

---

## 8. 运维检查清单

### 改参数后

```bash
python -m pytest tests/test_quant_contract.py
python scripts/quant_consistency_check.py --preset zen-1 --start 2025-01-01 --end 2026-05-19
```

### 改成交口径 / 调仓逻辑后

```bash
python -m pytest tests/test_quant_backtest_execution.py tests/test_quant_consistency.py
python scripts/quant_consistency_check.py --preset act-1 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset zen-1 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset gam-1 --start 2025-01-01 --end 2026-05-19
```

### 改正式页 payload 后

```bash
python -m pytest tests/test_update_report.py -k "quant_preset_params or quant_payload_config_section"
python -m py_compile scripts/update_report.py scripts/quant_contract.py
```

### 改数据源后

```bash
python scripts/quant_data_fetcher.py --code 512400
python scripts/quant_tuner.py
# 打开 http://localhost:5179/api/data_status
```

---

## 六、日更参数速查

## 目的

这份文档只回答一件事：**哪些内容需要日更，靠什么命令刷新，改动会落到哪里。**

默认从项目根目录执行：

```bash
python scripts/update_report.py
```

---

## 每日会刷新的内容

### 1. K 线数据

- **文件**: `data/etf_full_kline_data.json`
- **内容**: 日线、周线、MA 均线
- **触发方式**: `python scripts/update_report.py` → Step 1

### 2. 实时行情数据

- **文件**: `data/etf_realtime_data.json`
- **内容**: ETF 涨跌、成分股涨跌、交易量、时间戳
- **触发方式**: `python scripts/update_report.py` → Step 2 / Step 3

### 3. HTML 报告日期与页面数据

- **文件**: 根目录 `index.html`
- **内容**: 报告日期、数据截止、生成时间、页面数据块
- **触发方式**: `python scripts/update_report.py` → HTML 更新阶段

### 4. 解释层内容回填

- **来源**: `config/editorial_content.yaml`
- **页面结果**: 研究卡 / 宏观卡正文与逐条日期
- **触发方式**: `python scripts/update_report.py` 读取配置后统一回填

---

## 通常不需要频繁改的内容

### ETF 列表与基准指数

- **位置**: `config/config.yaml`
- **频率**: 按需
- **场景**: 换标的、调基准、调整 ETF 池

### API 配置

- **位置**: `config/config.yaml`
- **频率**: 按需
- **场景**: API 变更、限流调整

### 显示参数

- **位置**: `config/config.yaml`
- **频率**: 季度 / 半年级别
- **场景**: 调整显示区间、均线预热期、视觉参数

---

## 日常维护节奏

| 频率 | 操作 | 命令 |
|------|------|------|
| 每天 | 刷新报告主流程 | `python scripts/update_report.py` |
| 每周 | 跑健康检查 | `python scripts/health_check.py` |
| 按需 | 审查目录卫生 | `python scripts/audit_project.py --quick` |

---

## 影响路径

```text
config/*.yaml / data/*.json
        ↓
python scripts/update_report.py
        ↓
根目录 index.html + logs/*.jsonl
```

---

## 最佳实践

- **一次性输出**：统一放到本地临时目录（如 `_working/`），不提交到 Git
- **正式运行数据**：只留在 `data/`、`logs/`
- **根目录**：只保留源码、文档和主报告 `index.html`
- **健康检查基线**：需要时用 `python scripts/health_check.py --json > _working/xxx.json`

---

**最后更新**: 2026-04-17

---

## 七、健康检查

## 一、使用指南

## 概述

`health_check.py` 用于快速验证 `etf-report` 当前目录、数据、HTML、工作流和配置是否处于可运行状态。

- **检查项数**: 26 项（6 大类别，含解释层鲜度检查）
- **默认入口**: `python scripts/health_check.py`
- **常见输出**: 终端彩色表格；可选 JSON / HTML
- **目录约定**: 一次性导出建议写到本地临时目录（如 `_working/`，不提交到 Git）

---

## 快速开始

### 基础检查

```bash
python scripts/health_check.py
```

### 生成 JSON 报告

```bash
python scripts/health_check.py --json > _working/health_check_baseline.json
```

### 常用变体

```bash
python scripts/health_check.py --strict
python scripts/health_check.py --category E
python scripts/health_check.py --html
```

---

## 命令行选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `--json` | 输出 JSON 格式报告 | `python scripts/health_check.py --json` |
| `--html` | 输出 HTML 可视化报告 | `python scripts/health_check.py --html` |
| `--strict` | 严格模式（警告 = 失败） | `python scripts/health_check.py --strict` |
| `--category A,B,C` | 只检查特定类别 | `python scripts/health_check.py --category A,B` |
| `--verbose` | 输出详细日志 | `python scripts/health_check.py --verbose` |

---

## 返回码

| 返回码 | 含义 | 说明 |
|--------|------|------|
| 0 | PASS | 无警告、无失败 |
| 1 | WARN | 仅在 `--strict` 模式下，警告会返回 1 |
| 2 | FAIL | 存在失败项 |

---

## 检查项结构

### A 类：文件完整性（5 项）
- `A1`: 根目录 `index.html` 是否存在
- `A2`: `data/` 下 2 个必需 JSON 是否存在
- `A3`: 5 个核心脚本是否存在
- `A4`: HTML / K 线数据体积是否异常偏小
- `A5`: 主 HTML 目录与关键文件是否可读写

### B 类：数据有效性（6 项）
- `B1`: JSON 可解析
- `B2`: ETF 代码完整
- `B3`: K 线结构完整
- `B4`: 日期可提取
- `B5`: 数据时效性
- `B6`: 成分股数据数量

### C 类：脚本依赖（5 项）
- `C1`: Python 版本
- `C2`: `requests` / `yaml` 导入
- `C3`: 核心脚本导入链
- `C4`: 新浪财经 API 可达性
- `C5`: 项目根目录临时探针写入能力

### D 类：HTML 结构（4 项）
- `D1`: HTML 标签平衡
- `D2`: 必需数据块（`klineData`）存在；`realtimeData` 为可选块
- `D3`: ECharts 引入存在
- `D4`: 关键样式类存在

### E 类：工作流逻辑（4 项）
- `E1`: `.backup/` 事务快照目录状态
- `E2`: HTML 日期同步
- `E3`: `update_report.py` 主流程函数完整性
- `E4`: 解释层鲜度（按 `freshness_policy` 校验）

### F 类：系统配置（2 项）
- `F1`: ETF 成分股配置完整性
- `F2`: 基准指数配置正确性

---

## 常见问题

### Q1: D2 缺少 `klineData`

**原因**: 页面未经过主流程刷新，或 HTML 被旧文件覆盖。

**处理**:

```bash
python scripts/update_report.py
```

### Q2: B5 数据时效性出现 WARN

**原因**: 非交易日或最新数据尚未刷新，常见于周末 / 节假日。

**处理**: 在下一个交易日收盘后重新运行 `python scripts/update_report.py`。

### Q3: E4 解释层鲜度出现 WARN / FAIL

**原因**: `config/editorial_content.yaml` 中的 `content_date` 与 `freshness_policy` 不匹配。

**处理**:
- 日更内容优先使用 `manual_daily`
- 编辑态内容可用 `sticky`
- 修正后重新运行主流程

### Q4: C2 库缺失

```bash
pip install requests pyyaml
```

---

## 与主流程集成

主流程 `python scripts/update_report.py` 末尾会自动执行健康检查，并把摘要写入终端与结构化日志。

如需单独留一份 JSON 基线：

```bash
python scripts/health_check.py --json > _working/health_check_latest.json
```

---

## 八、每日自动化

> v2.0 产品线：量化回测 → 信号排名 → Server酱推送。理性信息。
> 正式页报告（v1.0）见 `REPORT_RUNBOOK.md`。

### 定时任务

| 时间 | 任务名 | 脚本 | 做什么 |
|------|--------|------|--------|
| 11:20 | `etf早盘报告` | `preclose_push.bat` | 盘中数据刷新 → 回测 → 推送 top-10 |
| 14:50 | `etf午盘报告` | `preclose_push.bat` | 盘中数据刷新 → 回测 → 推送 top-10 |
| 15:15 | `etf盘后数据更新` | `postmarket_update.bat` | 拉取今日收盘 K 线 → 写入 CSV |

### 数据流

```
腾讯 fqkline → quant_data_fetcher.py → data/quant/{code}_daily.csv (45支)
                              ↓
                    preclose_push.py
                      ① 启动 Tuner (Flask :5179)
                      ② /api/refresh_data → 刷新日内缓存或 CSV
                      ③ /api/run → run_backtest() → 信号排名
                      ④ Server酱 → 微信推送 top-10 持仓表
```

早盘/午盘推送使用**日内盘中数据**（Tuner intraday cache），回测窗口为 `当年5月1日 ~ 今日`。
15:15 盘后直接拉取收盘 K 线写入 CSV，不经过 Tuner（绕过时段路由），不推送。

### 容错

- **非交易日**：`preclose_push.py` 内置交易日检测，自动跳过
- **Tuner 未启动**：脚本自动启动并等待就绪（最长 60s）
- **15:15 被跳过**：16:00 的 `daily_report.bat` 会补拉数据（见 `REPORT_RUNBOOK.md`）
- **多个任务冲突**：任务计划程序设置 `MultipleInstances IgnoreNew`，前一个未完成则跳过

### Server酱

推送渠道。配置在 `config/secrets.yaml`：

```yaml
publish:
  serverchan:
    sendkey: "SCTxxxxx"
```

sendkey 从 [Server酱官网](https://sct.ftqq.com/) 获取，免费档每日限额 5 条。

### 新电脑初始化

```powershell
# 同 REPORT_RUNBOOK 的初始化步骤 1-3（clone / secrets / 数据）

# 安装量化定时任务
powershell -ExecutionPolicy Bypass -File batchfiles\setup_quant_tasks.ps1
```

---

## 相关文档

- 系统架构：`../../architecture.md`
- 正式页运维：`REPORT_RUNBOOK.md`
- 发布门禁：`RELEASE_RUNBOOK.md`
- 代码审计：`AUDIT_RUNBOOK.md`
