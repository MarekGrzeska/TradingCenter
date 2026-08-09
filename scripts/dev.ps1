<#
.SYNOPSIS
    Everything the terminal needs, in the order it needs it.

.DESCRIPTION
    migrations -> capital-gateway -> market-data -> terminal

    The order is not tidiness. market-data opens a subscription per tracked pair
    as it starts, so a gateway that is not listening yet costs it a round of
    backoff; and the terminal's charts read the archive, so starting it first
    fills the console with proxy errors that mean nothing. Each step waits for
    the one before it to answer, not merely to have been launched.

    The database is not started here — it is `market_data_dev` on the Azure
    server (openspec/changes/provision-azure-platform, design.md, "Praca lokalna
    korzysta z market_data_dev na serwerze w Azure"). The services run here,
    where they reload on save and can be attached to.

    Neither module depends on this script: each still starts on its own with the
    command in its README. `scripts/dev.sh` is the macOS and Linux counterpart.

.PARAMETER NoTerminal
    Back end only — the gateway and the archive. What the live tests need.

.PARAMETER WaitSeconds
    How long to wait for each service to answer. `uv run` may resolve
    dependencies on a cold start, which is the slow part.

.EXAMPLE
    ./scripts/dev.ps1
    ./scripts/dev.ps1 -NoTerminal
#>

param(
    [switch]$NoTerminal,
    [int]$WaitSeconds = 120
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "modules\capital-gateway"
$archiveDir = Join-Path $repoRoot "modules\market-data"
$terminalDir = Join-Path $repoRoot "modules\terminal"

$gatewayPort = 8010
$archivePort = 8020
$terminalPort = 5173
# 127.0.0.1, not "localhost": uvicorn binds IPv4 loopback, while "localhost" can
# resolve to ::1 first on Windows.
$gatewayUrl = "http://127.0.0.1:$gatewayPort"
$archiveUrl = "http://127.0.0.1:$archivePort"
$terminalUrl = "http://localhost:$terminalPort"

Write-Host "Checking prerequisites..." -ForegroundColor Cyan

$problems = @()

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $problems += "uv is not on PATH (runs both Python services) - https://docs.astral.sh/uv/"
}

$gatewayEnv = Join-Path $gatewayDir ".env"
if (-not (Test-Path $gatewayEnv)) {
    $problems += "$gatewayEnv is missing - copy .env.example and fill in demo credentials"
}
$archiveEnv = Join-Path $archiveDir ".env"
if (-not (Test-Path $archiveEnv)) {
    $problems += "$archiveEnv is missing - copy .env.example and fill in the database identity"
}

if (-not $NoTerminal) {
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
        $problems += "pnpm is not on PATH (runs the terminal) - https://pnpm.io/installation"
    }
    if (-not (Test-Path (Join-Path $terminalDir "node_modules"))) {
        $problems += "$terminalDir\node_modules is missing - run 'pnpm install' in modules\terminal"
    }
}

# A port already taken is the commonest reason a run appears to hang: the new
# process cannot bind, and the wait then watches somebody else's service.
function Get-PortOwner {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $conn) { return $null }
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return "pid $($conn.OwningProcess)" }
    return "$($proc.ProcessName) (pid $($proc.Id))"
}

$ports = @($gatewayPort, $archivePort)
if (-not $NoTerminal) { $ports += $terminalPort }
foreach ($port in $ports) {
    $owner = Get-PortOwner -Port $port
    if ($null -eq $owner) { continue }
    $problems += "port $port is already in use by $owner - stop it first, or it is a leftover run"
}

# The quiet disaster this guards against: `.env` pointing at `market_data` - the
# production database - instead of `market_data_dev`. Nothing about running the
# module locally would fail; it would just migrate and fill the wrong database.
if (Test-Path $archiveEnv) {
    $urlLine = Select-String -Path $archiveEnv -Pattern '^DATABASE_URL=' | Select-Object -First 1
    if ($null -ne $urlLine -and $urlLine.Line -match '/([a-zA-Z0-9_]+)(\?.*)?$') {
        $dbName = $Matches[1]
        if ($dbName -ne "market_data_dev") {
            $problems += "modules\market-data\.env's DATABASE_URL names database '$dbName', not 'market_data_dev' - local runs MUST NOT point at production"
        }
    }
}

if ($problems.Count -gt 0) {
    Write-Host "Cannot start:" -ForegroundColor Red
    foreach ($p in $problems) { Write-Host "  - $p" -ForegroundColor Red }
    exit 1
}

$gatewayJob = $null
$archiveJob = $null
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

function Wait-ForHttp {
    param([string]$Url, [string]$Label, $Job, [string]$Prefix, [string]$Color)
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        # Show the service's own output while waiting - a silent script for 30+
        # seconds is indistinguishable from a hung one.
        Write-Prefixed -Prefix $Prefix -Color $Color -Lines (Receive-Job $Job)
        if ($Job.State -in @("Failed", "Completed", "Stopped")) {
            Write-Host "$Label exited before answering." -ForegroundColor Red
            return $false
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return $true }
        } catch {
            # Not up yet. Keep waiting until the deadline.
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "$Label did not answer $Url within $WaitSeconds s." -ForegroundColor Red
    Write-Host "A cold 'uv run' resolving dependencies is the usual slow part." -ForegroundColor DarkGray
    return $false
}

