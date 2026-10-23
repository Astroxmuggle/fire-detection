<#
.SYNOPSIS
    Start FireWatch AI from its virtual environment with the settings in .env.

.DESCRIPTION
    Convenience launcher for a Windows host. It activates the project's virtual
    environment, points the app at local data folders and starts the Flask
    server in the foreground, so Ctrl+C stops it cleanly.

    For an unattended service, register this script with NSSM or Task Scheduler:

        nssm install FireWatchAI "powershell.exe" `
            "-NoProfile -ExecutionPolicy Bypass -File C:\path\to\deploy\run-windows.ps1"

    NSSM is preferred because it can restart the process and rotate output.

.PARAMETER Host
    Bind address. Defaults to 127.0.0.1; use 0.0.0.0 only behind a proxy.

.PARAMETER Port
    TCP port. Defaults to 5000.
#>
[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment not found at $VenvPython. Create it first: python -m venv .venv"
}

Set-Location $ProjectRoot

$env:HOST = $BindHost
$env:PORT = "$Port"
$env:DATABASE_PATH = Join-Path $ProjectRoot "fire_detection.db"
$env:EVIDENCE_DIR = Join-Path $ProjectRoot "snapshots"
$env:LOG_DIR = Join-Path $ProjectRoot "logs"

Write-Host "Starting FireWatch AI on http://${BindHost}:${Port}/" -ForegroundColor Cyan
& $VenvPython "app.py"
