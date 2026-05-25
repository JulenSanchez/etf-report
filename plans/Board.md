# ETF 报告技能 — 需求看板

## 当前版本信息

| 字段 | 值 |
|------|------|
| **当前版本** | v3.2.0 |
| **发布日期** | 2026-05-22 |
| **下一目标版本** | v3.3.0 |
| **开发中需求** | 0 |
| **待办需求** | 27 |
| **池子规模** | 44 支 ETF，11 个扇区 |



---

## in_progress (开发中)

| ID | 标题 | 优先级 | 目标版本 | 最后活动 | 备注 |
|----|------|--------|---------|---------|------|
| — | — | — | — | — | — |
















## done (已完成，待发布)

| ID | 标题 | 完成日期 | 备注 |
|----|------|---------|------|
| REQ-213 | ETF 元数据补充 — 规模 + 前十大重仓股 | 2026-05-22 | `fetch_etf_metadata.py` 拉取东方财富 AUM+Top10 持仓 → `etf_metadata.json`。Tuner 启动加载 + `/api/refresh_metadata` 端点 + 前端 chk-meta 勾选框顺带更新。44 支全量，38 支有持仓数据。 |
| REQ-221 | 扇区语义配色 | 2026-05-22 | 11 扇区固定语义配色（科技蓝/TMT青/新能源绿/医药粉/消费橙/金融金/资源棕/传统石灰/制造紫/宽基银灰/另类堇），替代顺序随机分配。热力图+快照表同步。 |
| REQ-220 | Tuner UI 综合优化 | 2026-05-21~22 | nav-chart boundaryGap 对齐 + freq-tabs 入 chart + 快照扇区色块/火焰后置/sticky thead/滚动区 + 个股回放独立 kline-section + contrib-grid 重构 + metric 居中 + guide 公式标准化 + 导览栏目重排 + param-schema 字号 + kline-replay 成交额亿元标注 + 滚动条隐藏 |
| REQ-219 | 超额收益 + 10 卡指标重排 | 2026-05-22 | 胜率/赔率拆分 + 超额(沪深300)新增。5×2 网格: 年化→总→超额→胜率→赔率→Sharpe→Sortino→回撤→换仓率→佣金。excessReturn 后端计算。 |
| REQ-218 | 回测结果持久化缓存 | 2026-05-22 | `/api/run` 后存盘 `last_backtest.json`，页面刷新 `renderResults()` 自动恢复 + 参数还原。版本 hash 校验(5 源文件)，代码变更自动失效。 |
| REQ-217 | 盘中 CSV 写入 bug 修复 | 2026-05-21 | `refresh_data()` 盘中不再跑 `_run_incremental_fetch`，实时数据仅写 intraday_cache。根因: `fetch_end=today_str` 覆盖 `_latest_allowed_date()` 安全机制 + `<=` 闭区间包含当日未完成 K 线。 |
| REQ-216 | ETF 贡献度评估系统 | 2026-05-22 | `_compute_etf_contributions()` 9 项指标(选中率/均权重/均持有/笔数/胜率/赔率/交易盈亏/份额/共现)。`docs/ETF_CONTRIBUTION_FRAMEWORK.md` 分析框架。`scripts/analyze_contributions.py`。前端 contrib-grid + 扇区图例过滤。观察期排除(上市<80日)。选中率按有效信号数归一化。 |
| REQ-215 | 逐笔配对胜率 + 赔率 (替代日胜率) | 2026-05-20 | `_execute_rebalance` 埋点 trade_log(FIFO配对)。quant_backtest.py 返回 trade_log，quant_tuner.py 聚合胜率/赔率。tuner + formal page 同步。 |
| REQ-214 | ETF 池子 40→44 + 扇区重划 + preset 重命名 | 2026-05-21 | −德国 +巴西(520870) +纳指科技(159509) +中概互联(513050) +稀土(516150) +粮食(159698)。中概互联入 TMT。preset weekly_trend→preset1, daily_aggressive→preset2, daily_aggressive_f6→preset3, custom→preset4。 |
| REQ-199 | 搭建标的池扩容流程 | 2026-05-12 | 完成: 512010/159766/513690/563300 入库, 池子 30→34, 新增红利/宽基扇区。注意事项: 此后池子继续增至 40 支(6 支未编号加入,待追溯), 持续扩容优化移交 `research/pool/`。 |
| REQ-198 | 搭建回测预计算管道 + Tuner 调试页基础设施 | 2026-05-12 | 完成: 抽出 benchmark/trading-calendar/quant-data 模块; 盘中估算+时间戳; preload 优化。持续性能优化移交 `research/params/`。注意事项: F2 计算未移除(仅 w2=0); 当前 3Y 回测约 24.5s(40 支 ETF), 与 12s 标称有差距(原值基于 30 支池子测量)。 |
| REQ-108 | 添加腾讯财经 API 作为备用源 | 2026-05-09 | 腾讯已作为 quant_data_fetcher.py 主数据源接入（东财 API IP 被封后切换）。后续数据源问题移交 `docs/01-数据源与工具生态.md`。 |
| REQ-208 | Tuner 涨跌幅热力图 (5日/20日) | 2026-05-18 | 全部达标。40×40px 固定方格+格内数值，自定义横/纵蓝色滑块，日期标签置顶作为列头，ETF 标签列固定左侧，点击日期头排序，5/20日切换，色阶图例，后端预计算接入 preload+refresh。 |
| REQ-205 | 仓位策略改进 — 集中度参数 + 调仓执行模型 | 2026-05-18 | C 参数(T→1/T)、成交额排序买入、先卖后买两遍遍历、`_execute_rebalance()` 共用函数、ma_trend 熊市现金保护。离散度列(Z-score)加入 tuner snapshot。详见 DESIGN.md §调仓执行模型。 |
| REQ-209 | 统一参数优化框架 `quant_optimizer.py` | 2026-05-21 | grid/random/bayesian(Optuna TPE) 三种策略，checkpoint 续跑，结构化 results.json+report.md 输出。详见 `runbooks/QUANT_RUNBOOK.md` §6。 |
| REQ-210 | PARAM_BOUNDS + Tuner 前端解锁 | 2026-05-21 | `quant_contract.py` 新增 33 参数搜索范围定义 + `auto_bounds()`。Tuner 解锁 max_holdings(1~8)/conf_type(5种)/w4 控件，新增 JSON 粘贴精确加载，setSlider 步长绕过。 |
| REQ-211 | preset4 集中趋势 + spot-check 参数验证 | 2026-05-21 | CLI spot-check 验证 max_holdings=4(6Y+711%)>>6(+479%), MA=20w(+545%)>26w, C=1.0(+567%)>0.5。组合为 preset4 MH=4/C=1.0/MA=20w，CLI 实测 6Y+710.6%/MDD-17.3%/Sharpe=1.50。一致性检查 PASS。 |
| REQ-212 | Optimizer bug修复 (复合指标 + preloaded cache) | 2026-05-21 | 复合指标从 raw mean 改为相对基线归一化（避免 1Y 绑架）；移除预加载 HS300 MA cache（避免 period 错配导致结果污染）。 |
| REQ-196 | 实盘调仓信号生成器 | 2026-05-21 | 已通过 Tuner snapshot 动作列落地。14:45 盘中数据+回测→14:50 出信号→收盘前调仓；7/6 新规后支持盘后收盘价成交。独立脚本不再需要。 |



