# AGENTS.md — etf-report 冷启动入口

本仓库是普通项目 repo，不再按 Claude / CodeBuddy Skill 理解。默认以当前工作目录作为项目根目录。

## 用户首轮输入 1：开放式冷启动

当用户说：

```text
按 AGENTS.md 开始，输出版本摘要和 Top3 推进建议
```

执行：

1. 读取 `README.md`。
2. 读取 `plans/Board.md`。
3. 评估当前版本进度：
   - 当前版本与目标版本
   - `in_progress`
   - `done` 但未发布事项
   - `backlog` 优先级
   - 活跃 bugs
   - 下一个需求 ID
4. 只在必要时读取候选需求文档：最多读取 3-5 个最相关的 `plans/REQ-*.md`。
5. 不要全仓扫描；不要读取 `logs/`、`data/`、`outputs/`、`_working/`，除非用户明确要求。

输出：

- 当前版本摘要
- 版本推进状态和风险判断
- 下一步 Top3 推进建议
- 每个建议包含：
  - REQ ID 和标题
  - 为什么现在做
  - 需要先读哪些文件
  - 预计改动区域
  - 最小验证命令

只输出建议，不要开始实现。等待用户选择方向。

## 用户首轮输入 2：指定/关键词需求冷启动

当用户说：

```text
按 AGENTS.md 开始，开始 xxx需求
按 AGENTS.md 开始，继续 xxx需求
```

其中 `xxx` 可能是 REQ 编号，也可能只是关键词。

执行：

1. 读取 `README.md`。
2. 读取 `plans/Board.md`。
3. 如果用户给出 REQ 编号：
   - 读取对应 `plans/REQ-XXX.md`。
   - 再读取该需求直接指向的代码/文档。
4. 如果用户只给关键词：
   - 先在 `plans/Board.md` 中定位候选需求。
   - 若无法唯一定位，再搜索 `plans/REQ-*.md`，最多读取 3-5 个最相关候选。
   - 不要读取所有 REQ。
5. 根据领域选择最小阅读范围：
   - 量化 / Tuner / 回测：`docs/runbook/v2-quant/overview.md`、`config/quant_universe.yaml`、`scripts/quant_*.py`
   - 正式页 / 报告 / 发布：`docs/runbook/v1-report.md`、`docs/runbook/release.md`、`scripts/update_report.py`、`scripts/deployer.py`、`assets/js/`
   - stable / 计划任务：`batchfiles/`、`docs/runbook/stable.md`
   - 架构 / 包化：`docs/design/overview.md`、`src/`、`scripts/`

输出：

- 命中的候选需求排序
- 推荐主需求
- 判断：继续开发 / 新开需求 / 先处理依赖 / 暂缓 / 可关闭
- 需要先读的文件
- 预计改动区域
- 最小验证命令
- 简短实施计划

不要直接编辑。等待用户确认后再实现。

## 当前事实源优先级

1. `plans/Board.md`：当前状态事实源。
2. 对应 `plans/REQ-XXX.md`：需求详情事实源。
3. 运行代码与配置：最终实现事实源。
4. `docs/`：架构与运维说明。
5. `plans/Archive.md`、历史 REQ、research：历史上下文，不作为当前状态事实源。

## 开放式讨论 / 问题探索协议

当用户发起**非指令性**讨论时——描述问题、痛点、疑虑、"能不能优化"、"这个设计对吗"——
AI 必须识别为"开放式讨论"，**禁止直接修改代码**。

### 触发信号

**语言信号**（匹配任一即进入讨论模式）：

- "我在想…"、"有个痛点…"、"总觉得…"、"这里是不是有问题…"
- "能不能优化…"、"这个设计合理吗…"、"长期来看…"、"架构层面…"、"整体上…"
- "烦"、"老是"、"又坏了"、"受不了"、"每次都" — 负面情绪信号，通常意味根因未挖到
- 任何没有明确"做什么、改哪里"的**描述性/评价性输入**

**与执行模式的边界**：用户说"改 X"、"修 Y"、"跑 Z"、"处理 REQ-NNN" → 执行模式。其余默认倾向讨论模式。

### 讨论模式行为约束

1. **禁止直接改代码** — 不编辑、不写脚本、不跑命令（只读检索除外）
2. **先问边界问题** — 确认范围、严重程度、影响面、优先级
3. **系统化分析**：
   - 问题属于哪个子系统？（量化/报告/管线/架构/前端）
   - 涉及哪些模块和文件？（只列不改）
   - 是全链路问题还是局部问题？（参照"策略变更全链路审计"表判断影响面）
   - 有哪些边界条件和关联影响？
   - 这个问题之前是否出现过？（查 Archive.md、历史 REQ、Board.md bugs）
