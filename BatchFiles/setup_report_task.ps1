# 正式页报告发布 — 定时任务一键部署
# 用法: 右键 → 使用 PowerShell 运行，或管理员终端: .\setup_report_task.ps1

$repoDir = Split-Path -Parent $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

$action = New-ScheduledTaskAction -Execute "$repoDir\batchfiles\daily_report.bat"
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "16:00"
Register-ScheduledTask -TaskName "etf报告发布" -Action $action -Trigger $trigger `
    -Settings $settings -Force
Write-Host "✅ etf报告发布 (16:00)"
Write-Host "`n1 report task registered. Verify: taskschd.msc"