## backlog (待开发)

| ID | 标题 | 优先级 | 目标版本 | 创建日期 | 来源 |
|----|------|--------|---------|---------|------|
| REQ-222~229 | **稳健策略** (8项): 多周期测试/Walk-forward/信号稳定性/因子衰减/相关性矩阵/压力测试/容量估算/滑点测量 | 🔴🟠 | v3.3.0 | 2026-05-24 | 头脑风暴 |
| REQ-230~239 | **好用界面** (10项): 快捷回测/策略对比/历史浏览器/因子归因/调仓日历/流向图/K线注释/仪表盘/快捷键/主题切换 | 🟠🟡🟢 | v3.3.0 | 2026-05-24 | 头脑风暴 |
| REQ-240~248 | **商业化** (9项): 策略向导/市场/白标PDF/因子教程/策略动画/解剖课/分享链接/微信集成/订阅制 | 🟡🟢 | v3.3.0+ | 2026-05-24 | 头脑风暴 |
| REQ-194 | 统一数据获取管线 + 数据结构统一 | 🟠 High | v3.3.0 | 2026-05-09 | 合并 quant_data_fetcher + fix_ma_and_benchmark K线拉取 + realtime_updater 为统一脚本 |
| REQ-204 | 核心量化模块测试覆盖补全 | 🟠 High | v3.3.0 | 2026-05-14 | quant_backtest/tuner/build_payload 等核心模块零测试覆盖，优先补 backtest 核心路径 |
| REQ-159 | editorial 国内政策源增强 | 🟢 Low | - | 2026-04-21 | 央行/证监会官网解析 |
| REQ-112 | HTML/JS 分离与数据解耦 | 🟢 Low | - | 2026-04-08 | 已评审降级 |
| REQ-207 | index.html 前端工程质量审计 | 🟢 Low | - | 2026-05-15 | 8 项子检查 |

