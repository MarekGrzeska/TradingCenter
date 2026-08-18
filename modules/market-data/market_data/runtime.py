"""Where this module keeps its migrations.

Its advisory-lock key stays in `db.py` with the rest of this module's database plumbing —
unlike agent and teams, this module kept that file, because it is not a copy of theirs
(`packages-replace-the-hand-copies/design.md`, D4).
"""

from __future__ import annotations

from pathlib import Path

# `market_data/` and `migrations/` are siblings — in the repository and in the image.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
