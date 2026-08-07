# Refuses `openspec archive` while the change has no review.md.
#
# The gate lives here rather than in OpenSpec because OpenSpec does not have one:
# `openspec archive` exits 0 with the review artifact missing, and an `archive.requires`
# block in the schema validates but is ignored. The archive skill only warns and asks.
# A hook is executed by the harness, so it is the one layer a model cannot talk past.

$ErrorActionPreference = 'Stop'

function Allow {
    exit 0
}

function Deny([string]$reason) {
    $payload = @{
        hookSpecificOutput = @{
            hookEventName            = 'PreToolUse'
            permissionDecision       = 'deny'
            permissionDecisionReason = $reason
        }
    }
    $payload | ConvertTo-Json -Depth 5 -Compress
    exit 0
}

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { Allow }

try { $event = $raw | ConvertFrom-Json } catch { Allow }

$command = $event.tool_input.command
if (-not $command) { Allow }

# Only guard the archive verb. `openspec status`, `validate`, `new change` and the rest
# are untouched.
if ($command -notmatch '(?i)openspec[^|;&]*\barchive\b') { Allow }

# The change name is the first bare argument after `archive` — flags and their values
# are skipped, and a quoted name is unwrapped.
$name = $null
if ($command -match '(?i)\barchive\b(?<rest>.*)') {
    $rest = $Matches['rest']
    foreach ($token in ($rest -split '\s+')) {
        if (-not $token) { continue }
        if ($token -like '-*') { continue }
        if ($token -match '^[|;&]') { break }
        $name = $token.Trim('"', "'")
        break
    }
}

if (-not $name) {
    Deny 'Name the change explicitly: openspec archive <change-name>. Without a name this hook cannot check that the change has been reviewed.'
}

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
$changeDir = Join-Path $root "openspec\changes\$name"

# No such change: let OpenSpec produce its own error rather than inventing one here.
if (-not (Test-Path $changeDir)) { Allow }

$review = Join-Path $changeDir 'review.md'
if (Test-Path $review) { Allow }

$message = 'openspec/changes/{0}/review.md is missing. This project reviews a change before archiving it, and the review archives with the change - so it is written first, not skipped. Run: openspec instructions review --change {0} --json' -f $name
Deny $message
