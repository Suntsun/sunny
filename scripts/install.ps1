# Sunny Installation Script
# Run with: powershell -ExecutionPolicy Bypass -File scripts/install.ps1

Write-Host "Installing Sunny dependencies..." -ForegroundColor Cyan

# Check if venv exists
if (-Not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate venv and install dependencies
& ".venv\Scripts\Activate.ps1"
pip install --upgrade pip
pip install typer rich pydantic sqlite-utils ollama pyautogui pywinauto pillow pytesseract mss playwright python-dotenv

# Install Playwright browsers
Write-Host "Installing Playwright browsers..." -ForegroundColor Yellow
playwright install chromium

# Install Sunny in editable mode
Write-Host "Installing Sunny in editable mode..." -ForegroundColor Yellow
pip install -e .

Write-Host "`nInstallation complete!" -ForegroundColor Green
Write-Host "Run 'sunny --help' to get started." -ForegroundColor Cyan