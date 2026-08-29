# SCF 定时触发函数 — 源码与部署配置

> 归属：`docs/runbook/v2-quant/daily-automation.md`「远端定时触发」。
> 本文件是腾讯云云函数 `trigger-signal-push` 的**唯一版本化源码**，控制台以本文件为准。

## 作用

用标准库 `urllib` 调 GitHub `workflow_dispatch` API，触发 `signal_push.yml`，实现收盘前信号推送的精确定时（解决 GitHub Actions 自带 cron 的队列延迟，BUG-066）。

## 函数源码

```python
import os, json, urllib.request, urllib.error

def main_handler(event, context):
    token = os.environ.get("ETF_REPORT_GITHUB_PAT")
    if not token:
        return {"ok": False, "error": "ETF_REPORT_GITHUB_PAT not set"}

    url = ("https://api.github.com/repos/JulenSanchez/etf-report/"
           "actions/workflows/signal_push.yml/dispatches")
    payload = json.dumps({"ref": "main", "inputs": {"dry_run": "false"}}).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        # GitHub 明确返回错误状态码（401/403/404/422…），请求已被处理，正常返回即可
        return {"ok": False, "status": e.code, "body": e.read().decode()}
    except urllib.error.URLError as e:
        # 网络层错误（超时/DNS/连接重置）。此时请求可能已送达 GitHub，
        # 重试只会造成重复推送 —— 正常返回、不触发 SCF 异步重试。
        return {"ok": False, "error": f"URLError: {e.reason}"}
```

## 部署配置（腾讯云控制台）

| 项 | 值 | 说明 |
|----|----|------|
| 函数名 | `trigger-signal-push` | |
| Runtime | Python 3.9 | 仅标准库，无第三方依赖 |
| 超时时间 | **30s** | 必须 ≥ 代码内 `urlopen` 的 15s，否则函数超时被 SCF 判定失败 → 重试 |
| 异步重试次数 | **0** | 关闭重试：函数崩溃/超时不再自动重跑，避免重复推送 |
| 环境变量 | `ETF_REPORT_GITHUB_PAT` | Fine-grained PAT（仅 `actions: write`、仅 etf-report 仓） |
| 定时触发器 | 见 daily-automation.md | 11:20 早盘 + 14:48 尾盘 |

## 为什么「超时 30s + 重试 0」是硬约束

2026-08-20 / 08-25 尾盘推送各重复一次，链路：

```
第一次 POST 已送达 GitHub（workflow 成功跑完、已推送）
  → 但 204 响应慢/丢 → urlopen 抛 URLError(timeout)
  → 旧代码只 catch HTTPError、没接住 URLError → 函数崩溃
  → SCF 异步重试（60s 后）→ 第二次 dispatch → 重复推送
```

`URLError` 是 `HTTPError` 的**父类**，`except HTTPError` 接不住超时/网络错误。修复三件套缺一不可：

1. catch `URLError`（正常 return，函数不再崩溃）
2. 函数超时 30s（≥ urlopen 的 15s，别让函数超时先于 urlopen 超时）
3. 异步重试次数 0（即使偶发崩溃也不自动重跑）

## 排障

| 症状 | 处理 |
|------|------|
| 推送重复 | 见 daily-automation.md 排障表；先查「超时时间 / 重试次数」是否被改回 |
| SCF 测试非 204 | 查 PAT 是否设置 / 是否被吊销 |