## wishlist (远期愿景)

| ID | 标题 | 创建日期 | 备注 |
|----|------|---------|------|
| REQ-163 | K 线主图对数 Y 轴（log scale）模式 | 2026-04-21 | 详见 plans/REQ-163.md。4 个设计分歧点+建议方案，待交易体系视图成熟后触发。 |
| REQ-206 | 债券 ETF 入池（搁置讨论） | 2026-05-13 | 讨论结论：国债 ETF 波动太低（1-3%）需加杠杆才能与权益持仓并列；企业债与权益强相关无法对冲；当前策略以权益轮动为核心，下行保护更适合走信心函数压仓→现金路径。搁置，不急于开需求。 |
| REQ-167 | 主题切换器：多套配色方案（富途夜间/Bloomberg/FT日间等），CSS变量化+localStorage | 2026-04-21 | 详见 plans/REQ-167.md |
| REQ-169 | "活人味道"板块：股民情绪温度计/黑话角标/舆情/黑历史日历，四方向分阶段演进 | 2026-04-21 | 详见 plans/REQ-169.md |
| REQ-174 | ETF 替换标准流程设计 | 2026-04-23 | 首次实战完成（159566→159755）。后续 meta 需求（onboard CLI / 模板化 / 标准文档）远期推进。 |
| REQ-178 | ETF 估值引擎全覆盖 | 2026-04-27 | 当前部分 ETF 有估值数据，F4 因子尚未接入回测。池子已扩至 40 支，覆盖范围需重新估算。 |

## abandoned (已废弃)

| ID | 标题 | 废弃日期 | 备注 |
|----|------|---------|------|
| REQ-109 | 资源优化（压缩 CSS/JS） | 2026-04-17 | 压缩/单行化尝试导致 index.html 挂掉，回退 GitHub 版本。 |
| REQ-114 | WebSocket 实时更新集成 | 2026-05-16 | 模糊构想，从未进入实际开发。 |
| REQ-115 | 技术分析指标（布林带、MACD、RSI） | 2026-05-16 | 模糊构想，从未进入实际开发。 |
| REQ-116 | 多格式报告生成（PDF、JSON） | 2026-05-16 | 模糊构想，从未进入实际开发。 |
| REQ-117 | 高级过滤 UI（行业、业绩范围） | 2026-05-16 | 模糊构想，从未进入实际开发。 |
| REQ-180 | 量化回测前端二期优化 | 2026-05-21 | Tuner 已独立演进（热力图/snapshot/参数契约），原需求范围已被覆盖。 |
| REQ-181 | 桌面版仪表盘重设计 | 2026-05-21 | Tuner 已独立发展成完整工坊，原设计过时。 |
| REQ-182 | 移动/传播版海报生成 + 自动发布 | 2026-05-21 | 依赖 REQ-181，链式废弃。 |
| REQ-161 | 调试工具栏重构 + 三档配置周更支线 | 2026-05-21 | 用户明确推迟过，且 Tuner 已覆盖调试需求。 |
| REQ-122 | 底栏扩展性与模块滚动优化 | 2026-05-21 | 从 REQ-120 衍生，原始上下文已消失。 |
| REQ-165 | 涨跌配色由"绿涨红跌"反转为"红涨绿跌" | 2026-04-21 | 2026-04-21 代码已回退到最初 `#10b981`/`#ef4444`。废弃原因：红涨绿跌方案虽完成端到端落地（CSS 12 处 / JS 9 处 / Python 3 处 / 测试翻转 128 全绿），但用户视觉回访时觉得深蓝底+饱和红刺眼、不舒服，继而认识到"配色反转是个系统性问题、不能只改涨跌语义那一层"。REQ-165 本身是**色值层级的局部替换**，与 REQ-166 都属于"只改一部分逻辑"的思路；用户判定这条路线从根本上不对，应归入 REQ-167 的整体视觉重设计。代码已完整回滚，id 命名（`text-green` / `highlight-red` / `.positive` / `.bullish` 等）与原始绿/红颜色语义保持一致，避免 id 和颜色错位的语义债务。 |
| REQ-166 | 涨跌配色改为蓝橙脱钩色（富途/Stripe 风格，评级/推荐/风险卡脱钩到青紫灰） | 2026-04-21 | 2026-04-21 代码已回退到最初 `#10b981`/`#ef4444`。废弃原因：在 REQ-165 视觉回访基础上设计了"涨=琥珀 `#fbbf24`，跌=蓝 `#60a5fa`，评级=青紫灰"的两色板脱钩方案，端到端落地后（128 全绿 / `update_report.py` EXIT=0）用户发现**涨跌蓝色与页面内其他中性/信息性蓝色（如 `holdings-concentration-value-*` 等）产生严重冲突**——这证明了一个更深的问题："方向性语义色"无法脱离"全页配色系统"单独设计，蓝色不是"未被使用的安全色"，它已经作为中性信息色在很多 id 里占位。由此得出用户判断：**配色方案必须是整体设计，单改一部分逻辑都不太好**。相关愿景归入 REQ-167（重新立意为"整体视觉重设计 + 主题切换器"）。本次的代码完整回退，保留了最初 `text-green`/`text-red`/`.positive`/`.bullish` 的 id 语义与颜色一致性，给未来的整体重设计留干净的起点。 |

