"""The team tools as the conversation's registry sees them — the adapter between them. It lives here because
it is the one thing that knows both `agent`'s tool-source protocol and `teams_tools`' registry.

A drop-in for a `ToolServer`, so nothing above the registry had to learn that one of its sources is not on
a network: it is always configured, nothing is retried, no session can be gone, and `moves_the_account` is
always false. What a tool raises becomes an outcome rather than an exception, exactly as it does over the wire."""

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
        """What the model may call this turn. Read from the registry rather than from a session, so it
        cannot fail — and it does not depend on who is asking, which is why the argument is ignored."""
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
        """One tool call, in the operator's name and inside this process. The identity is set for the
        duration and reset after, and it is the only way it reaches the tool."""
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
    """What the model reads. `call_tool` answers a `(content, structured)` pair for a tool with a declared
    output schema, and the structured half is the one to read: content blocks are one per item, and joining
    them hands a reader expecting one JSON document several of them back to back."""
    if isinstance(result, tuple) and len(result) == 2:
        return json.dumps(result[1])
    if isinstance(result, dict):
        return json.dumps(result)
    return "\n".join(
        block.text for block in result if getattr(block, "type", None) == "text"
    ).strip()
