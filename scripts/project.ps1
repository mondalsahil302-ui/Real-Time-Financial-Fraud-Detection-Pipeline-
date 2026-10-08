param(
    [ValidateSet('Start', 'Stop', 'Status', 'Validate', 'Demo')]
    [string]$Action = 'Status'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$stateRoot = Join-Path $env:LOCALAPPDATA 'RealTimeFinancialFraudDetectionPipeline'
$stateFile = Join-Path $stateRoot 'project-processes.json'
$logRoot = Join-Path $stateRoot 'logs'
$script:Failures = [System.Collections.Generic.List[string]]::new()

function Test-Port([int]$Port, [int]$TimeoutMs = 800) {
    foreach ($address in [System.Net.Dns]::GetHostAddresses('localhost')) {
        $client = New-Object System.Net.Sockets.TcpClient($address.AddressFamily)
        try {
            $connect = $client.BeginConnect($address, $Port, $null, $null)
            if ($connect.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
                $client.EndConnect($connect)
                return $true
            }
        } catch {
        } finally {
            $client.Dispose()
        }
    }
    return $false
}

function Test-Http([string]$Url, [int]$TimeoutSeconds = 4) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSeconds -UseBasicParsing
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Wait-Port([int]$Port, [int]$Seconds, [System.Diagnostics.Process]$Process = $null) {
    $until = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-Port $Port) { return $true }
        if ($Process -and $Process.HasExited) { return $false }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $until)
    return (Test-Port $Port)
}

function Wait-Http([string]$Url, [int]$Seconds, [System.Diagnostics.Process]$Process = $null) {
    $until = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-Http $Url 3) { return $true }
        if ($Process -and $Process.HasExited) { return $false }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $until)
    return (Test-Http $Url 3)
}

function Wait-DockerHealthy([string[]]$Containers, [int]$Seconds) {
    $until = (Get-Date).AddSeconds($Seconds)
    do {
        $pending = @()
        foreach ($container in $Containers) {
            $state = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $container 2>$null | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or $state -ne 'healthy') { $pending += "$container=$state" }
        }
        if ($pending.Count -eq 0) { return $true }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $until)
    Add-Failure "Docker healthchecks did not become healthy within $Seconds seconds: $($pending -join ', ')"
    return $false
}

function Get-State {
    if (Test-Path $stateFile) {
        try { return (Get-Content $stateFile -Raw | ConvertFrom-Json) } catch {
            throw "Cannot read managed-process state at $stateFile : $($_.Exception.Message)"
        }
    }
    return [pscustomobject]@{ processes = @() }
}

function Save-State {
    New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
    $script:State | ConvertTo-Json -Depth 5 | Set-Content -Path $stateFile -Encoding UTF8
}

function Get-ProjectProcesses([string]$Marker) {
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine.Contains($root) -and $_.CommandLine.Contains($Marker)
    }
}

