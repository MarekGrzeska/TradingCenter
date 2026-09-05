"""The session with `market-mcp`, and the one place the `mcp` package is imported — a deliberate twin of agent's, with
one divergence: agent answers `[]` when a server cannot be asked, while this raises rather than let agents guess."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import McpError
from tc_mcp_kit.outbound_identity import ManagedIdentityAuth

from ..config import Settings

log = logging.getLogger(__name__)

# What the SDK turns a `404` on `POST /mcp` into. The status never reaches this file, so the string is the
# only handle there is — brittle on purpose: a real client drives a real forgetful server in the tests.
_SESSION_GONE_CODE = 32600
_SESSION_GONE_MESSAGE = "Session terminated"

# FastMCP's own default, and market-mcp does not override it (`server.py`, which builds
# `streamable_http_app()` and wraps it without touching the route).
MCP_PATH = "/mcp"


class ToolAccessError(RuntimeError):
    """Anything that stops a run before an agent is called. The run start catches this one type; the
    subclasses say which of the two things went wrong, for the message and for the trace."""


class ToolServerUnavailable(ToolAccessError):
    """The server could not be asked at all — unconfigured, unreachable, too slow, or it
    refused this module's identity. Nothing is known about the tools either way."""


@dataclass(frozen=True)
class ToolDescriptor:
    """One tool as the server announced it. `input_schema` is JSON Schema and is handed to the provider
    unread: a second opinion here would only be a second thing to keep in step."""

    name: str
    description: str
    input_schema: dict[str, Any]
    # From the server's own `readOnlyHint` — `None` when a tool carries no annotation at all, which
    # `GET /tools` reads as "unknown" rather than guessing.
    read_only: bool | None = None


class ToolOutcomeKind(StrEnum):
    OK = "ok"
    # The server answered, and its answer is "not like that". Carries the sentence
    # market-mcp writes for exactly this: what to change so the call would work.
    REFUSED = "refused"
    # The server did not answer at all — unreachable, timed out, refused the identity.
    # Nothing was asked, so nothing about the archive is known either way.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ToolOutcome:
    kind: ToolOutcomeKind
    text: str
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.kind is ToolOutcomeKind.OK



