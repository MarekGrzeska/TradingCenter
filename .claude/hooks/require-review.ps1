# Refuses to archive a change that has no review.md.
#
# The gate lives here rather than in OpenSpec because OpenSpec does not have one:
# `openspec archive` exits 0 with the review artifact missing, and an `archive.requires`
# block in the schema validates but is ignored. The archive skill only warns and asks.
# A hook is executed by the harness, so it is the one layer a model cannot talk past.
#
# Two ways a change gets archived, and both are covered:
#   openspec archive <name>
#   mv openspec/changes/<name> openspec/changes/archive/<date>-<name>
# The second is the documented happy path — the archive skill uses mkdir + mv, not the
# CLI — so a gate that only watched the CLI would watch the road nobody drives.

$ErrorActionPreference = 'Stop'

function Allow {
    exit 0
}

function Deny([string]$reason) {
    @{
        hookSpecificOutput = @{
            hookEventName            = 'PreToolUse'
            permissionDecision       = 'deny'
            permissionDecisionReason = $reason
        }
    } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}

# Flags that swallow the next token. Without this, `openspec archive --store trading X`
# reads the store id as the change name and then finds no such change to check.
$ValueFlags = @('--store', '--type', '--concurrency', '--schema', '--change')

function Get-ArchiveTargetFromCli([string[]]$tokens) {
    # The archive *verb*, not the word anywhere: `openspec instructions archive` is a
    # read and must stay non-blocking.
    $i = 0
    while ($i -lt $tokens.Count -and $tokens[$i] -notmatch '(?i)(^|[\\/])openspec(\.js|\.cmd)?$') { $i++ }
    if ($i -ge $tokens.Count) { return $null }
    $i++

    while ($i -lt $tokens.Count -and $tokens[$i] -like '-*') {
        if ($ValueFlags -contains $tokens[$i].ToLower()) { $i++ }
        $i++
    }
    if ($i -ge $tokens.Count -or $tokens[$i] -ne 'archive') { return $null }
    $i++

    while ($i -lt $tokens.Count) {
        $t = $tokens[$i]
        if ($t -like '-*') {
            # `--store trading add-capital-gateway`: without consuming the value, the
            # store id is read as the change name and the check silently targets
            # nothing.
            if ($ValueFlags -contains $t.ToLower()) { $i++ }
            $i++
            continue
        }
        return $t.Trim('"', "'")
    }
    # `openspec archive` with no name: the CLI picks interactively, so there is nothing
    # here to check against.
    return ''
}

function Get-ArchiveTargetFromMove([string[]]$tokens) {
    if ($tokens.Count -lt 2) { return $null }
    if ($tokens[0] -notmatch '(?i)^(mv|move-item|move)$') { return $null }

    foreach ($t in $tokens) {
        # The destination also lives under changes/, so the segment literally named
        # `archive` is skipped and the source is what is left.
        if ($t -match '(?i)openspec[\\/]+changes[\\/]+(?<name>[^\\/"'']+)') {
            $candidate = $Matches['name'].Trim('"', "'")
            if ($candidate -and $candidate -ne 'archive') { return $candidate }
        }
    }
    return $null
}

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { Allow }

try { $payload = $raw | ConvertFrom-Json } catch { Allow }

$command = $payload.tool_input.command
if (-not $command) { Allow }

# Split on shell separators first: a gate that reads the whole line as one command is
# bypassed by putting the archive after a `&&`, and trips over a trailing `;`.
$segments = [regex]::Split($command, '(?:&&|\|\||[;&|\r\n])')

$target = $null
foreach ($segment in $segments) {
    $tokens = @($segment.Trim() -split '\s+' | Where-Object { $_ })
    if ($tokens.Count -eq 0) { continue }
    if ($tokens -contains '--help' -or $tokens -contains '-h') { continue }

    $found = Get-ArchiveTargetFromCli $tokens
    if ($null -eq $found) { $found = Get-ArchiveTargetFromMove $tokens }
    if ($null -ne $found) { $target = $found; break }
}

# Nothing here archives anything.
if ($null -eq $target) { Allow }

if ($target -eq '') {
    Deny 'Name the change explicitly: openspec archive <change-name>. Without a name this hook cannot check that the change has been reviewed.'
}

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
$changeDir = Join-Path $root (Join-Path 'openspec\changes' $target)

# No such change: let OpenSpec produce its own error rather than inventing one here.
if (-not (Test-Path $changeDir)) { Allow }

if (Test-Path (Join-Path $changeDir 'review.md')) { Allow }

$message = 'openspec/changes/{0}/review.md is missing. This project reviews a change before archiving it, and the review archives with the change - so it is written first, not skipped. Run: openspec instructions review --change {0} --json' -f $target
Deny $message
