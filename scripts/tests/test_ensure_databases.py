"""`retire` runs after every `ensure` in `deploy/postgres/ensure-databases.sh`, so a name on both lists is a database
created and dropped by the same deploy — the trap the strategy engine sidestepped by not reusing `strategy`
(`openspec/changes/a-strategy-is-a-document`, design D1)."""

from __future__ import annotations

import pathlib
import re

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "deploy" / "postgres" / "ensure-databases.sh"


def _called(function: str) -> set[str]:
    return set(re.findall(rf"^{function}\s+(\w+)", SCRIPT.read_text(encoding="utf-8"), re.MULTILINE))


def test_no_database_is_both_ensured_and_retired() -> None:
    ensured, retired = _called("ensure"), _called("retire")

    assert ensured, "the script ensures no database at all; the pattern no longer matches it"
    assert not ensured & retired, f"created and dropped by the same deploy: {sorted(ensured & retired)}"
