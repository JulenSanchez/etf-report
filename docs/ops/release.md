# ETF Report 安全发布规程

## 定位

1. **唯一门禁**：发布前到底要做什么，只由本文定义。
2. **单一事实源**：发布检查只维护在本文，其他文档只链接本文。
3. **治理文档**：本文位于 `docs/ops/release.md`，随仓库提交。治理文件（`plans/`、`docs/ops/` 等）均纳入版本控制。

## 提交边界速查

| 类别 | 典型路径 | 是否可提交 | 原因 |
|------|----------|------------|------|
| 稳定文档 | `README.md`、`docs/` 下稳定补充文档 | ✅ 可以 | 对外用户可见，且内容稳定、可复用 |
| 实现与模板 | `scripts/`、`src/`、`tests/`、`requirements.txt`、`config/*.example.yaml`、`config/holdings.yaml`、根目录 `index.html` | ✅ 按需 | 属于实际功能、测试、公开模板或发布产物 |
| 治理文档 | `PLAN.md`、`plans/`、`docs/ops/`、`docs/ai/` | ✅ 可以 | 治理文件纳入版本控制，便于跨机器同步与协作追溯 |
| 运行时配置 | `config/config.yaml` | ✅ 可以 | 已移除本地绝对路径，内容可公开 |
| 敏感配置 | `config/secrets.yaml` | ❌ 不可 | 含 API 密钥等敏感信息，.gitignore 必须覆盖 |
| 运行产物与缓存 | `data/`、`logs/`、`_working/`、`.backup/`、`outputs/`、`research/` | ❌ 不可 | 运行缓存、日志、临时输出或备份，本地生成即可 |

### `docs/` 准入标准

只有满足下面任一条件，文档才允许留在 `docs/`：

1. 它是**根目录核心公开文档**（如 `README.md`）的稳定补充说明。
2. 它是对外读者也需要长期查阅的**重要公开支线**，且不会随着某个单次需求关闭而失效。

以下内容**不得**留在 `docs/`：

- 需求草案、协议草案、填写模板
- postmortem / incident / 紧急事故复盘
- 单个需求的集成笔记、一次性迁移说明、内部协作口径

### 文档归位规则

- **需求草案 / 模板** → `plans/REQ-XXX.md`
- **事件复盘** → `plans/BUG-XXX.md`
- **开发者规程** → `docs/ops/`

## 发布前工作流

### Phase 0: 发布资格判定

在任何 Git 操作前，先确认这次发布是否具备资格：

- [ ] `plans/Board.md` 的 `in_progress` 区无活跃开发项（搁置项不阻塞）
- [ ] `plans/Board.md` 的 `bugs` 区没有 `open/fixing` 状态的 `critical/major` Bug
- [ ] 正常发布时，`plans/Board.md` 的 `done` 区有内容
- [ ] 如果是"已发布后的补救治理"，先明确远端 / Pages 是否已经处于目标版本状态，再决定补救范围

任一项不满足：**停止发布**，先说明阻塞原因，不得继续。

### Phase 1: 本地验证与审计

先确认本地生成与检查链路正常：

- [ ] 运行 `python scripts/update_report.py`（不带 `--publish`）
- [ ] 检查生成的 `index.html` / `runtime_payload.js` / 关键数据文件是否完整
- [ ] 查看健康检查、日志、关键页面表现是否正常
- [ ] 运行 `python scripts/audit_project.py --full --report-only`
- [ ] 若审计报告有异常，先修复后再继续

### Phase 2: 安全审查

在暂存前，先审视"哪些内容绝不能提交"：

- [ ] 回读 `git diff`
- [ ] 回读 `git diff --stat`
- [ ] 排查本地绝对路径（如 `C:/Users/...`、`file:///...`）
- [ ] 排查私有规则 / 本地协作协议引用（如 `~/.codebuddy/...`、只对本机成立的守卫说明）
- [ ] 排查敏感信息（密钥、密码、token、secret）——尤其关注 `config/secrets.yaml` 是否误入暂存
- [ ] 排查调试分支、一次性注释、临时样本、手工排查产物
- [ ] 排查 `docs/` 是否混入草案、复盘、私有规程

