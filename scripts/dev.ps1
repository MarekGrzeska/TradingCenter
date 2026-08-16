<#
.SYNOPSIS
    Everything the terminal needs, in the order it needs it.

.DESCRIPTION
    migrations -> capital-gateway -> market-data -> market-mcp -> trading-mcp ->
    agent -> teams -> terminal

    The order is not tidiness, and every arrow in it is now a real dependency.
    market-data opens a subscription per tracked pair as it starts, so a gateway
    that is not listening yet costs it a round of backoff; market-mcp reads
    market-data's own contract; trading-mcp asks the gateway whether it is bound to
    the demo account and refuses to open a port at all if it is not, so a gateway
    that is not answering yet is a module that exits rather than waits; the agent
    asks market-mcp for its tool list on the first turn, and a market-mcp that was
    not up yet means an agent answering without tools rather than an error anyone
    would notice; teams reads both tool lists for the agents a run assigns tools to;
    the terminal's charts read the archive, so starting it first fills the console
    with proxy errors that mean nothing. Each step waits for the one before it to
    answer, not merely to have been launched.

    market-mcp needs no .env of its own here: every setting it reads has a
    working default for loopback (config.py), unlike the gateway and the archive,
    which hold real credentials with no safe default to fall back to. trading-mcp is
    the other kind: the gateway checks its X-Gateway-Key on every caller, loopback
    included, so this one module has a credential to fill in even locally.

    The database is the container in ..\compose.yaml — started here, before
    migrations (openspec/changes/local-dev-database-in-docker). The services run
    here on the host, where they reload on save and can be attached to;
    `docker compose down` stops the database and keeps the data.

    `agent`'s and `teams`' own databases are further logical databases in that same
    container, created here if missing rather than through
    docker-entrypoint-initdb.d — that only runs on a volume's first boot, so it
    would never fire for anyone who already has tradingcenter-db-data from before
    either module existed (design.md, "Baza: druga baza logiczna, jeden serwer").
    Three databases, one server, the same shape production has.

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

[CmdletBinding()]
param(
    [switch]$NoTerminal,
    [int]$WaitSeconds = 120
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "modules\capital-gateway"
$archiveDir = Join-Path $repoRoot "modules\market-data"
$mcpDir = Join-Path $repoRoot "modules\market-mcp"
$tradingDir = Join-Path $repoRoot "modules\trading-mcp"
$agentDir = Join-Path $repoRoot "modules\agent"
$teamsDir = Join-Path $repoRoot "modules\teams"
$terminalDir = Join-Path $repoRoot "modules\terminal"

$gatewayPort = 8010
$archivePort = 8020
$agentPort = 8030
$mcpPort = 8040
$teamsPort = 8050
$tradingPort = 8060
$terminalPort = 5173
# 127.0.0.1, not "localhost": uvicorn binds IPv4 loopback, while "localhost" can
# resolve to ::1 first on Windows.
$gatewayUrl = "http://127.0.0.1:$gatewayPort"
$archiveUrl = "http://127.0.0.1:$archivePort"
$agentUrl = "http://127.0.0.1:$agentPort"
$mcpUrl = "http://127.0.0.1:$mcpPort"
$teamsUrl = "http://127.0.0.1:$teamsPort"
$tradingUrl = "http://127.0.0.1:$tradingPort"
$terminalUrl = "http://localhost:$terminalPort"

Write-Host "Checking prerequisites..." -ForegroundColor Cyan

$problems = @()

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $problems += "uv is not on PATH (runs all three Python services) - https://docs.astral.sh/uv/"
}

# The database lives in a container again, so Docker is back to being a requirement
# for running the stack, not only for testing market-data.
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $problems += "docker is not on PATH (runs the database, compose.yaml) - https://docs.docker.com/get-docker/"
} else {
    # `*> $null` alone would still abort under $ErrorActionPreference = "Stop": redirecting
    # a native command's stderr wraps each line as a NativeCommandError, which -Stop then
    # promotes to terminating regardless of the redirect target — so a harmless line like
    # Docker's own "WARNING: No blkio throttle.read_bps_device support" would kill the
    # script before it ever got to say the daemon was fine. Scoped down to SilentlyContinue
    # for just this call, the same way dev.sh silences both streams unconditionally.
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    docker info *> $null
    $ErrorActionPreference = $previousEap
    if ($LASTEXITCODE -ne 0) {
        $problems += "docker is installed but the daemon is not answering - start Docker Desktop"
    }
}

