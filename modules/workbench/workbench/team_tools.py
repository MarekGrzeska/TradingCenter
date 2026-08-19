"""The team tools as the conversation's registry sees them — the adapter between them.

It lives here rather than in either package because it is the one thing that knows both:
`agent`'s tool-source protocol and `teams_tools`' FastMCP registry. `teams_tools` imports
neither of the other two — its client takes an application object, not a package — and
`agent` does not know these tools are local. The assembly is the only layer allowed to
know both, and `tests/test_layering.py` is what keeps it that way.


A drop-in for a `ToolServer` (`agent/tools/client.py`): same `configured`, `label`,
`list_tools`, `moves_the_account`, `call`, `aclose` — so nothing above the registry had to
learn that one of its sources is not on a network. That is the whole of what this file is
for; the tools themselves are unchanged, and so are their descriptions, their schemas and
the wording of every refusal.

Three differences from a `ToolServer`, all of them subtractions:

* **`configured` is always true.** There is no address to leave unset, so there is no state
  in which the conversation has no team tools. The two network sources keep theirs.
* **Nothing is retried and no session can be gone.** A `ToolServer` reopens a session the
  server has forgotten; there is no session here, and a failure is the tool's own.
* **`moves_the_account` is always false.** Nothing here reaches the account — that is
  trading-mcp's, one source over.

What a tool raises becomes an outcome rather than an exception, exactly as it does over the
network: a turn that dies because a catalogue refused is a worse answer than a turn that
says so.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError
from starlette.types import ASGIApp

from agent.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind
from teams_tools.client import TeamsClient
from teams_tools.operator import carrying
from teams_tools.server import build_server, say_whose_name_the_tools_act_in

log = logging.getLogger(__name__)


class LocalTeamsTools:
    """Built once, in the lifespan, over the application it will call back into."""

    label = "team tools"
    configured = True

    def __init__(self, app: ASGIApp, *, operator_identity_optional: bool) -> None:
        say_whose_name_the_tools_act_in(operator_identity_optional)
        self._client = TeamsClient(app, operator_identity_optional=operator_identity_optional)
        self._mcp = build_server(self._client)
        self._tools: list[ToolDescriptor] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_tools(self, operator_principal: str | None = None) -> list[ToolDescriptor]:
        """What the model may call this turn.

        Read from the registry rather than from a session, so it cannot fail and cannot be
        empty for a reason worth reporting — and it does not depend on who is asking, which
        is why the argument is accepted and ignored: the registry hands every source the
        same one.
        """
        if self._tools is None:
            self._tools = [
                ToolDescriptor(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    read_only=tool.annotations.readOnlyHint if tool.annotations else None,
                )
                for tool in await self._mcp.list_tools()
            ]
            log.info("%s: published %d tools", self.label, len(self._tools))
        return self._tools

    def moves_the_account(self, name: str) -> bool:
        return False

    async def call(
        self, name: str, arguments: dict[str, Any], operator_principal: str | None = None
    ) -> ToolOutcome:
        """One tool call, in the operator's name and inside this process.

        The identity is set for the duration of the call and reset after it, including when
        the tool raises (`operator.carrying`). It is the only way it reaches the tool: a
        model that writes a principal into an argument is writing into a field nothing
        reads.
        """
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            with carrying(operator_principal):
                result = await self._mcp.call_tool(name, arguments)
        except ToolError as err:
            # Everything a tool raises arrives wrapped in this, including the refusals the
            # tools write deliberately — so the text a `ToolServer` would have received
            # from the far side as `isError` is the text of this exception. The tools'
            # own words travel rather than a summary of them.
            return ToolOutcome(ToolOutcomeKind.REFUSED, str(err), elapsed())
        except Exception as err:  # noqa: BLE001 - a broken tool is not a broken turn
            log.warning("tool call %s failed: %s", name, err)
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"the team tools could not answer {name!r}: {err}. The call was not made.",
                elapsed(),
            )

        return ToolOutcome(ToolOutcomeKind.OK, _text_of(result), elapsed())


def _text_of(result: Any) -> str:
    """What the model reads.

    `call_tool` answers a `(content, structured)` pair for a tool with a declared output
    schema — which is every tool here, since each returns a pydantic model — and bare
    content blocks otherwise. The structured half is the one to read, for the reason
    `agent/tools/client.py` gives about a list-returning tool: content blocks are one per
    item, and joining them hands a reader expecting one JSON document several of them back
    to back.
    """
    if isinstance(result, tuple) and len(result) == 2:
        return json.dumps(result[1])
    if isinstance(result, dict):
        return json.dumps(result)
    return "\n".join(
        block.text for block in result if getattr(block, "type", None) == "text"
    ).strip()
