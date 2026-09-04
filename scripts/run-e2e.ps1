$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$E2ePort = if ($env:TTC_E2E_PORT) { $env:TTC_E2E_PORT } else { "8765" }

$env:TTC_DATABASE_URL = "sqlite:///runtime/playwright-$E2ePort.sqlite3"
$env:TTC_HOST = "127.0.0.1"
$env:TTC_PORT = $E2ePort
$env:TTC_LOG_LEVEL = "WARNING"
$env:TTC_E2E_EXTERNAL_SERVER = "1"

Set-Location $FrontendRoot
npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Server = Start-Process `
    -FilePath $Python `
    -ArgumentList "-m", "tabletop_companion.main" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -PassThru

$TestExitCode = 1
try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 120; $Attempt += 1) {
        try {
            $Response = Invoke-WebRequest "http://127.0.0.1:$E2ePort/health" -UseBasicParsing
            if ($Response.StatusCode -eq 200) {
                $Ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $Ready) { throw "E2E host did not become ready." }
    npx playwright test
    $TestExitCode = $LASTEXITCODE
}
finally {
    if (-not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force
        $Server.WaitForExit()
    }
}
exit $TestExitCode
