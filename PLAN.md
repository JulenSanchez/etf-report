# ETF Report — 需求管理

## 看板文件

| 文件 | 职责 |
|------|------|
| `plans/Board.md` | 当前状态快照（in_progress / done / backlog / wishlist / bugs） |
| `plans/Backlog.md` | 待开发需求详情 |
| `plans/Archive.md` | 版本发布记录 + 已废弃需求墓碑 |
| `plans/REQ-XXX.md` | 复杂需求的独立文档（按需创建） |

版本信息和 ID 计数器统一维护在 `plans/Board.md`。

## 需求状态流转

```
Backlog.md → Board.md (in_progress) → Board.md (done) → Archive.md (released)
                                                    ↘ Board.md (abandoned)
```

## Bug 状态流转

```
open → fixing → fixed → closed
  ↓        ↓        ↑
  └→ wontfix   验证不通过回到 open
```

## 操作指引

| 操作 | 做法 |
|------|------|
| 新建需求 | Backlog.md 新增 + 更新 Board.md ID 计数器 |
| 拉取开发 | Backlog.md 删除 → Board.md in_progress 新增 |
| 标记完成 | Board.md in_progress → done |
| 废弃需求 | Board.md abandoned 区，注明原因和日期 |
| 新建 Bug | Board.md bugs 区新增 + 更新 ID 计数器 |
| 发布版本 | 见「版本发布」节 |

### 编号前置守卫

**原则**：只要某个事项已经不再是纯讨论，而是会进入**持续跟踪、改文件、排查修复、状态流转、归档复盘**中的任一项，就要**先申请编号，再继续做事**。

**适用范围**：
- **新需求**：需要持续推进的新功能、改造项、流程项
- **新 Bug**：需要排查、修复、验证、归档的异常

**标准动作**：
1. 先读取 `Board.md` 的 **下一个需求 ID / 下一个 Bug ID**
2. 立即在对应锚点登记（需求至少进 `Backlog.md` / `Board.md`；Bug 至少进 `Board.md bugs`）
3. 同步递增 `Board.md` 里的 ID 计数器
4. 后续实现、测试、状态流转、归档都复用这个编号

**允许暂不编号的情况**：
- 纯讨论、纯审视、纯问答
- 尚未确定是否值得跟踪的短暂现象确认
- 一次性轻任务，且明确不会进入需求 / Bug 看板

**补救规则**：
- 如果执行中途才发现它其实已经构成需求或 Bug，应该**立刻补号并登记后再继续**，不要等做到完成 / 归档时才补
- 状态栏里可以临时用主题名或现象摘要占位，但一旦进入持续推进，必须尽快切到 `REQ-XXX` / `BUG-XXX`

**轻任务 vs 必须编号（简版）**：

| 情况 | 怎么做 |
|------|--------|
| 一次性小改，做完就结束，不需要后续跟踪 | 作为轻任务处理，可不编号 |
| 会继续推进、排查修复、改多个文件、做回归验证、需要归档复盘 | 先申请 `REQ` / `BUG` 编号，再继续 |
| 当前还不确定 | 先按轻任务观察；一旦进入持续推进，立刻补号 |

### 状态栏协议入口

`PLAN.md` 不再作为状态网络正文的维护位置；从本轮开始，`etf-report` 的状态栏能力按“**协议宿主 + 配置 + 项目守卫**”拆分维护：

| 事实源 | 文件 | 职责 |
|------|------|------|
| 通用状态栏协议宿主 | `.codebuddy/rules/statusbar-protocol.mdc` | 定义状态抬头三行结构、渲染安全写法、配置发现 / 选中与通用降级行为 |
| 技能级状态网络配置 | `statusbar.config.md` | 定义 `States` / `Actions` / `Routing` / `Stacking` / `Display` / `Extensions` |
| 项目级需求看板守卫 | `.codebuddy/rules/etf-report.mdc` | 负责 `etf-report` 自己的入口 / 出口守卫、需求看板、版本信息与 Bug 治理 |
| 协议草案与字段冻结说明 | `docs/STATUSBAR_PROTOCOL_DRAFT.md` | 说明协议职责、配置发现 / 选中流程、v1 schema、迁移映射 |
| 通用填写模板 | `docs/STATUSBAR_CONFIG_TEMPLATE.md` | 提供给其他工作区 / 技能复用的最小模板 |


当前 `etf-report` 的旧状态网络内容已迁移为：

- `分类体系` → `statusbar.config.md` 中的 `States` / `Actions`
- `意图分类` → `statusbar.config.md` 中的 `Routing`
- `状态栈` → `statusbar.config.md` 中的 `Stacking`
- `人格切换`、`流程雷达`、`监察胶囊`、`落地原则` → `statusbar.config.md` 中的 `Extensions`
- 状态栏右侧附加信息 → `statusbar.config.md` 中的 `Display.context_presets`

维护原则：

- **不要**再把状态网络正文回写到 `PLAN.md`
- 调整状态 / 动作 / 路由时，直接改 `statusbar.config.md`
- 调整状态抬头固定三行格式、渲染约束、配置发现 / 选中规则时，改 `.codebuddy/rules/statusbar-protocol.mdc`
- 调整 `etf-report` 自己的需求看板守卫、版本治理、出口检查时，改 `.codebuddy/rules/etf-report.mdc`
- 调整协议字段定义、冻结口径、迁移方法时，改 `docs/STATUSBAR_PROTOCOL_DRAFT.md`


