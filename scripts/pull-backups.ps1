<#
.SYNOPSIS
  Collects the server's database dumps onto this computer, and tells the server it did.

.DESCRIPTION
  The only copy of the dumps that is not on the server (move-from-azure-to-vps, design.md decision 18). The server holds no
  credential to this machine: this script reaches *it*, with a key that can list, read and acknowledge dumps and do nothing
  else (`deploy/scripts/backup-serve.sh`). A dump is written under a name that is not a dump yet, checked against the size
  the server listed, and renamed — so a connection that drops halfway leaves nothing that looks like a backup.

  The acknowledgement is sent only when every listed dump is here. A server that hears nothing for three days says so.

  Schedule it, because a backup nobody remembers to take is the one that is missing:

    $action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -File "C:\path\to\pull-backups.ps1" -Server tcbackup@HOST'
    $trigger = New-ScheduledTaskTrigger -Daily -At 9:00
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable
    Register-ScheduledTask -TaskName 'tradingcenter-pull-backups' -Action $action -Trigger $trigger -Settings $settings

  `-StartWhenAvailable` is the part that matters: a computer that was off at nine runs it when it is next on.

.PARAMETER Server
  user@host of the backup account.
.PARAMETER Destination
  Where dumps are kept. Default: Documents\tradingcenter-backups.
.PARAMETER KeyFile
  The private key of the backup account. Default: whatever ssh would use.
.PARAMETER KeepDays
  Dumps older than this are removed from here — except the newest of each database, always.
.PARAMETER Ssh
  The ssh executable; a parameter so the script can be run against a stand-in.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Server,
  [string]$Destination = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'tradingcenter-backups'),
  [string]$KeyFile,
  [int]$KeepDays = 60,
  [string]$Ssh = 'ssh'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

function Invoke-Server([string]$Command) {
  $sshArgs = @('-o', 'BatchMode=yes')
  if ($KeyFile) { $sshArgs += @('-i', $KeyFile, '-o', 'IdentitiesOnly=yes') }
  $sshArgs += @($Server, $Command)
  $output = & $Ssh @sshArgs
  if ($LASTEXITCODE -ne 0) { throw "ssh '$Command' failed with exit code $LASTEXITCODE" }
  return $output
}

# "<name> <bytes>" per line; a line of any other shape is not something to download.
$listed = @(Invoke-Server 'list' | ForEach-Object {
    if ($_ -match '^(?<name>[a-z0-9_]+-\d{8}T\d{6}Z\.dump) (?<bytes>\d+)$') {
      [pscustomobject]@{ Name = $Matches.name; Bytes = [int64]$Matches.bytes }
    }
  })

if ($listed.Count -eq 0) { throw 'the server lists no dumps; nothing is acknowledged' }

$fetched = 0
foreach ($dump in $listed) {
  $target = Join-Path $Destination $dump.Name
  if ((Test-Path $target) -and (Get-Item $target).Length -eq $dump.Bytes) { continue }

  $partial = Join-Path $Destination ".$($dump.Name).partial"
  $sshArgs = @('-o', 'BatchMode=yes')
  if ($KeyFile) { $sshArgs += @('-i', $KeyFile, '-o', 'IdentitiesOnly=yes') }
  $sshArgs += @($Server, "get $($dump.Name)")
  # Raw bytes straight to a file: PowerShell's pipeline would re-encode a binary dump as text.
  $process = Start-Process -FilePath $Ssh -ArgumentList $sshArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput $partial
  if ($process.ExitCode -ne 0 -or (Get-Item $partial).Length -ne $dump.Bytes) {
    Remove-Item -Force -ErrorAction SilentlyContinue $partial
    throw "$($dump.Name): the copy is not the size the server listed ($($dump.Bytes) bytes); not acknowledging"
  }
  Move-Item -Force $partial $target
  $fetched++
  Write-Host "collected $($dump.Name) ($($dump.Bytes) bytes)"
}

# Every listed dump is here: say so. Reaching this line is the whole condition.
Invoke-Server 'ack' | Out-Null
Write-Host "done: $fetched new, $($listed.Count) listed, acknowledged"

# Retention here is this computer's own business; the newest dump of each database is never removed.
$cutoff = (Get-Date).AddDays(-$KeepDays)
Get-ChildItem -Path $Destination -Filter '*.dump' |
  Group-Object { $_.Name -replace '-\d{8}T\d{6}Z\.dump$', '' } |
  ForEach-Object {
    $_.Group | Sort-Object LastWriteTime -Descending | Select-Object -Skip 1 |
      Where-Object { $_.LastWriteTime -lt $cutoff } |
      ForEach-Object { Remove-Item -Force $_.FullName; Write-Host "removed $($_.Name)" }
  }
