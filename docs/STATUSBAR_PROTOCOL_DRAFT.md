# 状态栏协议草案（v1 草案）

## 1. 目标

把当前 `etf-report` 已验证有效的带状态回复能力，抽离为一套可迁移的 **状态栏协议 + 状态网络配置** 机制，使其能够：

- 在不改造目标工作区业务内容的前提下迁移到其他工作区
- 支持同一工作区下多个主题 / 技能各自拥有独立配置
- 让新用户仅通过模板即可理解如何定义自己的状态网络
- 将 `PLAN.md` 等需求面板文档中的状态网络内容完整迁出，避免边界混杂

---

## 2. 设计原则

### 2.1 单一事实源
- 状态栏协议由协议文档定义
- 某个主题的状态网络由其配置文件定义
- 需求看板、路线图、实施文档不再承载状态网络正文

### 2.2 先发现、后持有
- 协议在**激活时**执行一次配置发现与选中
- 选中后进入“活动配置”阶段，后续回复默认沿用该配置
- 仅在明确切换主题、配置失配、配置文件更新或用户要求重判时重新发现

### 2.3 配置作用域就近生效
- 配置可以放在技能目录、模块目录或工作区级目录下
- 配置放在哪里，不直接决定语义；真正决定生效的是配置内部声明的**作用域与激活条件**
- 同一工作区允许多个配置并存，由协议动态选中当前活动配置

### 2.4 v1 核心最小化
- v1 核心 schema 只保留任何工作区都容易理解的概念
- 专属或暂未稳定的语义通过 `extensions` 承接
- 协议必须解释所有核心字段的用途与填写方式

---

## 3. 协议职责

协议负责以下四类能力：

### 3.1 显示协议
定义状态栏的固定外观：

```text
> {网络段} | {状态段} | {micro-stage} | {上下文}
────────────────────────────────────────────
正文从这里开始
```

其中：
- `网络段` 通常来自 `Display.network_marker`，例如 `🧠 Risk`
- `状态段` 由配置里已定义的 canonical state/action 组成，例如 `🔍 审视`
- `micro-stage` 是 AI 针对当前片段自由生成的 `emoji + prompt`，例如 `✅ 校验`、`🧩 收口`
- `上下文` 用于表达该片段的主题、范围或对象，例如 `时间状态机`
- 对于 `skill`、`module` 等具名主题配置，`Display.network_marker` 视为必填
- 只有 `workspace-default` 配置或协议内置配置，才允许降级为 `> {状态段} | {micro-stage} | {上下文}`，占用无命名空间的公共格式
- 推荐示例：`> 🧠 Risk | 🔍 审视 | ✅ 校验 | 时间状态机`

并要求使用渲染安全写法，确保 markdown 环境中稳定显示为三行。

额外约束：
- `状态段` 必须稳定引用配置中定义的 canonical key，不得被 AI 临场生成的新标签替换
- `micro-stage` 允许自由发挥，但目标是增强节奏感、位置感与可读性，而不是制造第二套状态体系





### 3.2 发现协议
定义如何在当前工作区内搜索所有候选配置，并识别哪些文件属于状态栏配置。

### 3.3 选中协议
定义当多个配置同时存在时，如何根据当前对话上下文选中一个活动配置。

### 3.4 结构协议
定义配置文件的最小结构、核心字段含义、冲突处理、降级行为，以及 `extensions` 的兼容方式。

---

## 4. 配置职责

配置负责描述某个**具体主题**下的状态网络，例如：

- `etf-report` 开发状态网络
- `ashare-trading-system` 实盘执行状态网络
- 某个工作区的默认通用状态网络

一份配置主要回答这些问题：

- 这份配置是谁的
- 何时应当生效
- 有哪些状态
- 有哪些动作
- 用户说什么时优先进入哪个状态或动作
- 这些状态如何嵌套 / 流转 / 替换
- 状态栏右侧上下文如何组织
- 哪些专属语义暂时放入 `extensions`