## bugs (活跃缺陷)

> 只放 open / fixing / fixed 状态的 bug。closed / wontfix 归档到 Archive.md。

| ID | 标题 | 严重度 | 状态 | 引入版本 | 关联 | 发现日期 | 根因 | 修复版本 |
|----|------|--------|------|---------|------|---------|------|---------|
| BUG-023 | 手动启动 Tuner 前台窗口且页面延迟打开 | 🟡 Medium | fixed | - | Tuner 启动入口 | 2026-05-08 | PowerShell 3s wait + preload 阻塞 Flask 启动 | v3.2.0 |
| BUG-024 | `set()` 迭代顺序非确定 → CLI/Tuner 回测结果不一致 | 🔴 Critical | fixed | v3.2.0-dev | REQ-205 | 2026-05-18 | PYTHONHASHSEED 随机化导致买入循环顺序不同、现金分配不同。修复: `sorted()` + 成交额排序 | v3.2.0 |
| BUG-025 | MA 趋势信号 lookahead bias — `merge_asof(direction="forward")` | 🔴 Critical | fixed | v3.2.0-dev | weekly_trend/daily_aggressive | 2026-05-18 | 周一~周四用了本周五的 MA 信号(未来数据)。修复: `direction="backward"` | v3.2.0 |
| BUG-026 | `is_last` 残量回收无视 total_target 上限 → 熊市现金被花光 | 🔴 Critical | fixed | v3.2.0-dev | REQ-205 | 2026-05-18 | 第一 pass `buy_value=cash`→修了；第二 pass 用 `cash2` 变量名不同 → 漏修。修复: `min(cash, max(diff,0))` + 共用函数 | v3.2.0 |
| BUG-027 | setSlider `removeAttribute('step')` → 浏览器默认 step=1 → 滑块锁死 0%/100% | 🟡 Medium | fixed | v3.2.0-dev | ma_bull/ma_bear 滑块 | 2026-05-21 | HTML 规范: range input 无 step 属性时默认值=1。修复: `el.step='any'` 代替 `removeAttribute` | v3.2.0 |
| BUG-028 | 中概互联(513050) `--full` 分页 bug → CSV 仅 2017-2019 数据 → 不进因子计算 | 🟡 Medium | fixed | v3.2.0-dev | REQ-214 池子扩容 | 2026-05-22 | `fetch_etf_kline` full 模式后处理丢失中间页数据。手动分页重建 2264 行 CSV。后续 full fetch 仍可能有此问题，需统一修复。 | v3.2.0 |











---


## ID 计数器

**下一个需求 ID**: REQ-249





**下一个 Bug ID**: BUG-029