function Start-ManagedProcess([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$Marker) {
    $existing = @(Get-ProjectProcesses $Marker)
    if ($existing.Count -gt 0) {
        Write-Host "$Name process already exists (PID $($existing[0].ProcessId))."
        return $null
    }
    New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
    $stdout = Join-Path $logRoot "$Name.out.log"
    $stderr = Join-Path $logRoot "$Name.err.log"
    $argLine = ($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + $_.Replace('"', '\"') + '"' } else { $_ }
    }) -join ' '
    $process = Start-Process -FilePath $Executable -ArgumentList $argLine -WorkingDirectory $root `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    $script:State.processes += [pscustomobject]@{
        name = $Name
        pid = $process.Id
        executable = $Executable
        marker = $Marker
    }
    Save-State
    Write-Host "Started $Name (PID $($process.Id)); logs: $logRoot"
    return $process
}

function Add-Failure([string]$Message) {
    $script:Failures.Add($Message)
    Write-Host "FAIL: $Message" -ForegroundColor Red
}

function Get-DotEnvValue([string]$Name, [string]$Default) {
    $line = Get-Content (Join-Path $root '.env') -ErrorAction SilentlyContinue |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))=(.*)$" } |
        Select-Object -First 1
    if ($line -and $line -match "^\s*$([regex]::Escape($Name))=(.*)$") { return $Matches[1].Trim() }
    return $Default
}

function Invoke-Check([string]$Name, [scriptblock]$Check) {
    try {
        $detail = & $Check
        if ($detail -is [string] -and $detail) { Write-Host "PASS: $Name ($detail)" -ForegroundColor Green }
        else { Write-Host "PASS: $Name" -ForegroundColor Green }
    } catch {
        Add-Failure "$Name - $($_.Exception.Message)"
    }
}

function Start-Project([switch]$DemoMode) {
    if ($DemoMode -and (Test-Port 8002)) {
        throw 'Demo mode requires Spark to be stopped so it can start with a fresh isolated checkpoint and latest offsets. Run scripts\stop_project.cmd, then retry.'
    }
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { throw 'Docker CLI is not installed.' }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not running or is inaccessible.' }
    & docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up -d failed.' }

    $script:State = Get-State
    if (-not (Wait-DockerHealthy @('fraud-kafka', 'fraud-cassandra', 'fraud-prometheus',
        'fraud-alertmanager', 'fraud-grafana') 180)) { exit 1 }
    foreach ($service in @(
        @{ name = 'Kafka'; port = 9092 }, @{ name = 'Cassandra'; port = 9042 },
        @{ name = 'Prometheus'; port = 9090 }, @{ name = 'Grafana'; port = 3000 },
        @{ name = 'Alertmanager'; port = 9093 }, @{ name = 'cAdvisor'; port = 8080 }
    )) {
        if (-not (Wait-Port $service.port 15)) {
            Add-Failure "$($service.name) did not open port $($service.port) within 15 seconds after Docker healthchecks passed."
        } else {
            Write-Host "$($service.name) is reachable on $($service.port)."
        }
    }

    if (-not (Test-Path $python)) { Add-Failure "Python environment not found: $python" }
    else {
        if (Test-Http 'http://localhost:8001/api/health') {
            Write-Host 'Control Center API is already healthy on port 8001.'
        } elseif (Test-Port 8001) {
            Add-Failure 'Port 8001 is occupied, but /api/health is not responding.'
        } else {
            $apiArgs = @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8001', '--app-dir', $root)
            $proc = Start-ManagedProcess 'backend' $python $apiArgs 'backend.app.main:app'
            if (-not (Wait-Http 'http://localhost:8001/api/health' 30 $proc)) { Add-Failure 'Control Center API did not become healthy on port 8001.' }
        }

        $consumer = @(Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and $_.CommandLine.Contains('rag.investigation.kafka_investigation_consumer')
        })
        if ($consumer.Count -gt 0) {
            Write-Host "Investigation consumer is already running (PID $($consumer[0].ProcessId))."
        } elseif (Test-Port 8000) {
            Add-Failure 'Port 8000 is occupied; refusing to launch a duplicate metrics/consumer process.'
        } else {
            $consumerArgs = @('-m', 'rag.investigation.kafka_investigation_consumer')
            $proc = Start-ManagedProcess 'investigation-consumer' $python $consumerArgs 'rag.investigation.kafka_investigation_consumer'
            if (-not (Wait-Http 'http://localhost:8000/metrics' 20 $proc)) { Add-Failure 'Investigation consumer metrics did not start on port 8000.' }
        }

        if (Test-Http 'http://localhost:8003/metrics') {
            Write-Host 'Transaction producer metrics are already active on port 8003.'
        } elseif (Test-Port 8003) {
            Write-Host 'Port 8003 is open.'
        } else {
            $producerArgs = @('-m', 'producer.metrics_server')
            $proc = Start-ManagedProcess 'transaction-producer' $python $producerArgs 'producer.metrics_server'
            if (-not (Wait-Http 'http://localhost:8003/metrics' 15 $proc)) {
                Add-Failure 'Transaction producer metrics did not start on port 8003.'
            }
        }

        if ((Test-Path (Join-Path $root 'models\isolation_forest_final.pkl')) -and (Test-Path (Join-Path $root 'models\xgboost_second_stage.json'))) {
            if (Test-Port 8002) {
                Write-Host 'Spark metrics port 8002 is already occupied.'
            } else {
                $sparkFile = Join-Path $root 'streaming\spark_streaming.py'
                $previousCheckpoint = $env:SPARK_CHECKPOINT_DIR
                $previousOffsets = $env:SPARK_STARTING_OFFSETS
                if ($DemoMode) {
                    $demoCheckpoint = Join-Path $env:TEMP ("fraud-pipeline-demo-" + [guid]::NewGuid().ToString('N'))
                    New-Item -ItemType Directory -Force -Path $demoCheckpoint | Out-Null
                    $env:SPARK_CHECKPOINT_DIR = $demoCheckpoint
                    $env:SPARK_STARTING_OFFSETS = 'latest'
                    Write-Host "Demo Spark checkpoint: $demoCheckpoint"
                }
                try {
                    $proc = Start-ManagedProcess 'spark-streaming' $python @($sparkFile) $sparkFile
                } finally {
                    if ($null -eq $previousCheckpoint) { Remove-Item Env:\SPARK_CHECKPOINT_DIR -ErrorAction SilentlyContinue }
                    else { $env:SPARK_CHECKPOINT_DIR = $previousCheckpoint }
                    if ($null -eq $previousOffsets) { Remove-Item Env:\SPARK_STARTING_OFFSETS -ErrorAction SilentlyContinue }
                    else { $env:SPARK_STARTING_OFFSETS = $previousOffsets }
                }
                if (-not (Wait-Http 'http://localhost:8002/metrics' 120 $proc)) {
                    $tail = Get-Content (Join-Path $logRoot 'spark-streaming.err.log') -Tail 12 -ErrorAction SilentlyContinue
                    Add-Failure "Spark did not expose metrics on port 8002. $($tail -join ' ')"
                }
            }
        } else {
            Add-Failure 'Spark model files are missing; refusing to start Spark.'
        }
    }

    if (Test-Http 'http://localhost:5173') {
        Write-Host 'Frontend is already responding on port 5173.'
    } elseif (Test-Port 5173) {
        Add-Failure 'Port 5173 is occupied, but the frontend is not responding.'
    } else {
        $node = Get-Command node.exe -ErrorAction SilentlyContinue
        $vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
        if (-not $node -or -not (Test-Path $vite)) { Add-Failure 'Node.js or installed frontend dependencies are missing.' }
        else {
            $args = @($vite, '--host', '127.0.0.1', '--port', '5173', '--strictPort')
            $proc = Start-ManagedProcess 'frontend' $node.Source $args $vite
            if (-not (Wait-Http 'http://localhost:5173' 20 $proc)) { Add-Failure 'Frontend did not become available on port 5173.' }
        }
    }

    if ($script:Failures.Count -gt 0) {
        Write-Host "Startup completed with $($script:Failures.Count) failure(s)."
        exit 1
    }
    Write-Host 'Startup requests completed. Run scripts\validate_project.cmd for real service checks.'
}

function Stop-Project {
    if (-not (Test-Path $stateFile)) {
        Write-Host 'No project-managed application processes are recorded; Docker services and data were left untouched.'
        return
    }
    $state = Get-State
    $all = @(Get-CimInstance Win32_Process)
    foreach ($record in @($state.processes)) {
        $rootProc = $all | Where-Object { $_.ProcessId -eq [int]$record.pid } | Select-Object -First 1
        if (-not $rootProc -or -not $rootProc.CommandLine.Contains([string]$record.marker) -or
            -not $rootProc.ExecutablePath.Equals([string]$record.executable, [StringComparison]::OrdinalIgnoreCase)) {
            Write-Host "Skipped $($record.name) PID $($record.pid); ownership could not be verified."
            continue
        }
        $tree = [System.Collections.Generic.List[int]]::new()
        function Add-ChildProcesses([int]$ParentId) {
            foreach ($child in $all | Where-Object { $_.ParentProcessId -eq $ParentId }) {
                Add-ChildProcesses ([int]$child.ProcessId)
                $tree.Add([int]$child.ProcessId)
            }
        }
        Add-ChildProcesses ([int]$record.pid)
        $tree.Add([int]$record.pid)
        foreach ($processId in $tree) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
        Write-Host "Stopped managed $($record.name) process tree (root PID $($record.pid))."
    }
    Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
    Write-Host 'Docker services and all persistent data were left untouched.'
}

function Show-Status {
    foreach ($port in @(5173, 8001, 8000, 8002, 8003, 9090, 3000, 9093, 8080, 9092, 9042)) {
        $label = if (Test-Port $port) { 'UP' } else { 'DOWN' }
        Write-Host ('{0,-5} {1}' -f $port, $label)
    }
    if (Get-Command docker.exe -ErrorAction SilentlyContinue) { & docker compose ps }
}

function Validate-Project {
    Invoke-Check 'Frontend' { if (-not (Test-Http 'http://localhost:5173')) { throw 'HTTP check failed.' }; 'HTTP 200' }
    foreach ($endpoint in @(
        'http://localhost:8001/api/health', 'http://localhost:8001/api/system/status',
        'http://localhost:8001/api/monitoring/overview', 'http://localhost:8001/docs'
    )) {
        $checkEndpoint = $endpoint
        $check = { if (-not (Test-Http $checkEndpoint 20)) { throw 'HTTP check failed.' }; 'HTTP 200' }.GetNewClosure()
        Invoke-Check $endpoint $check
    }
    Invoke-Check 'Application metrics :8000' { if (-not (Test-Http 'http://localhost:8000/metrics')) { throw 'Metrics endpoint unavailable.' }; 'HTTP 200' }
    Invoke-Check 'Control Center metrics :8001' { if (-not (Test-Http 'http://localhost:8001/metrics')) { throw 'Metrics endpoint unavailable.' }; 'HTTP 200' }
    Invoke-Check 'Spark metrics :8002' { if (-not (Test-Http 'http://localhost:8002/metrics')) { throw 'Spark metrics endpoint unavailable.' }; 'HTTP 200' }
    Invoke-Check 'Kafka' { if (-not (Test-Port 9092)) { throw 'TCP port 9092 unavailable.' }; 'TCP 9092' }
    Invoke-Check 'Cassandra' { if (-not (Test-Port 9042)) { throw 'TCP port 9042 unavailable.' }; 'TCP 9042' }
    Invoke-Check 'Prometheus' { if (-not (Test-Http 'http://localhost:9090/-/healthy')) { throw 'Health endpoint unavailable.' }; 'healthy' }
    Invoke-Check 'Grafana' { if (-not (Test-Http 'http://localhost:3000/api/health')) { throw 'Health endpoint unavailable.' }; 'healthy' }
    Invoke-Check 'Alertmanager' { if (-not (Test-Http 'http://localhost:9093/-/healthy')) { throw 'Health endpoint unavailable.' }; 'healthy' }
    Invoke-Check 'cAdvisor metrics' { if (-not (Test-Http 'http://localhost:8080/metrics')) { throw 'Metrics endpoint unavailable.' }; 'HTTP 200' }
    Invoke-Check 'Gemini provider' {
        $llm = Invoke-RestMethod 'http://localhost:8001/api/llm/status' -TimeoutSec 20
        if ($llm.provider -ne 'gemini' -or $llm.available -ne $true) { throw "Gemini status is $($llm.status)." }
        "$($llm.provider) $($llm.model) [$($llm.status)]"
    }

    $status = $null
    try { $status = Invoke-RestMethod 'http://localhost:8001/api/system/status' -TimeoutSec 20 } catch { Add-Failure "Service status API: $($_.Exception.Message)" }
    if ($status) {
        foreach ($service in @('kafka', 'spark', 'cassandra', 'chroma', 'gemini', 'prometheus', 'grafana', 'alertmanager', 'cadvisor')) {
            $item = $status.services.$service
            if ($item.available -ne $true) { Add-Failure "$service status is $($item.status)." }
            else { Write-Host "PASS: $service reports $($item.status)" -ForegroundColor Green }
        }
    }

    $promUrl = Get-DotEnvValue 'PROMETHEUS_URL' 'http://localhost:9090'
    try {
        $targets = Invoke-RestMethod "$promUrl/api/v1/targets" -TimeoutSec 8
        $expected = @{ 'fraud-pipeline-app' = '8000'; 'control-center-api' = '8001'; 'spark-streaming' = '8002'; 'transaction-producer' = '8003' }
        foreach ($job in $expected.Keys) {
            $target = $targets.data.activeTargets | Where-Object { $_.labels.job -eq $job } | Select-Object -First 1
            if (-not $target -or $target.labels.instance -notmatch (":$($expected[$job])$")) {
                Add-Failure "Prometheus job $job does not target port $($expected[$job])."
            } elseif ($job -ne 'transaction-producer' -and $target.health -ne 'up') {
                Add-Failure "Prometheus target $job is $($target.health)."
            } else {
                Write-Host "PASS: Prometheus $job => $($target.labels.instance) [$($target.health)]" -ForegroundColor Green
            }
        }
    } catch { Add-Failure "Prometheus targets API: $($_.Exception.Message)" }

    $grafanaUser = Get-DotEnvValue 'GRAFANA_ADMIN_USER' 'admin'
    $grafanaPassword = Get-DotEnvValue 'GRAFANA_ADMIN_PASSWORD' 'admin'
    $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${grafanaUser}:${grafanaPassword}"))
    $headers = @{ Authorization = "Basic $auth" }
    Invoke-Check 'Grafana Prometheus datasource' {
        $ds = Invoke-RestMethod 'http://localhost:3000/api/datasources/uid/prometheus' -Headers $headers -TimeoutSec 5
        if ($ds.type -ne 'prometheus') { throw 'Prometheus datasource is missing.' }
        $ds.name
    }
    Invoke-Check 'Grafana provisioned dashboards' {
        $dashboards = Invoke-RestMethod 'http://localhost:3000/api/search?type=dash-db' -Headers $headers -TimeoutSec 5
        if (@($dashboards).Count -eq 0) { throw 'No dashboards are provisioned.' }
        "$(@($dashboards).Count) dashboards"
    }
    Invoke-Check 'Grafana live Prometheus query' {
        $query = Invoke-RestMethod 'http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query?query=up' -Headers $headers -TimeoutSec 8
        if ($query.status -ne 'success' -or @($query.data.result).Count -eq 0) { throw 'Datasource returned no live query results.' }
        "$(@($query.data.result).Count) live series"
    }

    Invoke-Check 'Prometheus configuration' {
        & docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
        if ($LASTEXITCODE -ne 0) { throw 'promtool rejected prometheus.yml.' }
        'promtool valid'
    }

    if ($script:Failures.Count -gt 0) {
        Write-Host "Validation failed: $($script:Failures.Count) check(s)."
        exit 1
    }
    Write-Host 'All required project checks passed.' -ForegroundColor Green
}

function Invoke-DemoAIQuestion([string]$Question, [string]$TransactionId, [string]$ConversationId) {
    $body = @{
        question = $Question
        include_cassandra = $true
        include_fraud_knowledge = $true
        include_paysim_cases = $true
    }
    if ($TransactionId) { $body.transaction_id = $TransactionId }
    if ($ConversationId) { $body.conversation_id = $ConversationId }
    Invoke-RestMethod 'http://localhost:8001/api/llm/chat' -Method Post `
        -Headers @{ 'Idempotency-Key' = [guid]::NewGuid().ToString() } `
        -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 6) -TimeoutSec 75
}

function Run-Demo50 {
    $script:State = Get-State
    Start-Project -DemoMode
    Validate-Project

    $requiredServices = @('kafka', 'spark', 'cassandra', 'chroma', 'gemini', 'prometheus',
        'grafana', 'alertmanager', 'cadvisor')
    $system = Invoke-RestMethod 'http://localhost:8001/api/system/status' -TimeoutSec 30
    foreach ($name in $requiredServices) {
        if ($system.services.$name.available -ne $true) {
            throw "Demo prerequisite $name is $($system.services.$name.status)."
        }
    }

    $requestBody = @{ count = 50; delay = 0.1; source = 'frontend_simulator' } | ConvertTo-Json
    $batch = Invoke-RestMethod 'http://localhost:8001/api/batches' -Method Post `
        -Headers @{ 'Idempotency-Key' = [guid]::NewGuid().ToString() } `
        -ContentType 'application/json' -Body $requestBody -TimeoutSec 15
    Write-Host "Demo batch ID: $($batch.batch_id)"
    Write-Host 'Requested: 50; producer delay: 0.10 seconds per transaction.'

    $producerDeadline = (Get-Date).AddMinutes(5)
    do {
        Start-Sleep -Seconds 2
        $batch = Invoke-RestMethod "http://localhost:8001/api/batches/$($batch.batch_id)" -TimeoutSec 10
        Write-Host ("Producer: {0}/{1} generated, {2} Kafka acknowledged" -f
            $batch.generated_count, $batch.requested_count, $batch.sent_count)
        if ($batch.status -in @('COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED')) { break }
    } while ((Get-Date) -lt $producerDeadline)
    if ($batch.status -notin @('COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED')) {
        throw 'The 50-transaction producer batch did not finish within five minutes.'
    }
    if ($batch.generated_count -ne 50 -or $batch.sent_count -ne 50) {
        throw "Demo batch was incomplete: generated $($batch.generated_count), Kafka acknowledged $($batch.sent_count), requested 50."
    }

    $processingDeadline = (Get-Date).AddMinutes(4)
    do {
        Start-Sleep -Seconds 2
        $batch = Invoke-RestMethod "http://localhost:8001/api/batches/$($batch.batch_id)" -TimeoutSec 10
        if ($batch.processed -ge $batch.sent_count -and $batch.investigations_pending -eq 0) { break }
    } while ((Get-Date) -lt $processingDeadline)
    if ($batch.processed -lt $batch.sent_count) {
        Add-Failure "Spark processed $($batch.processed) of $($batch.sent_count) acknowledged transactions within four minutes."
    }
    if ($batch.investigations_pending -gt 0) {
        Add-Failure "$($batch.investigations_pending) investigations were still pending after the bounded processing wait."
    }

    Write-Host 'Waiting 15 seconds for Prometheus scrape and metric stabilization.'
    Start-Sleep -Seconds 15
    $batch = Invoke-RestMethod "http://localhost:8001/api/batches/$($batch.batch_id)" -TimeoutSec 10

    $elapsed = 'unavailable'
    if ($batch.started_at) {
        $ended = if ($batch.completed_at) { [DateTimeOffset]::Parse($batch.completed_at) } else { [DateTimeOffset]::UtcNow }
        $elapsed = '{0:N1} seconds' -f ($ended - [DateTimeOffset]::Parse($batch.started_at)).TotalSeconds
    }
    Write-Host ''
    Write-Host '50-TRANSACTION DEMO RESULTS'
    Write-Host "Batch ID: $($batch.batch_id)"
    Write-Host "Status: $($batch.status)"
    Write-Host "Requested: $($batch.requested_count)"
    Write-Host "Generated: $($batch.generated_count)"
    Write-Host "Kafka acknowledged: $($batch.sent_count)"
    Write-Host "Spark processed: $($batch.processed)"
    Write-Host "Fraud alerts: $($batch.fraud_alerts)"
    Write-Host "Low risk: $($batch.low_risk)"
    Write-Host "Investigations: $($batch.investigation_requests)"
    Write-Host "Successful investigations: $($batch.investigations_succeeded)"
    Write-Host "Partial investigations: $($batch.investigations_partial)"
    Write-Host "Failed investigations: $($batch.investigations_failed)"
    Write-Host "Elapsed: $elapsed"

    $general = $null
    try {
        $general = Invoke-DemoAIQuestion 'What are the main early warning signals for financial transaction fraud?' $null $null
        Write-Host "AI general: PASS (model=$($general.llm_model), evidence=$($general.retrieval_count))"
    } catch {
        Add-Failure "AI general question failed: $($_.Exception.Message)"
    }

    $batchTransactions = Invoke-RestMethod `
        "http://localhost:8001/api/batches/$($batch.batch_id)/transactions?page=1&page_size=100" -TimeoutSec 10
    $alert = $batchTransactions.items | Where-Object { $_.processing_status -eq 'FRAUD_ALERT' } | Select-Object -First 1
    if (-not $alert) {
        $alert = (Invoke-RestMethod 'http://localhost:8001/api/alerts?page=1&page_size=1' -TimeoutSec 10).items |
            Select-Object -First 1
    }
    if ($alert) {
        $conversationId = $null
        $transactionResults = [System.Collections.Generic.List[object]]::new()
        foreach ($question in @(
            'Why was this transaction flagged?',
            'What evidence is missing?',
            'Compare this transaction with similar historical PaySim cases.'
        )) {
            try {
                $answer = Invoke-DemoAIQuestion $question $alert.transaction_id $conversationId
                $conversationId = $answer.conversation_id
                $transactionResults.Add($answer)
                Write-Host ("AI transaction/follow-up: PASS (transaction={0}, model={1}, evidence={2})" -f
                    $alert.transaction_id, $answer.llm_model, $answer.retrieval_count)
            } catch {
                Add-Failure "AI question '$question' failed: $($_.Exception.Message)"
            }
        }
        $realEvidence = @($transactionResults | ForEach-Object { $_.evidence } |
            Where-Object { $_.source_type -in @('cassandra', 'synthetic_paysim_reference', 'fraud_knowledge') })
        if ($realEvidence.Count -gt 0) { Write-Host 'RAG transaction evidence: PASS (real cited retrieval sources returned).' }
        else { Add-Failure 'RAG transaction evidence was not returned by the live assistant.' }
    } else {
        Write-Host 'AI transaction-aware/follow-up: SKIPPED (no real alert exists in this batch or prior records; no alert was forced).'
    }

    Write-Host 'Waiting 15 seconds for Prometheus to observe RAG/LLM activity.'
    Start-Sleep -Seconds 15
    $targets = (Invoke-RestMethod 'http://localhost:9090/api/v1/targets' -TimeoutSec 10).data.activeTargets
    $upTargets = @($targets | Where-Object { $_.health -eq 'up' }).Count
    Write-Host ("Prometheus targets: {0} UP / {1} total" -f $upTargets, @($targets).Count)
    foreach ($target in $targets) {
        Write-Host ("  {0} => {1} [{2}]" -f $target.labels.job, $target.labels.instance, $target.health)
    }

    $grafanaUser = Get-DotEnvValue 'GRAFANA_ADMIN_USER' 'admin'
    $grafanaPassword = Get-DotEnvValue 'GRAFANA_ADMIN_PASSWORD' 'admin'
    $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${grafanaUser}:${grafanaPassword}"))
    $dashboards = Invoke-RestMethod 'http://localhost:3000/api/search?type=dash-db' `
        -Headers @{ Authorization = "Basic $auth" } -TimeoutSec 10
    Write-Host "Grafana dashboards: $(@($dashboards).Count)"
    foreach ($dashboard in $dashboards) { Write-Host "  $($dashboard.title)" }
    Write-Host ''
    Write-Host 'Frontend: http://localhost:5173'
    Write-Host 'API: http://localhost:8001/docs'
    Write-Host 'Prometheus: http://localhost:9090'
    Write-Host 'Grafana: http://localhost:3000'
    Write-Host 'Alertmanager: http://localhost:9093'
    Write-Host 'cAdvisor: http://localhost:8080'

    if ($script:Failures.Count -gt 0) {
        Write-Host "Demo finished with $($script:Failures.Count) validation failure(s)." -ForegroundColor Red
        exit 1
    }
    Write-Host '50-transaction demo passed.' -ForegroundColor Green
}

switch ($Action) {
    'Start' {
        $script:State = Get-State
        Start-Project
    }
    'Stop' { Stop-Project }
    'Status' { Show-Status }
    'Validate' {
        $script:State = Get-State
        Validate-Project
    }
    'Demo' { Run-Demo50 }
}
