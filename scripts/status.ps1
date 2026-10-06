$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
docker compose ps
if ($LASTEXITCODE -ne 0) { Write-Warning 'Docker Compose status unavailable; check Docker Desktop.' }
python .\tools\health_check.py
exit $LASTEXITCODE
