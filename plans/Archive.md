# ETF 报告技能 — 归档

> 看板总览见 Board.md

## 版本发布记录

| 版本 | 日期 | 包含需求 | 备注 |
|------|------|---------|------|
| v1.0.0 | 2026-04-01 | REQ-001~006 | 基础系统 |
| v2.1.0 | 2026-04-07 | REQ-101~107 | Phase 1 完成：配置化、日志、健康检查 |
| v2.2.0 | 2026-04-07 | REQ-110, REQ-111 | 懒加载 + 归档系统 |
| v2.3.0 | 2026-04-11 | REQ-118 | 状态栏栈模型 + 人格切换 + 版本发布一条龙 |
| v2.4.0 | 2026-04-17 | REQ-113, REQ-118, REQ-120, REQ-121, REQ-123, REQ-124, REQ-125, REQ-126, REQ-127, REQ-128, REQ-129, REQ-130, REQ-131, REQ-132, REQ-133, REQ-134, REQ-135, REQ-136 | 动态数据绑定与单轨渲染收口、份额变动与解释层日更、调试链路与目录卫生、发布仓模板化和公开导航收口 |
| v2.5.0 | 2026-04-21 | REQ-138, REQ-137, REQ-139, REQ-140, REQ-141, REQ-142, REQ-143, REQ-144, REQ-145, REQ-147, REQ-146, REQ-157, REQ-158, REQ-160, REQ-164, REQ-168, REQ-148 | 调试工具链增强、CSS/JS 外链化、基准与解释层自动化升级、TOP5 归属列、K 线交互优化、成交额口径修正与首屏懒加载收口 |
| v2.6.0 | 2026-04-29 | REQ-184 | 波动率因子(F5)探索与归零验证，策略基线锁定为(20,0,80,0,0)，量化面板改造为纯展示模式 |
| v3.0.0 | 2026-05-08 | REQ-173, REQ-183, REQ-185, REQ-186, REQ-187, REQ-189, REQ-190, REQ-192, REQ-193 | 量化回测大版本：策略参数优化(MA26/B30/DirON Calmar 1.55)、量化正式页UI改造(2:1布局+K线replay+markLine)、日调仓+佣金模拟、残差动量/后视镜因子归零验证、开发环境便携化(batchfiles+rules bundle+repo公开) |
| v3.1.0 | 2026-05-12 | REQ-195, REQ-197, REQ-191 | next_open 实盘成交口径（后续已统一回 same_close）、标的池筛选(universe filter + chip picker UI + URL深链接)、纳指ETF(159941)+黄金ETF(518880)新增(sector=另类,25→27支)、依赖文档完善、绝对路径清理 |
| v3.2.0 | 2026-05-22 | REQ-213~221 | ETF池扩容(40→44)+扇区重划、逐笔配对胜率+赔率、ETF贡献度评估系统(9指标+分析框架)、盘中CSV修复、回测持久化缓存、超额收益+10卡指标、Tuner UI综合优化、扇区语义配色、ETF元数据(规模+Top10持仓)、BUG-027/028 |
| v3.4.0 | 2026-06-02 | REQ-252~267 | QDII停牌感知+全日量估算+push停牌标注、德国入池、AUDIT_RUNBOOK v4.0、Tuner快捷键+键盘快捷键、收盘前信号推送、三派TPE收敛、F2/F4/F5全量清退、人设系统基建 |
| v3.5.0 | 2026-06-05 | REQ-265/269/271/273 + REQ-204 | QDII停牌L2实测完成、精算师退化诊断、F7双重角色研究(黑洞螺旋)、REQ-269三流派负贡献分析(最终结论:不干预选股池)、回测并行化(quant_data_cache+2.7x加速)、核心量化测试覆盖(+27 tests)、Sina快速通道修复+多日补拉清退、_Avoid_术语表(30+术语)+ADR门控+技能闭环审计、CONTRIBUTING.md分拆删除、K线箭头键+点击联动、Matt Pocock调研、养殖研报采集 |
| v3.6.0 | 2026-06-10 | REQ-277 | F1 检查点/冻结点机制 — 修复多 bit 抢跑时中间日自由移动的 bug |
| v3.8.0 | 2026-06-18 | REQ-274/277/280/281/282/283/284/286/287/289/290/291 | shared 模块包化 Phase 1+2（src/etf_report/core/ 迁入 7 个 shared 模块）、ETF 全市场自动筛选引擎 v2 + R14 换池(48支)、ETF 默认勾选机制(active+5%TR阈值)、三派优化 promotion 评审、参数优化报告规范(8节+6方法论)、权重转换逻辑工程化修复、AI 文档/治理文档去 Skill 化、量化运维文档拆分精简、stable 自动更新与计划任务观测、BUG-032/033/034 修复 |
| v3.9.0 | 2026-06-24 | REQ-296/297/298/299/300/278/292/306/308 + 三派赌徒完整优化 | Stage A 合成杠杆引擎(exposure管线+风险指标+Tuner展示)、三周期等权 composite 优化体系、三派赌徒分层优化(gam-1 mdd=-20% bull=0.89 / gam-2 mdd=-25% bull=1.58 / gam-3 mdd=-35% bull=1.92)、MH=2范式发现与沉淀、bootstrap稳健性验证、交易日历CNY后处理(akshare Sina历史数据)、四类聚合标签(group1+一级/二级切换+配色重设计)、宽基ETF白名单筛选(科创50流程走完)、Tuner十大成分股展示、正式页合成杠杆摘要、筛选流datalen修复+并发限流、Sina batch盘中冷却修复、优化器--two-stage串联+analyzer复合排序、子Agent报告生成流程 |
| **v3.10.0** | **2026-07-02** | REQ-310/322/325/327/328/331/332/335/336/337/338/339/341/344/347 + REQ-340(closed) + BUG-041/042 | financing (rate=0.06) + C/CS/B/BS dynamic band + 44 frontier pts re-ran + multi-zone + Tuner cards 15->10 + baseline.yaml + defaults.yaml |
| **v3.11.0** | **2026-07-06** | REQ-348/353/354/355/357 + BUG-042/043/044 | 盘后定价信号推送 + 实盘调仓执行表 + 数据管理面板 + 因子缓存治理 + 引擎NaN防护 + 去杠杆计算修复 |
| **v3.12.0** | **2026-07-08** | REQ-360 + BUG-045/047 | disc_step slider精度修复 + stable交易日历修复 + Gambler前沿扩区(6区→6点) + 拆股后数据修复工作流 |
| **v3.13.0** | **2026-07-17** | REQ-112/159/174/236/268/349/350/351/356/359/361/362/364/365/366/367(证伪)/368/371/372/373/374/375/376 + top_boost/N-TB研究 + BUG-046/048/052/053/054/055 | 预设清理+优化原子提取(research_utils)、F7 双侧参数与双侧扫参(gam-0 AR 119.7%→137.6%, f7_up_power/f7_up_span/f7_down_power/f7_down_span 命名)、信号/执行步长分离+top_boost、参数缩放统一、杠杆上限治理(移除 max_gross_exposure)、停牌感知、分组约束优化框架、Tuner onclick→事件委托+三文件拆分、调仓决策可追溯、NAV 事件锚点、回测输出分级 |