$gatewayEnv = Join-Path $gatewayDir ".env"
if (-not (Test-Path $gatewayEnv)) {
    $problems += "$gatewayEnv is missing - copy .env.example and fill in demo credentials"
}
$archiveEnv = Join-Path $archiveDir ".env"
if (-not (Test-Path $archiveEnv)) {
    $problems += "$archiveEnv is missing - copy .env.example; the defaults match compose.yaml"
}
$agentEnv = Join-Path $agentDir ".env"
if (-not (Test-Path $agentEnv)) {
    $problems += "$agentEnv is missing - copy .env.example and fill in OPENAI_API_KEY"
}
# teams needs a key and a MODELS catalogue: config.py refuses to build Settings without
# either, so the module would exit at import rather than start and misbehave.
$teamsEnv = Join-Path $teamsDir ".env"
if (-not (Test-Path $teamsEnv)) {
    $problems += "$teamsEnv is missing - copy .env.example and fill in OPENAI_API_KEY (MODELS has a working default there)"
}
# trading-mcp cannot fall back the way market-mcp does: config.py requires the gateway's
# caller key, and the gateway checks it on loopback too.
$tradingEnv = Join-Path $tradingDir ".env"
if (-not (Test-Path $tradingEnv)) {
    $problems += "$tradingEnv is missing - copy .env.example and set CAPITAL_GATEWAY_API_KEY to the gateway's own GATEWAY_API_KEY"
}