try {
    # --- migrations ---
    #
    # No "start the database" step - it is already running, in Azure
    # (market_data_dev, see the .env check above).

    # Applied every run, not only on a fresh one: a checkout that has just pulled
    # a new migration is exactly the case where forgetting this produces an error
    # that reads like a bug in the archive.
    Write-Host "Applying migrations..." -ForegroundColor Cyan
    Push-Location $archiveDir
    try {
        uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            Write-Host "migrations failed - the archive would fail on its first query, so stopping here." -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
    Write-Host "Schema is up to date." -ForegroundColor Green

    # --- capital-gateway ---

    Write-Host "Starting capital-gateway on port $gatewayPort..." -ForegroundColor Cyan
    $gatewayJob = Start-Job -Name "gateway" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        uv run uvicorn capital_gateway.app:app --reload --port $port 2>&1
    } -ArgumentList $gatewayDir, $gatewayPort

    # "/" specifically - every other route needs X-Gateway-Key since group 1's auth
    # work, and "/" is the one exception carved out for exactly this kind of probe.
    if (-not (Wait-ForHttp -Url "$gatewayUrl/" -Label "capital-gateway" `
                -Job $gatewayJob -Prefix "gateway " -Color Blue)) {
        Write-Prefixed -Prefix "gateway " -Color Yellow -Lines (Receive-Job $gatewayJob)
        exit 1
    }
    Write-Host "capital-gateway is answering." -ForegroundColor Green

    # --- market-data ---
    #
    # After the gateway, because it subscribes to it as it starts. Before the
    # terminal, because the terminal's charts read it.

    Write-Host "Starting market-data on port $archivePort..." -ForegroundColor Cyan
    $archiveJob = Start-Job -Name "archive" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        uv run uvicorn market_data.app:app --reload --port $port 2>&1
    } -ArgumentList $archiveDir, $archivePort

    if (-not (Wait-ForHttp -Url "$archiveUrl/health" -Label "market-data" `
                -Job $archiveJob -Prefix "archive " -Color Magenta)) {
        Write-Prefixed -Prefix "archive " -Color Yellow -Lines (Receive-Job $archiveJob)
        exit 1
    }
    Write-Host "market-data is answering." -ForegroundColor Green

    # --- the terminal ---

    if (-not $NoTerminal) {
        Write-Host "Starting the terminal on port $terminalPort..." -ForegroundColor Cyan
        $terminalJob = Start-Job -Name "terminal" -ScriptBlock {
            param($dir, $port)
            Set-Location $dir
            pnpm exec vite --port $port --strictPort 2>&1
        } -ArgumentList $terminalDir, $terminalPort
    }

    Write-Host ""
    Write-Host "Ready:" -ForegroundColor Green
    if (-not $NoTerminal) {
        Write-Host "  Terminal            $terminalUrl"
        Write-Host "  Archive panel       $terminalUrl/archive"
    }
    Write-Host "  market-data docs    $archiveUrl/docs"
    Write-Host "  Gateway docs        $gatewayUrl/docs"
    Write-Host "  Database            market_data_dev @ Azure"
    Write-Host ""
    Write-Host "Nothing is archived until a pair is added in the Archive panel - that is deliberate." -ForegroundColor DarkGray
    Write-Host "Ctrl+C to stop the services." -ForegroundColor DarkGray
    Write-Host ""

    $watched = @(
        @{ Job = $gatewayJob; Label = "capital-gateway"; Prefix = "gateway "; Color = "Blue" },
        @{ Job = $archiveJob; Label = "market-data"; Prefix = "archive "; Color = "Magenta" }
    )
    if (-not $NoTerminal) {
        $watched += @{ Job = $terminalJob; Label = "terminal"; Prefix = "terminal"; Color = "Cyan" }
    }

    while ($true) {
        $died = $false
        foreach ($w in $watched) {
            Write-Prefixed -Prefix $w.Prefix -Color $w.Color -Lines (Receive-Job $w.Job)
            if ($w.Job.State -in @("Failed", "Completed", "Stopped")) {
                Write-Host "$($w.Label) exited unexpectedly." -ForegroundColor Red
                $died = $true
            }
        }
        if ($died) { break }
        Start-Sleep -Milliseconds 300
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping..." -ForegroundColor Cyan
    foreach ($job in @($gatewayJob, $archiveJob, $terminalJob)) {
        if ($null -ne $job) {
            Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
            Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
        }
    }
    # Start-Job's child process tree (uv -> uvicorn, pnpm -> vite) can outlive the
    # job object itself, which is what actually leaves a process squatting on the
    # port - so processes bound to the ports we used are swept explicitly too.
    $sweep = @($gatewayPort, $archivePort)
    if (-not $NoTerminal) { $sweep += $terminalPort }
    foreach ($port in $sweep) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    }
}
