"""Where this module keeps its migrations. Its advisory-lock key stays in `db.py`, which unlike
agent's and teams' this module kept, because it is not a copy of theirs."""

from __future__ import annotations

from pathlib import Path

# `market_data/` and `migrations/` are siblings — in the repository and in the image.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
