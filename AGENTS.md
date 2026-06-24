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

## 工作流

每个操作都有对应的流水线。AI 按触发词自动进入对应流程。

### 需求开发（REQ）

```
用户说"处理 REQ-XXX" → EnterPlanMode → 调研 → 写 plan → 用户审批 → 执行 → 验证
```
- 简单操作除外：单行修/config 改/文档更新/数据拉取/查进度
- Plan 文件落在 `~/.claude/plans/`

### ETF 筛选

```
用户说"筛选 ETF" → 读 `docs/runbook/v2-quant/screening.md` → scan_etf_universe.py --debug → 出候选 → 审阅 → 决定是否进入换池
```

### 换池

```
用户说"换池" → 读 SOP → 逐支执行 → 基线对比 → 更新追踪文档
```
详见 `docs/runbook/v2-quant/pool-change.md`

### 参数优化

```
用户说"优化 <preset>" → 自检数据 → 推导空间 → TPE 搜索 → auto-analyze → 写报告
```
详见 `docs/runbook/v2-quant/optimization.md`

### 策略变更

| 类型 | 触发词 | 全链路审计（必须逐层检查） |
|------|--------|--------------------------|
| 改参数 | "删参数 X"/"加参数 Y"/"改参数 Z" | `PARAM_SCHEMA` → `PARAM_BOUNDS` → `preset_to_tuner_params` → `tuner_params_to_config_override` → `tuner.html` 控件 → `quant_tuner.py` getParams/setParams → `quant_backtest.py` 消费 → tests |
| 改因子 | "改 F1/F3/F7" | `quant_factors.py` → `quant_backtest.py` compute/sensitivity → `quant_contract.py` 映射 → `tuner.html` 控件 → `config/quant_universe.yaml` preset → `docs/design/factors.md` |
| 改引擎 | "改回测逻辑"/"改仓位分配" | `quant_backtest.py` → `quant_contract.py` config_override → `docs/design/backtest-engine.md` → tests |

核心原则：**不改孤岛，必审全链**。看不懂 `engine_path` 就查 `PARAM_SCHEMA`，不知道哪些测试就查 `overview.md` 变更路由。

### 发布

```
用户说"发布" → Phase 0-8 全流程
用户说"提交" → 快速路径（跳过版本治理）
```
详见 `docs/runbook/release.md`

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
- 不扫描或修改 `logs/`、`data/`、`outputs/`、`_working/`，除非任务明确需要
- **禁止主动询问是否提交** — 提交（git commit / git push）由用户主动发起，AI 不得建议、询问"要提交吗"、"要 push 吗"

## 术语

需要术语定义时：`docs/design/glossary.md`
