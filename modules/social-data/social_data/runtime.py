"""The two facts `tc-runtime` cannot know about this module: where its migrations live, and which
advisory-lock key they take."""

from __future__ import annotations

from pathlib import Path

# `social_data/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both), so one expression locates it in both.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

# Advisory locks are scoped to one database, so the value only has to be stable. It carries the
# module's port, like every other key here, so a log line naming it says which module took it.
MIGRATION_LOCK_KEY = 8090
