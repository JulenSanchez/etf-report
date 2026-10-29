# StartTuner.ps1
# Hot-swap launcher: preloads data while old process still serves, then atomically swaps.
#
# Flow:
#   1. Clean stale signal file
#   2. Start new Python (preloads while old process holds the port)
#   3. Wait for signal: ".tuner_ready_to_bind" appears = preload done
#   4. Kill old process on the port
#   5. Delete signal file → new Python binds port immediately
#   6. Wait for Flask to actually listen, then open Edge
#
# Port vacuum: ~100ms (vs ~2000ms in the old kill-then-start approach).
#
# Note: 5179 was retired because Tencent iOA (iOAGuard.exe) reserves loopback ports
# 5175-5179 with SO_EXCLUSIVEADDRUSE, so bind() fails with WinError 10013 (WSAEACCES).
# Port is read from config/tuner_config.json — the single source of truth shared with
# the Python scripts (tuner_config.py). Change the port there, not here.

$skillDir   = (Get-Item $PSScriptRoot).Parent.FullName
$script     = Join-Path $skillDir "scripts\quant_tuner.py"
$signalFile = Join-Path $skillDir ".tuner_ready_to_bind"
$configFile = Join-Path $skillDir "config\tuner_config.json"
if (-not (Test-Path $configFile)) {
    Write-Host "[StartTuner] ERROR: config not found: $configFile"
    exit 1
}
$tunerConfig = Get-Content $configFile -Raw | ConvertFrom-Json
$tunerPort   = [int]$tunerConfig.dev_port
$url         = "http://localhost:$tunerPort"
$edge       = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$outLog     = Join-Path $skillDir ".tuner_startup.out.log"
$errLog     = Join-Path $skillDir ".tuner_startup.err.log"

function Get-TunerPidsOnPort {
    $lines = netstat -aon | Select-String ":$tunerPort"
    $pids = @()
    foreach ($line in $lines) {
        $text = $line.ToString().Trim()
        if ($text -match "LISTENING\s+(\d+)$") {
            $pids += [int]$matches[1]
        }
    }
    return $pids | Select-Object -Unique
}

# 1. Clean stale signal from any previous crashed run
if (Test-Path $signalFile) {
    Remove-Item $signalFile -Force
}

# 2. Launch new Python — preloads synchronously while old process still serves.
#    Redirect output to logs so preload/bind errors are diagnosable (window is hidden).
Start-Process python `
    -ArgumentList "`"$script`" --preload-then-wait --no-browser --port $tunerPort" `
    -WorkingDirectory $skillDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

# 3. Wait for new Python to finish preload (signal file appears)
$preloadOk = $false
for ($i = 0; $i -lt 120; $i++) {
    if (Test-Path $signalFile) {
        $preloadOk = $true
        break
    }
    Start-Sleep -Milliseconds 250
}
if (-not $preloadOk) {
    Write-Host "[StartTuner] WARNING: preload timed out (30s), proceeding anyway"
}

# 4. Kill old process(es) on the port
foreach ($pidToKill in Get-TunerPidsOnPort) {
    & taskkill.exe /F /T /PID $pidToKill | Out-Null
}

# 5. Delete signal file — new Python detects this and binds the port
if (Test-Path $signalFile) {
    Remove-Item $signalFile -Force
}

# 6. Wait for Flask to actually listen (post-bind, should be fast since preload is done).
#    A synchronous Connect() throws on "connection refused", so a successful return
#    really means Flask is listening — unlike ConnectAsync().Wait(), which also returns
#    true on refusal and used to open Edge on a dead port.
$tunerUp = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", $tunerPort)
        $tunerUp = $true
        $tcp.Close()
        break
    } catch {
        # not listening yet
    }
    Start-Sleep -Milliseconds 100
}

# 7. Open Edge only if Flask actually came up; otherwise fail loudly.
if (-not $tunerUp) {
    Write-Host "[StartTuner] ERROR: Tuner did not start listening on port $tunerPort."
    Write-Host "[StartTuner] Check logs: $outLog and $errLog"
    if (Test-Path $errLog) {
        Write-Host "[StartTuner] Last stderr lines:"
        Get-Content $errLog -Tail 20 | ForEach-Object { Write-Host "    $_" }
    }
    exit 1
}

if (Test-Path $edge) {
    Start-Process $edge $url
} else {
    Start-Process $url
}
