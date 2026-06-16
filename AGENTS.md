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
   - 量化 / Tuner / 回测：`docs/ops/quant/overview.md`、`config/quant_universe.yaml`、`scripts/quant_*.py`
   - 正式页 / 报告 / 发布：`docs/ops/report.md`、`docs/ops/release.md`、`scripts/update_report.py`、`scripts/deployer.py`、`assets/js/`
   - stable / 计划任务：`BatchFiles/`、`docs/ops/release.md`
   - 架构 / 包化：`docs/architecture.md`、`src/`、`scripts/`

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

## 安全规则

- 涉及**换池/新增/移除/替换 ETF** 的任何操作前，**必须先读取 `docs/ops/pool-change.md`**，按逐支执行 SOP 操作。禁止批量改 config，禁止合并验证。
- 不主动 push、发布、删除目录、修改 Windows 计划任务，除非用户明确要求。
- 遇到 destructive / shared-state 操作先确认。
- 不使用 `--force` / `--force-with-lease`，除非用户明确要求且说明原因。
- 修改核心逻辑后跑相关最小验证；涉及回测/参数/发布链时优先跑对应测试。
- 不扫描或修改 `logs/`、`data/`、`outputs/`、`_working/`，除非任务明确需要。
- **遭遇 Tuner/回测/数据异常时，先查排障表**：
  - 量化/Tuner/回测 → `docs/ops/quant/overview.md` §7 故障排查
  - 正式页/推送/数据管线 → `docs/ops/report.md` 常见问题
  - 不要猜进程/网络/缓存，先按症状索引定位。

## 详细 AI 协作说明

需要术语、任务路由或高风险规则时，再读取：

```text
docs/ai/AGENT_GUIDE.md
```