class ToolServer:
    """One MCP session over one server, named by which triplet of `Settings` fields it reads. `can_move_the_account`
    marks the one server whose writes land somewhere this module cannot look afterwards."""

    def __init__(
        self,
        settings: Settings,
        *,
        prefix: str = "market_mcp",
        can_move_the_account: bool = False,
    ) -> None:
        self.label = prefix.replace("_", "-")
        self.can_move_the_account = can_move_the_account
        self._env_prefix = prefix.upper()
        self._url: str | None = getattr(settings, f"{prefix}_url")
        self._scope: str | None = getattr(settings, f"{prefix}_scope")
        self._timeout: float = getattr(settings, f"{prefix}_request_timeout_seconds")
        self._credential = DefaultAzureCredential() if self._scope else None

        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[ToolDescriptor] | None = None
        # Guards connecting and reconnecting. A run works several agents at once, so two arriving while
        # the session is down must not open two sessions.
        self._lock = asyncio.Lock()

        if self._url is None:
            log.info("%s: no tool server configured — only teams assigning no tools can run", self.label)
        else:
            log.info(
                "%s: tool server at %s, authenticating with a managed identity: %s",
                self.label,
                self._url,
                f"scope={self._scope}" if self._scope else "no (loopback)",
            )

    @property
    def configured(self) -> bool:
        return self._url is not None

    async def aclose(self) -> None:
        await self._disconnect()
        if self._credential is not None:
            await self._credential.close()

    async def list_tools(self) -> list[ToolDescriptor]:
        """What the server publishes right now, read once per session. Raises rather than answering `[]`:
        an empty list is still a possible answer and means the server was asked and announces nothing."""
        if self._url is None:
            raise ToolServerUnavailable(
                f"no tool server is configured ({self._env_prefix}_URL is unset), so "
                f"its tools could not be read"
            )
        if self._tools is not None:
            return self._tools
        try:
            result = await self._listed()
        except TimeoutError as err:
            await self._disconnect()
            raise ToolServerUnavailable(
                f"the {self.label} tool server at {self._url} did not answer within "
                f"{self._timeout:g}s"
            ) from err
        except Exception as err:
            # Every failure here means the same thing to a caller — the server could not be asked. The one
            # exception is a session the server has forgotten, which is worth one reopening.
            await self._disconnect()
            if not _session_is_gone(err):
                raise ToolServerUnavailable(
                    f"the {self.label} tool server at {self._url} could not be reached: "
                    f"{_describe(err)}"
                ) from err
            log.info("%s: the tool list was refused as an unknown session — reopening", self.label)
            try:
                result = await self._listed()
            except Exception as second:
                await self._disconnect()
                raise ToolServerUnavailable(
                    f"the {self.label} tool server at {self._url} could not be reached "
                    f"after reopening the session: {_describe(second)}"
                ) from second
        self._tools = [
            ToolDescriptor(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
                read_only=tool.annotations.readOnlyHint if tool.annotations else None,
            )
            for tool in result.tools
        ]
        log.info("%s: tool server published %d tools", self.label, len(self._tools))
        return self._tools

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        """One logical call, and at most two requests: the second happens only when the server rejected the first as
        belonging to a session it does not know. A restart on the other side is the ordinary way that happens."""
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        if self._url is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"no tool server is configured ({self.label}), so this call was not made",
                elapsed(),
            )
        try:
            result = await self._send(name, arguments)
        except TimeoutError:
            await self._disconnect()
            return ToolOutcome(ToolOutcomeKind.UNAVAILABLE, self._timed_out(), elapsed())
        except Exception as err:  # noqa: BLE001 - a broken session is not a broken run
            await self._disconnect()
            if not _session_is_gone(err):
                log.warning("tool call %s failed against %s: %s", name, self._url, _describe(err))
                return ToolOutcome(
                    ToolOutcomeKind.UNAVAILABLE, self._unreachable(err), elapsed()
                )
            log.info(
                "%s: %s was refused as an unknown session — reopening and sending it once more",
                self.label,
                name,
            )
            try:
                result = await self._send(name, arguments)
            except TimeoutError:
                await self._disconnect()
                return ToolOutcome(ToolOutcomeKind.UNAVAILABLE, self._timed_out(), elapsed())
            except Exception as second:  # noqa: BLE001 - same reason as above
                log.warning(
                    "tool call %s failed against %s after reopening the session: %s",
                    name,
                    self._url,
                    _describe(second),
                )
                await self._disconnect()
                return ToolOutcome(
                    ToolOutcomeKind.UNAVAILABLE, self._unreachable(second), elapsed()
                )

        if result.isError:
            # market-mcp's refusals are written for a reader who can act on them, so its own words travel
            # rather than a summary. A refusal has no structured output — the SDK reports prose only.
            return ToolOutcome(ToolOutcomeKind.REFUSED, _text_of(result.content), elapsed())
        # A tool whose return type is a bare list is not one text block but one per item, because the SDK
        # recurses into a list. `structuredContent` is its own well-formed answer, built before the split.
        text = (
            json.dumps(result.structuredContent)
            if result.structuredContent is not None
            else _text_of(result.content)
        )
        return ToolOutcome(ToolOutcomeKind.OK, text, elapsed())

    async def _listed(self):
        """One `tools/list`, on whatever session is open — reopening one if none is."""
        session = await self._connected_session()
        return await asyncio.wait_for(session.list_tools(), timeout=self._timeout)

    async def _send(self, name: str, arguments: dict[str, Any]):
        """One request, on whatever session is open — reopening one if none is."""
        session = await self._connected_session()
        return await asyncio.wait_for(session.call_tool(name, arguments), timeout=self._timeout)

    def _timed_out(self) -> str:
        return (
            f"the {self.label} tool server did not answer within {self._timeout:g}s. "
            "The call was not made — this says nothing about what the tool would "
            "have answered."
        )

    def _unreachable(self, err: BaseException) -> str:
        return (
            f"the {self.label} tool server could not be reached: {_describe(err)}. "
            "The call was not made — this says nothing about what the tool would "
            "have answered."
        )

    async def _connected_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            assert self._url is not None
            stack = AsyncExitStack()
            try:
                auth = (
                    ManagedIdentityAuth(self._credential, self._scope)
                    if self._credential is not None and self._scope is not None
                    else None
                )
                # `create_mcp_http_client` rather than a bare `httpx.AsyncClient`: the transport relies on
                # defaults it sets. `read` is left long; per-call time is bounded at the call sites.
                http_client = await stack.enter_async_context(
                    create_mcp_http_client(
                        timeout=httpx.Timeout(self._timeout, read=None), auth=auth
                    )
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(f"{self._url}{MCP_PATH}", http_client=http_client)
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=self._timeout)
            except BaseException:
                await stack.aclose()
                raise
            self._stack = stack
            self._session = session
            return session

    async def _disconnect(self) -> None:
        """Drops the session so the next call opens a fresh one. The tool list goes with it: a server that
        restarted may publish a different set, and holding the old one would be keeping a copy."""
        stack, self._stack = self._stack, None
        self._session = None
        self._tools = None
        if stack is None:
            return
        try:
            await stack.aclose()
        except Exception as err:  # noqa: BLE001 - closing a broken stream often raises
            log.debug("closing the tool session raised on the way out: %s", err)


