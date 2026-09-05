"""The two facts `tc-runtime` cannot know about this module.

Where its migrations live, and which advisory-lock key they take.
"""

from __future__ import annotations

from pathlib import Path

# `strategy/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both), so one expression locates it in both.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations" / "strategy"

# Advisory locks are scoped to one database and this module has its own, so the value only has to be stable. It is
# the port this module had before it joined the workbench, like every other key here, so a log line names the chain.
MIGRATION_LOCK_KEY = 8080
