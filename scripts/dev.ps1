# A wrapper. The stack is started by `dev.py` — one implementation for every platform,
# because this file and `dev.sh` were the same script written twice and drifted three times
# before 18 August 2026, each time in one of them and not the other. The last of the three
# left this script starting teams-mcp and immediately forgetting it.
#
#   ./scripts/dev.ps1              # everything
#   ./scripts/dev.ps1 -NoTerminal  # back end only, e.g. to run the live tests
#   ./scripts/dev.ps1 --explain    # the start order and the reason for each position
#
# `-NoTerminal` and `--no-terminal` both work: `dev.py` accepts either spelling, so this is
# not a place a difference between the two platforms can appear again.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& uv run --project $here python (Join-Path $here "dev.py") @args
exit $LASTEXITCODE
