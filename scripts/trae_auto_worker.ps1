param(
    [string]$SwarmBaseUrl = "http://127.0.0.1:8000",
    [int]$PollSeconds = 5,
    [string]$StatePath = "D:\SWARM.AI\.trae\auto_worker_state.json"
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;

public class Win32Window {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

$ErrorActionPreference = "Stop"
$ShowNormal = 5

function Read-WorkerState {
    if (-not (Test-Path -LiteralPath $StatePath)) {
        return @{ triggered_run_ids = @(); triggered_run_keys = @() }
    }

    try {
        $raw = Get-Content -LiteralPath $StatePath -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return @{ triggered_run_ids = @(); triggered_run_keys = @() }
        }
        $parsed = $raw | ConvertFrom-Json
        return @{
            triggered_run_ids = @($parsed.triggered_run_ids)
            triggered_run_keys = @($parsed.triggered_run_keys)
        }
    } catch {
        return @{ triggered_run_ids = @(); triggered_run_keys = @() }
    }
}

function Write-WorkerState($state) {
    $parent = Split-Path -Parent $StatePath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StatePath
}

function Get-LatestWaitingRun {
    $response = Invoke-RestMethod -Uri "$SwarmBaseUrl/runs" -Method Get
    $waiting = @($response.runs | Where-Object {
        $_.agent_statuses.builder -eq "waiting_for_trae" -and $_.done -eq $false
    })

    if ($waiting.Count -eq 0) {
        return $null
    }

    return $waiting | Sort-Object updated_at -Descending | Select-Object -First 1
}

function Get-TraeWindow {
    $candidates = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -match "TRAE|Trae" -and $_.MainWindowHandle -ne 0
    })

    if ($candidates.Count -eq 0) {
        return $null
    }

    return $candidates | Sort-Object MainWindowTitle -Descending | Select-Object -First 1
}

function New-TraeBuildPrompt($runId) {
@"
Use the swarm_ai MCP server.

Call get_project_context for run_id "$runId".
Then try to call get_quality_report for run_id "$runId".
- If a quality report exists, this is a revision attempt. Also call get_submitted_code_files for run_id "$runId", fix the existing project using the revision_instructions, and resubmit the full improved file set.
- If no quality report exists, build the project from scratch using the builder_prompt.

The final submitted app must score at least 90/100 in SWARM.AI's quality gate.

Requirements:
- Generate every source/config file required to run locally.
- Do not include node_modules, dist, build artifacts, cache files, or temporary files.
- If using TypeScript, include all required @types packages.
- Validate the generated project as much as possible with install, type-check, test, and build commands.
- Fix any errors you find before submitting.
- Add strong local-language support: language files, locale switching, formatted dates/numbers/currency, and translated demo copy.
- Add realistic seed data and a README demo flow so the first run looks complete.

When finished, call submit_code_files on the swarm_ai MCP server with:
- run_id: "$runId"
- files: a JSON object mapping each relative filepath to its full file content.

Do not stop after showing code. You must call submit_code_files.
"@
}

function Invoke-TraeBuild($runId) {
    $window = Get-TraeWindow
    if ($null -eq $window) {
        throw "Trae window not found. Open Trae SOLO and focus the chat once."
    }

    $prompt = New-TraeBuildPrompt -runId $runId
    Set-Clipboard -Value $prompt

    [Win32Window]::ShowWindow($window.MainWindowHandle, $ShowNormal) | Out-Null
    Start-Sleep -Milliseconds 500
    [Win32Window]::SetForegroundWindow($window.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 800

    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
}

Write-Host "SWARM.AI Trae auto worker started."
Write-Host "Backend: $SwarmBaseUrl"
Write-Host "Poll interval: $PollSeconds seconds"
Write-Host "Keep Trae open with the chat input focused once. Press Ctrl+C to stop."

$state = Read-WorkerState

while ($true) {
    try {
        $run = Get-LatestWaitingRun
        if ($null -ne $run) {
            $runId = [string]$run.run_id
            $updatedAt = [string]$run.updated_at
            if ([string]::IsNullOrWhiteSpace($updatedAt)) {
                $updatedAt = "no-updated-at"
            }
            $runKey = "$runId|$updatedAt"
            if ($state.triggered_run_keys -notcontains $runKey) {
                Write-Host "Triggering Trae build/revision for run $runId"
                Invoke-TraeBuild -runId $runId
                if ($state.triggered_run_ids -notcontains $runId) {
                    $state.triggered_run_ids += $runId
                }
                $state.triggered_run_keys += $runKey
                Write-WorkerState $state
            }
        }
    } catch {
        Write-Host "Auto worker error: $($_.Exception.Message)"
    }

    Start-Sleep -Seconds $PollSeconds
}
