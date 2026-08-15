"""The session with `market-mcp`, and the one place the `mcp` package is imported.

Three things this file is responsible for, and they are easy to conflate:

- **What tools exist.** Asked once per session with the server and kept in the process,
  not asked per turn — the same choice market-mcp made for its own indicator catalogue.
  Nothing is committed and nothing is checked before start: MCP describes itself, so the
  contract travels in the session that uses it (specs/agent-tool-access, "Moduł nie
  trzyma kopii tego, co ogłasza serwer narzędzi").
- **Three outcomes, not two.** A tool that answered "not like that" and a server that
  did not answer at all are different facts, and the model can act on the first
  (specs/agent-tool-access, "Przekroczenie czasu MUST być odróżnialne od odmowy
  narzędzia").
- **Never raising into the turn.** Every failure here comes back as a `ToolOutcome`.
  A turn that dies because the archive is busy is a worse answer than a turn that says
  so.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from ..config import Settings

log = logging.getLogger(__name__)

# FastMCP's own default, and market-mcp does not override it (`server.py`, which builds
# `streamable_http_app()` and wraps it without touching the route).
MCP_PATH = "/mcp"


@dataclass(frozen=True)
class ToolDescriptor:
    """One tool as the server announced it. `input_schema` is JSON Schema and is handed
    to the provider unread — this module does not validate arguments the server already
    describes, and a second opinion here would only be a second thing to keep in step."""

    name: str
    description: str
    input_schema: dict[str, Any]


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


class _ManagedIdentityAuth(httpx.Auth):
    """A bearer token per request rather than per connection.

    The streamable-http transport fixes its headers when the connection opens, and a
    session outliving its token would start failing mid-conversation for a reason that
    reads like nothing at all. `DefaultAzureCredential` caches internally and only
    reaches the identity endpoint again near expiry, so this is not a round trip per
    call — the same reasoning market-mcp's own client documents on its side of this
    seam.
    """

    def __init__(self, credential: DefaultAzureCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    async def async_auth_flow(self, request: httpx.Request):
        token = await self._credential.get_token(self._scope)
        request.headers["Authorization"] = f"Bearer {token.token}"
        yield request


class ToolServer:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.market_mcp_url
        self._scope = settings.market_mcp_scope
        self._timeout = settings.market_mcp_request_timeout_seconds
        self._credential = DefaultAzureCredential() if self._scope else None

        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[ToolDescriptor] | None = None
        # Guards connecting and reconnecting. Turns run as concurrent background tasks,
        # and two of them arriving while the session is down must not open two.
        self._lock = asyncio.Lock()

        if self._url is None:
            log.info("no tool server configured — the agent runs without tools")
        else:
            log.info(
                "tool server at %s, authenticating with a managed identity: %s",
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
        """What the model may call this turn. An empty list is the answer whenever the
        server is not configured or not reachable — the caller's job is to run the turn
        without tools, not to fail it (specs/agent-tool-access, "Brak serwera narzędzi
        nie odbiera agentowi mowy")."""
        if self._url is None:
            return []
        if self._tools is not None:
            return self._tools
        try:
            session = await self._connected_session()
            result = await asyncio.wait_for(session.list_tools(), timeout=self._timeout)
        except Exception as err:  # noqa: BLE001 - every failure here means "no tools"
            log.warning("could not read the tool list from %s: %s", self._url, _describe(err))
            await self._disconnect()
            return []
        self._tools = [
            ToolDescriptor(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
            )
            for tool in result.tools
        ]
        log.info("tool server published %d tools", len(self._tools))
        return self._tools

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        if self._url is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                "no tool server is configured, so this call was not made",
                elapsed(),
            )
        try:
            session = await self._connected_session()
            result = await asyncio.wait_for(
                session.call_tool(name, arguments), timeout=self._timeout
            )
        except TimeoutError:
            await self._disconnect()
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"the tool server did not answer within {self._timeout:g}s. The call was "
                "not made — this says nothing about the archive's own data.",
                elapsed(),
            )
        except Exception as err:  # noqa: BLE001 - a broken session is not a broken turn
            log.warning("tool call %s failed against %s: %s", name, self._url, _describe(err))
            await self._disconnect()
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"the tool server could not be reached: {_describe(err)}. The call was not "
                "made — this says nothing about the archive's own data.",
                elapsed(),
            )

        if result.isError:
            # market-mcp's refusals are written for a reader who can act on them, so its
            # own words travel rather than a summary of them (specs/agent-tools, "Odmowa
            # narzędzia jest wynikiem, nie awarią tury"). A refusal has no structured
            # output — the SDK reports it as unstructured prose only.
            return ToolOutcome(ToolOutcomeKind.REFUSED, _text_of(result.content), elapsed())
        # A tool whose return type is a bare list — `list_tracked_pairs`, e.g. — is not
        # one text block but one *per item*, because `_convert_to_content` recurses into
        # a list rather than serializing it whole. Joining those with `_text_of` below
        # would hand a reader expecting one JSON document N of them back to back — valid
        # for nothing (`json.loads` sees "Extra data" past the first), and silently wrong
        # for exactly one (a single object, not the one-item array it should be).
        # `structuredContent` is the SDK's own well-formed answer to that, built from the
        # same return value before it gets split apart for `content` — read it when the
        # server declared one instead of reassembling it by hand from prose blocks meant
        # for a model to read, not a parser.
        text = json.dumps(result.structuredContent) if result.structuredContent is not None else _text_of(result.content)
        return ToolOutcome(ToolOutcomeKind.OK, text, elapsed())

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
                    _ManagedIdentityAuth(self._credential, self._scope)
                    if self._credential is not None and self._scope is not None
                    else None
                )
                # `create_mcp_http_client` rather than a bare `httpx.AsyncClient`: the
                # transport relies on defaults it sets (redirects, in particular), and
                # a client built by hand here would be a second place to keep them.
                # `read` is left long — the connection carries the session's own event
                # stream and is meant to stay open between calls; per-call time is
                # bounded by `asyncio.wait_for` at the call sites instead.
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
        """Drops the session so the next call opens a fresh one. The tool list goes with
        it: a server that restarted may be publishing a different set, and holding the
        old one would be this module keeping exactly the copy it is not supposed to."""
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
    """The cause, not the wrapper.

    Both the streamable-http transport and the MCP session run their halves in an anyio
    task group, so a refused connection surfaces as `unhandled errors in a TaskGroup
    (1 sub-exception)` — a sentence that names nothing. It reached a live run before it
    reached this function, and the model would have been handed it verbatim. Groups
    nest, so this recurses.
    """
    if isinstance(err, BaseExceptionGroup):
        inner = [_describe(sub) for sub in err.exceptions]
        # Deduplicated: a group of five identical connection refusals is one fact.
        unique = list(dict.fromkeys(part for part in inner if part))
        if unique:
            return "; ".join(unique)
    text = str(err).strip()
    return text or type(err).__name__


def _text_of(content: list[Any]) -> str:
    """Text blocks only, joined. market-mcp answers in prose by design — its ceilings,
    its aggregation notes and its refusals are all sentences — so a non-text block is
    something new on that side, named here rather than dropped silently."""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(f"[{getattr(block, 'type', 'unknown')} content, not shown]")
    return "\n".join(parts)