## bugs (已关闭 / 不修复)

### v3.13.0 发布归档（2026-07-17，原 Board bugs 区，均 fixed → closed）

| ID | 标题 | 严重度 | 状态 | 引入版本 | 关联 | 发现日期 | 根因 | 修复版本 |
|----|------|--------|------|---------|------|---------|------|---------|
| BUG-023 | 手动启动 Tuner 前台窗口且页面延迟打开 | 🟡 Medium | closed | - | Tuner 启动入口 | 2026-05-08 | PowerShell 3s wait + preload 阻塞 Flask 启动 | v3.2.0 |
| BUG-024 | `set()` 迭代顺序非确定 → CLI/Tuner 回测结果不一致 | 🔴 Critical | closed | v3.2.0-dev | REQ-205 | 2026-05-18 | PYTHONHASHSEED 随机化导致买入循环顺序不同、现金分配不同。修复: `sorted()` + 成交额排序 | v3.2.0 |
| BUG-025 | MA 趋势信号 lookahead bias — `merge_asof(direction="forward")` | 🔴 Critical | closed | v3.2.0-dev | weekly_trend/daily_aggressive | 2026-05-18 | 周一~周四用了本周五的 MA 信号(未来数据)。修复: `direction="backward"` | v3.2.0 |
| BUG-026 | `is_last` 残量回收无视 total_target 上限 → 熊市现金被花光 | 🔴 Critical | closed | v3.2.0-dev | REQ-205 | 2026-05-18 | 第一 pass `buy_value=cash`→修了；第二 pass 用 `cash2` 变量名不同 → 漏修。修复: `min(cash, max(diff,0))` + 共用函数 | v3.2.0 |
| BUG-027 | setSlider `removeAttribute('step')` → 浏览器默认 step=1 → 滑块锁死 0%/100% | 🟡 Medium | closed | v3.2.0-dev | ma_bull/ma_bear 滑块 | 2026-05-21 | HTML 规范: range input 无 step 属性时默认值=1。修复: `el.step='any'` 代替 `removeAttribute` | v3.2.0 |
| BUG-028 | 中概互联(513050) `--full` 分页 bug → CSV 仅 2017-2019 数据 → 不进因子计算 | 🟡 Medium | closed | v3.2.0-dev | REQ-214 池子扩容 | 2026-05-22 | `fetch_etf_kline` full 模式后处理丢失中间页数据。手动分页重建 2264 行 CSV。后续 full fetch 仍可能有此问题，需统一修复。 | v3.2.0 |
| BUG-035 | tuner-metrics 翻页高度跳动 — 杠杆指标第二页(2x5)容器高度与第一页不一致 | 🟡 Medium | closed | v3.9.0 | — | 2026-06-24 | 占位卡无内部结构导致grid行高塌陷。修复：填充 `.label+.value` 占位内容 | v3.10.0 |
| BUG-036 | tuner-snapshot-footer 全选/全不选/反选无响应 — 三个筛选按钮点击不触发sectorFilter变更 | 🟡 Medium | closed | v3.9.0 | — | 2026-06-24 | `JSON.stringify(allKeys)` 含双引号嵌入 `onclick="..."` 属性导致 HTML 解析截断。修复：全局存储 + 独立函数 | v3.10.0 |
| BUG-037 | nav-chart / MDD副图 / K线图缩放平移无联动 | 🟡 Medium | closed | v3.9.0 | BUG-035 | 2026-06-24 | 三个图表 `dataZoom` 缺少 `groupId`。修复：统一添加 `groupId:'tuner-zoom'` | v3.10.0 |
| BUG-038 | 🔴 合成杠杆从未生效 — `_execute_rebalance` 买入金额被现金上限截断 | 🔴 Critical | closed | v3.0.0 | 全部杠杆回测 | 2026-06-25 | 3 处修复: buy_value 上限改为 max_gross_exposure×tv + 契约不再覆盖 account.mode + 前端账户模式选择器 | v3.10.0 |
| BUG-039 | echarts.init() 清空 #nav-chart 子元素 → kline-freq-tabs 按钮被抹除 | 🟡 Medium | closed | v3.9.0 | REQ-328 | 2026-06-29 | ECharts 5.5.1 `init(dom)` 清空容器 innerHTML。修复: `#kline-freq-tabs` 移出到父级作兄弟节点 | v3.11.0 |
| BUG-040 | preclose_push 杀 dev Tuner — 端口 5179 冲突 | 🟡 Medium | closed | v3.2.0 | preclose_push | 2026-06-29 | `_ensure_tuner()` 无条件 taskkill 端口 5179。修复: `--port` 参数 + preclose_push 改用 5180 | v3.10.0 |
| BUG-041 | 盘中回测不含今日数据 — 因子计算用 CSV，不含盘中 bar | 🟡 Medium | closed | v3.10.0-dev | — | 2026-06-30 | `all_daily` 改为使用盘中合并数据 + 刷新自动补历史缺口 | v3.10.0 |
| BUG-042 | gam-0 种子指标计算错误 — AR 公式 `**(365/d-1)` 误把 -1 放入指数 | 🟡 Medium | closed | v3.10.0-dev | — | 2026-06-30 | gambler pool 中 gam-0 AR=2.5% 而非 110%，未被 narrow_bounds 选中 | v3.10.0 |
| BUG-043 | 杠杆贡献 exposure≤100% 时显示非零 — nav[0]≠initial_capital 导致分母不一致 | 🟡 Medium | closed | v3.11.0-dev | — | 2026-07-02 | `total_return` 分母为初始本金 1M，`unlevered_total_return` 经由 nav[0] 复利，建仓佣金使 nav[0]<1M | v3.11.0 |
| BUG-044 | 去杠杆计算反向放大熊市不满仓收益 — exp<1.0 时 daily_ret/exp 反向放大 | 🟡 Medium | closed | v3.9.0 | — | 2026-07-02 | `exp > 0.01` 门控太宽，熊市 54% 仓位被 `/0.54` 放大到 100% | v3.11.0 |
| BUG-045 | 前端 disc_step slider 精度丢失致信号错误 — Math.round(16.5)→17 | 🟡 Medium | closed | v3.11.0 | REQ-348 preclose_push | 2026-07-08 | slider step=1 无法表示 0.005 精度 | v3.12.0 |
| BUG-046 | 仓位百分比四舍五入不保证总和等于总敞口 | 🟡 Medium | closed | v3.11.0 | 展示层 | 2026-07-08 | 个仓 Math.round 各自进位。修复: 调仓快照表格用最大余数法保证和=totalPos | v3.13.0 |
| BUG-047 | stable 交易日历缺失 → 数据管理面板日线空白 | 🟡 Medium | closed | v3.11.0 | 数据管理面板 | 2026-07-08 | 手动复制治标, `load_trading_calendar()` 自愈生成治本；新增 `generate_trading_calendar.py` | v3.12.0 |
| BUG-048 | "补全空缺"无法修复中间缺口 — freshness check 只看 CSV 末尾日期 | 🟡 Medium | closed | v3.12.0 | 数据管理面板 | 2026-07-08 | 中间缺口(gap_end < last_csv)使用 patch_range 按范围拉取合并 | v3.13.0 |
| BUG-049 | P2 前沿点 Tuner 回测结果不刷新 — pool 旧量程参数混入前沿 JSON | 🟡 Medium | closed | v3.12.0 | 前沿面板 | 2026-07-08 | REQ-361 量程重构副作用。修复：前沿数据归一化 + $id() 缺失补全 | v3.12.0 |
| BUG-050 | BUG-043 根因补完：softmax 数值稳定性 — stable softmax 替代 clip(±700) | 🟡 Medium | closed | v3.11.0 | BUG-043, REQ-361 | 2026-07-09 | clip(±700) 接近 float64 边界，高 effective_c 时溢出 → NaN → 前沿 re-validation 丢弃候选点 | v3.12.0 |
| BUG-051 | load_config 权重未跟随 REQ-361 迁移 → CLI/Tuner 不一致 | 🟡 Medium | closed | v3.12.0 | REQ-361 | 2026-07-09 | REQ-361 迁移不完整。修复：`load_config` 加权重 ÷100 | v3.12.0 |
| BUG-052 | build_frontier_output MDD 范围错配 + 重验证后缺槽位去重 | 🟡 Medium | closed | v3.12.0 | /optimize 前沿刷新 | 2026-07-10 | mdd_range 默认值不对齐 + 缺 post-validation 槽位去重 | v3.13.0 |
| BUG-053 | Tuner 权重量程 ÷100 → CLI/Tuner 回测结果不一致 | 🟡 Medium | closed | v3.13.0 | REQ-361, REQ-375 | 2026-07-15 | REQ-361 权重量程迁移不完整。修复：移除 ÷100，默认值对齐 YAML | v3.13.0 |
| BUG-054 | defaults.yaml 缺 F7 超跌侧参数 → Tuner 回退硬编码值 → AR 差 17pp | 🟡 Medium | closed | v3.13.0 | REQ-375 | 2026-07-16 | 新增参数契约未完整覆盖 defaults.yaml | v3.13.0 |
| BUG-055 | research_utils `_build_override` 提前 return → F7/权重扫参静默失效 | 🟡 Medium | closed | v3.13.0 | REQ-362, REQ-375 | 2026-07-16 | 死代码（return 后逻辑不可达）；同族修正两处测试 fixture 权重量程 | v3.13.0 |

