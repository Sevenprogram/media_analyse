param(
    [int]$Port = 8080,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
$StdOutLog = Join-Path $ProjectRoot ".codex-api.out.log"
$StdErrLog = Join-Path $ProjectRoot ".codex-api.err.log"
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".uv-cache"

if (-not (Test-Path $PythonExe)) {
    throw "Python runtime not found at $PythonExe"
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($existing) {
    throw "Port $Port is already in use by PID $($existing.OwningProcess)"
}

$command = @(
    "-m",
    "uvicorn",
    "api.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "$Port"
)

Push-Location $ProjectRoot
try {
    if ($Foreground) {
        & $PythonExe @command
        exit $LASTEXITCODE
    }

    $process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $command `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog `
        -PassThru

    Write-Output "Started API server on port $Port (PID $($process.Id))."
    Write-Output "stdout: $StdOutLog"
    Write-Output "stderr: $StdErrLog"
}
finally {
    Pop-Location
}
