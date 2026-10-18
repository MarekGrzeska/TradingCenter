"""What every tool module here needs, kept out of `__init__.py`."""

from __future__ import annotations

from dataclasses import dataclass

from mcp.types import ToolAnnotations

# A structural claim an MCP client can act on, not a convention this package merely follows.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs from the running application, read when the tool is called. Lazily: the surface is mounted in
    `create_app()` while everything it reads is put on `app.state` by the lifespan."""

    app: object

    @property
    def _state(self):
        return self.app.state  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def pool(self):
        return self._state.pool
