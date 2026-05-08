---
description: 需求管理守卫 — ETF 报告技能
alwaysApply: true
enabled: true
updatedAt: 2026-04-21T21:45:00.000Z
provider: 
---

# 需求管理守卫 — ETF 报告技能

## 激活条件

1. 用户提到/编辑的文件路径匹配：`c:/Users/julentan/CodeBuddy/StockMarket/.codebuddy/skills/etf-report/`
2. 用户对话包含触发词：`etf-report, etf 报告, 投资报告, etf 技能`

## 入口守卫

激活后执行：

1. 读取 `PLAN.md` + `plans/Board.md`
2. 记住：当前版本号、ID 计数器、in_progress 需求、活跃 Bug
3. 若用户当前讨论的是**新增需求 / 新增 Bug**，且已明显进入持续推进、改文件、排查修复、状态流转或后续归档范畴，则应先消费 `Board.md` 中的下一个 ID 完成登记，再继续实现
4. 若用户意图命中 **发布 / 上线 / 宣布发布 / 已经发布 / Pages 正常 / 恢复远端 / 推正式仓**，则应立刻切入「版本发布守卫」，不要把它当普通问答或一次性轻任务
5. 若用户已经明确表示"刚发布完""已经推上去""页面已经正常显示"，则要额外判断是否进入「已发布补救模式」

## 职责边界

本规则文件只负责 **ETF 报告技能自己的需求看板 / 版本 / Bug 守卫**，不再负责状态栏协议本身。

当前分工：
- 通用状态栏协议宿主：`.codebuddy/rules/statusbar-protocol.mdc`
- `etf-report` 状态网络配置：`.codebuddy/skills/etf-report/statusbar.config.md`
- `etf-report` 需求管理与版本治理：本文件
- `runbooks/RELEASE_RUNBOOK.md`：发布前**唯一门禁**与唯一步骤事实源，定义发布前到底要做什么
- `PLAN.md`：需求管理入口文件；不再重复维护发布前检查清单

## 版本发布守卫

### 0. 前置检查：IDE 端点判定（Claude ↔ CodeBuddy）

本守卫文件通过 agent-sync 在 Claude 侧（`.codebuddy/rules/etf-report.md`）与 CodeBuddy 侧（`.codebuddy/rules/etf-report.mdc`）两端同时存在。但 **发布动作的合法端只有 CodeBuddy**。

#### 🧠 助记模型：工坊 / 出版社

> **Claude 侧 = 开发工坊 + 本地展厅**
> **CodeBuddy 侧 = 出版社 + 发行部**
>
> 工坊里打磨样品，样品只给自己看（本地 `file://` 预览）；
> 月末把样品打包送到出版社（`agent-sync merge-all`）；
> 出版社走发行流程把它送到读者面前（`--publish` → 企微 / GitHub Pages）。

由此可以秒答常见问题：

- "Claude 里能跑 `--publish` 吗？" → 工坊不做发行，不能
- "Claude 里能改 `index.html` 吗？" → 可以，这是样品，不碰对外出版物
- "两端 `index.html` 会不会打架？" → 不会，一份在工坊、一份在出版社仓库，各自独立
- "月末改完代码怎么出版？" → 先 `agent-sync merge-all` 送到出版社，再由出版社走发布流程

这个助记模型**只服务于 etf-report 心智对齐**，严格的行为约束仍以下方判定规则和 `~/.codebuddy/rules/dual-ide-rhythm.md` §2 为准。

#### 判定规则

进入下方任何"正常发布 / 已发布补救 / 发布阻塞"子模式前，AI 必须先做一次端点判定：

- 若当前会话运行在 **Claude Code** ——
  - 立即拒绝发布动作，引用 `~/.codebuddy/rules/dual-ide-rhythm.md` §2 的硬约束
  - 明确告知用户："Claude 侧是开发沙箱，发布要到 CodeBuddy 会话里做"
  - 提醒用户正确路径：先 `agent-sync merge-all`，再切 CodeBuddy 跑 `update_report.py --publish`
  - **不进入**下面的 §1 / §2 / §3 子模式
- 若当前会话运行在 **CodeBuddy** ——
  - 正常进入下方发布守卫
