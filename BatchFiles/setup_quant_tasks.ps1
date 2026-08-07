# 量化信号推送 — 定时任务一键部署
$repoDir = Split-Path -Parent $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

$tasks = @(
    @{Name='etf早盘报告';     Time='11:20'; Script='trigger_signal_push.ps1'; Type='ps1'},
    @{Name='etf午盘报告';     Time='14:50'; Script='trigger_signal_push.ps1'; Type='ps1'},
    @{Name='etf盘后数据更新'; Time='15:30'; Script='refresh_data.bat';          Type='bat'}
)

foreach ($t in $tasks) {
    $scriptPath = "$repoDir\BatchFiles\$($t.Script)"
    if ($t.Type -eq 'ps1') {
        $action = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
    } else {
        $action = New-ScheduledTaskAction -Execute $scriptPath
    }
    $trigger = New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $t.Time
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Settings $settings -Force
    Write-Host "OK $($t.Name) ($($t.Time)) — $($t.Script)"
}
Write-Host '3 quant tasks registered.'
