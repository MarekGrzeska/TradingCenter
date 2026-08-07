<#
.SYNOPSIS
    Convenience wrapper: run capital-gateway and the terminal together for local
    testing. Neither module depends on this — each still starts on its own with
    its own documented command (see each module's README).
#>

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "modules\capital-gateway"
$terminalDir = Join-Path $repoRoot "modules\terminal"

$gatewayPort = 8010
$terminalPort = 5173
$gatewayUrl = "http://localhost:$gatewayPort"
$terminalUrl = "http://localhost:$terminalPort"

Write-Host "Checking prerequisites..." -ForegroundColor Cyan

$missing = @()
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $missing += "uv is not on PATH (needed to run capital-gateway) - https://docs.astral.sh/uv/"
}
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    $missing += "pnpm is not on PATH (needed to run the terminal) - https://pnpm.io/installation"
}
$gatewayEnv = Join-Path $gatewayDir ".env"
if (-not (Test-Path $gatewayEnv)) {
    $missing += "$gatewayEnv is missing - copy .env.example and fill in demo credentials"
}

if ($missing.Count -gt 0) {
    Write-Host "Cannot start:" -ForegroundColor Red
    foreach ($m in $missing) { Write-Host "  - $m" -ForegroundColor Red }
    exit 1
}

$gatewayJob = $null
$terminalJob = $null

function Write-Prefixed {
    param([string]$Prefix, [string]$Color, [object[]]$Lines)
    foreach ($line in $Lines) {
        if ($null -ne $line -and "$line" -ne "") {
            Write-Host "[$Prefix] " -ForegroundColor $Color -NoNewline
            Write-Host "$line"
        }
    }
}

try {
    Write-Host "Starting capital-gateway on port $gatewayPort..." -ForegroundColor Cyan
    $gatewayJob = Start-Job -Name "gateway" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        uv run uvicorn capital_gateway.app:app --port $port 2>&1
    } -ArgumentList $gatewayDir, $gatewayPort

    Write-Host "Starting terminal on port $terminalPort..." -ForegroundColor Cyan
    $terminalJob = Start-Job -Name "terminal" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        pnpm exec vite --port $port --strictPort 2>&1
    } -ArgumentList $terminalDir, $terminalPort

    Write-Host "Waiting for capital-gateway to answer /capabilities..." -ForegroundColor Cyan
    $healthy = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $response = Invoke-WebRequest -Uri "$gatewayUrl/capabilities" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch {
            if ($gatewayJob.State -eq "Failed") { break }
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $healthy) {
        Write-Host "capital-gateway did not answer in time. Its output so far:" -ForegroundColor Red
        Write-Prefixed -Prefix "gateway" -Color Yellow -Lines (Receive-Job $gatewayJob)
        exit 1
    }

    Write-Host ""
    Write-Host "Ready:" -ForegroundColor Green
    Write-Host "  Terminal          $terminalUrl"
    Write-Host "  Gateway Swagger   $gatewayUrl/docs"
    Write-Host ""
    Write-Host "Ctrl+C to stop both." -ForegroundColor DarkGray
    Write-Host ""

    while ($true) {
        Write-Prefixed -Prefix "gateway " -Color Blue -Lines (Receive-Job $gatewayJob)
        Write-Prefixed -Prefix "terminal" -Color Magenta -Lines (Receive-Job $terminalJob)

        if ($gatewayJob.State -in @("Failed", "Completed", "Stopped")) {
            Write-Host "capital-gateway exited unexpectedly." -ForegroundColor Red
            break
        }
        if ($terminalJob.State -in @("Failed", "Completed", "Stopped")) {
            Write-Host "terminal exited unexpectedly." -ForegroundColor Red
            break
        }
        Start-Sleep -Milliseconds 300
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping..." -ForegroundColor Cyan
    foreach ($job in @($gatewayJob, $terminalJob)) {
        if ($null -ne $job) {
            Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
            Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
        }
    }
    # Start-Job's child process tree (uv -> uvicorn, pnpm -> vite) can outlive the
    # job object itself, which is what actually leaves a process squatting on the
    # port - so processes bound to our two ports are swept explicitly too.
    foreach ($port in @($gatewayPort, $terminalPort)) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    }
}
