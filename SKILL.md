# ETF 报告生成技能 (etf-report)

自动分析与生成 6 支 ETF 的投资分析报告（K线、均线、实时行情、成分股、宏观分析）。
数据+模板分离架构，100% 保持原始 HTML 样式一致。

> **读到本文件 = 你是开发者。** 你有权感知需求看板、Bug 状态、审计规则等内部状态。应优先读本文件，再按首读顺序展开。
>
> 在这个项目里，你的工作方式：**语义先行、基准护航、路由完整、结论克制。** 不要边改边理解。

## 触发词

"更新ETF报告"、"生成ETF分析报告"、"刷新投资数据"、"看看今天的ETF"、"调参"、"量化调参"、"quant tuner"、"回测调试"

## 这个技能做什么

三类核心能力：

- **更新报告**：抓取 ETF 数据、生成并更新 `index.html`
- **调整配置**：修改 ETF 池、基准、解释层内容、发布开关等配置
- **接入发布**：把生成结果接到企微通知、GitHub Pages

## Agent 首读顺序

1. **`SKILL.md`**（本文件）：判断技能是否匹配当前任务 + 术语表
2. **`PLAN.md`** → **`plans/Board.md`**：当前版本、in_progress、活跃 Bug、ID 计数器
3. **`DESIGN.md`** → **`design/`**：系统架构总览 + 因子/引擎/贡献分析子系统设计
4. **`runbooks/QUANT_RUNBOOK.md`**：量化运维——变更路由、API、验证、排障、日更
5. **`runbooks/REPORT_RUNBOOK.md`**：正式页报告工作流——生成、发布、企微推送
6. **`runbooks/RELEASE_RUNBOOK.md`**：发布门禁
7. **`README.md`**：配置、运行、目录结构
8. **`research/README.md`**：量化调研索引
9. **`config/*.yaml`** / **`scripts/*.py`**：实现事实源

### 快捷提示词

| 用户说 | Agent 做 |
|--------|---------|
| "更新ETF报告" / "跑一下" | 运行 `python scripts/update_report.py` |
| "改配置" / "换 ETF" | 读 `README.md` 配置部分 |
| "发布" | 必须先读 `runbooks/RELEASE_RUNBOOK.md`（唯一门禁），勿直跳 README |
| "做个健康检查" | 读 `WORKFLOW.md` |
| "调参" / "量化调参" / "quant tuner" | 先读 `DESIGN.md` + `runbooks/QUANT_RUNBOOK.md`，再启动 `python scripts/quant_tuner.py` → http://localhost:5179 |
| "查看XX调研" / "后视镜调研" / "research" | 读 `research/README.md` 索引，定位对应 REQ 子目录 |
| "推进需求" / "修 Bug" / "开发XX" | 读 `PLAN.md` → `plans/Board.md` → 补编号 → 改文件 |
| "接发布链路" / "微信推送" | 读 `scripts/notifier.py` / `scripts/deployer.py` |
| "审计" / "audit" | 读 `runbooks/AUDIT_RUNBOOK.md` |

## 术语表

> 目标：AI 跨对话不产生命名漂移。新增术语时必须补 `_Avoid_` 行。

### 系统与架构

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **技能 / skill** | 整个 etf-report 项目 | 项目, 仓库, repo |
| **Tuner** | `quant_tuner.py` 启动的 Flask 本地服务（localhost:5179），用于交互式调参和回测 | 调参器, 调试器, 工坊, 后端 |
| **正式页** | `index.html` 在线报告页面，纯静态 + 预计算 payload | 报告页, 主页, 线上报告 |
| **payload** | 预计算的 JSON 数据文件（`assets/js/*.js`），由 Python 脚本生成，注入 HTML 供前端渲染 | 数据注入, JSON数据, 静态数据 |
| **人设 / Persona** | 精算师(Actuary)、禅修者(Zen)、赌徒(Gambler) 三套完整的策略参数 + 投资哲学。不仅是一组 preset 参数，还包含目标函数、风格坐标、弱项自知 | preset, 策略预设, 流派, 风格 |

