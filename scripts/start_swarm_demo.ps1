param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$WithTraeWorker
)

$ErrorActionPreference = "Stop"

$Root = "D:\SWARM.AI"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"

function Test-HttpOk($url) {
    try {
        $request = [System.Net.WebRequest]::Create($url)
        $request.Method = "GET"
        $request.Timeout = 3000
        $response = $request.GetResponse()
        $statusCode = [int]$response.StatusCode
        $response.Close()
        return $statusCode -ge 200 -and $statusCode -lt 500
    } catch {
        return $false
    }
}

function Start-Backend {
    if (Test-HttpOk "$BackendUrl/health") {
        Write-Host "Backend already running at $BackendUrl"
        return
    }

    Write-Host "Starting SWARM backend at $BackendUrl ..."
    Start-Process `
        -FilePath $Python `
        -ArgumentList "-m uvicorn backend.main:app --host 127.0.0.1 --port $BackendPort" `
        -WorkingDirectory $Root `
        -WindowStyle Hidden | Out-Null

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-HttpOk "$BackendUrl/health") {
            Write-Host "Backend ready."
            return
        }
    }

    throw "Backend did not become ready at $BackendUrl/health"
}

function Start-Frontend {
    if (Test-HttpOk $FrontendUrl) {
        Write-Host "Frontend already running at $FrontendUrl"
        return
    }

    Write-Host "Starting SWARM frontend at $FrontendUrl ..."
    $env:VITE_API_BASE_URL = $BackendUrl
    Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort" `
        -WorkingDirectory (Join-Path $Root "frontend") `
        -WindowStyle Hidden | Out-Null

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-HttpOk $FrontendUrl) {
            Write-Host "Frontend ready."
            return
        }
    }

    throw "Frontend did not become ready at $FrontendUrl"
}

Start-Backend
Start-Frontend

Write-Host ""
Write-Host "SWARM.AI is ready."
Write-Host "Frontend: $FrontendUrl"
Write-Host "Backend:  $BackendUrl"
Write-Host ""
Write-Host "Manual flow:"
Write-Host "1. Type an idea in the SWARM UI and click Generate MVP."
Write-Host "2. Analyst and Architect create the product blueprint."
Write-Host "3. SWARM Builder generates the app internally."
Write-Host "4. Use Preview, Validate, and Quality Gate from the UI."

if ($WithTraeWorker) {
    Write-Host ""
    Write-Host "Starting optional legacy Trae auto-worker. Focus Trae chat input once before any legacy Builder handoff."
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Root "scripts\trae_auto_worker.ps1"), "-SwarmBaseUrl", $BackendUrl `
        -WorkingDirectory $Root | Out-Null
}
