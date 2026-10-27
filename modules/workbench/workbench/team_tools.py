"""The team tools as the conversation's registry sees them, and the one thing that knows both `agent`'s tool-source
protocol and `teams_tools`' registry: a drop-in `ToolServer`, always configured, never retried, raising nothing. And the
same tools under `/team-tools/mcp`, for the operator's own MCP client (`operator-mcp-access`)."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send
from tc_mcp_kit.mounted_server import MOUNT_PATH, ToolSurfaceAddress, tool_surface_session
from tc_runtime.caller_access import CallerAccess, Record, in_process

from agent.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind
from teams_tools.client import TeamsClient
from teams_tools.operator import carrying
from teams_tools.server import build_network_server, build_server, say_whose_name_the_tools_act_in

from .config import Settings

log = logging.getLogger(__name__)


class LocalTeamsTools:
    """Built once, in the lifespan, over the application it will call back into."""

    label = "team tools"
    configured = True

    def __init__(self, app: ASGIApp, *, operator_identity_optional: bool) -> None:
        say_whose_name_the_tools_act_in(operator_identity_optional)
        # As this process: the root's own caller record (`root_access.py`) admits no application it cannot name.
        self._client = TeamsClient(
            in_process(app, "the conversation's team tools"),
            operator_identity_optional=operator_identity_optional,
        )
        self._mcp = build_server(self._client)
        self._tools: list[ToolDescriptor] | None = None

    def network_server(self) -> FastMCP:
        """The same tools over the same client, for the network surface below."""
        return build_network_server(self._client)

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
            # Everything a tool raises arrives wrapped in this, including the refusals the tools write deliberately,
            # so the tools' own words travel where a `ToolServer` would have received `isError` text.
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
    """What the model reads: `call_tool` answers a `(content, structured)` pair for a tool with an output schema, and the
    structured half is the one to read — content blocks are one per item, and joining them hands back several documents."""
    if isinstance(result, tuple) and len(result) == 2:
        return json.dumps(result[1])
    if isinstance(result, dict):
        return json.dumps(result)
    return "\n".join(
        block.text for block in result if getattr(block, "type", None) == "text"
    ).strip()


# Tools alone: nothing here is REST, and nothing answers without an identity.
SURFACE_RECORD = Record(
    open_paths=frozenset(),
    rest_paths=(),
    tools_prefix=MOUNT_PATH,
    starting_detail="the team tools are still starting",
)


def create_surface() -> Starlette:
    """Mounted at import, under `/team-tools`; the server behind it is built in the lifespan, once the client it calls
    through exists, and read off the state per request."""
    surface = Starlette()
    surface.router.routes.append(Mount(MOUNT_PATH, app=_ServerOnTheState(surface.state)))
    # In this order, as in every package: the address fix runs before routing, and the caller record before that.
    surface.add_middleware(ToolSurfaceAddress)
    surface.add_middleware(CallerAccess, state=surface.state, record=SURFACE_RECORD)
    return surface


class _ServerOnTheState:
    def __init__(self, state) -> None:
        self._state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        server = getattr(self._state, "mcp_server", None)
        if server is None:
            await JSONResponse({"detail": "the team tools are still starting"}, status_code=503)(scope, receive, send)
            return
        await server.session_manager.handle_request(scope, receive, send)


@asynccontextmanager
async def serving(surface: Starlette, tools: LocalTeamsTools, settings: Settings):
    """`CallerAccess` reads the process's own tool list and principal requirement; with no REST path it reads nothing else."""
    surface.state.mcp_server = tools.network_server()
    surface.state.settings = settings
    async with tool_surface_session(surface):
        yield
