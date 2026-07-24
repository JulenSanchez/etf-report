---
description: Tuner 前端热加载规则——改 HTML 不需重启，改 .py 才需
alwaysApply: true
priority: P2
---

# Tuner 前端热加载

## 规则

修改 `templates/tuner.html`（HTML/CSS/JS）后**不需要重启 Tuner 服务**。Flask 的 `send_from_directory` 每次请求都从磁盘读取，改完即生效。用户刷新浏览器（开 Disable cache）即可看到改动。

## 何时需要重启

只有以下情况需要重启 Tuner：

1. 修改了 `.py` 文件（`quant_tuner.py`、`quant_backtest.py` 等）
2. `__pycache__` 可能污染了路径解析（`paths.py` 的 `.pyc` 指向旧目录）

## Why

之前 REQ-328 开发中，每次改 `tuner.html` 后杀进程→重启→端口冲突→失败重试，浪费了大量轮次。根因就是没区分"HTML 变更"和"Python 变更"的重启策略。

## 验证

改完 HTML 后，浏览器 F12 → Network → 勾选 Disable cache → 刷新 → 检查 Elements 中是否有新元素。不要用 curl 验证后用"以防万一"的理由重启。
