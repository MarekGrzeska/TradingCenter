#!/usr/bin/env bash
#
# A wrapper: the stack is started by `dev.py`, one implementation for every platform, because this file and `dev.ps1`
# were the same script written twice and drifted three times.
#
#   ./scripts/dev.sh --no-terminal  # back end only, e.g. to run the live tests
#   ./scripts/dev.sh --explain      # the start order and the reason for each position
set -euo pipefail
exec uv run --project "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" \
  python "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dev.py" "$@"