| ID | 标题 | 结论 | 严重度 | 发现日期 | 关闭日期 | 备注 |
|----|------|------|--------|---------|---------|------|
| BUG-001 | ETF 详情页卡片高度与业绩区间距异常 | closed | minor | 2026-04-13 | 2026-04-13 | 用户确认“很顺眼”；已统一双栏等高策略，并为“近期业绩表现”补充分组标题间距规范 |
| BUG-002 | 515880 拆分后未复权K线失真 | closed | major | 2026-04-15 | 2026-04-15 | 已由 `REQ-124` 吸收为流程需求并完成：份额变动现改为 K 线生成阶段的数据清洗步骤，周线重建与归一化走势统一消费清洗后的日线数据 |
| BUG-004 | ETF 详情页与K线在开盘时段误混入盘中实时口径 | closed | major | 2026-04-16 | 2026-04-16 | 用户要求报告主展示严格以页面“数据截止”对应的最后收盘日为准；已完成修复：`fix_ma_and_benchmark.py` 盘中自动剔除未收盘日线 bar，`update_report.py` / `index.html` 不再用 `realtimeData.etf_price` / `etf_change` 覆盖详情页收盘价与日涨跌，当前回归 `79 passed`，真实生成页 `159865` 已按 `2026-04-15` 收盘口径显示 |
| BUG-005 | 提交后 `index.html` 被发布/更新流程覆盖 | closed | major | 2026-04-17 | 2026-04-17 | 已按发布前补救任务关闭：根因是发布仓配置漂移导致旧瘦仓强推覆盖正式仓；现已切回当前技能仓为发布源、停用旧 `pages_repo_root`、增加同 remote / 同分支保护，并已验证远端 `main` 与 Pages 恢复到 2026-04-17 报告 |
| BUG-006 | 热区模式误标 K 线标题且漏标运行时收益节点 | closed | major | 2026-04-18 | 2026-04-18 | 根因一：`REQ-137` 使用 `[id^="kline-daily-"]` / `[id^="kline-weekly-"]` 这类前缀选择器，误把 `kline-*title-*` / `kline-*card-*` 也扫进热区；根因二：`renderDetailPanel()` 重绘业绩表时丢失 `performance-return-*` 细粒度 id，导致真实热数据漏标。现已收窄图表选择器到 `.kline-container-small`，并在运行时/构建时统一保留收益单元格 id，同时把技术信号描述文本纳入热区。 |
| BUG-007 | 模糊搜索定位按钮点击无响应 | closed | major | 2026-04-18 | 2026-04-19 | 已完成收口：先修复搜索态事件绑定与旧版面板 DOM 混用导致的启动中断；本轮再补齐关闭聚焦面板即自动清除高亮的交互，使最终行为与 REQ-140 记录一致。 |
| BUG-008 | 热区模式切换 ETF 后首次查看节点漏框 | closed | major | 2026-04-19 | 2026-04-19 | 根因是 ETF 面板运行时重绘时对 `daily-change-value-*` / `moving-average-status-*` / `tech-rating-value-*` / `recommendation-rating-value-*` 等热区节点直接覆写 `className`，把已有 `debug-hotspot-target` 一并抹掉；现已改为只切换业务态 class、保留调试类，同时保留渲染后热区重刷作为兜底。 |
| BUG-009 | Alt 点击策略文本复制 id 失败 | closed | major | 2026-04-19 | 2026-04-19 | 根因是调试模式复制逻辑优先走 `navigator.clipboard.writeText()`，当浏览器在部分文本节点点击场景下拒绝授权时会直接抛错且没有 fallback；现已改为 Clipboard API 失败后自动回退到 `execCommand('copy')`，并补齐 selection 设置。 |
| BUG-010 | GitHub Actions 测试在 `main(c615520)` 失败 | closed | major | 2026-04-20 | 2026-04-21 | 随 `v2.5.0` 发布收口：CI 已补齐 `PyYAML` 依赖安装，`.github/workflows/test.yml` 同步到当前仓。 |
| BUG-011 | `update_report.py` 找不到 `klineData` 常量 | closed | minor | 2026-04-20 | 2026-04-21 | 随 `v2.5.0` 发布收口：HTML 内联 const 检查已降级为兼容路径，`runtime_payload.js` 成为唯一事实源。 |
| BUG-012 | 两个测试断言未跟随 REQ-146 架构更新 | closed | minor | 2026-04-20 | 2026-04-21 | 随 `v2.5.0` 发布收口：测试断言已补齐新增 id，适配 JS/CSS 外链化后的结构。 |
| BUG-013 | `fix_ma_and_benchmark.py` 残留 outputs/js/main.js 更新路径 | closed | minor | 2026-04-20 | 2026-04-21 | 随 `v2.5.0` 发布收口：旧 `outputs/js/main.js` 更新链路已移除，统一收束到 `runtime_payload.js`。 |
| BUG-014 | `health_check.py` A4 文件大小阈值未跟随 JS/CSS 抽离 | closed | minor | 2026-04-20 | 2026-04-21 | 随 `v2.5.0` 发布收口：HTML 体积阈值已下调，并补充外链资源存在性守护。 |
| BUG-015 | `health_check.py` D2 仍查 HTML 内联 const | closed | minor | 2026-04-20 | 2026-04-21 | 随 `v2.5.0` 发布收口：D2 已优先校验 `runtime_payload.js`，仅在兼容模式下回退内联 const。 |
| BUG-016 | 手电筒独开时按 Alt 触发"复制失败"+误激活放大镜 | closed | major | 2026-04-21 | 2026-04-21 | 随 `v2.5.0` 发布收口：Alt+click 现只保留复制语义，不再把放大镜状态写回手电筒流程。 |
| BUG-017 | 三档配置卡片 allocation-card-item / strategy 未接入日更链路 | closed | minor | 2026-04-21 | 2026-04-21 | 随 `v2.5.0` 发布收口：问题已在判词层面闭环，后续周更支线转入 `REQ-161`，本轮不再视作活跃缺陷。 |
| BUG-018 | 日 K / 周 K 副图显示成交量而非成交额，tooltip 错位 | closed | minor | 2026-04-21 | 2026-04-21 | 随 `v2.5.0` 发布收口：主行情链已补入 `amount` 字段，副图与 tooltip 统一切换为成交额口径。 |
| BUG-019 | 515880 通信设备 ETF 的 K 线基准、页面业绩基准、基金合同基准三者不一致 | closed | minor | 2026-04-21 | 2026-04-21 | 随 `v2.5.0` 发布收口：K 线基准与页面文案已统一改为创业板指。 |
| BUG-020 | 文档暴露本地绝对路径与用户级规则引用 | closed | major | 2026-04-21 | 2026-04-21 | `README.md` 曾写入本机 `file:///c:/Users/...` 绝对路径，并引用用户级规则文件；`SKILL.md`、`CONTRIBUTING.md`、`plans/REQ-161.md` 也带有用户级规则路径。现已统一改写为仓库内自洽表述，并将 `PLAN.md` 加入 `.gitignore` 且从 Git 跟踪中移出。 |
| BUG-021 | 发布前唯一门禁未收束到 `plans/private/GIT_WORKFLOW.md` | closed | major | 2026-04-21 | 2026-04-21 | 已完成治理收口：`.codebuddy/rules/etf-report.mdc` 与 `PLAN.md` 不再并列维护发布前检查，统一改为只引用 `plans/private/GIT_WORKFLOW.md`；该文档现已重写为发布前唯一门禁，并加入 `.gitignore` 且从 Git 跟踪中移出。 |
| BUG-024 | FetchData 后 Tuner 回测/K线仍停在 2026-05-08 | closed | medium | 2026-05-11 | 2026-05-12 | FetchData 依赖腾讯 weekly K线，周内未生成当周周线；已改为由本地 daily 重建 weekly。v3.1.0 修复。 |
| BUG-032 | **F1 跨周冻结失效** — checkpoint_f1 在周边界被重置为 None，新周周一跌入 else 分支重算 base，导致周一 F1 ≠ 上周五 | fixed | critical | 2026-06-15 | 2026-06-18 | `checkpoint_f1 = None` → 应携带 `f1_val[i-1]`。v3.6.1 修复。 |
| BUG-033 | **Tuner 启动白屏** — `SCHOOLS[3]`(`自定义`)缺 `target`/`constraint`，`renderPresetCards()` `school.target.split()` 抛 TypeError 阻塞页面 | fixed | critical | 2026-06-16 | 2026-06-18 | 补字段 + JS 加固 `undefined.split()`。v3.7.0 修复。 |
| BUG-034 | **Snapshot 仓位显示非整数** — 离散化后归一化 `* (total_target/pos_sum)` 把步长整数倍（22%/33%）变成浮点（22.2%/33.3%），前后端不一致 | fixed | medium | 2026-06-17 | 2026-06-18 | 归一化替为残量补最大权重者，保持步长整数倍。v3.7.0 修复。 |
| BUG-030 | 回测历史信号漂移：全量重拉CSV后6/3煤炭得分从65.3降至62.7，排名从第2跌至第7 | closed | critical | 2026-06-05 | 2026-06-05 | f1_active_days 重构重写了整个 F1 管线（rebuild_weekly + bitmask），旧基线不可比。 |
| BUG-031 | 交易日历缺失历史节假日 | closed | medium | 2026-06-10 | 2026-06-10 | 已转 REQ-278：增加中国节假日后处理修正日历，替换临时硬编码。 |










## abandoned (已废弃)

| ID | 标题 | 废弃日期 | 原因 |
|----|------|---------|------|
| REQ-109 | 资源优化（压缩 CSS/JS） | 2026-04-17 | 用户确认废弃：此前曾实现过一版压缩/单行化思路，结果导致 `index.html` 挂掉，后续修复继续恶化，最终只能在 GitHub 回退版本；当前不再继续沿此方向推进。 |

