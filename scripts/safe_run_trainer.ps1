# PowerShell Safety Launcher for Companion AI Trainer
# Sets console color to RED to indicate "Live Agent" status.
# Closing this window terminates the child python process.

$host.UI.RawUI.BackgroundColor = "DarkRed"
$host.UI.RawUI.ForegroundColor = "White"
Clear-Host

Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host "   🚨 COMPANION AI - COMPUTER CONTROL AGENT ACTIVE 🚨   " -ForegroundColor White -BackgroundColor Red
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "This window is running the Autonomous Training Loop."
Write-Host "The agent has control of your Mouse and Keyboard."
Write-Host ""
Write-Host "SAFETY:" -ForegroundColor Cyan
Write-Host "1. Keep this window visible."
Write-Host "2. To STOP immediately, CLICK 'X' to close this window."
Write-Host ""
Write-Host "Starting Trainer..."
Write-Host ""

# Run the trainer script
python companion_ai/trainer.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Trainer exited with error code $LASTEXITCODE" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Session Complete. Press Enter to close."
Read-Host
