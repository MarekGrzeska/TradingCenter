"""The two facts `tc-runtime` cannot know about this module.

Where its migrations live, and which advisory-lock key they take.
"""

from __future__ import annotations

from pathlib import Path

# `strategy/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both), so one expression locates it in both.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

# Advisory locks are scoped to one database and this module has its own
# (`strategy-database-connection`, "Własna baza, cudzych tabel nie dotyka"), so the value
# only has to be stable. It is this module's port, following the convention the other
# three set — market-data 8020, the conversation 8030, teams 8050 — so a log line naming
# the key still says which module took it. `tests/test_runtime.py` asserts the number.
MIGRATION_LOCK_KEY = 8080