---

## 5. 运行模型

## 5.1 激活阶段
协议被触发后，执行一次状态栏配置发现：

1. 以当前会话工作区为搜索边界
2. 在工作区 `.codebuddy/` 下全局搜索候选配置
3. 读取每个候选配置的元信息
4. 结合当前对话上下文，选出一个活动配置
5. 进入持有阶段

## 5.2 持有阶段
在活动配置未失效前，后续回复默认沿用该配置：

- 使用配置定义的状态 / 动作 / 路由 / 显示规则
- 不重复全量搜索配置
- 仅保留必要的状态切换判断

## 5.3 重判阶段
以下情况触发重新发现与选中：

- 用户明确切换到另一个主题 / 技能 / 模块
- 当前配置明显无法解释对话内容
- 配置文件被用户更新
- 用户要求“重新判断当前状态网络”

---

## 6. 配置发现与选中流程

### 6.1 发现范围
协议在当前工作区的 `.codebuddy/` 范围内全局搜索所有候选配置。

> 协议不预设“配置只属于技能”或“配置只属于工作区默认值”；这些语义由配置自己声明。

### 6.2 候选识别
一个文件被视为状态栏配置，至少应声明：

- 配置类型
- 配置名称
- 协议版本
- 激活条件

### 6.3 选中优先级
多个候选同时命中时，按以下顺序决策：

1. **更具体的主题命中** 优先于泛化命中
2. **显式路径 / 文件关联命中** 优先于仅关键词命中
3. **配置优先级更高** 的优先
4. 若仍冲突，则使用工作区默认配置
5. 若仍无结果，则降级到协议内置配置

### 6.4 降级行为
- **工作区默认配置**：当前工作区内的通用兜底
- **协议内置配置**：当工作区无任何可用配置时使用，同时也可作为模板参考

---

## 7. v1 核心 schema

v1 的目标不是完整表达所有协作哲学，而是先定义一套**新用户看得懂、第一次就能填、协议也能稳定读取**的最小配置结构。

### 7.1 冻结目标

从这一版开始，schema 不再继续无边界增长，而是把字段明确分成三档：

- **保留**：进入 v1 正式字段集
- **合并**：并入其他字段或直接借用 markdown 结构表达
- **删除**：不进入 v1 配置，由协议固定或直接放弃支持

### 7.2 最小可用配置

一份配置要被协议识别并可以工作，至少应满足：

| 部分 | 是否必填 | 最低要求 |
|------|----------|----------|
| frontmatter | 必填 | `config_type`、`name`、`protocol`、`scope`、`summary` |
| Activation | 必填 | `keywords` / `paths` / `topics` 三者至少有一种非空 |
| States | 必填 | 至少定义 1 个状态 |
| Routing | 条件必填 | 当存在多个可选状态/动作时必须提供 |
| Actions | 可选 | 没有动作也可以 |
| Stacking | 可选 | 不提供时使用协议默认栈规则 |
| Display | 条件必填 | 非 `workspace-default` 配置必须提供 `network_marker`；只有公共默认位可省略 |
| Extensions | 可选 | 用于承接专属语义 |


### 7.3 字段冻结总表

| 区块 | 保留 | 合并 | 删除 |
|------|------|------|------|
| frontmatter | `config_type`, `name`, `protocol`, `scope`, `summary`, `priority` | - | - |
| Activation | `keywords`, `paths`, `topics`, `examples`, `notes` | - | - |
| States | `key`, `emoji`, `summary`, `context_format`, `enter_when`, `nesting`, `transitions`, `notes` | `label` → 使用状态小节标题 | - |
| Actions | `key`, `emoji`, `summary`, `context_format`, `trigger_when`, `interrupts_state`, `notes` | `label` → 使用动作小节标题 | - |
| Routing | `rules` | `order` → 使用 `rules` 的书写顺序表达优先级 | - |
| Stacking | `operations`, `notes` | `default_behavior` → 融入 `notes` | `stacked_types`, `non_stacked_types` |
| Display | `network_marker`, `fallback_context`, `context_presets`, `notes` | - | `header_template`, `separator`, `markdown_safe_mode` |
| Meta | - | `scope_detail` / `owner` / `default_context` → 合并进 `summary`、`Activation.notes` 或 `Display.fallback_context` | 整个 `Meta` 区块不再作为 v1 正式部分 |

