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
- **paths**: `.codebuddy/skills/etf-report/`, `plans/REQ-`, `plans/Board.md`
- **topics**: 讨论 `etf-report` 的开发、优化、需求、缺陷、发布、规则抽离与技能演进
- **examples**:
  - `看看 etf-report 当前进度`
  - `这个 etf 报告需求怎么做`
  - `发布 etf-report`
  - `审视一下 etf-report 的状态栏规则`
- **notes**: 技能级配置；只要对话主题显著命中 `etf-report`，即应选中本配置；若同时命中默认配置，则本配置优先

## States

### 讨论
- **key**: `讨论`
- **emoji**: `💬`
- **summary**: 意图尚未完全收敛，但已明确在聊 `etf-report`
- **enter_when**:
  - 用户提出泛化问题、方向问题或开放式讨论
  - 尚未明确落入需求 / 缺陷 / 审视
- **context_format**: 讨论主题
- **nesting**: false
- **transitions**: `审视`, `需求`, `缺陷`
- **notes**: 作为兜底状态使用，目标是帮助对话收敛到更明确的状态

### 需求
- **key**: `需求`
- **emoji**: `📌`
- **summary**: 讨论、拆解、评审或推进某个具体需求
- **enter_when**:
  - 提到具体 `REQ-XXX`
  - 明确说“当成新需求来做”
  - 提出一个需要持续推进的新功能或改造目标
- **context_format**: `REQ-XXX | 标题/阶段`
- **nesting**: true
- **transitions**: `审视`, `讨论`, `缺陷`
- **notes**: 如果需求尚未编号，右侧上下文可先用主题名占位；但一旦判断它会进入持续推进、改文件、状态流转或后续归档，就应先申请 `REQ` 编号并登记，再继续执行

### 缺陷
- **key**: `缺陷`
- **emoji**: `🐛`
- **summary**: 讨论、排查或验证某个缺陷
- **enter_when**:
  - 提到具体 `BUG-XXX`
  - 明确描述一个异常并要求排查
- **context_format**: `BUG-XXX | 状态 | 严重度`
- **nesting**: true
- **transitions**: `讨论`, `需求`, `审视`
- **notes**: 若尚未编号，可临时显示现象摘要；但一旦进入排查、修复、验证或准备归档，就应先申请 `BUG` 编号并登记，再切换为标准格式

### 审视
- **key**: `审视`
- **emoji**: `🔍`
- **summary**: 从方向、结构、边界或流程视角审查 `etf-report`
- **enter_when**:
  - 用户明确说“审视一下”
  - 用户对当前方案、协作方式或结构设计提出怀疑
- **context_format**: 审视范围
- **nesting**: true
- **transitions**: `需求`, `讨论`, `缺陷`
- **notes**: 审视优先处理“这样设计是否合理”，而非直接进入实现细节；需要时再下钻代码或运行细节

## Actions

### 执行
- **key**: `执行`
- **emoji**: `🔄`
- **summary**: 跑脚本、更新报告、发布、生成结果等瞬时操作
- **trigger_when**:
  - 用户说“更新ETF报告”
  - 用户说“跑一下”
  - 用户说“发布”
- **context_format**: 在做什么
- **interrupts_state**: false
- **notes**: 执行是操作，不进入状态栈；执行结束后返回原状态或空栈

### 轻任务
- **key**: `轻任务`
- **emoji**: `🔧`
- **summary**: 局部、小范围、无需升级为需求的修改或整理
- **trigger_when**:
  - 改文档、调表述、修小配置、清理小范围内容
- **context_format**: 在做什么
- **interrupts_state**: false
- **notes**: 如果轻任务反复返工或范围扩大，应升级到 `需求` 或 `审视`

### 查看看板
- **key**: `查看看板`
- **emoji**: `📖`
- **summary**: 只读查看看板、版本、需求状态或缺陷列表
- **trigger_when**:
  - 用户说“看看看板”
  - 用户问“当前进度”
  - 用户问“现在哪些需求在做”
- **context_format**: 看什么
- **interrupts_state**: false
- **notes**: 查看看板不修改文件，只做上下文同步

### 异常
- **key**: `异常`
- **emoji**: `⚠️`
- **summary**: 在任意状态或动作中发现可疑现象，需临时提升注意力
- **trigger_when**:
  - 用户指出“这不对”
  - 发现当前分类、状态栏行为或结果存在明显异常
- **context_format**: 现象简述
- **interrupts_state**: true
- **notes**: 异常是短暂覆盖层；确认性质后应回落到 `缺陷`、`审视` 或原状态

