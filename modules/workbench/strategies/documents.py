"""A document checked against everything it depends on: the language, and the archive's catalogue and pairs as they are
now. Saving and `POST /validate` both come through here, so they cannot answer differently."""

from __future__ import annotations

from typing import Any

from .archive import Archive
from .document import Checked, servable, validate
from .problems import Problem


async def check(raw: Any, archive: Archive) -> tuple[Checked | None, list[Problem]]:
    """Raises `ArchiveUnavailable` rather than checking without it: a symbol nobody could verify is not a valid one."""
    catalogue, tracked = await archive.check_inputs()
    return validate(raw, catalogue, servable(tracked))
