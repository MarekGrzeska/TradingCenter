"""The two facts `tc-runtime` cannot know about this package: where its migrations live, and which advisory-lock key
they take."""

from __future__ import annotations

from pathlib import Path

# `strategies/` and `migrations/` are siblings — in the repository and in the image (`Dockerfile` copies both).
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations" / "strategies"

# Never a port: the next free number after the alerts' 8120. Not the removed platform's 8080, so a log line naming a key
# never reads as the package that is gone.
MIGRATION_LOCK_KEY = 8130
