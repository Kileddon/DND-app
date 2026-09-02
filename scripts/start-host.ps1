param(
    [switch]$RebuildFrontend
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not installed or is not available in PATH."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js/npm is not installed or is not available in PATH."
}

uv sync --locked --all-groups

$FrontendEntry = Join-Path $ProjectRoot "frontend\dist\index.html"
if ($RebuildFrontend -or -not (Test-Path $FrontendEntry)) {
    Push-Location (Join-Path $ProjectRoot "frontend")
    try {
        npm ci
        npm run build
    }
    finally {
        Pop-Location
    }
}

uv run tabletop-companion
