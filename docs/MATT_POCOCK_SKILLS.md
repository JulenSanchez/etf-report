# Matt Pocock Skills 调研 — 从 grill-with-docs 到 etf-report 落地

> 调研来源：[mattpocock/skills](https://github.com/mattpocock/skills)（117k+ stars, MIT）
> 落地日期：2026-06-04

---

## 1. 背景

Matt Pocock（TypeScript 教育者，Total TypeScript 作者）公开了他的 `.claude/skills/` 目录。仓库围绕 AI 辅助开发的**四个失败模式**组织：

| 失败模式 | 根本原因 | 对应技能 |
|---------|---------|---------|
| Agent 构建了错误的东西 | 需求未对齐 | `/grill-me`, `/grill-with-docs` |
| Agent 啰嗦且术语混乱 | 无共享词汇表 | `CONTEXT.md`（来自 `/grill-with-docs`） |
| 代码不工作 | 反馈循环太长 | `/tdd`, `/diagnose` |
| 代码腐化 | 架构关怀不足 | `/improve-codebase-architecture`, `/zoom-out` |

Pocock 刻意将这套体系与 GSD/BMAD/Spec-Kit 等重型框架区别开来——强调"小、易适配、可组合"。

---

## 2. 两个核心技能

### `/grill-me`

非代码场景的"审讯"会话。每个问题附带推荐答案，逐层走完决策树。

**适用场景**：动手前的需求对齐——"是什么、为什么、边界在哪"。

### `/grill-with-docs`

`grill-me` 的代码级升级版。额外做三件事：

1. **维护 `CONTEXT.md` 术语表**：只做术语定义，不含实现细节。术语随对话实时捕获，不批量补充。
2. **写入 ADR**：仅当同时满足三条——难以逆转、缺上下文会困惑、存在真实取舍。
3. **探查代码库**：能通过读代码回答的问题，不反问用户。

Pocock 称之为"整个仓库最酷的一个技巧"。

---

## 3. 三个核心模式

### 模式一：术语锁定（`_Avoid_`）

解决 AI 跨对话命名漂移。每个术语条目末尾列禁用同义词，下一个 AI 实例读到后无需重新校准语境。

### 模式二：ADR 三条件门控

不满足全部三条不写 ADR，避免信噪比下降。只满足 1-2 条时，原因记一句 changelog 即可。

### 模式三：延迟审讯

信息不足时不猜测，标记占位符 `⏳` 后暂停。防止未验证的猜测内容污染文档，被后续 AI 当作事实继续推导。

---

## 4. 在 etf-report 的落地

| 模式 | 落地位置 | 效果 |
|------|---------|------|
| 术语锁定 | `SKILL.md` 术语表（6 类 30+ 术语，含 `_Avoid_` 禁用词） | AI 跨对话不再产生命名漂移 |
| ADR 门控 | `DESIGN.md` ADR 节首（三条前置条件） | 只有真正需要记录的决策才会进 ADR 表 |
| 延迟审讯 | `SKILL.md` 数据抓取失败处置表 | 未知异常不猜测根因，按已知路径分类处理 |

### 4.1 术语表的扩展

原始 `CONTEXT.md` 只做项目特有的领域术语。etf-report 将这个概念扩展到四层：

- **系统架构层**：技能/Tuner/正式页/payload/人设
- **数据管线层**：intraday/daily/patch fetch/refresh/Sina API/Tencent API
- **量化引擎层**：因子原始值 vs 映射分、F7 PULL-IN vs PUSH-OUT、黑洞螺旋
- **研究运维层**：head-to-head、excess return、Promotion、发布

### 4.2 为什么没有用原始 `CONTEXT.md` 格式

Pocock 的 `CONTEXT.md` 是为**单项目代码库**设计的——术语就是代码里的类名/模块名。etf-report 是一个 AI 技能——它的"领域"同时包含金融概念（f7_raw/超跌/均值回归）、工程概念（Tuner/payload/intraday cache）和研究方法论（head-to-head/黑洞螺旋）。单一的术语表格式需要适配这种多域特征。

---

## 5. 对技能设计的启示

Pocock 技能体系的核心原则与 etf-report 的演进方向一致：

- **约定写进文件，不靠 AI 记忆**：术语表、ADR 门控、研究规则都是这一原则的体现
- **技能自包含**：所有引用在技能目录内闭环，外部依赖只走 `requirements.txt` 或调研文档
- **小、可组合**：不做框架级接管，每个约定是一段 Markdown，可以被任何 AI 实例读取
