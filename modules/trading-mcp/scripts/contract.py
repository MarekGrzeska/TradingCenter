"""capital-gateway's wire, snapshotted rather than assumed.

    uv run python scripts/contract.py generate   # rewrite contract/capital-gateway.openapi.json
    uv run python scripts/contract.py check      # fail if that file is stale

Same mechanism market-mcp uses for market-data's schema (`market-mcp/scripts/
contract.py`), ported here rather than shared — no library between modules. Unlike
market-data, capital-gateway has no dedicated `python -m ....openapi` module, so the
schema is read straight off `FastAPI.openapi()` — constructing `capital_gateway.app`
needs no database, no live provider session and no CAPITAL_* credentials: `Settings()`
is built inside `lifespan`, not at import time, so the schema is a property of the
route and DTO definitions alone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_ROOT = HERE.parent
CAPITAL_GATEWAY = MODULE_ROOT.parent / "capital-gateway"
OUTPUT = MODULE_ROOT / "contract" / "capital-gateway.openapi.json"

# The floor of capital-gateway's own `requires-python`, pinned for the same reason
# market-mcp pins market-data's: a newer interpreter can change a stdlib-sourced
# string FastAPI writes into the schema (Python 3.13 renamed HTTP 422's reason
# phrase), which would describe a contract change that never happened.
PYTHON_VERSION = "3.12"

_PRINT_SCHEMA = "import json; from capital_gateway.app import app; print(json.dumps(app.openapi()))"


def schema_text() -> str:
    # Windows pipes Python's stdout through the ANSI codepage unless told otherwise,
    # which turns every em dash in a docstring — and FastAPI puts docstrings into the
    # schema as `description` fields — into a byte `json.loads` cannot decode as
    # UTF-8. Same fix market-mcp's contract.py needed for the same reason.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory(prefix="trading-mcp-contract-") as scratch:
        env["UV_PROJECT_ENVIRONMENT"] = str(Path(scratch) / "python-env")
        try:
            result = subprocess.run(
                ["uv", "run", "--python", PYTHON_VERSION, "python", "-c", _PRINT_SCHEMA],
                cwd=CAPITAL_GATEWAY,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            print(
                f"Could not read capital-gateway's OpenAPI document from {CAPITAL_GATEWAY}.\n"
                "It is read off `capital_gateway.app.app.openapi()` and needs no database, "
                "no provider session and no CAPITAL_* credentials — so this failing means "
                "the Python environment is missing or broken, not that something is down.",
                file=sys.stderr,
            )
            raise SystemExit(1) from err
    # Reformatted rather than the raw stdout: two `uv run` invocations resolving the
    # same lockfile can still print in a different key order between runs, which
    # would make `check` flap on nothing. `sort_keys` makes the snapshot a function
    # of the schema alone.
    return json.dumps(json.loads(result.stdout), indent=2, sort_keys=True) + "\n"


def generate() -> str:
    text = schema_text()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    return text


def check() -> None:
    fresh = schema_text()
    committed = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None
    if committed != fresh:
        print(
            f"{OUTPUT.relative_to(MODULE_ROOT)} does not match capital-gateway's schema.\n"
            "Run `uv run python scripts/contract.py generate` and commit the result — "
            "the snapshot is versioned on purpose, so a contract change shows up as a "
            "diff next to the change that caused it.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print("Contract is up to date.")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode == "generate":
        generate()
        print(f"Wrote {OUTPUT.relative_to(MODULE_ROOT)}")
    elif mode == "check":
        check()
    else:
        print("Usage: python scripts/contract.py <generate|check>", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
