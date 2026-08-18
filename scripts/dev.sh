#!/usr/bin/env bash
#
# A wrapper. The stack is started by `dev.py` — one implementation for every platform,
# because this file and `dev.ps1` were the same script written twice and drifted three
# times before 18 August 2026, each time in one of them and not the other.
#
#   ./scripts/dev.sh                # everything
#   ./scripts/dev.sh --no-terminal  # back end only, e.g. to run the live tests
#   ./scripts/dev.sh --explain      # the start order and the reason for each position
#
# There is nothing to keep in step here: no decision, no service table, no order.
set -euo pipefail
exec uv run --project "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" \
  python "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dev.py" "$@"