### 数据管线

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **intraday** | 交易时段通过 Sina `hq.sinajs.cn` 拉取的当日实时 OHLCV，存在 Tuner 内存 `intraday_cache` 中，不写 CSV。盘中回测通过 `_get_daily_with_cache()` 合并进日线 | 盘中, realtime, 实时行情, live data |
| **daily** | `data/quant/{code}_daily.csv` 中的日线 OHLCV，收盘后确认数据。来源：腾讯 `fqkline` API（前复权） | 日线, K线, daily bar |
| **weekly** | 由 daily 通过 `rebuild_weekly_from_daily()` 聚合生成，不直接拉取 | 周线, weekly bar |
| **patch fetch** | `quant_data_fetcher.py --start YYYY-MM-DD --end YYYY-MM-DD`，补拉指定日期范围的 CSV 数据（覆盖写入） | 补拉, 回补, backfill, 历史补数据 |
| **incremental fetch** | `_run_incremental_fetch()` 增量拉取：只拉 CSV 最后日期之后的新数据 | 增量更新, 日常拉取 |
| **full fetch** | `quant_data_fetcher.py --full` 全量重拉所有历史数据 | 全量拉取, 重拉全部 |
| **refresh** | `/api/refresh_data` 端点。根据当前时段自动路由：post-market → CSV 增量拉取；intraday → 仅刷新 intraday_cache；非交易日 → CSV 增量拉取 | 刷新, 更新数据 |
| **Sina API** | `hq.sinajs.cn/list=` 实时行情接口，一次 HTTP 请求拉全部 45 支 ETF | 新浪, sina |
| **Tencent API** | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` 日 K 线接口（前复权），每支 ETF 一次请求 | 腾讯, tx, fqkline |

### 量化引擎

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **因子 / Factor** | F1(EMA偏离)、F3(量比)、F7(对数收益偏离)。F2/F4/F5/F6 已退役 | 信号, 指标 |
| **f1_raw / f3_raw / f7_raw** | 因子的原始计算值（未映射）。f1_raw=EMA偏离百分比，f3_raw=量比原始值，f7_raw=对数收益偏离 Z-score | raw value, 原始值, Z-score |
| **F1 / F3 / F7** | 原始值经映射函数后的 0-100 标准化分数。50=中性，>50=看多，<50=看空 | 因子分数, mapped score, 映射分 |
| **综合分 / score** | `F1×w1 + F3×w3 + F7×w7`，每个 ETF 的最终打分。决定排名和仓位 | 总分, 得分, composite score |
| **信心函数 / confidence** | 将综合分映射为仓位乘数（分段平方函数 + MA trend 覆盖） | 仓位函数, 信心乘数 |
| **C / CS** | C=仓位集中度（base concentration），CS=集中度敏感度（spread sensitivity）。C 高=持仓更集中，CS 高=分数差距放大更剧烈 | concentration, c_sensitivity |
| **execution_timing** | `same_close`=信号日收盘价成交，`next_open`=下一交易日开盘价成交 | 执行时点, 成交口径 |
| **preset** | `quant_universe.yaml` 中的一组参数快照（preset1/2/3/4/6）。三个人设各自对应一个 preset | 预设, 参数组 |
| **top-6** | 综合分排名前 6 的 ETF，构成策略持仓 | 前6, 选股池 |
| **position / 仓位** | 每支 ETF 的目标仓位权重（0-1），由综合分+信心函数+集中度参数共同决定 | 持仓, 权重, weight |

### F1 因子专项

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **抢跑** | 用当日价格提前更新 F1，不等周线 CSV 发布。本质是用不完整信息做估计 | 解冻, unfreeze |
| **检查点 / checkpoint** | 抢跑日收盘时刻的快照。用当日收盘价从 base EMA 滚一步得到 F1，保存为本周后续冻结日的复用值。数学上等价于"如果本周 bar 现在截止，它的 F1 会是多少" | bar_date, CSV 重建, 临时 bar |
| **冻结 / freeze** | 两个检查点之间的交易日复用上一个检查点的 F1，不做任何计算。非"信号缺失"——是主动选择不更新一个低质量估计 | 平线, 不变, 保持 |
| **hold / 保持** | 本周尚无检查点时，沿用上周最后一个完整周的 F1。等价于 freeze 在上周的检查点上 | 延迟, 滞后 |
| **f1_active_days** | bitmask 0-31，控制哪些交易日触发检查点。1=周五、9=周二+周五、31=每日。本质是"信息完整度门槛"的量化表达 | 三模式, friday/monday/daily |
| **信息完整度** | 当日已累积的本周交易日数 / 本周总交易日数。周五=5/5=无偏，周二=2/5=有偏 | 数据充分性 |
| **信息新鲜度** | 距上次完整周 bar 的天数。上周五=-5天，本周二=0天。新鲜度和完整度是抢跑决策的两个正交维度 | 时效性, 及时性 |
| **有偏估计** | 周中用不完整信息滚 EMA 得到的 F1。不是"错的"——是对真值的噪声近似。噪声随信息完整度上升而衰减，周五收盘时刻归零 | 不准, 假信号 |
| **收敛** | 检查点日盘中，price(t) → 收盘价的过程中，F1(t) 连续逼近无偏值。收盘时刻达到——此时检查点 = 真值 | 趋近, 逼近 |
| **无偏值** | 周五收盘时的 F1。信息完整度=5/5，与已完成周线 bar 的 EMA 完全一致。是下周 hold/freeze 的锚点 | 真值, 准确值, 真实F1 |

### F7 因子专项

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **f7_raw** | 20 日累计对数收益在过去 250 日的 Z-score。负值=超跌，正值=超涨 | F7 raw, Z-score, 偏离度, 原始F7 |
| **F7 PULL-IN** | F7 把 ETF 从"无 F7 不进前 6"拉入前 6。f7_raw << 0 → F7 >> 50，给自己加分 | F7主导买入, F7 decisive, F7拉动, 超跌买入 |
| **F7 PUSH-OUT** | F7 把 ETF 从"无 F7 能进前 6"踢出前 6。f7_raw >> 0 → F7 << 50，给对手扣分 | F7主导卖出, F7压制, F7惩罚, 超涨回避 |
| **黑洞螺旋** | F7 连续持有阴跌标的时，仓位随下跌加速集中。受 20 日滚动窗口自限：max DD < -10%，最长 9 天 | death march, death spiral, 死亡螺旋 |
| **`map_f7(z, t, k)`** | F7 映射函数。\|z\|≤k 用幂函数，\|z\|>k 用切线外延。t=幂次控制两端加速，k=切换点 | F7映射, 分数映射 |

### 回测与分析

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **head-to-head** | 有因子 vs 无因子（w=0），其他参数不变，对比组合级指标。**评估因子价值的第一方法**，优于单笔归因 | A/B对比, 对照回测, 因子消融 |
| **excess return** | 交易 PnL − 同期等权 ETF 基准收益。剥离市场 beta | alpha, 超额, 超额 alpha |
| **NAV** | 净值曲线。初始本金 100 万，逐日计算 | 净值, 资金曲线 |
| **TPE** | Tree-structured Parzen Estimator，Optuna 贝叶斯优化，用于参数搜索 | 贝叶斯优化, 超参搜索 |
| **回测窗口** | 回测的起止日期范围。1Y/3Y/6Y 指回测长度，非 Tuner 的显示区间 | backtest window, 回测区间 |

### 研究体系

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **Promotion** | 研究结论被采纳到生产配置。记录在 `research/promoted/` | 投产, 上线, 合入 |
| **research/** | 策略研究目录。自包含（文档+数据+脚本），与正式管线 `data/` 隔离。提交规则见 `research/README.md` | 研究目录, 调研 |
| **`_template/`** | `research/_template/`，新建研究项目时复制的目录骨架 | 模板, 研究模板 |

### 运维

| 术语 | 定义 | `_Avoid_` |
|------|------|-----------|
| **发布 / release** | 将本地改动推送到 GitHub Pages。唯一门禁：`runbooks/RELEASE_RUNBOOK.md` | 上线, 部署, deploy |
| **preclose push** | `preclose_push.bat` 收盘前推送：刷新 intraday → 跑回测 → Server酱推送到微信 | 收盘推送, 信号推送, 企微推送 |
| **审计 / audit** | `python scripts/audit_project.py --full` 或 AI 按 `AUDIT_RUNBOOK.md` 执行。发布前必须跑 | 代码审查, review |
| **健康检查 / health check** | `python scripts/health_check.py`，26 项自动检查，集成在 `update_report.py` 末尾 | 检查, 校验 |

https://julensanchez.github.io/etf-report/

## 数据抓取失败处置

运行 `update_report.py` 或量化管线时，若出现以下错误，按对应路径处置：

| 现象 | 可能原因 | AI 处置 |
|------|---------|---------|
| `ConnectionError` / `HTTPError 403/503` / `timeout` | 数据源被限流或 IP 封禁 | 告知用户当前数据源受限，建议等待 30 分钟后重试；不要反复重跑加剧封禁 |

## 协作准则

以下四条针对 etf-report 高频翻车点。

1. **实现概念不准进入对话**——用术语表的词（`intraday`、`daily`、`checkpoint`），不用实现细节（`bar_date`、`+3 days`、`CSV 重建`）。术语表有 `_Avoid_` 列，先查再用。
2. **改策略参数 = 跑全链路**——新增/改名任何参数，按 `QUANT_SYSTEM.md` §5.2 checklist 逐项核对。改完跑 smoke test + 至少一个 preset 的 6y 对比。
3. **没有基准不动策略逻辑**——改动前保存 NAV 序列 + 各 preset 指标 + 关键 ETF 因子样本。改动后对比。基准不存在就先建基准（REQ-275）。
4. **结论附验证范围**——"TR 恢复 741%" 必须说明窗口（6y/1y/smoke）、覆盖（是否含节假日短周）、对比基线。
| `AKShare` 相关 `Exception` / `KeyError` 找不到字段 | AKShare 接口变更或数据源下线 | 读 `WORKFLOW.md` 排障节；核查 `scripts/fix_ma_and_benchmark.py` 和 `realtime_data_updater.py` 的数据源调用 |
| 量化 CSV 相关 `No CSV data` / `FileNotFoundError` | `data/quant/` 为空（冷启动场景） | 运行 `python scripts/quant_tuner.py --auto` 触发冷启动（约 3-5 分钟），或手动 `python scripts/quant_data_fetcher.py --full` |
| 腾讯 fqkline `code: 1, msg: param error` / `HTTP 403` | 量化数据源被封 | 详见 `runbooks/QUANT_RUNBOOK.md` §3.6；核心对策：减少请求频率、换 IP、等待 24-48h 解封 |
| 脚本报错但不是上述类型 | 代码 bug 或环境问题 | 读完整报错栈，优先看最后一行 `caused by`；依赖缺失则 `pip install -r requirements.txt` |

**通用原则**：
- 数据源失败不等于代码 bug，先区分"网络/源问题"和"代码问题"再动手
- 上次成功的数据仍在本地缓存（`data/`），可用旧数据生成报告，告知用户数据日期可能不是最新