@dataclass(frozen=True)
class ToolServerRegistry:
    """Every tool server this module knows about, by label — a registry in place of the one `ToolServer` earlier groups
    built around. A source in this process is not one of them, and is kept in `local` for that reason."""

    servers: dict[str, ToolServer]
    # Sources this process serves itself. Not `servers`, because none of what that word implies is true of
    # them — no address, no identity, no session — and "which servers could not be reached" stays honest.
    local: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings: Settings, *, pool: Any | None = None) -> ToolServerRegistry:
        """Every source this module offers. `pool` is needed only to *call* the in-process tools —
        announcing them does not touch it, which lets the save-time paths build from settings alone."""
        from .memory import LABEL as MEMORY_LABEL
        from .memory import MemoryToolSource

        return cls(
            {
                "market-mcp": ToolServer(settings, prefix="market_mcp"),
                "trading-mcp": ToolServer(
                    settings, prefix="trading_mcp", can_move_the_account=True
                ),
                # No polymarket server: that archive is a package of this process, and the assembly
                # adds its tools to `local` — no address, no identity, no session.
                "social-mcp": ToolServer(settings, prefix="social_mcp"),
                # Sends a notification, and that is all it can do here: creating a bot and binding a
                # destination are REST-only in that module, out of reach of any team.
                "telegram-mcp": ToolServer(settings, prefix="telegram_mcp"),
                # The one a trigger reads: `pending_setups` is a number the clock compares against a
                # threshold, and it arrives here the same way every other reading does.
                "strategy-mcp": ToolServer(settings, prefix="strategy_mcp"),
            },
            {MEMORY_LABEL: MemoryToolSource(pool)},
        )

    def configured(self) -> list[Any]:
        """Every source that can be asked what it publishes — remote and local together,
        which is what resolving a name has to walk."""
        return self.remote() + list(self.local.values())

    def remote(self) -> list[ToolServer]:
        """Only the servers on the other end of a network. The distinction matters where a refusal has to
        name what is missing: "no tool server is configured" would be false of the registry as a whole."""
        return [server for server in self.servers.values() if server.configured]

    def unconfigured(self) -> list[str]:
        """Labels of the servers this module knows about and has no address for."""
        return sorted(
            label for label, server in self.servers.items() if not server.configured
        )

    async def aclose(self) -> None:
        for server in self.servers.values():
            await server.aclose()
        for source in self.local.values():
            await source.aclose()


def _describe(err: BaseException) -> str:
    """The cause, not the wrapper. Both halves run in an anyio task group, so a refused connection surfaces
    as "unhandled errors in a TaskGroup" — a sentence that names nothing. Groups nest, so this recurses."""
    if isinstance(err, BaseExceptionGroup):
        inner = [_describe(sub) for sub in err.exceptions]
        # Deduplicated: a group of five identical connection refusals is one fact.
        unique = list(dict.fromkeys(part for part in inner if part))
        if unique:
            return "; ".join(unique)
    text = str(err).strip()
    return text or type(err).__name__


def _session_is_gone(err: BaseException) -> bool:
    """Whether the server refused this request as belonging to a session it does not know. Recurses into
    groups for `_describe`'s reason: what reaches a caller is often the error wrapped in one."""
    if isinstance(err, BaseExceptionGroup):
        return any(_session_is_gone(sub) for sub in err.exceptions)
    return (
        isinstance(err, McpError)
        and err.error.code == _SESSION_GONE_CODE
        and err.error.message == _SESSION_GONE_MESSAGE
    )


def _text_of(content: list[Any]) -> str:
    """Text blocks only, joined. market-mcp answers in prose by design, so a non-text block is something new
    on that side, named here rather than dropped silently."""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(f"[{getattr(block, 'type', 'unknown')} content, not shown]")
    return "\n".join(parts)
