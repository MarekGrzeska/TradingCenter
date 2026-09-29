"""The two facts `tc-runtime` cannot know about this package: where its migrations live, and which advisory-lock key
they take."""

from __future__ import annotations

from pathlib import Path

# `youtube_data/` and `migrations/` are siblings — in the repository and in the image (`Dockerfile` copies both).
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations" / "youtube"

# The first key that was never a port: the seven before it carry the port their module used to have, and 8110 is
# nobody's — a log line naming it still says which chain took the lock.
MIGRATION_LOCK_KEY = 8110
