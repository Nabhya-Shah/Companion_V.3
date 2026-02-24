param(
    [switch]$SkipInstall,
    [switch]$SkipRequirements
)

$ErrorActionPreference = "Stop"

function Test-Python311 {
    try {
        $out = & py -3.11 --version 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

Write-Host "=== Companion AI Python 3.11 Setup ===" -ForegroundColor Cyan

if (-not $SkipInstall) {
    if (-not (Test-Python311)) {
        Write-Host "Python 3.11 not found. Installing with winget..." -ForegroundColor Yellow
        & winget install --id Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements

        if (-not (Test-Python311)) {
            Write-Host "Python 3.11 install may require a new terminal session." -ForegroundColor Yellow
            Write-Host "Please reopen PowerShell and rerun this script." -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Host "Python 3.11 already installed." -ForegroundColor Green
    }
}

if (Test-Path .venv) {
    Write-Host "Removing existing .venv..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force .venv
}

Write-Host "Creating .venv with Python 3.11..." -ForegroundColor Cyan
& py -3.11 -m venv .venv

$python = ".\.venv\Scripts\python.exe"

Write-Host "Upgrading pip..." -ForegroundColor Cyan
& $python -m pip install --upgrade pip

if (-not $SkipRequirements) {
    Write-Host "Installing requirements.txt..." -ForegroundColor Cyan
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Full requirements install failed. Installing minimal Phase 1 set..." -ForegroundColor Yellow
        & $python -m pip install flask python-dotenv groq requests PyYAML mss pillow pytest
    }
}

Write-Host "" 
Write-Host "Setup complete." -ForegroundColor Green
& $python --version
Write-Host "Run app: .venv\\Scripts\\python.exe run_companion.py" -ForegroundColor Green
