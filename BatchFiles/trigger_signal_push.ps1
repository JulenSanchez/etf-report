# Trigger GitHub Actions signal_push workflow via workflow_dispatch API.
# Requires GITHUB_PAT environment variable (repo-level or user-level).
# Usage: powershell -File trigger_signal_push.ps1
$ErrorActionPreference = "Stop"

$token = $env:GITHUB_PAT
if (-not $token) {
    Write-Host "[ERROR] GITHUB_PAT environment variable not set."
    Write-Host "  Run: setx GITHUB_PAT ""ghp_xxxx"""
    exit 1
}

$headers = @{
    Authorization = "Bearer $token"
    Accept        = "application/vnd.github.v3+json"
}
$body = '{"ref":"main"}'
$uri  = "https://api.github.com/repos/JulenSanchez/etf-report/actions/workflows/signal_push.yml/dispatches"

try {
    $resp = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body -ContentType "application/json"
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] Signal push triggered OK"
} catch {
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] ERROR: $($_.Exception.Message)"
    exit 1
}
