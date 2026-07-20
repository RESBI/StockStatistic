$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $root ".venv-v31\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Run scripts/install_v31.ps1 first."
}

& $pythonExe -m pytest (Join-Path $root "tests_v31") -q
