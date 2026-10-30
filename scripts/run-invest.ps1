# 启动 Invest API + H5（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File scripts/run-invest.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $root "invest-api"
$webDir = Join-Path $root "frontend/invest"

Write-Host "Starting API on http://127.0.0.1:8767 ..."
$api = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    conda run -n svquant python -m uvicorn app:app --host 127.0.0.1 --port 8767
} -ArgumentList $apiDir

Write-Host "Starting H5 on http://127.0.0.1:9540 ..."
$web = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    & "..\node_modules\.bin\vite.cmd" --host 127.0.0.1 --port 9540
} -ArgumentList $webDir

Write-Host "Demo login: demo / demo1234"
Write-Host "Press Ctrl+C to stop."

try {
    Wait-Job $api, $web
} finally {
    Stop-Job $api, $web -ErrorAction SilentlyContinue
    Remove-Job $api, $web -Force -ErrorAction SilentlyContinue
}
