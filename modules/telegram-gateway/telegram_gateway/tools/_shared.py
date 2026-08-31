"""What every tool module here needs, kept out of `__init__.py`."""

from __future__ import annotations

from dataclasses import dataclass

from mcp.types import ToolAnnotations

# Reading who can be written to. Nothing about it changes anything, and a client may act on that.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# Sending. Not read-only and not idempotent: the same call twice is two notifications on somebody's
# phone. `destructiveHint=False` is honest — nothing here is undone, but nothing is destroyed either.
SENDS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)


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
    def settings(self):
        return self._state.settings

    @property
    def telegram(self):
        return self._state.telegram
