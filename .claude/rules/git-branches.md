---
description: 分支策略、提交门禁（commit/push 必须用户触发）、回退方式
alwaysApply: true
priority: P0
---

# Git 分支规则（etf-report 项目专属）

## 分支策略

- `main` — 开发分支，所有改动在这里累积
- `stable`（`etf-report-stable`）— 生产分支，永远只拉不推，除非用户明确说"同步 stable"

## 提交门禁（main 分支）

**git commit / git push 只能由用户触发，AI 不得自行发起。**

| 触发词 | 流程 | 说明 |
|--------|------|------|
| **"发布"** | `docs/runbook/release.md` 全流程（Phase 0-8） | 含版本治理、安全审查、分段提交 |
| **"提交"** | 快速路径：跳过 Phase 4 版本治理，其余同发布 | 紧急修复、不想走完整版本的轻量场景 |
| **"同步 stable"** | 先 push main，再在 stable 仓库 `git pull` | 紧急修复 hotfix |

**禁止行为**：

- AI 在用户未说"发布"/"提交"时自行 `git commit`
- AI 在用户未说"发布"/"提交"/"同步 stable"时自行 `git push`
- `git add -A`（必须指定文件或目录）
- **`git checkout -- <file>` / `git restore <file>` / `git reset --hard` — 禁止用于"回退改动"。这些操作无差别清除所有未提交改动（含用户自己写的代码），不可恢复**

**正确行为**：

- 改动完成后告知用户"有未提交改动，当前分支 main"，不主动 commit
- 用户说"提交" → 走 release.md 快速路径
- 用户说"发布" → 走 release.md 全流程
- 用户说"同步 stable" → 先确认 main 已推送，再在 stable 仓库 pull

## 回退改动的正确方式

当用户说"回退刚才的改动"时，**禁止使用 `git checkout`**。必须：

1. **先 `git diff --stat`** — 确认哪些文件有未提交改动，每行改动是谁的
2. **定位 AI 的改动** — 用 `git diff <file>` 逐文件看，只回退 AI 产生的改动行
3. **用 `Edit` 逐条逆向** — 每条 Edit 都是精确的字符串替换，只影响一个逻辑块
4. **永远保留用户自己的未提交代码** — 即使看起来"顺手一起回退了更干净"也不行

`.git` 的作用是安全网：在动手之前用 `git diff` 看清楚范围，而不是在动手之后用 `git checkout` 核爆文件。

## stable 仓库同步

stable 仓库位于 `C:\Users\julentan\etf-report-stable`，独立 clone。同步步骤：

```bash
# 1. 在 main 仓库（当前项目）提交并推送
# 2. 在 stable 仓库拉取
cd C:\Users\julentan\etf-report-stable
git pull origin main
```
