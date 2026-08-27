"""The two facts `tc-runtime` cannot know about this module: where its migrations live, and which
advisory-lock key they take."""

from __future__ import annotations

from pathlib import Path

# `teams/` and `migrations/` are siblings, in the repository and in the image, so one expression locates
# it in both. The chain is named under `migrations/`, because the process runs a second one beside it.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations" / "teams"

# Advisory locks are scoped to one database and this surface has its own, so the value only has to be
# stable. It is the port this surface used to listen on, and a collision would be a start-up that hangs.
MIGRATION_LOCK_KEY = 8050