if (-not $NoTerminal) {
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        $usePnpm = $true
        $terminalInstall = "pnpm install"
    } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
        # pnpm is what the module documents, but a machine with only npm can still
        # run a dev server, and refusing over the choice of package manager helps
        # nobody.
        $usePnpm = $false
        $terminalInstall = "npm install"
    } else {
        $problems += "neither pnpm nor npm is on PATH (runs the terminal) - https://pnpm.io/installation"
        $usePnpm = $true
        $terminalInstall = "pnpm install"
    }
    if (-not (Test-Path (Join-Path $terminalDir "node_modules"))) {
        $problems += "$terminalDir\node_modules is missing - run '$terminalInstall' in modules\terminal"
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

$ports = @($gatewayPort, $archivePort, $mcpPort, $tradingPort, $agentPort, $teamsPort)
if (-not $NoTerminal) { $ports += $terminalPort }
foreach ($port in $ports) {
    $owner = Get-PortOwner -Port $port
    if ($null -eq $owner) { continue }
    $problems += "port $port is already in use by $owner - stop it first, or it is a leftover run"
}

# The quiet disaster this guards against: `.env` still pointing at the Azure server -
# production, or the retired dev database - instead of the local container. config.py
# refuses the same thing at startup (no DATABASE_USER means loopback only); repeating
# the check here just refuses earlier, before anything has been launched, with the
# file to fix named. Reads the host between the optional `user:pass@` and the port.
function Test-LocalDatabaseHost {
    param([string]$EnvPath, [string]$Label)
    if (-not (Test-Path $EnvPath)) { return }
    $urlLine = Select-String -Path $EnvPath -Pattern '^DATABASE_URL=' | Select-Object -First 1
    if ($null -ne $urlLine -and $urlLine.Line -match '^DATABASE_URL=[a-z+]+://(?:[^@/]+@)?(?<dbhost>[^:/?]+)') {
        $dbHost = $Matches['dbhost']
        if ($dbHost -ne "localhost" -and $dbHost -notlike "127.*" -and $dbHost -ne "::1") {
            $script:problems += "$Label's DATABASE_URL points at '$dbHost' - local runs use the compose.yaml container (localhost), never a remote database"
        }
    }
}
Test-LocalDatabaseHost -EnvPath $archiveEnv -Label "modules\market-data\.env"
Test-LocalDatabaseHost -EnvPath $agentEnv -Label "modules\agent\.env"
Test-LocalDatabaseHost -EnvPath $teamsEnv -Label "modules\teams\.env"

# The two halves of one credential, in two files. The gateway checks X-Gateway-Key on
# every caller including loopback, and trading-mcp asks it about the account *before* it
# opens a port - so a mismatch here is not a failed tool call later, it is a module that
# exits during start-up and takes this whole script down with it.
function Get-EnvValue {
    param([string]$EnvPath, [string]$Name)
    if (-not (Test-Path $EnvPath)) { return $null }
    $line = Select-String -Path $EnvPath -Pattern "^$Name=(.*)$" | Select-Object -First 1
    if ($null -eq $line) { return $null }
    return $line.Matches[0].Groups[1].Value
}
$gatewayKey = Get-EnvValue -EnvPath $gatewayEnv -Name "GATEWAY_API_KEY"
$tradingKey = Get-EnvValue -EnvPath $tradingEnv -Name "CAPITAL_GATEWAY_API_KEY"
if ([string]::IsNullOrWhiteSpace($tradingKey)) {
    if (Test-Path $tradingEnv) {
        $problems += "modules\trading-mcp\.env has no CAPITAL_GATEWAY_API_KEY - the gateway requires it from every caller, loopback included"
    }
} elseif (-not [string]::IsNullOrWhiteSpace($gatewayKey) -and $gatewayKey -ne $tradingKey) {
    $problems += "modules\trading-mcp\.env's CAPITAL_GATEWAY_API_KEY does not match modules\capital-gateway\.env's GATEWAY_API_KEY - trading-mcp would be refused by the gateway and exit before it listens"
}

if ($problems.Count -gt 0) {
    Write-Host "Cannot start:" -ForegroundColor Red
    foreach ($p in $problems) { Write-Host "  - $p" -ForegroundColor Red }
    exit 1
}

# Not a problem - an agent without tools is a supported state, and the one it degrades
# to when market-mcp is down. Worth saying out loud, though: an `.env` written before
# the tools existed leaves the agent answering from the model alone, which looks from
# the panel exactly like tools that are broken.
if ((Test-Path $agentEnv) -and
    -not (Select-String -Path $agentEnv -Pattern '^MARKET_MCP_URL=.+' -Quiet)) {
    Write-Host "modules\agent\.env has no MARKET_MCP_URL - the agent will run without tools." -ForegroundColor DarkGray
    Write-Host "  Add MARKET_MCP_URL=$mcpUrl to give it market-mcp's, as .env.example does." -ForegroundColor DarkGray
}

# Same for teams, with a sharper edge: the agent without a tool server answers from the
# model alone, while a team whose agents were *assigned* tools refuses to run at all
# (specs/teams-tool-access). Both are supported states; only one of them looks like the
# module is broken.
if ((Test-Path $teamsEnv) -and
    -not (Select-String -Path $teamsEnv -Pattern '^MARKET_MCP_URL=.+' -Quiet)) {
    Write-Host "modules\teams\.env has no MARKET_MCP_URL - teams whose agents assign tools will refuse to run." -ForegroundColor DarkGray
    Write-Host "  Add MARKET_MCP_URL=$mcpUrl to give it market-mcp's, as .env.example does." -ForegroundColor DarkGray
}

# The same again for the write half, and it is the one worth saying twice: a team given
# only reading tools runs perfectly without this line, so its absence shows up as a
# refusal on the one run that was supposed to place an order.
if ((Test-Path $teamsEnv) -and
    -not (Select-String -Path $teamsEnv -Pattern '^TRADING_MCP_URL=.+' -Quiet)) {
    Write-Host "modules\teams\.env has no TRADING_MCP_URL - teams will have no order tools, and one assigning them refuses to run." -ForegroundColor DarkGray
    Write-Host "  Add TRADING_MCP_URL=$tradingUrl to give it trading-mcp's, as .env.example does." -ForegroundColor DarkGray
}

$gatewayJob = $null
$archiveJob = $null
$mcpJob = $null
$tradingJob = $null
$agentJob = $null
$teamsJob = $null
$terminalJob = $null

# One logical database and the role that owns it, created if either is missing. Called
# from inside a Push-Location on the repository root, where `docker compose` finds
# compose.yaml.
function Confirm-LogicalDatabase {
    param([string]$Name)
    # "$(...)" and not (...).Trim(): psql -tAc prints nothing at all when the row is
    # absent, PowerShell binds that to $null, and $null.Trim() throws "You cannot call a
    # method on a null-valued expression" - in exactly the case this exists to handle.
    # The subexpression makes an absent row an empty string.
    $roleExists = "$(docker compose exec -T db psql -U market_data -d market_data -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$Name'")".Trim()
    if ($roleExists -ne "1") {
        docker compose exec -T db psql -U market_data -d market_data -v ON_ERROR_STOP=1 -c "CREATE ROLE $Name LOGIN PASSWORD 'change-me';"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "could not create the '$Name' role." -ForegroundColor Red
            exit 1
        }
    }
    $dbExists = "$(docker compose exec -T db psql -U market_data -d market_data -tAc "SELECT 1 FROM pg_database WHERE datname = '$Name'")".Trim()
    if ($dbExists -ne "1") {
        docker compose exec -T db psql -U market_data -d market_data -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Name OWNER $Name;"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "could not create the '$Name' database." -ForegroundColor Red
            exit 1
        }
    }
}

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
    # --- the database ---
    #
    # `--wait` blocks on the healthcheck in compose.yaml, which names the user and
    # the database on purpose: a bare `pg_isready` answers before first-boot
    # initialisation finishes, and the migrations below would then race it.
    Write-Host "Starting the database container..." -ForegroundColor Cyan
    Push-Location $repoRoot
    try {
        docker compose up -d --wait db
        if ($LASTEXITCODE -ne 0) {
            Write-Host "the database container did not become healthy - 'docker compose logs db' has the reason." -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
    Write-Host "Database is up." -ForegroundColor Green

    # --- the agent's and teams' own databases ---
    #
    # Further logical databases in the same container, not further containers - the free
    # grant is one Postgres server and this mirrors it (design.md, "Baza: druga baza
    # logiczna, jeden serwer"). Checked and created here rather than through
    # docker-entrypoint-initdb.d, which only ever runs against an empty volume: anyone
    # with a tradingcenter-db-data from before either module existed would never see it
    # fire.
    Write-Host "Ensuring the agent and teams databases exist..." -ForegroundColor Cyan
    Push-Location $repoRoot
    try {
        Confirm-LogicalDatabase -Name "agent"
        Confirm-LogicalDatabase -Name "teams"
    } finally {
        Pop-Location
    }
    Write-Host "agent and teams databases are ready." -ForegroundColor Green

    # --- migrations ---

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
    Push-Location $agentDir
    try {
        uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            Write-Host "agent's migrations failed - it would fail on its first query, so stopping here." -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
    Push-Location $teamsDir
    try {
        uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            Write-Host "teams' migrations failed - it would fail on its first query, so stopping here." -ForegroundColor Red
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

    # --- market-mcp ---
    #
    # After market-data, whose contract it reads. No `--reload`: unlike the other
    # services this one is not started through uvicorn's own CLI (server.py's
    # caller-identity wrapper needs the ASGI app built in Python first), so a code
    # change here needs a manual restart for now.

    Write-Host "Starting market-mcp on port $mcpPort..." -ForegroundColor Cyan
    $mcpJob = Start-Job -Name "mcp" -ScriptBlock {
        param($dir)
        Set-Location $dir
        uv run python -m market_mcp http 2>&1
    } -ArgumentList $mcpDir

    if (-not (Wait-ForHttp -Url "$mcpUrl/health" -Label "market-mcp" `
                -Job $mcpJob -Prefix "mcp     " -Color Green)) {
        Write-Prefixed -Prefix "mcp     " -Color Yellow -Lines (Receive-Job $mcpJob)
        exit 1
    }
    Write-Host "market-mcp is answering." -ForegroundColor Green

    # --- trading-mcp ---
    #
    # After the gateway, and this one is not a preference: __main__.py asks
    # GET /capabilities and refuses to open a port unless the answer says `demo`
    # (specs/trading-mcp-upstream-access). A gateway that is not answering yet is a
    # module that exits rather than one that retries.
    #
    # No `--reload`, same as market-mcp: the ASGI app is built in Python (the
    # caller-identity wrapper), not handed to uvicorn's CLI.

    Write-Host "Starting trading-mcp on port $tradingPort..." -ForegroundColor Cyan
    $tradingJob = Start-Job -Name "trading" -ScriptBlock {
        param($dir)
        Set-Location $dir
        uv run python -m trading_mcp 2>&1
    } -ArgumentList $tradingDir

    if (-not (Wait-ForHttp -Url "$tradingUrl/health" -Label "trading-mcp" `
                -Job $tradingJob -Prefix "trading " -Color DarkGreen)) {
        Write-Prefixed -Prefix "trading " -Color Yellow -Lines (Receive-Job $tradingJob)
        exit 1
    }
    Write-Host "trading-mcp is answering." -ForegroundColor Green

    # --- agent ---
    #
    # Last among the back ends: nothing else calls it, so nothing else waits on it -
    # unlike the gateway, which market-data subscribes to as it starts. It does call
    # market-mcp, which is why it starts after it: the tool list is read on the first
    # turn, and a market-mcp still coming up would mean a turn answered without tools.

    Write-Host "Starting agent on port $agentPort..." -ForegroundColor Cyan
    $agentJob = Start-Job -Name "agent" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        uv run uvicorn agent.app:app --reload --port $port 2>&1
    } -ArgumentList $agentDir, $agentPort

    if (-not (Wait-ForHttp -Url "$agentUrl/health" -Label "agent" `
                -Job $agentJob -Prefix "agent   " -Color Yellow)) {
        Write-Prefixed -Prefix "agent   " -Color Yellow -Lines (Receive-Job $agentJob)
        exit 1
    }
    Write-Host "agent is answering." -ForegroundColor Green

    # --- teams ---
    #
    # After market-mcp for the same reason the agent is, and after the agent for no
    # reason at all beyond a fixed order: nothing calls teams, and teams calls nobody the
    # agent does not. The two are siblings, not a chain.

    Write-Host "Starting teams on port $teamsPort..." -ForegroundColor Cyan
    $teamsJob = Start-Job -Name "teams" -ScriptBlock {
        param($dir, $port)
        Set-Location $dir
        uv run uvicorn teams.app:app --reload --port $port 2>&1
    } -ArgumentList $teamsDir, $teamsPort

    if (-not (Wait-ForHttp -Url "$teamsUrl/health" -Label "teams" `
                -Job $teamsJob -Prefix "teams   " -Color DarkCyan)) {
        Write-Prefixed -Prefix "teams   " -Color Yellow -Lines (Receive-Job $teamsJob)
        exit 1
    }
    Write-Host "teams is answering." -ForegroundColor Green

    # --- the terminal ---

    if (-not $NoTerminal) {
        Write-Host "Starting the terminal on port $terminalPort..." -ForegroundColor Cyan
        $terminalJob = Start-Job -Name "terminal" -ScriptBlock {
            param($dir, $port, $usePnpm)
            Set-Location $dir
            if ($usePnpm) {
                pnpm exec vite --port $port --strictPort 2>&1
            } else {
                npx vite --port $port --strictPort 2>&1
            }
        } -ArgumentList $terminalDir, $terminalPort, $usePnpm
    }

    Write-Host ""
    Write-Host "Ready:" -ForegroundColor Green
    if (-not $NoTerminal) {
        Write-Host "  Terminal            $terminalUrl"
        Write-Host "  Instruments panel   $terminalUrl/instruments"
    }
    Write-Host "  market-data docs    $archiveUrl/docs"
    Write-Host "  Gateway docs        $gatewayUrl/docs"
    Write-Host "  market-mcp health   $mcpUrl/health"
    Write-Host "  trading-mcp health  $tradingUrl/health"
    Write-Host "  agent docs          $agentUrl/docs"
    Write-Host "  teams docs          $teamsUrl/docs"
    Write-Host "  Database            market_data, agent, teams @ localhost:55432 (compose.yaml; 'docker compose down' keeps the data)"
    Write-Host ""
    Write-Host "Nothing is archived until a pair is added in the Archive panel - that is deliberate." -ForegroundColor DarkGray
    Write-Host "Ctrl+C to stop the services." -ForegroundColor DarkGray
    Write-Host ""

    $watched = @(
        @{ Job = $gatewayJob; Label = "capital-gateway"; Prefix = "gateway "; Color = "Blue" },
        @{ Job = $archiveJob; Label = "market-data"; Prefix = "archive "; Color = "Magenta" },
        @{ Job = $mcpJob; Label = "market-mcp"; Prefix = "mcp     "; Color = "Green" },
        @{ Job = $tradingJob; Label = "trading-mcp"; Prefix = "trading "; Color = "DarkGreen" },
        @{ Job = $agentJob; Label = "agent"; Prefix = "agent   "; Color = "Yellow" },
        @{ Job = $teamsJob; Label = "teams"; Prefix = "teams   "; Color = "DarkCyan" }
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
    foreach ($job in @($gatewayJob, $archiveJob, $mcpJob, $tradingJob, $agentJob, $teamsJob, $terminalJob)) {
        if ($null -ne $job) {
            Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
            Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
        }
    }
    # Start-Job's child process tree (uv -> uvicorn, pnpm -> vite) can outlive the
    # job object itself, which is what actually leaves a process squatting on the
    # port - so processes bound to the ports we used are swept explicitly too.
    $sweep = @($gatewayPort, $archivePort, $mcpPort, $tradingPort, $agentPort, $teamsPort)
    if (-not $NoTerminal) { $sweep += $terminalPort }
    foreach ($port in $sweep) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    }
}
