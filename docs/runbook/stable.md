# stable 仓库与计划任务运维

stable 仓库用于日常计划任务和发布，本文用 `<STABLE_REPO>` 表示。

开发仓用于日常改代码，本文用 `<DEV_REPO>` 表示。

本机默认示例：

```text
STABLE_REPO=C:/Users/julentan/etf-report-stable
DEV_REPO=C:/Users/julentan/etf-report
```

## 更新策略

- stable 默认只做快进更新：`git pull --ff-only origin main`。
- 如果 stable 有本地改动，先人工判断，不自动覆盖。
- 不使用 `git reset --hard` 作为日常更新手段。
- 不使用 `--force` / `--force-with-lease`。

推荐更新方式：

```bat
batchfiles\GitPull.bat
```

或手动：

```bash
git status --short
git pull --ff-only origin main
```

## 计划任务

| 任务名 | 时间 | 脚本 |
|---|---:|---|
| `etf早盘报告` | 11:20 | `batchfiles/preclose_push.bat` |
| `etf午盘报告` | 14:50 | `batchfiles/preclose_push.bat` |
| `etf盘后数据更新` | 15:15 | `batchfiles/postmarket_update.bat` |
| `etf报告发布` | 16:00 | `batchfiles/daily_report.bat` |

重新注册：

```powershell
<STABLE_REPO>/batchfiles/setup_quant_tasks.ps1
<STABLE_REPO>/batchfiles/setup_report_task.ps1
```

检查：

```powershell
$names = @('etf早盘报告','etf午盘报告','etf盘后数据更新','etf报告发布')
foreach ($name in $names) {
  Get-ScheduledTask -TaskName $name
  Get-ScheduledTaskInfo -TaskName $name
}
```

## 观测规则

- 每个交易日收盘后可抽查四个任务的 `LastTaskResult`。
- `0` 表示任务脚本正常退出。
- 非 0 时，手动运行对应 bat 复现；不要直接改计划任务。
- 若任务路径不是 `<STABLE_REPO>/batchfiles/*.bat`，重新运行 setup 脚本。

## 常见问题

| 症状 | 处理 |
|---|---|
| stable pull 被拒绝 | 先看 `git status --short`；有本地改动则人工决定提交、stash 或丢弃 |
| 计划任务未触发 | 检查 Task Scheduler 中触发器和用户权限 |
| preclose push 未推送 | 检查 Tuner 是否能启动、`config/secrets.yaml` 是否有 Server酱 sendkey |
| 报告发布失败 | 手动运行 `batchfiles/daily_report.bat`，再看 `docs/runbook/release.md` |