4. **产出结构化讨论结论**：
   - 问题定义（一句话）
   - 影响范围
   - 解决方向（至少 A/B 两个选项，不能只有一个）
   - 建议拆分为几个 REQ
   - 优先级建议
   - 验证方式
5. **等待用户选择方向后，再进入下一阶段**

### 讨论结论 → 路由

- 用户说"建 REQ" → 用 `req-generator` 生成需求单 → 记录到 Board.md → 进入 Plan Mode
- 用户说"展开这个方向" → EnterPlanMode → 调研 → 写 plan → 审批 → 执行
- 用户说"先记下来" → 新增条目到 Board.md `discussing` 列，标记优先级
- 用户说"只是聊聊，不改" → 不做任何工程变更，不做任何记录

### Board.md `discussing` 列

`plans/Board.md` 中的 `discussing` 列用于跟踪正在讨论但尚未形成 REQ 的话题。
AI 在冷启动时应读取该列，识别哪些话题处于探索阶段、不应直接执行。

条目格式：

```markdown
| 日期 | 话题 | 状态 | 备注 |
|------|------|------|------|
| 2026-07-01 | 示例：AI 讨论→执行跳步问题 | 探索中 | 待产出 REQ |
```

状态可选：`探索中` / `已产出 REQ` / `搁置` / `已关闭`

## 工作流路由

触发词 → owner 文档映射见 `docs/runbook/workflows.md`。AI 匹配触发词后读取对应 owner 文档执行，不在此处复制步骤。

### 需求开发（REQ）

```
用户说"处理 REQ-XXX" → EnterPlanMode → 调研 → 写 plan → 用户审批 → 执行 → 验证
```
- 简单操作除外：单行修/config 改/文档更新/数据拉取/查进度
- Plan 文件落在 `~/.claude/plans/`

### 策略变更 — 全链路审计

以下审计链是 AGENTS 专属（不在 runbook 中），改策略时必须逐层检查：

| 类型 | 触发词 | 全链路审计 |
|------|--------|--------------------------|
| 改参数 | "删参数 X"/"加参数 Y"/"改参数 Z" | `PARAM_SCHEMA` → `PARAM_BOUNDS` → `defaults.yaml` → `preset_to_tuner_params` → `tuner_params_to_config_override` → `tuner.html` 控件 → `quant_tuner.py` getParams/setParams → `quant_backtest.py` 消费 → tests |
| 改默认值 | "改某参数的默认值" | `defaults.yaml` → `preset_to_tuner_params` → `tuner_params_to_config_override` → `quant_backtest.py` load_config → CLI 验证 → 更新 `research/params/baseline.yaml` |
| 改因子 | "改 F1/F3/F7" | `quant_factors.py` → `quant_backtest.py` compute/sensitivity → `quant_contract.py` 映射 → `tuner.html` 控件 → `config/quant_universe.yaml` preset → `docs/design/factors.md` |
| 改引擎 | "改回测逻辑"/"改仓位分配" | `quant_backtest.py` → `quant_contract.py` config_override → `docs/design/backtest-engine.md` → tests |

核心原则：**不改孤岛，必审全链**。看不懂 `engine_path` 就查 `PARAM_SCHEMA`，不知道哪些测试就查 `overview.md` 变更路由。

### Bug 排查

```
遭遇异常 → 自动查排障表 → 按症状定位 → 修复
```
- 量化/Tuner/回测 → `docs/runbook/v2-quant/overview.md` 故障排查索引
- 正式页/推送/数据管线 → `docs/runbook/v1-report.md` 常见问题
- 不要猜进程/网络/缓存

## 行为约束

- 不主动删除目录、修改 Windows 计划任务，除非用户明确要求
- 遇到 destructive / shared-state 操作先确认
- 不使用 `--force` / `--force-with-lease`，除非用户明确要求且说明原因
- 修改核心逻辑后跑相关最小验证
- **实施完成后输出变更摘要** — 每次代码改动完成后，必须输出：改了什么文件、每处改动的性质（新增/修改/删除/重构）、为什么改、如何验证。让用户不看 diff 也能判断影响面
- 不扫描或修改 `logs/`、`data/`、`outputs/`、`_working/`，除非任务明确需要
- **禁止主动询问是否提交** — 提交（git commit / git push）由用户主动发起，AI 不得建议、询问"要提交吗"、"要 push 吗"
- **用户输入不含明确执行指令时，默认进入讨论模式** — "改 X"、"修 Y"、"跑 Z"、"处理 REQ-NNN" 之外，先问边界再行动。禁止把问题描述当任务指令直接执行

## 术语

需要术语定义时：`docs/design/glossary.md`
