"""What a source is, to this module: a name and a way of asking it for one day's posts.

The protocol exists before the second source does, and that is the whole cost of the module being
called `social-data` rather than after its first feed — a second source is a file here, not a rewrite."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..models import RawPost


class SourceError(Exception):
    """The source did not answer with posts. Never confused with a day that had none."""


class SourceUnreachable(SourceError):
    """No answer at all — a timeout, a refusal, a name that did not resolve."""


class SourceUnreadable(SourceError):
    """An answer this module cannot read. Kept apart from the above because one is somebody else's
    outage and the other is a document that changed shape, and only the second needs a code change."""


@runtime_checkable
class PostSource(Protocol):
    """One place posts come from. `name` is what identity is keyed on and what a state row is filed
    under, so it is a stable identifier and never a display string."""

    @property
    def name(self) -> str: ...

    async def fetch(self, day: date) -> list[RawPost]:
        """Every post that source published on that UTC date. Raises `SourceError` rather than
        answering with an empty list: a quiet day and an outage are different facts."""
        ...
