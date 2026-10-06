$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host 'Stop producer, investigation consumer, and Spark terminals with Ctrl+C first.'
docker compose stop
if ($LASTEXITCODE -ne 0) { throw 'docker compose stop failed; inspect Docker Desktop.' }
Write-Host 'Containers stopped. Persistent Kafka, Cassandra, Prometheus, Grafana, and Alertmanager data volumes were preserved.'
