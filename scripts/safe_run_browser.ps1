# PowerShell Safety Launcher for Browser Demo
# Sets console color to RED to indicate "Live Agent" status.
# Closing this window terminates the child python process.

$host.UI.RawUI.BackgroundColor = "DarkRed"
$host.UI.RawUI.ForegroundColor = "White"
Clear-Host

Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host "   COMPANION AI - BROWSER CONTROL TEST   " -ForegroundColor White -BackgroundColor Red
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "This window is running the Browser Automation Test."
Write-Host "The agent has control of your Mouse and Keyboard."
Write-Host ""
Write-Host "TASK: Open Chrome -> Wikipedia -> Search 'cheeseburger'"
Write-Host ""
Write-Host "SAFETY:" -ForegroundColor Cyan
Write-Host "1. Keep this window visible."
Write-Host "2. To STOP immediately, CLICK 'X' to close this window."
Write-Host ""
Write-Host "Starting Browser Demo..."
Write-Host ""

# Run the browser demo script
python tools/demo_browser.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Demo exited with error code $LASTEXITCODE" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Session Complete. Press Enter to close."
Read-Host
