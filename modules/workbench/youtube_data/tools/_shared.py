"""What every tool module here needs, kept out of `__init__.py`."""

from __future__ import annotations

from dataclasses import dataclass

from mcp.types import ToolAnnotations

# A structural claim an MCP client can act on, not a convention this package merely follows.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
# Adds to the watch list or the queue and removes nothing — `destructiveHint` is false and the surface has no tool that is
# true of, which a test holds.
ADDS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
# Reads, but spends the source's day to do it: not a change to the archive, and not free.
SPENDS = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True)

# The most films one call returns. A model choosing between forty is already choosing badly, and every one of them is
# paid for by the token.
MAX_FILMS = 30
SUMMARY_CHARS = 280


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

    @property
    def settings(self):
        return self._state.settings

    @property
    def providers(self):
        return self._state.providers


def refused(reason: str, do_first: str) -> dict:
    """A refusal that says so and says what to do, not an empty answer: nothing found and a tool that could not run look
    the same to a model when the answer is nothing at all."""
    return {"refused": reason, "do_first": do_first}


def excerpt(text: str, limit: int = SUMMARY_CHARS) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit].rstrip() + "…"
