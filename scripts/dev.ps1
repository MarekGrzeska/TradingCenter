# A wrapper: the stack is started by `dev.py`, one implementation for every platform, because this file and `dev.sh`
# were the same script written twice and drifted three times — the last leaving this one starting a service and
# forgetting it. `-NoTerminal` and `--no-terminal` both work.
#
#   ./scripts/dev.ps1 -NoTerminal  # back end only, e.g. to run the live tests
#   ./scripts/dev.ps1 --explain    # the start order and the reason for each position
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& uv run --project $here python (Join-Path $here "dev.py") @args
exit $LASTEXITCODE