### 版本发布

用户说"发布"，AI 一条龙执行以下流程。整个发布是**一个操作**（🔄 执行），遇障即停，不改任何文件。

**Step 1: 发布前检查**
- Board.md in_progress 区为空
- Board.md bugs 区没有 open/fixing 状态的 critical/major Bug
- Board.md done 区有内容
- 检查不通过 → 告知阻塞原因 → 结束

**Step 2: 版本号递增**
- done 区有 High 优先级需求 → minor 递增（v2.2.0 → v2.3.0）
- 否则 → patch 递增（v2.2.0 → v2.2.1）
- 用户可提前指定版本号覆盖默认行为

**Step 3: 归档**
- 收集 done 区所有 REQ 的 ID 和标题
- Archive.md「版本发布记录」新增一行：`| {版本} | {今天} | {REQ列表} | {标题拼成的备注} |`
- 清空 Board.md done 区

**Step 4: 更新版本号**
- Board.md「当前版本」「发布日期」「开发中需求」更新

**Step 5: Git 推送**
- git add + commit（"release {版本}: {REQ列表}"）+ push

**结果**：
- 成功 → "vX.Y.Z 发布完成"
- 失败 → 告知哪一步卡了，用户自行处理（轻任务/Bug/需求）

对话结束前批量更新文件，不在中间频繁写文件。

## 需求文档规范

### 两层结构

| 层级 | 载体 | 何时用 |
|------|------|--------|
| **总览条目** | Backlog.md 内联 | 所有需求，一眼扫完 |
| **完整需求单** | plans/REQ-XXX.md | 拉取开发时自动创建，或需求复杂度需要 |

Backlog.md 只放一句话摘要 + 元数据。完整拆解放到独立 REQ-XXX.md。

### 总览条目格式（Backlog.md）

```markdown
| REQ-XXX | 标题 | 优先级 | 估时 | 目标版本 | 状态 |
```

### 完整需求单格式（REQ-XXX.md）

以下是标准模板。**字段可按需增减** — 简单需求只填核心字段，复杂需求全部填满。没有硬性要求。

```markdown
# REQ-XXX: 标题

**优先级**: 🟠/🟡/🟢
**估时**: Xh
**状态**: backlog / in_progress / done / abandoned
**目标版本**: vX.Y.Z（或 -）
**依赖**: REQ-XXX（或 无）
**创建日期**: YYYY-MM-DD
**最后活动**: YYYY-MM-DD

---

## 动机

> 一两句话说明为什么要做这件事。解决什么痛点。

**现状问题**（可选）：
- 具体描述当前系统在这方面的不足

**不做会怎样**（可选）：
- 描述不做的后果，帮助判断优先级

## 实施步骤

### Step 1: 步骤标题
- 具体做什么
- 涉及文件：`path/to/file.py`（改什么）
- 预期产出：...

### Step 2: ...

> 步骤粒度：每个 step 应该是一个可独立验证的原子操作。
> 如果某步超过 2h，考虑进一步拆分。

## 文件影响分析

| 文件 | 改动类型 | 改动说明 |
|------|---------|---------|
| `scripts/xxx.py` | 新增/修改/重构 | 具体改什么函数/类 |
| `config/config.yaml` | 修改 | 新增/修改什么配置节 |

## 验证方式

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| 核心功能 | 命令/测试 | 具体预期结果 |
| 边界情况 | 手动测试 | ... |
| 回归验证 | 跑一次完整报告 | 报告正常生成 |

## 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| ... | 高/中/低 | ... | ... |

## 评审记录

- YYYY-MM-DD: 评审结论/调整
```

### 灵活使用原则

1. **简单需求**（估时 < 3h）— 只在 Backlog.md 保留条目，不创建 REQ-XXX.md
2. **中等需求**（3-6h）— 拉取开发时创建 REQ-XXX.md，填写核心字段即可
3. **复杂需求**（> 6h 或涉及架构变化）— 创建时全部填满
4. **字段可省略** — 如果某个 section 没有内容，直接不写。不要为了填模板而注水
5. **格式可调整** — 需求特殊时可以加自定义 section（如 REQ-112 的"为什么降级"）

### 用户覆盖 AI 建议记录

当用户主动推翻 AI 的优先级、方案、分类、边界判断时，AI 必须把这次覆盖记录到**最近的锚点**里，避免下个对话只看到结果、看不到原因。

**记录优先级**：
1. **首选**：相关 `REQ-XXX.md` 的「评审记录」
2. **次选**：`Board.md` / `Backlog.md` 的备注或摘要
3. **补充**：如果这体现稳定偏好，再沉淀为长期记忆

**推荐记录格式**：
- `[用户覆盖] AI 原建议：...`
- `用户决定：...`
- `理由摘要：尽量保留用户原话味道`
- `影响：是否改变后续评审标准 / 是否仅本次特例`

**例子**：
- `2026-04-11: [用户覆盖] AI 原建议：REQ-108 保持 High；用户决定：降为 Low；理由："挂了再说"；影响：当前阶段不为单点风险提前投入。`

> 这条记录的目标不是争论对错，而是给未来的 AI 一个“为什么会这样”的上下文锚点。
