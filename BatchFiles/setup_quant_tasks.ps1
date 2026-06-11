# 量化信号推送 — 定时任务一键部署
# 用法: 右键 → 使用 PowerShell 运行，或管理员终端: .\setup_quant_tasks.ps1

$repoDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

$tasks = @(
    @{Name="etf早盘报告";     Time="11:20"; Script="preclose_push.bat"},
    @{Name="etf午盘报告";     Time="14:50"; Script="preclose_push.bat"},
    @{Name="etf盘后数据更新"; Time="15:15"; Script="postmarket_update.bat"}
)

foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute "$repoDir\batchfiles\$($t.Script)"
    $trigger = New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $t.Time
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Settings $settings -Force
    Write-Host "✅ $($t.Name) ($($t.Time))"
}
Write-Host "`n3 quant tasks registered. Verify: taskschd.msc"
