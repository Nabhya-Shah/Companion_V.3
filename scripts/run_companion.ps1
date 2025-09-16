<#!
PowerShell helper script to run Companion AI with environment loading.
Usage examples:
  .\scripts\run_companion.ps1 web
  .\scripts\run_companion.ps1 warm
  .\scripts\run_companion.ps1 gui
  .\scripts\run_companion.ps1 chat
  .\scripts\run_companion.ps1 tests
#>
param(
    [string]$Mode = 'web'
)

$ErrorActionPreference = 'Stop'

# Detect project root (script directory parent)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir '..')
Set-Location $Root

# Load .env if present (simple parser: KEY=VALUE lines, skip comments)
$EnvFile = Join-Path $Root '.env'
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^[A-Za-z_][A-Za-z0-9_]*=') {
            $k,$v = $_ -split '=',2
            if (-not [string]::IsNullOrWhiteSpace($k)) {
                $trimV = $v.Trim().Trim('"')
                # Set only if not already set in the process
                if (-not [System.String]::IsNullOrWhiteSpace($trimV)) {
                    Set-Item -Path Env:$k -Value $trimV -ErrorAction SilentlyContinue
                }
            }
        }
    }
    Write-Host "Loaded environment variables from .env" -ForegroundColor Cyan
} else {
    Write-Host ".env not found — using existing environment only" -ForegroundColor Yellow
}

# Ensure venv activation if folder exists
$Venv = Join-Path $Root 'venv'
if (Test-Path (Join-Path $Venv 'Scripts/Activate.ps1')) {
    . (Join-Path $Venv 'Scripts/Activate.ps1')
    Write-Host "Virtual environment activated" -ForegroundColor Green
}

function Invoke-CompanionCmd {
    param([string]$Cmd)
    Write-Host "> $cmd" -ForegroundColor DarkGray
    Invoke-Expression $Cmd
}

switch ($Mode.ToLower()) {
    'web' { Invoke-CompanionCmd 'python run_companion.py --web' }
    'warm' { Invoke-CompanionCmd 'python run_web_with_warmup.py' }
    'gui' { Invoke-CompanionCmd 'python copilot_gui.py' }
    'chat' { Invoke-CompanionCmd 'python chat_cli.py' }
    'tests' { Invoke-CompanionCmd 'pytest -q' }
    default { Write-Host "Unknown mode '$Mode'. Use web|warm|gui|chat|tests" -ForegroundColor Red; exit 1 }
}
