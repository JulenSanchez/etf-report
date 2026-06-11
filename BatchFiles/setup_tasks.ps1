# etf-report 定时任务一键部署
# 用法: 右键 → 使用 PowerShell 运行，或管理员终端执行 .\setup_tasks.ps1
# 在新电脑 clone 仓库后运行一次即可。

$repoDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

$tasks = @(
    @{Name="etf早盘报告";     Time="11:20"; Script="preclose_push.bat";      Desc="盘中数据+回测→Server酱推送"},
    @{Name="etf午盘报告";     Time="14:50"; Script="preclose_push.bat";      Desc="盘中数据+回测→Server酱推送"},
    @{Name="etf盘后数据更新"; Time="15:15"; Script="postmarket_update.bat"; Desc="拉取收盘K线数据"},
    @{Name="etf报告发布";     Time="16:00"; Script="daily_report.bat";      Desc="更新+发布正式页到GitHub Pages"}
)

foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute "$repoDir\batchfiles\$($t.Script)"
    $trigger = New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $t.Time
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Settings $settings -Description $t.Desc -Force
    Write-Host "✅ $($t.Name) ($($t.Time))"
}

Write-Host ""
Write-Host "4 tasks registered. Verify with: taskschd.msc"
