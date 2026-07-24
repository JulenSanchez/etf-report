---
description: 禁止 python -c，一律写临时脚本；输出重定向到文件防 UTF-8 截断
alwaysApply: true
priority: P0
---

# 禁止 python -c / python3 -c（项目级兜底）

用户级 `command-line-best-practices.md` 已有此规则，但 PowerShel 环境下 AI 容易因"图快"而违反。本规则是项目级兜底。

## 为什么

PowerShell 的字符串引号规则与 Python 引号冲突。`python -c "f'{d[\"key\"]}'"` 这类嵌套在 PowerShel 下极易产生不可预期的转义错误，且错误是**静默的**——不会报 SyntaxError，而是产生完全错误的运行结果（变量值为空/乱码/数字错位）。本次会话三次踩坑：涨幅数字 ×0.01、ETF 名乱码、持仓过滤条件静默失效。

## 替代方案（零开销）

任何需要 Python 代码的场景，一律写临时脚本到 `C:\Users\julentan\temp_scripts\temp_YYYYMMDD_HHMMSS_desc.py`，然后 `python <path>` 执行。任务结束时按 `skill-sanitization.md` 清理。

## AI 自检

写 `python -c` 或 `python3 -c` 之前 → **Stop**。问自己："这个逻辑会不会有引号嵌套？会 → 写文件。不会 → 还是写文件——因为 PowerShell 下不会也有概率出错。"

## 输出验证（防误判）

凡是要展示给用户的数据（ETF 名/涨幅/板块），**输出必须重定向到文件**（`> C:\Users\julentan\temp_scripts\out.txt 2>&1`），然后用 **Read 工具**读取。PowerShell 控制台对 UTF-8 中文有编码截断，`+15.9%` 可能显示为 `+0.2%`（差 100 倍）——直接看控制台输出 = 赌命。Read 工具读文件 = 正确编码。"
