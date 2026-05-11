# StartTuner.ps1
# Starts the Quant Tuner Flask server as a background process, then opens Edge.

$skillDir = (Get-Item $PSScriptRoot).Parent.FullName
$script    = Join-Path $skillDir "scripts\quant_tuner.py"
$url       = "http://localhost:5179"
$edge      = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 1. Launch Tuner server in background
Start-Process python `
    -ArgumentList "`"$script`" --no-browser" `
    -WorkingDirectory $skillDir `
    -WindowStyle Hidden

# 2. Open Edge immediately
if (Test-Path $edge) {
    Start-Process $edge $url
} else {
    Start-Process $url
}
