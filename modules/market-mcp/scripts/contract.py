"""market-data's wire, snapshotted rather than assumed.

    uv run python scripts/contract.py generate   # rewrite contract/market-data.openapi.json
    uv run python scripts/contract.py check      # fail if that file is stale

Same mechanism the terminal uses for its generated types (`contract.mjs`), ported
here rather than shared — no library between modules. The schema is printed by
`python -m market_data.openapi`, a process run in the sibling `market-data` checkout,
not an import and not a running server: the document is a property of that module's
Pydantic models, so producing it needs no database, no gateway and no network. A check
that needed a running service is the check nobody would run, which is how two copies
of a contract drift apart in the first place.
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
MARKET_DATA = MODULE_ROOT.parent / "market-data"
OUTPUT = MODULE_ROOT / "contract" / "market-data.openapi.json"

# The floor of market-data's own `requires-python`, pinned rather than left to uv:
# Python 3.13 renamed HTTP 422's reason phrase from "Unprocessable Entity" to
# "Unprocessable Content", which FastAPI reads from the stdlib and prints into the
# schema. Regenerating on a newer interpreter than the one that wrote the committed
# file would then describe a contract change that never happened.
PYTHON_VERSION = "3.12"


def schema_text() -> str:
    # Windows pipes Python's stdout through the ANSI codepage unless told otherwise,
    # which turns every em dash in a docstring — and FastAPI puts docstrings into the
    # schema as `description` fields — into a byte `read_text` cannot decode as UTF-8.
    # Same fix `contract.mjs` needed for the same reason.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory(prefix="market-mcp-contract-") as scratch:
        # A throwaway environment for the pinned interpreter, so generating the
        # contract does not rebuild market-data's real `.venv` on 3.12 underneath
        # whoever is working there.
        env["UV_PROJECT_ENVIRONMENT"] = str(Path(scratch) / "python-env")
        try:
            result = subprocess.run(
                ["uv", "run", "--python", PYTHON_VERSION, "python", "-m", "market_data.openapi"],
                cwd=MARKET_DATA,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            print(
                f"Could not read market-data's OpenAPI document from {MARKET_DATA}.\n"
                "It is printed by `uv run python -m market_data.openapi` and needs no "
                "database, no gateway and no running server — so this failing means "
                "the Python environment is missing or broken, not that something is "
                "down.",
                file=sys.stderr,
            )
            raise SystemExit(1) from err
    # Reformatted rather than the raw stdout: two `uv run` invocations resolving the same
    # lockfile can still print in a different key order between runs, which would make
    # `check` flap on nothing. `sort_keys` makes the snapshot a function of the schema
    # alone.
    #
    # `ensure_ascii=False` because the whole worth of a committed snapshot is a readable
    # diff, and this document is mostly Polish prose: escaped, one reworded sentence
    # arrives as a wall of `\uXXXX` nobody reads. The file is written as UTF-8 either way.
    return json.dumps(json.loads(result.stdout), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


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
            f"{OUTPUT.relative_to(MODULE_ROOT)} does not match market-data's schema.\n"
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