| Extensions | `extensions` 下任意扩展块 | - | - |

### 7.4 frontmatter（必填）

frontmatter 用于让协议快速识别候选配置。

**必填字段**：

- `config_type`：固定为 `statusbar`
- `name`：配置名称
- `protocol`：协议版本，如 `statusbar/v1`
- `scope`：作用域说明，如 `skill`、`module`、`workspace-default`
- `summary`：一句话说明这份配置的用途

**可选字段**：

- `priority`：冲突时用于比较优先级；默认 `50`

### 7.5 Activation（必填）

Activation 描述何时应选中这份配置。

**至少填写一类命中线索**：

- `keywords`：关键词列表
- `paths`：路径线索列表
- `topics`：主题描述

**可选字段**：

- `examples`：触发示例
- `notes`：补充说明

> 规则：如果 `keywords`、`paths`、`topics` 全为空，则该配置不能被视为可激活配置。

### 7.6 States（必填）

States 描述会进入状态栈、具有持续性的状态对象。

每个状态的**建议最小字段**：

- `key`：内部标识
- `emoji`：状态栏图标
- `summary`：状态含义
- `context_format`：右侧上下文的组织方式

每个状态的**常用可选字段**：

- 小节标题：天然承担显示名职责，不再单独保留 `label`
- `enter_when`：进入条件说明
- `nesting`：是否允许嵌套；默认 `false`
- `transitions`：允许流转到哪些状态
- `notes`：补充说明

### 7.7 Actions（可选）

Actions 描述瞬时动作，不一定进入状态栈。

每个动作的**建议最小字段**：

- `key`
- `emoji`
- `summary`
- `context_format`

每个动作的**常用可选字段**：

- 小节标题：天然承担显示名职责，不再单独保留 `label`
- `trigger_when`：触发条件说明
- `interrupts_state`：是否中断当前状态；默认 `false`
- `notes`

### 7.8 Routing（条件必填）

Routing 描述用户输入与状态 / 动作之间的匹配关系。

**何时必须填写**：

- 配置中存在多个状态
- 或同时存在状态与动作
- 或希望覆盖协议默认兜底规则

**保留字段**：

- `rules`：规则列表
  - `match`
  - `target_type`（`state` / `action` / `default`）
  - `target`：对应状态或动作的 `key`
  - `reason`

**冻结结论**：

- 不再保留单独的 `order` 字段
- `rules` 的书写顺序本身就是优先级顺序

> 简化规则：若配置只定义了 1 个状态，且没有动作，可省略 `Routing`，协议默认把该状态视为兜底状态。

### 7.9 Stacking（可选）

Stacking 描述状态网络的结构关系。

**保留字段**：

- `operations`：支持哪些切换机制，如 `push / replace / clear / resume`
- `notes`

**协议默认值**：

- `states` 入栈
- `actions` 不入栈
- 支持 `push` 与 `resume`

**冻结结论**：

- `stacked_types`、`non_stacked_types` 删除，因为 v1 已在协议层固定
- `default_behavior` 不再单独保留，需要时写入 `notes`

### 7.10 Display（条件必填）

Display 描述**配置级**显示差异，而不是协议外观本身。

**保留字段**：

