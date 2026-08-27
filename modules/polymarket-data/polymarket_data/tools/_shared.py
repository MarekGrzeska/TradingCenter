"""What every tool module here needs, kept out of `__init__.py`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

# The six tools that only answer questions. A structural claim an MCP client can act on,
# not a convention this module merely follows.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# The three that change the list of observations — and nothing else. `destructiveHint` is false and
# that is exact: nothing in this set can lose data, because the one operation that can is not here.
CHANGES_OBSERVATIONS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True
)

# Every price this surface returns is a probability on 0..1. Repeated in each field's description
# rather than said once: 0,62 misread as 62 is wrong by two orders of magnitude without one error.
PROBABILITY = "probability of this outcome, 0..1 — not a percentage"


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs from the running application, read when the tool is called. Lazily: the surface
    is mounted in `create_app()` while everything it reads is put on `app.state` by the lifespan."""

    app: object

    @property
    def _state(self):
        return self.app.state  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def pool(self):
        return self._state.pool

    @property
    def provider(self):
        return self._state.provider

    @property
    def ingest(self):
        return self._state.ingest

    @property
    def settings(self):
        return self._state.settings


class Age(BaseModel):
    """A moment and how long ago it was, together. Apart, a model has to do arithmetic on an ISO string
    to know whether a price describes now or last Tuesday."""

    at: datetime
    seconds_ago: float

    @classmethod
    def of(cls, moment: datetime | None) -> Age | None:
        if moment is None:
            return None
        return cls(at=moment, seconds_ago=(datetime.now(UTC) - moment).total_seconds())


class Refusal(BaseModel):
    """What a tool answers with when it will not do the thing: what happened, whether asking again could
    help, and what to do first. The last is the one that matters at the ceiling."""

    refused: str = Field(description="what happened, in a sentence")
    do_first: str | None = Field(
        default=None, description="what would have to change for this to succeed"
    )
    retryable: bool = False
