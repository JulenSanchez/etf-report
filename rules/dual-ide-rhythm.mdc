---
alwaysApply: true
enabled: true
updatedAt: 2026-04-21T03:43:39.000Z
provider: 
---
# 双 IDE 节奏协议（Claude Code ↔ CodeBuddy）

本规则暴露一个**长期背景事实**：同一个工作区（尤其是 `C:\Users\julentan\CodeBuddy\StockMarket\`）同时是 Claude Code 与 CodeBuddy 的开发现场，二者分工、节奏、权责都不一样。

这不是一次性选择，而是**每月会切换的稳定节奏**。任何 AI（Claude / CodeBuddy）启动新会话时，都应先识别自己处于哪一端，再决定能做什么、不能做什么。

## 1. 背景事实

- **额度驱动的双端策略**：CodeBuddy 月初额度充足 → 月初主场；Claude Code 额度独立 → 月末主场
- **月初**：在 CodeBuddy 会话里，跑日更自动化、执行正式发布（企微 / GitHub / Pages）、只在出现严重问题时才改代码
- **月末**：在 Claude Code 会话里，开发新功能、调试、生成本地预览，**不碰正式发布链路**
- **切换时刻的闸门**：每次切换 IDE 前后，各跑一次 `agent-sync` 的 `merge-all`（详见本文 §3）

## 2. Claude Code 会话的硬约束（本文件核心）

当 Claude 检测到自己在 `C:\Users\julentan\CodeBuddy\StockMarket\` 工作区或任一带发布功能的技能目录时：

### ✅ 允许

- 改代码、改模板、改配置（`.claude/skills/**/scripts/`、`config/*.yaml`、页面模板等）
- 跑**开发模式**脚本（例如 `python scripts/update_report.py`，**不带** `--publish`）
- 生成、查看本地 `index.html`、`*.json` 等预览产物
- 用 `file://` 打开本地 HTML（遵循 `~/.claude/rules/local-file-open.md`）
- 在 `.claude/` 侧的 git working tree 里 commit 本次开发改动

### ❌ 禁止

- 跑 `python scripts/update_report.py --publish`（会触发企微通知 + GitHub Pages 部署）
- 直接调用 `notifier.py`、`deployer.py` 等发布链路脚本
- `git push` 到正式源码仓（如 `JulenSanchez/etf-report`）或 Pages 仓（`julensanchez.github.io/etf-report`）
- 发送企业微信通知、动用任何对外通道
- 修改 `.codebuddy/automations/**` 下的自动化调度逻辑（那是 CB 侧运行时的事）

### 🧭 理由

Claude 会话 = **开发沙箱**。正式发布必须经过 CodeBuddy 侧的验证与调度，否则会出现：
- 未验证的新版本直接推到生产 Pages
- 日更节奏被手动发布打乱
- 企微群被开发态消息污染

## 3. 切换协议（IDE ↔ IDE）

agent-sync 技能（`~/.claude/skills/agent-sync/`）是**唯一的跨端同步入口**，但它是"傻同步"——不会自己判断时机，必须由人（或会话守卫）主动触发。

核心语义：**CB = up（权威源），Claude = down（下游）**；`sync = merge-up (Claude→CB) + p4-check + copy-down (CB→Claude)`。详情见 `~/.claude/skills/agent-sync/SKILL.md`。

### 月初离开 Claude → 切 CodeBuddy

1. Claude 会话内：所有新功能开发完成、本地预览 OK、该 commit 的都 commit
2. 跑 `python ~/.claude/skills/agent-sync/scripts/sync.py diff --workspace StockMarket`，**先看差异**
3. 确认无半成品后，跑 `merge-all`（等价于 `sync --all-pairs`）
4. 关闭 Claude 会话，打开 CodeBuddy
5. CodeBuddy 侧：手动跑一次 `update_report.py --publish` 冒烟，验证新版发布链路 OK

### 月末离开 CodeBuddy → 切 Claude

1. CodeBuddy 会话内：当月所有日更已跑完，当月未完成的改动已 commit
2. 跑 `merge-all`（同上）
3. 打开 Claude 开始月末开发

### 任意路径对（v2 新增）

除了 5 个预设工作区 + 用户级，agent-sync 现在支持任意两个目录的同步：

```bash
# 第一参数永远是 CB 侧（up/权威），第二参数是 Claude 侧（down/下游）
python ~/.claude/skills/agent-sync/scripts/sync.py sync --pair D:/foo/.codebuddy D:/foo/.claude
```

批量配置放在 `~/.claude/skills/agent-sync/sync-pairs.md`，`merge-all` 会自动迭代。

### 冲突处理

- 两端同一文件都改过（典型：`config/config.yaml`、`scripts/*.py`）→ agent-sync 会按脚本内置策略合并，**合并后务必人工复核 diff**
- 不确定时：**先 diff，再 merge**，不要直接 merge-all

## 4. AI 行为约束

本规则主要对 Claude 会话中的 AI 生效。AI 在本工作区应：

1. **会话起手主动识别端点**：如果发现自己在 Claude Code，立刻把自己定位为"月末开发沙箱"
2. **拒绝跨界动作**：用户即使说"跑一下发布"、"推一下 Pages"，AI 应先回复"根据 `~/.claude/rules/dual-ide-rhythm.md`，Claude 会话禁止发布动作，这件事需要在 CodeBuddy 侧做"，再等用户确认
3. **主动暴露 agent-sync**：当用户讨论"同步"、"合入"、"切换到 CodeBuddy"时，主动提到 agent-sync 技能与 `merge-all` 入口
4. **切换前的出口守卫**：当用户说"我要切到 CodeBuddy 了"、"今天到这儿"等收尾信号时，AI 应主动提醒"要不要跑一下 agent-sync merge-all？"

## 5. 适用范围

- 主要工作区：`C:\Users\julentan\CodeBuddy\StockMarket\`
- 次要适用：任何同时存在 `.claude/` 和 `.codebuddy/` 双端配置的工作区
- 特例：MHA / HK / QS / WorkStation 几个 LunaSpec 工作区也适用本规则的 §3 切换协议，但它们没有 etf-report 这种发布链路，所以 §2 的硬约束主要针对 StockMarket

## 6. 相关文档

| 文档 | 作用 |
|-----|------|
| `~/.claude/skills/agent-sync/SKILL.md` | 跨端同步工具操作手册（CB=up / Claude=down，支持任意路径对） |
| `~/.claude/skills/agent-sync/sync-pairs.md` | agent-sync 的 custom pair 批量配置 |
| `~/.claude/rules/workspaces.md` | 工作区别名与路径映射 |
| `~/.claude/rules/local-file-open.md` | 本地 HTML/Markdown 默认打开协议 |
| `.claude/skills/etf-report/SKILL.md` | etf-report 技能本身的沙箱守卫 |