- `network_marker`：网络段的固定显示内容，建议使用“专属 emoji + 短名”，如 `📊 ETF`、`🧠 Risk`
  - 当 `scope` 为 `skill`、`module` 等具名主题配置时，视为必填
  - 只有 `workspace-default` 配置才允许省略；无 `network_marker` 的公共格式视为保留给默认 / 内置空间
- `fallback_context`：默认上下文文案
- `context_presets`：常见状态的上下文预设，建议使用状态 / 动作的 `key` 作为项名
- `notes`

**协议固定项**：

- 状态栏三行结构
- 头部四段式顺序：`网络段 | 状态段 | micro-stage | 上下文`
- 分隔线文本
- markdown 渲染安全策略
- `micro-stage` 的运行时生成方式（自由生成 `emoji + prompt`，但不替换 canonical 状态段）

**冻结结论**：

- `header_template`、`separator`、`markdown_safe_mode`、`micro_stage_template` 不再放入配置；这些都属于协议本身，而不是主题配置
- `network_marker` 不应再被视为普通装饰字段，而是主题配置声明边界的命名空间标识


### 7.11 Extensions（可选）

Extensions 保留暂未进入核心 schema 的专属语义。

原则：

- 协议允许存在 `extensions`
- v1 协议可以忽略不认识的扩展项
- 迁移时优先保证语义不丢；如果某类扩展被多个工作区反复使用，再考虑正式提升为核心字段

---

## 8. `etf-report` 的映射方式

当前 `etf-report` 已提供一份“技能级状态网络配置” `statusbar.config.md`，用于表达：

- 当前在讨论 `etf-report` 的开发 / 评审 / bug / 轻任务 / 执行
- 如何进入这些状态
- 这些状态之间如何切换
- 状态栏右侧如何展示需求号、bug 状态、讨论主题等上下文

首轮落地已完成的迁移动作包括：

- `PLAN.md` 中原有状态网络正文已迁出并瘦身为协议入口
- `.codebuddy/rules/statusbar-protocol.mdc` 已作为通用状态栏协议宿主落位，承接固定显示协议、渲染约束与配置发现 / 选中规则
- `.codebuddy/rules/etf-report.mdc` 已收窄为 `etf-report` 项目级需求看板守卫
- `statusbar.config.md` 已成为 `etf-report` 状态网络的单一事实源


这也意味着后续若继续调整 `etf-report` 的状态网络，应直接改配置或协议文档，而不是把旧说明文结构回填到 `PLAN.md`。


---

## 9. 迁移映射建议

为避免迁移时再次把“说明文目录”直接搬进新配置，建议先按**状态对象 / 动作对象 / 关系对象 / 扩展语义**四类重写，再落到配置结构中。

| `PLAN.md` 旧内容 | 新配置落点 | 迁移方式 |
|------|------|------|
| 分类体系 | `States` + `Actions` | 把“场景 / 操作 / 异常”拆成可引用的状态与动作对象 |
| 意图分类 | `Routing.rules` | 改写成按顺序匹配的路由规则 |
| 状态栈 | `Stacking.operations` + `States.nesting` + `States.transitions` | 只保留结构关系，不保留旧文的解释性铺陈 |
| 人格切换 | `Extensions.persona_handoff` | 作为扩展语义保留摘要交接与恢复点规则 |
| 审视的特殊处理 | `States.审视.notes` + `Extensions.review_mode` | 核心行为放状态说明，细化约束放扩展 |
| 流程雷达与监察 | `Extensions.process_radar` | 作为诊断与升级机制保留 |
| 监察子agent | `Extensions.process_radar.agent_policy` | 保留职责边界与未来工具接入点 |
| 流程监察胶囊 | `Extensions.diagnostic_capsule` | 保留诊断时应携带的最小上下文结构 |
| 落地原则 | `Extensions.persistence_policy` | 保留什么时候要写回 `REQ` / `Board` / 规则锚点 |
| 状态栏附加信息 | `Display.context_presets` | 重写为面向状态 / 动作 `key` 的上下文模板 |