## Routing
- **rules**:
  - **match**: `更新ETF报告|跑一下|发布`
    - **target_type**: `action`
    - **target**: `执行`
    - **reason**: 用户显式要求执行操作
  - **match**: `看看看板|当前进度|开发中需求|活跃缺陷`
    - **target_type**: `action`
    - **target**: `查看看板`
    - **reason**: 用户意图是读取当前状态而非推进具体实现
  - **match**: `REQ-\d+|新需求|当成新需求来做`
    - **target_type**: `state`
    - **target**: `需求`
    - **reason**: 命中需求语义
  - **match**: `BUG-\d+|异常|报错|怎么回事`
    - **target_type**: `state`
    - **target**: `缺陷`
    - **reason**: 命中缺陷或问题排查语义
  - **match**: `审视一下|这个方向对不对|怎么这么绕|这个规则是否合理`
    - **target_type**: `state`
    - **target**: `审视`
    - **reason**: 命中结构和方向性审查
  - **match**: `.*`
    - **target_type**: `state`
    - **target**: `讨论`
    - **reason**: 默认兜底到讨论

## Stacking
- **operations**:
  - `push`: 新状态压栈，保留旧状态
  - `replace`: 用户显式要求切换主题时替换栈顶
  - `clear`: 用户说“从头来”或“换个方向”时清空状态栈
  - `resume`: 动作结束或异常关闭后回到上一层状态
- **notes**: 协议默认 `states` 入栈、`actions` 不入栈；空栈是合法状态；只有在需要显式表达持续上下文时才进入状态栈

## Display
- **network_marker**: `📊 ETF`
- **fallback_context**: `进行中`
- **context_presets**:
  - `需求`: `REQ-XXX | 标题/阶段`
  - `缺陷`: `BUG-XXX | 状态 | 严重度`
  - `审视`: `审视范围`
  - `讨论`: `讨论主题`
  - `执行`: `在做什么`
  - `轻任务`: `在做什么`
  - `查看看板`: `看什么`
  - `异常`: `现象简述`
- **notes**: 状态栏三行结构、分隔线与 markdown 安全写法属于协议固定能力，不在本配置中重复定义；若协议支持网络标记，则共享状态如 `讨论`、`审视` 也应以前置网络徽标形式稳定显示 `📊 ETF`；涉及状态 / 动作的机器引用统一使用 `key`



## Extensions
### review_mode
- `审视` 状态默认先看顶层规则与设计文档，再决定是否下钻实现细节
- 当问题本质是流程摩擦、边界混乱或协作失稳时，优先从 PM / 治理视角给建议
- 只有在需要举证实现缺陷或模式异常时，才回头抽样检查实现细节

### persona_handoff
- 状态切换时，旧状态只保留一句摘要给新状态
- 返回旧状态时，以该摘要作为恢复点，而不是继承全部细节
- 目标是让嵌套状态可恢复、上下文不过载

### process_radar
- **signals**:
  - 用户推翻 AI 建议
  - 流程摩擦：重复澄清、返工、场景抖动
  - 跨会话上下文可能丢失
  - 新需求 / 新 Bug 已实质推进但尚未编号
  - 状态栏、人格或行为与协议不一致
- **levels**:
  - `silent`: 仅记分，不打断当前任务
  - `acknowledge`: 一句话承认偏差并重述目标或重分类
  - `escalate`: 以 `异常` 覆盖层或 `审视` 状态介入
- **agent_policy**:
  - 如果未来工具层支持监察子 agent，则其职责只做诊断，不直接执行实现
  - 当前 v1 先保留策略接口，不要求协议内建 agent 行为

### diagnostic_capsule
- **current_state**: 当前状态或动作
- **current_goal**: 当前目标
- **latest_ai_judgment**: 最近一次 AI 判断
- **user_correction**: 用户纠偏或异常现象
- **repeated_count**: 已出现次数
- **anchors**: 相关锚点（REQ / Board / 规则 / 用户关键原话）
- **risk_type**: 目标偏移 / 流程摩擦 / 上下文丢失 / 模式异常
- **resume_point**: 分析结束后原状态应从哪句恢复

### persistence_policy
- 流程信号默认不持久化，避免引入第二套文档系统
- 只有当问题已影响需求、缺陷、规则或跨会话判断时，才写回 `REQ-XXX.md`、`Board.md`、`Backlog.md` 等锚点
- 用户覆盖 AI 建议时，优先记录到最近锚点，而不是散落到新文档

### legacy_section_mapping
- `分类体系` → `States` / `Actions`
- `意图分类` → `Routing.rules`
- `状态栈` → `Stacking.operations` + `States.nesting` + `States.transitions`
- `人格切换` → `persona_handoff`
- `审视的特殊处理` → `review_mode`
- `流程雷达与监察` → `process_radar`
- `监察子agent` / `流程监察胶囊` → `process_radar.agent_policy` + `diagnostic_capsule`
- `落地原则` → `persistence_policy`
- `状态栏附加信息` → `Display.context_presets`
