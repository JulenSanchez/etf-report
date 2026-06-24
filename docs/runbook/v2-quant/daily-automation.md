# 每日自动化与信号推送

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

## 常见故障

| 症状 | 处理 |
|---|---|
| 计划任务 LastResult 非 0 | 先按 `docs/runbook/stable.md` 定位任务脚本，再手动运行对应 bat 复现 |
| Tuner 未启动 | 手动运行 `python scripts/quant_tuner.py` 检查 preload |
| Server酱未推送 | 检查 `config/secrets.yaml` 中 sendkey |
| stable 未更新 | 按 `docs/runbook/stable.md` 运行 `batchfiles/GitPull.bat` 或手动 `git pull --ff-only` |

## 稳定仓原则

- stable 仓用于日常发布和计划任务。
- 更新 stable 前先确认没有未提交改动。
- 不自动 force pull；遇到本地改动先人工判断保留或丢弃。
