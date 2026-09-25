$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$oauthName = 'client_secret_231644001146-h9a4bl1hsdg6sso36d7qh46p6jlog9cm.apps.googleusercontent.com.json'
$oauthCandidates = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) $oauthName),
    (Join-Path ([Environment]::GetFolderPath('UserProfile')) "Downloads/$oauthName")
)
$oauthFile = $oauthCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not (Test-Path -LiteralPath $oauthFile)) {
    throw 'OAuth JSON was not found on Desktop or Downloads. Run setup_oauth.py with your JSON and --enable-audio-cleanup.'
}
Write-Host 'Step 1: Sign in to Google Cloud in the browser.'
& gcloud auth login mememori8888@mambyo.net --force
if ($LASTEXITCODE -ne 0) { throw 'Google Cloud login failed.' }
Write-Host 'Step 2: Deploy the tested audio cleanup code.'
& (Join-Path $PSScriptRoot 'deploy.ps1') -Stage Deploy
Write-Host 'Step 3: Authorize Drive changes in the browser. Processed audio will go to Trash.'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'setup_oauth.py') $oauthFile --enable-audio-cleanup
if ($LASTEXITCODE -ne 0) { throw 'Drive authorization failed; cleanup was not enabled.' }
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'app.py') --check --local-gcloud
if ($LASTEXITCODE -ne 0) { throw 'Connection check failed.' }
Write-Host 'Audio cleanup is enabled for the daily scheduled job. Tell Codex: done.'
