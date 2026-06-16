# 每日自动化与信号推送

本项目的日常自动化主要通过 Windows 计划任务调用 `BatchFiles/` 下的脚本完成。稳定发布仓通常使用：

```text
C:/Users/julentan/etf-report-stable
```

## 计划任务

| 任务名 | 时间 | 脚本 |
|---|---:|---|
| `etf早盘报告` | 11:20 | `BatchFiles/preclose_push.bat` |
| `etf午盘报告` | 14:50 | `BatchFiles/preclose_push.bat` |
| `etf盘后数据更新` | 15:15 | `BatchFiles/postmarket_update.bat` |
| `etf报告发布` | 16:00 | `BatchFiles/daily_report.bat` |

注册脚本：

```powershell
C:/Users/julentan/etf-report-stable/BatchFiles/setup_quant_tasks.ps1
C:/Users/julentan/etf-report-stable/BatchFiles/setup_report_task.ps1
```

## 数据流

```text
preclose_push.bat
  → scripts/preclose_push.py
  → 确保 Tuner 运行
  → /api/refresh_data
  → /api/run
  → Server酱推送 Top12

postmarket_update.bat
  → scripts/quant_data_fetcher.py --start <today> --end <today>

daily_report.bat
  → scripts/quant_data_fetcher.py --start <today> --end <today>
  → scripts/update_report.py --publish
```

## 常见故障

| 症状 | 处理 |
|---|---|
| 计划任务 LastResult 非 0 | 查看对应 bat 输出或手动运行脚本复现 |
| Tuner 未启动 | 手动运行 `python scripts/quant_tuner.py` 检查 preload |
| Server酱未推送 | 检查 `config/secrets.yaml` 中 sendkey |
| stable 未更新 | 手动运行 `BatchFiles/GitPull.bat`，确认无本地未提交改动 |

## 检查计划任务

```powershell
Get-ScheduledTask -TaskName etf早盘报告,etf午盘报告,etf盘后数据更新,etf报告发布
```

## 稳定仓原则

- stable 仓用于日常发布和计划任务。
- 更新 stable 前先确认没有未提交改动。
- 不自动 force pull；遇到本地改动先人工判断保留或丢弃。
