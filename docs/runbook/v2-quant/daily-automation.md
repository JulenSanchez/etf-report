# 每日自动化与信号推送

> **触发词**: `每日自动化` `收盘推送` `计划任务` `信号推送`

本文件说明日常自动化的数据流和故障排查。Windows 计划任务的注册、时间表、stable 仓更新策略统一见 `docs/runbook/stable.md`。

## 数据流

```text
batchfiles/preclose_push.bat
  → scripts/preclose_push.py
  → 确保 Tuner 运行
  → /api/refresh_data
  → /api/run
  → Server酱推送 Top12

batchfiles/postmarket_update.bat
  → scripts/quant_data_fetcher.py --start <today> --end <today>

batchfiles/daily_report.bat
  → scripts/quant_data_fetcher.py --start <today> --end <today>
  → scripts/update_report.py --publish
```

## 远端定时触发（腾讯云 SCF）

收盘前信号推送的**精确触发**由腾讯云 SCF 定时触发器负责，解决 GitHub Actions 自带 cron 的队列延迟（BUG-066）。

### 触发链路

```text
腾讯云 SCF 定时 14:45 CST (Mon-Fri)
  → POST workflow_dispatch API（inputs.dry_run=false）
    → signal_push.yml → preclose_push.py → Server酱推送
```

### 为什么是 14:45（不是 14:50）

推送在 GitHub 上有执行耗时，触发要提前：

| 缓存状态 | 耗时 | 推送落地 |
|---|---|---|
| 热缓存（正常，每天被访问） | ~60-90s | ~14:46 |
| 冷启动（缓存被清 / 7 天未访问） | 全量拉取 ~7min | ~14:52 |

14:45 是折中：热缓存时信号价几乎无差，冷启动时仍在 15:00 收盘前。

### 云函数配置

- 函数名 `trigger-signal-push`，Python 3.9，标准库 `urllib`（无第三方依赖）
- 环境变量 `ETF_REPORT_GITHUB_PAT` = Fine-grained PAT（仅 `actions: write`、仅 etf-report 仓）
- 定时 Cron：`0 45 14 * * MON-FRI *`（7 段：秒 分 时 日 月 星期 年）

### PAT 最小权限

触发 workflow_dispatch 只需 `actions: write`。用 **Fine-grained PAT**（`github_pat_` 开头），只授权 etf-report 单仓 + Actions 读写，**不要用经典 `ghp_` token**（`repo` 全量读写会暴露仓库 secret）。

### 排障

| 症状 | 处理 |
|---|---|
| SCF 测试非 204 | 查函数环境变量 PAT 是否设置 / 是否已被吊销 |
| 返回 204 但手机没推送 | 去 GitHub Actions 查 signal_push run 是否启动、是否报错 |
| 推送晚到（~14:52） | 查 run 日志是否出现 `--full`（冷启动，说明缓存被清了） |

## 常见故障

| 症状 | 处理 |
|---|---|
| 计划任务 LastResult 非 0 | 先按 `docs/runbook/stable.md` 定位任务脚本，再手动运行对应 bat 复现 |
| Tuner 未启动 | 手动运行 `python scripts/quant_tuner.py` 检查 preload |
| Server酱未推送 | 检查 `config/secrets.yaml` 中 sendkey |
| stable 未更新 | 按 `docs/runbook/stable.md` 运行 `batchfiles/GitPull.bat` 或手动 `git pull --ff-only` |

## 交易日检查

```bash
python -c "from scripts.trading_calendar import is_trading_day; exit(0 if is_trading_day() else 1)"
```
→ 预期: 交易日 EXIT=0，非交易日 EXIT=1。

非交易日时计划任务仍然触发但脚本应自行跳过（preclose_push.py / update_report.py 内置了交易日检测）。

## 正常状态

| 时间 | 检查点 | 预期 |
|------|--------|------|
| 14:45~14:52 | Server酱推送 | 收到"收盘前信号"微信消息（腾讯云 SCF 14:45 触发，热缓存 ~14:46 / 冷启动 ~14:52） |
| 15:10+ | CSV 更新 | `data/quant/*.csv` 最后一行日期为今日 |
| 16:00+ | 正式页更新 | `index.html` 报告日期为今日，GitHub Pages 部署 |
| 任意 | stable 同步 | `git -C <STABLE_REPO> log -1 --oneline` 与 dev 一致 |

→ **AI 验证**: 若用户报告某项异常，先按上表检查对应时间点的状态，定位是计划任务未触发 / 脚本报错 / 推送失败。

## 稳定仓原则

- stable 仓用于日常发布和计划任务。
- 更新 stable 前先确认没有未提交改动。
- 不自动 force pull；遇到本地改动先人工判断保留或丢弃。