迁移原则：

- **不要照搬段落标题**：先改写成结构化对象，再落到配置字段
- **核心优先最小化**：能进入 `States` / `Actions` / `Routing` / `Display` 的先进入核心
- **复杂语义先进 `Extensions`**：先保证语义不丢，再观察是否值得升格为通用字段
- **迁移完成后单源化**：一旦正式切换，以配置文件为唯一状态网络事实源

---

## 10. 配置模板骨架（示意）

完整的通用模板请见 `docs/STATUSBAR_CONFIG_TEMPLATE.md`。

下面保留一个面向人类维护的 markdown 配置骨架示意：

```markdown
---
config_type: statusbar
name: etf-report-dev
protocol: statusbar/v1
scope: skill
priority: 90
summary: etf-report 开发状态网络
---

## Activation
- **keywords**: `etf-report`, `etf 报告`, `投资报告`, `etf 技能`
- **paths**: `.codebuddy/skills/etf-report/`
- **topics**: 讨论 etf-report 的开发、优化、需求、bug、发布相关工作
- **notes**: 命中 etf-report 相关语境时优先激活

## States

### 讨论
- **key**: `discussion`
- **emoji**: `💬`
- **summary**: 意图尚未收敛时的缓冲状态
- **enter_when**: 用户主题模糊，但已明确在聊 etf-report
- **context_format**: 讨论主题
- **nesting**: false
- **transitions**: `review`, `requirement`, `bug`

### 需求
- **key**: `requirement`
- **emoji**: `📌`
- **summary**: 讨论或推进某个需求
- **enter_when**: 提到具体 REQ 或新需求
- **context_format**: `REQ-XXX | 标题/阶段`
- **nesting**: true
- **transitions**: `review`, `discussion`, `bug`

## Actions

### 执行
- **key**: `execute`
- **emoji**: `🔄`
- **summary**: 运行脚本、发布、执行操作
- **trigger_when**: 用户要求更新报告、跑脚本、发布
- **context_format**: 在做什么
- **interrupts_state**: false

## Routing
- **rules**:
  - **match**: `发布|更新ETF报告`
    - **target_type**: `action`
    - **target**: `execute`
    - **reason**: 命中执行意图
  - **match**: `REQ-\d+|新需求`
    - **target_type**: `state`
    - **target**: `requirement`
    - **reason**: 命中需求语义
  - **match**: `.*`
    - **target_type**: `state`
    - **target**: `discussion`
    - **reason**: 默认兜底

## Stacking
- **operations**:
  - `push`: 新状态压栈
  - `replace`: 替换栈顶
  - `clear`: 清空状态栈
  - `resume`: 回到上一层状态
- **notes**: 协议默认 `states` 入栈、`actions` 不入栈

## Display
- **network_marker**: `📊 ETF`
- **fallback_context**: `进行中`
- **context_presets**:
  - `requirement`: `REQ-XXX | 标题/阶段`
  - `discussion`: `讨论主题`
  - `execute`: `在做什么`
- **notes**: `context_presets` 建议使用状态 / 动作的 `key` 作为项名；若同工作区存在多套状态网络，建议稳定填写 `network_marker`


## Extensions
### persona_handoff
- 这里保留当前还未进入核心 schema 的专属语义
```

---

## 11. 下一阶段建议

在首轮落地已经完成的前提下，后续第二阶段可继续推进：

1. 把 `STATUSBAR_PROTOCOL_DRAFT.md` 从草案收敛为正式协议文档
2. 基于 `statusbar.config.md` 继续打磨 `etf-report` 的正式状态网络配置细节
3. 在其他工作区验证“仅迁移宿主规则 + 新增配置文件”是否足以跑通
4. 明确运行时如何发现、缓存、重判活动配置，并补充验证用例
5. 保留工作区默认配置 / 协议内置配置作为兜底与模板



