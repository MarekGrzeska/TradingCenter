"""The session with `market-mcp`, and the one place the `mcp` package is imported. Three responsibilities easy to
conflate: what tools exist, asked once per session; three outcomes rather than two; and never raising into the turn."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
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
_MAY_HAVE_LANDED = (
    "The call may have gone through — do not send it again. Tell the operator the "
    "outcome is unknown and that they should check the account."
)
_WAS_NOT_MADE = "The call was not made — this says nothing about the archive's own data."

_SESSION_GONE_CODE = 32600
_SESSION_GONE_MESSAGE = "Session terminated"

# FastMCP's own default, and market-mcp does not override it (`server.py`, which builds
# `streamable_http_app()` and wraps it without touching the route).
MCP_PATH = "/mcp"

# No header for an operator's own credential any more: every server reached from here is reached on this
# module's own identity. The one tool source that acts for a person is not on a network at all.


@dataclass(frozen=True)
class ToolDescriptor:
    """One tool as the server announced it. `input_schema` is JSON Schema and is handed to the provider
    unread: a second opinion here would only be a second thing to keep in step."""

    name: str
    description: str
    input_schema: dict[str, Any]
    # From the server's own `readOnlyHint`. `None` means the tool carried no annotation at all, which is
    # not the same as "reads" — the difference decides how a call that never answered is recorded.
    read_only: bool | None = None


class ToolOutcomeKind(StrEnum):
    OK = "ok"
    # The server answered, and its answer is "not like that". Carries the sentence
    # market-mcp writes for exactly this: what to change so the call would work.
    REFUSED = "refused"
    # The server did not answer at all — unreachable, timed out, refused the identity.
    # Nothing was asked, so nothing about the archive is known either way.
    UNAVAILABLE = "unavailable"
    # The server did not answer *and* the call may have landed anyway. Only ever produced for a call that
    # can change the account. Kept apart from UNAVAILABLE: retry the read, never the order.
    UNKNOWN = "unknown"


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
    decides nothing about how a call is made and everything about how one that did not answer is recorded."""

    def __init__(
        self,
        settings: Settings,
        *,
        prefix: str = "market_mcp",
        can_move_the_account: bool = False,
    ) -> None:
        self.label = prefix.replace("_", "-")
        self._env_prefix = prefix.upper()
        self.can_move_the_account = can_move_the_account
        self._url: str | None = getattr(settings, f"{prefix}_url")
        self._scope: str | None = getattr(settings, f"{prefix}_scope")
        self._timeout: float = getattr(settings, f"{prefix}_request_timeout_seconds")
        self._credential = DefaultAzureCredential() if self._scope else None

        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[ToolDescriptor] | None = None
        # Guards connecting and reconnecting. Turns run as concurrent background tasks,
        # and two of them arriving while the session is down must not open two.
        self._lock = asyncio.Lock()

        if self._url is None:
            log.info("%s: not configured — the agent runs without its tools", self.label)
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

    async def list_tools(self, operator_principal: str | None = None) -> list[ToolDescriptor]:
        """What the model may call this turn. An empty list is the answer whenever the server is not configured or not
        reachable, so the caller runs the turn without tools; `operator_principal` is accepted and ignored for one signature."""
        if self._url is None:
            return []
        if self._tools is not None:
            return self._tools
        try:
            async with self._session_for() as session:
                result = await asyncio.wait_for(session.list_tools(), timeout=self._timeout)
        except Exception as err:  # noqa: BLE001 - every failure here means "no tools"
            log.warning(
                "%s: could not read the tool list from %s: %s",
                self.label,
                self._url,
                _describe(err),
            )
            await self._disconnect()
            return []
        self._tools = [
            ToolDescriptor(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
                read_only=tool.annotations.readOnlyHint if tool.annotations else None,
            )
            for tool in result.tools
        ]
        log.info("%s: published %d tools", self.label, len(self._tools))
        return self._tools

    def moves_the_account(self, name: str) -> bool:
        """Whether a call to `name` could leave the account changed even if nothing comes back. Asked before
        the call. A tool we hold no descriptor for counts as moving it: a row too many beats none."""
        if not self.can_move_the_account:
            return False
        for tool in self._tools or ():
            if tool.name == name:
                return tool.read_only is not True
        return True

    async def call(
        self, name: str, arguments: dict[str, Any], operator_principal: str | None = None
    ) -> ToolOutcome:
        """One logical call, and at most two requests: the second only when the server rejected the first as belonging
        to a session it does not know. Without the retry an order reads as `UNKNOWN` and sends the operator to check nothing."""
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        if self._url is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"the {self.label} tool server is not configured, so this call was not made",
                elapsed(),
            )
        # Asked before anything is dispatched, because `_disconnect()` below drops the
        # tool list and with it the only thing that could answer this afterwards.
        may_have_landed = self.moves_the_account(name)
        try:
            result = await self._send(name, arguments)
        except TimeoutError:
            await self._disconnect()
            return ToolOutcome(*self._timed_out(may_have_landed), elapsed())
        except Exception as err:  # noqa: BLE001 - a broken session is not a broken turn
            await self._disconnect()
            if not _session_is_gone(err):
                log.warning("tool call %s failed against %s: %s", name, self._url, _describe(err))
                return ToolOutcome(*self._unreachable(err, may_have_landed), elapsed())
            log.info(
                "%s: %s was refused as an unknown session — reopening and sending it once more",
                self.label,
                name,
            )
            try:
                result = await self._send(name, arguments)
            except TimeoutError:
                await self._disconnect()
                return ToolOutcome(*self._timed_out(may_have_landed), elapsed())
            except Exception as second:  # noqa: BLE001 - same reason as above
                log.warning(
                    "tool call %s failed against %s after reopening the session: %s",
                    name,
                    self._url,
                    _describe(second),
                )
                await self._disconnect()
                return ToolOutcome(*self._unreachable(second, may_have_landed), elapsed())

        if result.isError:
            # market-mcp's refusals are written for a reader who can act on them, so its own words travel
            # rather than a summary. A refusal has no structured output — the SDK reports prose only.
            return ToolOutcome(ToolOutcomeKind.REFUSED, _text_of(result.content), elapsed())
        # A tool whose return type is a bare list is not one text block but one per item, because the SDK
        # recurses into a list. `structuredContent` is its own well-formed answer to that.
        text = (
            json.dumps(result.structuredContent)
            if result.structuredContent is not None
            else _text_of(result.content)
        )
        return ToolOutcome(ToolOutcomeKind.OK, text, elapsed())

    async def _send(self, name: str, arguments: dict[str, Any]) -> Any:
        """One request. Separate from `call` so the retry above is the same request
        twice rather than two spellings of it."""
        async with self._session_for() as session:
            return await asyncio.wait_for(session.call_tool(name, arguments), timeout=self._timeout)

    def _timed_out(self, may_have_landed: bool) -> tuple[ToolOutcomeKind, str]:
        opening = f"the tool server did not answer within {self._timeout:g}s."
        if may_have_landed:
            return ToolOutcomeKind.UNKNOWN, f"{opening} {_MAY_HAVE_LANDED}"
        return ToolOutcomeKind.UNAVAILABLE, f"{opening} {_WAS_NOT_MADE}"

    def _unreachable(
        self, err: BaseException, may_have_landed: bool
    ) -> tuple[ToolOutcomeKind, str]:
        opening = f"the tool server could not be reached: {_describe(err)}."
        if may_have_landed:
            return ToolOutcomeKind.UNKNOWN, f"{opening} {_MAY_HAVE_LANDED}"
        return ToolOutcomeKind.UNAVAILABLE, f"{opening} {_WAS_NOT_MADE}"

    @asynccontextmanager
    async def _session_for(self) -> AsyncIterator[ClientSession]:
        """One session for the life of the process — the credential this module presents never varies, so a
        connection is paid for once. The branch for a per-person credential went with the server that needed it."""
        yield await self._connected_session()

    async def _connected_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            stack = AsyncExitStack()
            try:
                session = await self._open(stack)
            except BaseException:
                await stack.aclose()
                raise
            self._stack = stack
            self._session = session
            return session

    async def _open(self, stack: AsyncExitStack) -> ClientSession:
        assert self._url is not None
        auth = (
            ManagedIdentityAuth(self._credential, self._scope)
            if self._credential is not None and self._scope is not None
            else None
        )
            # `create_mcp_http_client` rather than a bare `httpx.AsyncClient`: the transport relies on
            # defaults it sets. `read` is left long; per-call time is bounded at the call sites instead.
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
    """Whether the server refused this request as belonging to a session it does not know. Byte for byte the
    same as `teams/tools/client.py`'s, so a correction travels by copying rather than by rewriting."""
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
