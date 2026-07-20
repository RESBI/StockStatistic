param(
    [string]$Python = "py -3.12"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv-v31"

if (-not (Test-Path $venv)) {
    Invoke-Expression "$Python -m venv `"$venv`""
}

$pythonExe = Join-Path $venv "Scripts\python.exe"
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r (Join-Path $root "requirements-v31.txt")

$packages = @(
    "packages/contracts",
    "packages/kernel",
    "services/storage",
    "services/dispatcher",
    "packages/sdk",
    "services/worker",
    "packages/local"
)

foreach ($package in $packages) {
    & $pythonExe -m pip install -e (Join-Path $root $package)
}

Write-Host "V3.1 environment ready: $pythonExe"
