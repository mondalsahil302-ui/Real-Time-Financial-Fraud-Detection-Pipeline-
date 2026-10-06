$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Wait-Tcp($HostName, $Port, $Label, $TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-NetConnection -ComputerName $HostName -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue) {
            Write-Host "$Label is reachable"
            return
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "$Label did not become reachable at ${HostName}:$Port"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI was not found. Install/start Docker Desktop, then retry.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not reachable. Start Docker Desktop, then retry.' }
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed; inspect Docker output.' }

Wait-Tcp localhost 9092 'Kafka'
Wait-Tcp localhost 9042 'Cassandra' 240
Wait-Tcp localhost 9090 'Prometheus'
Wait-Tcp localhost 3000 'Grafana'
Wait-Tcp localhost 9093 'Alertmanager'

if ($env:GEMINI_API_KEY) {
    Write-Host "GEMINI_API_KEY is configured"
} else {
    Write-Host "Notice: GEMINI_API_KEY is not set. Gemini LLM investigation requires an API key."
}

Write-Host ''
Write-Host 'Infrastructure is up. In separate activated .venv terminals, run:'
Write-Host '  python .\streaming\spark_streaming.py'
Write-Host '  python -m rag.investigation.kafka_investigation_consumer'
Write-Host '  python .\producer\producer.py --max-transactions 1000 --delay 0.05'
Write-Host '  python .\tools\health_check.py'
