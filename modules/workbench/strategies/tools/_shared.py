"""What every tool module here needs, kept out of `__init__.py`."""

from __future__ import annotations

import json
from dataclasses import dataclass

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..problems import Problem

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
# A revision is the next row and a run is counted; neither destroys anything, and neither is the same call twice.
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)


# Gone for good: the one tool here whose effect a client may want to confirm before it runs.
DELETES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs from the running application, read when the tool is called: everything it reads is put on
    `app.state` by the lifespan, after the server was built."""

    app: object

    @property
    def state(self):
        return self.app.state  # pyright: ignore[reportAttributeAccessIssue]


def refusal(detail: str, problems: list[Problem] | None = None) -> ToolError:
    """A refusal the model can act on: the reason, and every problem with its path, column and hint."""
    if not problems:
        return ToolError(detail)
    return ToolError(json.dumps({"detail": detail, "problems": [p.as_dict() for p in problems]}, ensure_ascii=False))
