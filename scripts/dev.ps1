<#
.SYNOPSIS
    Convenience wrapper for local work. Starts the terminal on its own by
    default; add -WithGateway to bring capital-gateway up alongside it.

.DESCRIPTION
    The terminal's default data source is the offline mock, so it is fully
    usable with no gateway, no credentials and no network. Only switching the
    source to "gateway" in the top bar needs one running.

    Neither module depends on this script — each still starts on its own with
    its own documented command (see each module's README).

.PARAMETER WithGateway
    Also start capital-gateway on port 8010 and wait for it to answer before
    reporting ready. Requires uv and modules/capital-gateway/.env.

.EXAMPLE
    ./scripts/dev.ps1
    Terminal only, on the mock source.

.EXAMPLE
    ./scripts/dev.ps1 -WithGateway
    Terminal plus capital-gateway, for working against live demo data.
#>

param(
    [switch]$WithGateway
)

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
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    $missing += "pnpm is not on PATH (needed to run the terminal) - https://pnpm.io/installation"
}
if (-not (Test-Path (Join-Path $terminalDir "node_modules"))) {
    $missing += "$terminalDir\node_modules is missing - run 'pnpm install' in modules\terminal"
}
# Only the gateway's requirements are conditional: without -WithGateway they are
# none of this script's business.
if ($WithGateway) {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        $missing += "uv is not on PATH (needed to run capital-gateway) - https://docs.astral.sh/uv/"
    }
    $gatewayEnv = Join-Path $gatewayDir ".env"
    if (-not (Test-Path $gatewayEnv)) {
        $missing += "$gatewayEnv is missing - copy .env.example and fill in demo credentials"
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
    if ($WithGateway) {
        Write-Host "Starting capital-gateway on port $gatewayPort..." -ForegroundColor Cyan
        $gatewayJob = Start-Job -Name "gateway" -ScriptBlock {
            param($dir, $port)
            Set-Location $dir
            uv run uvicorn capital_gateway.app:app --port $port 2>&1
        } -ArgumentList $gatewayDir, $gatewayPort
    }

    Write-Host "Starting terminal on port $terminalPort..." -ForegroundColor Cyan
    $terminalJob = Start-Job -Name "terminal" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        pnpm exec vite --port $port --strictPort 2>&1
    } -ArgumentList $terminalDir, $terminalPort

    if ($WithGateway) {
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
    }

    Write-Host ""
    Write-Host "Ready:" -ForegroundColor Green
    Write-Host "  Terminal          $terminalUrl"
    if ($WithGateway) {
        Write-Host "  Gateway Swagger   $gatewayUrl/docs"
        Write-Host ""
        Write-Host "  Switch Source to 'gateway' in the top bar for live demo data." -ForegroundColor DarkGray
    } else {
        Write-Host ""
        Write-Host "  Running on the mock source. For live demo data:" -ForegroundColor DarkGray
        Write-Host "  ./scripts/dev.ps1 -WithGateway" -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "Ctrl+C to stop." -ForegroundColor DarkGray
    Write-Host ""

    while ($true) {
        if ($null -ne $gatewayJob) {
            Write-Prefixed -Prefix "gateway " -Color Blue -Lines (Receive-Job $gatewayJob)
            if ($gatewayJob.State -in @("Failed", "Completed", "Stopped")) {
                Write-Host "capital-gateway exited unexpectedly." -ForegroundColor Red
                break
            }
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
    $ports = @($terminalPort)
    if ($WithGateway) { $ports += $gatewayPort }
    foreach ($port in $ports) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    }
}
