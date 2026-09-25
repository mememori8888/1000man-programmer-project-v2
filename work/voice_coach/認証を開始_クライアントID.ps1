$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$clientId = '231644001146-9re1sum9h53tkvt917edngssomrkib8a.apps.googleusercontent.com'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'setup_oauth.py') --client-id $clientId
if ($LASTEXITCODE -ne 0) { throw 'OAuth setup failed. Check the error shown above.' }
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'app.py') --check --local-gcloud
if ($LASTEXITCODE -ne 0) { throw 'Connection check failed.' }
Write-Host 'OAuth and connection check completed. Tell Codex: done.'
