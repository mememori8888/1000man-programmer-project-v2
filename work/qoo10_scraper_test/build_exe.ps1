$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

python -m pip install -r requirements.txt
python -m playwright install chromium
python -m PyInstaller --noconfirm --clean --onefile --name Qoo10ValidationScraper `
  --collect-all playwright qoo10_scraper.py

Write-Host "Built: $projectDir\dist\Qoo10ValidationScraper.exe"
