"""The two facts `tc-runtime` cannot know about this package: where its migrations live, and which advisory-lock key
they take."""

from __future__ import annotations

from pathlib import Path

# `alerts/` and `migrations/` are siblings — in the repository and in the image (`Dockerfile` copies both).
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations" / "alerts"

# Never a port: 8110 was the last one handed out, and 8120 continues the run so a log line naming it still says which
# chain took the lock.
MIGRATION_LOCK_KEY = 8120
