$ErrorActionPreference = "Stop"
$env:TTC_DATABASE_URL = "sqlite:///runtime/playwright.sqlite3"
$env:TTC_HOST = "127.0.0.1"
$env:TTC_PORT = "8765"
$env:TTC_LOG_LEVEL = "WARNING"
Set-Location (Join-Path $PSScriptRoot "..")
uv run tabletop-companion
