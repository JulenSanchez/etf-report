---
alwaysApply: true
enabled: true
updatedAt: 2026-04-21T03:43:39.000Z
provider: 
---
# 本地文件默认打开协议

本规则适用于**全部工作区**，优先级高于各子技能 / 项目内的描述性口径。
它规定了在 Claude Code 会话中引导用户"打开 / 预览 / 查看"某个本地文件时的默认行为。

## 1. HTML 文件：一律用 `file://` 协议本地打开，默认浏览器 Microsoft Edge

### 规则

- 需要用户查看本地 HTML 产物时，**默认用 Microsoft Edge 打开**对应的 `file://` 路径
- 如果当前环境无法自动唤起浏览器，**只回完整 `file://` 地址**，让用户自己复制粘贴到 Edge
- ❌ **禁止**主动切到 `http://localhost`、起本地静态服务器（`python -m http.server` / `live-server` / `npx serve` 等）
- ❌ **禁止**用 `http` 预览替代 `file://` 预览，即便"http 更稳"也不行
- ❌ **不要**默认用 Chrome / Firefox / IE 或让用户"用你喜欢的浏览器打开"

### 路径格式

Windows 绝对路径需转成标准 `file://` URL，盘符保持小写或大写均可，但**反斜杠一律替换为正斜杠**，且前缀是三斜杠 `file:///`：

```
C:\Users\julentan\CodeBuddy\StockMarket\.claude\skills\etf-report\index.html
↓
file:///c:/Users/julentan/CodeBuddy/StockMarket/.claude/skills/etf-report/index.html
```

### 启动方式（Windows）

Edge 可执行文件路径：

```
C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
```

PATH 中**没有** `msedge` 命令，必须用绝对路径调用。

**Bash / Git Bash 下**（父命令会瞬间返回、Edge 以独立进程后台运行，属正常）：

```bash
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" "file:///c:/path/to/file.html" &
```

**PowerShell 下**：

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "file:///c:/path/to/file.html"
```

**CMD 下**：

```cmd
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "file:///c:/path/to/file.html"
```

### 给用户的回复口径

当引导用户查看某个 HTML 文件时，优先写成：

> 用 Edge 打开：`file:///c:/path/to/file.html`
>
> 或执行：`"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "file:///c:/path/to/file.html"`

### 例外

- "在线发布产物"（如 GitHub Pages 的 `https://xxx.github.io/...`）是另一条线，不受本规则约束
- 若用户**明确要求**起本地服务器（例如为了调试 fetch / CORS），可按用户指令执行；但不得默认切换
- 若用户**明确要求**用别的浏览器（Chrome / Firefox 等），按用户指令来
- 若 Edge 未安装，可降级用系统默认浏览器，但应同时提醒用户安装 Edge 以恢复默认体验

## 2. Markdown 文件：一律用 Typora 打开

### 规则

- 需要用户查看本地 `.md` 文件时，**默认用 Typora 启动**
- ❌ **不要**默认用 VS Code / 记事本 / 浏览器 / 在终端 `cat` 大段输出给用户看
- ✅ 如果只是 AI 自己需要读文件内容用于分析，继续使用 `Read` 工具，不受本规则约束 —— 本规则只管"引导用户去看"的那一步

### 启动方式（Windows）

Typora 可执行文件路径：

```
C:\Program Files\Typora\Typora.exe
```

PATH 中**没有** `typora` 命令，必须用绝对路径调用。

**Bash / Git Bash 下**：

```bash
"/c/Program Files/Typora/Typora.exe" "C:\path\to\file.md" &
```

**PowerShell 下**：

```powershell
& "C:\Program Files\Typora\Typora.exe" "C:\path\to\file.md"
```

**CMD 下**：

```cmd
start "" "C:\Program Files\Typora\Typora.exe" "C:\path\to\file.md"
```

### 给用户的回复口径

当引导用户查看某个 md 文件时，优先写成：

> 用 Typora 打开：`C:\path\to\file.md`
>
> 或执行：`"C:\Program Files\Typora\Typora.exe" "C:\path\to\file.md"`

不要写"用你喜欢的编辑器打开"这类模糊表述。

### 例外

- 用户**明确要求**用 VS Code / 其他编辑器打开时，按用户指令来
- 若 Typora 未安装（新机器 / 同事机器），可降级用 VS Code，但应同时提醒用户安装 Typora 以恢复默认体验

## 3. 其他文件类型

本规则目前只覆盖 HTML 与 Markdown 两类。其他文件（PDF / 图片 / 代码 / 配置）沿用各工作区既有约定或系统默认程序，不在此规定。

## 4. 维护

- 本规则为用户级规则，改动默认需用户确认
- 各项目内如有与本规则冲突的描述性口径（例如 `etf-report/README.md` 里"本地预览默认 file://"的段落），以**本规则为准**，项目内文档可以保留为"本规则在该项目的落地说明"
