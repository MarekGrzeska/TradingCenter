<#
.SYNOPSIS
    Convenience wrapper for local work: starts capital-gateway, waits for it,
    then starts the terminal against it.

.DESCRIPTION
    The gateway comes up first and the terminal only once it answers, so the
    terminal never spends its first seconds hammering a proxy with nothing
    behind it. The terminal has no offline mode — the gateway is its only
    source of market data.

    Neither module depends on this script — each still starts on its own with
    its own documented command (see each module's README).

.PARAMETER GatewayTimeoutSeconds
    How long to wait for the gateway to answer /capabilities. `uv run` may
    resolve dependencies on a cold start, which is the slow part.

.EXAMPLE
    ./scripts/dev.ps1
#>

param(
    [int]$GatewayTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "modules\capital-gateway"
$terminalDir = Join-Path $repoRoot "modules\terminal"

$gatewayPort = 8010
$terminalPort = 5173
# 127.0.0.1, not "localhost": uvicorn binds IPv4 loopback, while "localhost" can
# resolve to ::1 first on Windows.
$gatewayUrl = "http://127.0.0.1:$gatewayPort"
$terminalUrl = "http://localhost:$terminalPort"

Write-Host "Checking prerequisites..." -ForegroundColor Cyan

$missing = @()
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    $missing += "pnpm is not on PATH (needed to run the terminal) - https://pnpm.io/installation"
}
if (-not (Test-Path (Join-Path $terminalDir "node_modules"))) {
    $missing += "$terminalDir\node_modules is missing - run 'pnpm install' in modules\terminal"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $missing += "uv is not on PATH (needed to run capital-gateway) - https://docs.astral.sh/uv/"
}
$gatewayEnv = Join-Path $gatewayDir ".env"
if (-not (Test-Path $gatewayEnv)) {
    $missing += "$gatewayEnv is missing - copy .env.example and fill in demo credentials"
}

# A port already taken is the most common reason a previous run "hangs": the new
# process cannot bind, and the wait below would sit there watching someone
# else's service. Name it up front instead.
function Get-PortOwner {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $conn) { return $null }
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return "pid $($conn.OwningProcess)" }
    return "$($proc.ProcessName) (pid $($proc.Id))"
}

foreach ($port in @($gatewayPort, $terminalPort)) {
    $owner = Get-PortOwner -Port $port
    if ($null -ne $owner) {
        $missing += "port $port is already in use by $owner - stop it first, or it is a leftover run"
    }
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

    Write-Host "Waiting for it to answer $gatewayUrl/capabilities" -NoNewline -ForegroundColor Cyan
    Write-Host " (uv may resolve dependencies first)..." -ForegroundColor DarkGray

    $healthy = $false
    $deadline = (Get-Date).AddSeconds($GatewayTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        # Show the gateway's own output while waiting - a silent script for
        # 30+ seconds is indistinguishable from a hung one.
        Write-Prefixed -Prefix "gateway " -Color Blue -Lines (Receive-Job $gatewayJob)

        if ($gatewayJob.State -in @("Failed", "Completed", "Stopped")) {
            Write-Host "capital-gateway exited before answering." -ForegroundColor Red
            Write-Prefixed -Prefix "gateway " -Color Yellow -Lines (Receive-Job $gatewayJob)
            exit 1
        }

        try {
            $response = Invoke-WebRequest -Uri "$gatewayUrl/capabilities" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch {
            # Not up yet. Keep waiting until the deadline.
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $healthy) {
        Write-Host "capital-gateway did not answer within $GatewayTimeoutSeconds s." -ForegroundColor Red
        Write-Prefixed -Prefix "gateway " -Color Yellow -Lines (Receive-Job $gatewayJob)
        Write-Host "Raise the limit with -GatewayTimeoutSeconds if it was still starting." -ForegroundColor DarkGray
        exit 1
    }

    Write-Host "capital-gateway is answering." -ForegroundColor Green

    # Started only now: bringing the terminal up first would have it retrying
    # against a gateway that is not listening yet, filling the log with proxy
    # errors that mean nothing.
    Write-Host "Starting terminal on port $terminalPort..." -ForegroundColor Cyan
    $terminalJob = Start-Job -Name "terminal" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        pnpm exec vite --port $port --strictPort 2>&1
    } -ArgumentList $terminalDir, $terminalPort

    Write-Host ""
    Write-Host "Ready:" -ForegroundColor Green
    Write-Host "  Terminal          $terminalUrl"
    Write-Host "  Gateway Swagger   $gatewayUrl/docs"
    Write-Host ""
    Write-Host "Ctrl+C to stop." -ForegroundColor DarkGray
    Write-Host ""

    while ($true) {
        Write-Prefixed -Prefix "gateway " -Color Blue -Lines (Receive-Job $gatewayJob)
        if ($gatewayJob.State -in @("Failed", "Completed", "Stopped")) {
            Write-Host "capital-gateway exited unexpectedly." -ForegroundColor Red
            break
        }

        Write-Prefixed -Prefix "terminal" -Color Magenta -Lines (Receive-Job $terminalJob)
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
    # port - so processes bound to the ports we used are swept explicitly too.
    foreach ($port in @($gatewayPort, $terminalPort)) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    }
}
