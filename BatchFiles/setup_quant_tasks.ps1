# 量化信号推送 — 定时任务一键部署
$repoDir = Split-Path -Parent $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

$tasks = @(
    @{Name='etf早盘报告';     Time='11:20'; Script='preclose_push.bat'},
    @{Name='etf午盘报告';     Time='14:50'; Script='preclose_push.bat'},
    @{Name='etf盘后数据更新'; Time='16:00'; Script='daily_report.bat'}
)

foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute "$repoDir\BatchFiles\$($t.Script)"
    $trigger = New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $t.Time
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Settings $settings -Force
    Write-Host "OK $($t.Name) ($($t.Time))"
}
Write-Host '3 quant tasks registered.'
