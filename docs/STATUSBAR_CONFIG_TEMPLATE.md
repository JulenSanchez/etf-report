# 状态栏配置模板（v1 通用模板）

> 用途：给任何工作区 / 技能 / 模块提供一份“拿来就能填”的状态栏配置模板。
> 约定：本模板服务于 `statusbar/v1`，字段说明以 `STATUSBAR_PROTOCOL_DRAFT.md` 为准。

---

## 1. 使用说明

### 1.1 你至少需要填什么

一份最小可用配置至少要有：

- frontmatter：`config_type`、`name`、`protocol`、`scope`、`summary`
- `Activation`：至少填写 `keywords` / `paths` / `topics` 之一
- `States`：至少定义 1 个状态
- `Routing`：如果你定义了多个状态/动作，就应该填写
- `Display.network_marker`：若 `scope` 不是 `workspace-default`，则必须填写


### 1.2 哪些现在不该再填

v1 冻结后，以下内容**不再建议写进配置**：

- 单独的 `Meta` 区块
- `label` 字段
- `Routing.order`
- `Stacking.stacked_types`
- `Stacking.non_stacked_types`
- `Stacking.default_behavior`
- `Display.header_template`
- `Display.separator`
- `Display.markdown_safe_mode`

这些要么已经由协议固定，要么已经被更简单的表达方式取代。

### 1.3 什么时候该用 `Extensions`

当你有一些**当前模板装不下、但又不想丢**的专属语义时，把它放到 `Extensions`。

例如：

- 某个项目自己的特殊协作约定
- 某个状态的额外解释
- 暂时还不确定是否值得升级成通用字段的内容

---

## 2. 空白模板

```markdown
---
config_type: statusbar
name: your-config-name
protocol: statusbar/v1
scope: skill
priority: 50
summary: 用一句话说明这份配置服务于什么主题
---

## Activation
- **keywords**: `至少填一类命中线索`
- **paths**: `可选，路径线索`
- **topics**: 可选，主题说明
- **examples**:
  - `示例触发语句 1`
  - `示例触发语句 2`
- **notes**: 可选

## States

### 讨论
- **key**: `discussion`
- **emoji**: `💬`
- **summary**: 描述这个状态是什么意思
- **enter_when**: 什么时候进入这个状态
- **context_format**: 右侧上下文怎么写
- **nesting**: false
- **transitions**: `review`, `bug`
- **notes**: 可选

## Actions

### 执行
- **key**: `execute`
- **emoji**: `🔄`
- **summary**: 描述这个动作做什么
- **trigger_when**: 什么时候触发
- **context_format**: 在做什么
- **interrupts_state**: false
- **notes**: 可选

## Routing
- **rules**:
  - **match**: `关键词或正则`
    - **target_type**: `state`
    - **target**: `discussion`
    - **reason**: 为什么命中这里

## Stacking
- **operations**:
  - `push`: 新状态压栈
  - `replace`: 替换栈顶
  - `clear`: 清空状态栈
  - `resume`: 回到上一层状态
- **notes**: 可选

## Display
- **network_marker**: `除 workspace-default 外必填，建议使用固定 emoji + 短标记，如 📊 ETF`
- **fallback_context**: `进行中`
- **context_presets**:
  - `discussion`: `讨论主题`
  - `execute`: `在做什么`
- **notes**: 可选



## Extensions
### custom_notes
- 这里放当前 schema 不好表达、但你又想保留的项目专属内容
```

---

## 3. 填写建议

### 3.1 `scope` 怎么选

- **`skill`**：适合某个技能、子系统、子项目
- **`module`**：适合更小的模块级作用域
- **`workspace-default`**：适合作为工作区的默认兜底配置

### 3.2 `keywords`、`paths`、`topics` 怎么分工

- **`keywords`**：用户最可能直接说出的词
- **`paths`**：与该配置强关联的文件 / 目录线索
- **`topics`**：给维护者看的主题解释

### 3.3 `States` 和 `Actions` 怎么区分

- **State**：有持续时间，会形成“当前在做什么”的上下文
- **Action**：瞬时操作，本身不一定持续存在
- **`key`**：给协议引用的内部标识，应保持稳定
- **小节标题**：给人看的名字，可以更偏业务语义

### 3.4 什么时候需要 `Routing`

如果只有一个兜底状态，可以暂时不写复杂路由。  
只要你有多个状态 / 动作需要区分，就应显式写出 `Routing.rules`，并**按书写顺序表达优先级**。

补充约定：

- `Routing.rules[*].target` 应填写对应状态 / 动作的 `key`
- `Display.context_presets` 也建议使用状态 / 动作的 `key` 作为项名

### 3.5 `network_marker` 怎么选

- 当 `scope` 是 `skill`、`module` 等具名主题配置时，应该填写，而不是可选装饰
- 只有 `workspace-default` 才允许留空；留空代表你在占用无命名空间的公共格式
- 推荐格式：`专属 emoji + 短名`，例如 `📊 ETF`、`🧠 Risk`
- 在状态头里，它会直接作为最前面的 `网络段` 出现，例如 `🧠 Risk | 🔍 审视 | ✅ 校验 | 时间状态机`
- 一旦选定，尽量长期保持稳定，避免用户重新学习视觉映射

### 3.6 `micro-stage` 怎么理解

- `micro-stage` 不是配置字段，而是**协议运行时生成的片段级提示**
- 推荐理解为：`自由 emoji + 短 prompt`
- 它的职责是补充“我们此刻在这段回复里具体在做什么”，例如 `✅ 校验`、`🧩 收口`、`🔄 回读`
- `micro-stage` 可以灵活，但 `状态段` 不可以随之漂移；状态段仍必须引用配置中定义的 canonical state/action
- 如果一句 micro-stage 太长、太花或形成第二套状态词表，就说明它已经越界



### 3.6 什么时候该先放 `Extensions`


如果你在填模板时出现这类感觉：

- “这个内容很重要，但又不像通用字段”
- “我现在能写下来，但还不确定以后是不是所有人都需要”

那就先放进 `Extensions`，不要急着扩张核心 schema。

---

## 4. 最小示例

```markdown
---
config_type: statusbar
name: my-feature-dev
protocol: statusbar/v1
scope: skill
summary: 某个功能的开发状态网络
---

## Activation
- **keywords**: `my-feature`

## States
### 讨论
- **key**: `discussion`
- **emoji**: `💬`
- **summary**: 默认讨论状态
- **context_format**: 讨论主题

## Display
- **network_marker**: `🧩 MyFeature`
```

这已经是一份**最小可识别的具名主题配置**。后续再逐步补充 `Routing`、`Actions`、`Stacking` 和其余 `Display` 字段即可；只有 `workspace-default` 才可以不填 `network_marker`。


