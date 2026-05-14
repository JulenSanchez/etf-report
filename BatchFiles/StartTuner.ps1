# StartTuner.ps1
# Hot-swap launcher: preloads data while old process still serves, then atomically swaps.
#
# Flow:
#   1. Clean stale signal file
#   2. Start new Python (preloads while old process holds port 5179)
#   3. Wait for signal: ".tuner_ready_to_bind" appears = preload done
#   4. Kill old process on port 5179
#   5. Delete signal file → new Python binds port immediately
#   6. Wait for Flask, then open Edge
#
# Port 5179 vacuum: ~100ms (vs ~2000ms in the old kill-then-start approach).

$skillDir   = (Get-Item $PSScriptRoot).Parent.FullName
$script     = Join-Path $skillDir "scripts\quant_tuner.py"
$signalFile = Join-Path $skillDir ".tuner_ready_to_bind"
$url        = "http://localhost:5179"
$edge       = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

function Get-TunerPidsOnPort {
    $lines = netstat -aon | Select-String ":5179"
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

# 2. Launch new Python — preloads synchronously while old process still serves 5179
Start-Process python `
    -ArgumentList "`"$script`" --preload-then-wait --no-browser" `
    -WorkingDirectory $skillDir `
    -WindowStyle Hidden

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

# 4. Kill old process(es) on port 5179
foreach ($pidToKill in Get-TunerPidsOnPort) {
    & taskkill.exe /F /T /PID $pidToKill | Out-Null
}

# 5. Delete signal file — new Python detects this and binds port 5179
if (Test-Path $signalFile) {
    Remove-Item $signalFile -Force
}

# 6. Wait for Flask to be listening (post-bind, should be fast since preload is done)
for ($i = 0; $i -lt 30; $i++) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        if ($tcp.ConnectAsync("127.0.0.1", 5179).Wait(300)) {
            $tcp.Close()
            break
        }
        $tcp.Close()
    } catch {}
    Start-Sleep -Milliseconds 100
}

# 7. Open Edge
if (Test-Path $edge) {
    Start-Process $edge $url
} else {
    Start-Process $url
}
