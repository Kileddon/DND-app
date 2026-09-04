$ErrorActionPreference = "Stop"
$E2ePort = if ($env:TTC_E2E_PORT) { $env:TTC_E2E_PORT } else { "8765" }
$env:TTC_DATABASE_URL = "sqlite:///runtime/playwright-$E2ePort.sqlite3"
$env:TTC_HOST = "127.0.0.1"
$env:TTC_PORT = $E2ePort
$env:TTC_LOG_LEVEL = "WARNING"
Set-Location (Join-Path $PSScriptRoot "..")
uv run --no-sync tabletop-companion