### Phase 3: 敏感文件边界核对

确认仓库中不存在敏感文件：

- [ ] `.gitignore` 已覆盖 `config/secrets.yaml`、运行数据、日志、临时目录
- [ ] 运行 `git ls-files config/secrets.yaml`，应返回空结果
- [ ] 若发现 `secrets.yaml` 已被跟踪，立即执行 `git rm --cached` + `.gitignore` 修复 + `git filter-branch` 清历史
- [ ] 治理文件（`plans/`、`docs/ops/` 等）已合法跟踪，无需排除

### Phase 4: 分段暂存与提交审查

只在上面通过后，才允许进入暂存：

- [ ] 按文件 / 功能分段 `git add`，禁止 `git add .`
- [ ] 运行 `git status` 核对暂存范围
- [ ] 运行 `git diff --cached` 核对即将提交的真实内容
- [ ] 提交消息清晰明确，能说明这次改动解决了什么

### Phase 5: 版本治理

只有在发布资格与安全审查都通过后，才更新治理文件：

- [ ] 若 `done` 区包含 High 需求，执行 `minor` 递增；否则执行 `patch` 递增；若用户明确指定版本号，以用户决定为准
- [ ] 收集 `done` 区的 REQ ID 与标题，写入 `plans/Archive.md` 的版本发布记录
- [ ] 清空 `plans/Board.md` 的 `done` 区
- [ ] 更新 `plans/Board.md` 的当前版本、发布日期、开发中需求
- [ ] 关闭本轮已收口的活跃 Bug，并同步归档 / 计数器

### Phase 6: 预推送检查

推送前再做一次远端视角核对：

- [ ] 运行 `git fetch origin`
- [ ] 运行 `git log origin/main..HEAD --oneline`
- [ ] 运行 `git diff origin/main HEAD`
- [ ] 确认没有混入无关提交、调试提交、敏感文件异常
- [ ] 确认 `docs/` 里只剩稳定公开补充文档
- [ ] 明确本次走 **PR 路径** 还是 **快速直推路径**

### Phase 7: 推送策略

#### 默认路径：特性分支 + PR

首选以下流程：

1. `git checkout -b feature/<topic>`
2. `git push origin feature/<topic>`
3. 在 GitHub 创建 PR
4. 审查通过后合并到 `main`

#### 快速路径：直接推送到 `main`

只有同时满足以下条件才允许：

- [ ] 用户已明确要求直接推送
- [ ] 本文前 0~6 阶段已全部完成
- [ ] 当前改动范围已确认安全、必要、无多余文件

允许后再执行：

1. `git push origin main`
2. 推送后立即做发布后复核

### Phase 8: 发布后复核

- [ ] 运行 `git log -1 --oneline`
- [ ] 运行 `git status`
- [ ] 检查目标页面 / Pages / 通知链路是否处于预期状态
- [ ] 若发现异常，立即进入回滚 / 补救治理，而不是口头宣称"已发布完成"

## 与审计规程的关系

- 发布前的完整审计，以 `AUDIT_RUNBOOK.md` 为执行细则。
- 固定周期的周审计由自动化调度触发，默认每周一上午执行一次 `python scripts/audit_project.py --full --report-only`。
- 若审计发现敏感文件边界被破坏（如 `secrets.yaml` 泄露），应先修复边界，再谈发布。

## 执行口径

- 发布前，AI 必须把本文当成**唯一门禁**逐项执行。
- 若本文漏写了某个发布前必做动作，先补本文，再继续发布。
- `PLAN.md` 与 `.codebuddy/rules/etf-report.mdc` 不再维护并列的发布前检查副本。



