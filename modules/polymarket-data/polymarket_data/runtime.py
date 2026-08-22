"""The two facts `tc-runtime` cannot know about this module.

Where its migrations live, and which advisory-lock key they take.
"""

from __future__ import annotations

from pathlib import Path

# `polymarket_data/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both), so one expression locates it in both.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

# Advisory locks are scoped to one database and this module has its own, so the value only
# has to be stable. It carries the module's port, like every other key here, so a log line
# naming it says which module took it — 8020 is market-data's, 8030 and 8050 the
# workbench's two chains.
#
# 8070 was listed in CLAUDE.md as one of three ports belonging to nobody until this module
# claimed it. `tests/test_runtime.py` asserts this number.
MIGRATION_LOCK_KEY = 8070
