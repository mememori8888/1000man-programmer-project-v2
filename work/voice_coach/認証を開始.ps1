$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Add-Type -AssemblyName System.Windows.Forms
$picker = New-Object System.Windows.Forms.OpenFileDialog
$picker.Title = 'Select the Desktop OAuth client JSON downloaded from GCP'
$picker.Filter = 'JSON files (*.json)|*.json'
if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit }
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'setup_oauth.py') $picker.FileName
if ($LASTEXITCODE -ne 0) { throw 'OAuth setup failed. Check the error shown above.' }
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'app.py') --check --local-gcloud
if ($LASTEXITCODE -ne 0) { throw 'Connection check failed.' }
Write-Host 'OAuth and connection check completed. Tell Codex: done.'