- 若当前 IDE 端点**无法判定** ——
  - 主动向用户确认一次："你现在是在 Claude 还是 CodeBuddy 会话里？"
  - 用户明确回答后再决定是否放行

**理由**：两端共享同一份项目级规则（经 agent-sync 保证内容一致），但每端的合法动作集不同。项目级规则必须**自己知道**这个差异，不能依赖上层宏观规则被 AI 记得引用。

### 1. 正常发布模式

当用户明确说"发布"时，默认进入正常发布模式。**发布前唯一门禁是 `runbooks/RELEASE_RUNBOOK.md`。** 本规则只负责保证它一定被触发，而不是被忽略成普通聊天。

执行要求：

1. **唯一门禁**
   - 必须逐项对照 `runbooks/RELEASE_RUNBOOK.md`
   - `Board.md` / `Archive.md` / 版本号 / Git / PR / 直推策略 / 敏感信息排查等，一律以 `runbooks/RELEASE_RUNBOOK.md` 的定义为准
   - 若 `runbooks/RELEASE_RUNBOOK.md` 未覆盖某个准备发布必须做的动作，先补写该文档，再继续发布
2. **禁止双轨口径**
   - 不得同时再以 `PLAN.md` 或本规则正文维护另一套发布前检查列表
   - 不得把 `runbooks/RELEASE_RUNBOOK.md` 之外的检查口径视为并列门禁
3. **Git 提交 / 推送限制**
   - 未完成 `runbooks/RELEASE_RUNBOOK.md` 的核对前，不得进入 Git 提交 / 推送
   - 若用户要求快速直推，也必须先走完 `runbooks/RELEASE_RUNBOOK.md` 中定义的快速路径前置检查
4. **发布完成口径**
   - 只有 `runbooks/RELEASE_RUNBOOK.md` 定义的全部发布前动作都完成后，才可以对外口径写成"`vX.Y.Z` 发布完成"

### 2. 已发布补救模式

当**实际发布已经发生**，但 `Board.md` / `Archive.md` / Bug 状态 / 计数器还没收尾时，进入已发布补救模式。

典型触发：
- 本轮或上一轮已经发生 `push` / `force push`
- GitHub Pages 已经正常显示目标页面
- 用户说"其实已经发布了，就当补救发布前任务处理"

处理原则：

1. 将其视为**发布治理补救**，不是普通闲聊
2. 先确认远端仓 / Pages 是否已经处于目标版本状态
3. 若已实际发布，则必须补齐：
   - `Archive.md` 版本发布记录
   - `Board.md` 的 `done` 清空
   - `Board.md` 的当前版本 / 发布日期 / 开发中需求
   - 活跃 Bug 的关闭 / 转状态 / 归档
   - ID 计数器递增
4. 用户若明确表示**不必再提交 / 推送 GitHub**，则可以只做本地治理文件补齐，不重复推送
5. 只有补齐后，才可以把口径从"已经上线"升级成"正式发布完成"

### 3. 发布失败 / 阻塞处理

若发布前检查失败，或中途卡在远端、页面、配置、权限等步骤：

1. 先明确卡在哪一步
2. 判断它是一次性轻任务、活跃 Bug、还是需要继续推进的新需求
3. 若已进入持续跟踪，应补号登记后再继续
4. 不要在版本治理未完成的情况下直接宣称"发布完成"

## 出口守卫

对话结束前检查：

1. `Board.md` / `Backlog.md` / `Archive.md` 是否需要更新？
2. ID 计数器是否需要递增？
3. 本轮是否出现了**已实质推进但尚未编号**的新需求 / 新 Bug？若有，先补登记再结束
4. 版本信息是否需要更新？
5. 若本轮发生了**发布 / 补救发布 / 远端恢复 / Pages 生效**，则必须额外检查：
   - `Board.md done` 是否已清空
   - `Archive.md` 是否已新增版本发布记录
   - 活跃 `major/critical` Bug 是否已关闭、转状态或给出阻塞说明
   - `Board.md` 的版本号、发布日期、开发中需求是否已更新
6. 若已经发生实际发布，但治理收尾还没补齐，则**不要结束对话**；应先补齐，或明确告诉用户当前仍缺哪一步
