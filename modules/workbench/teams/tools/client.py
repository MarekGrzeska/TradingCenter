"""The session with `market-mcp`, and the one place the `mcp` package is imported.

A deliberate twin of `agent/tools/client.py`, copied rather than shared — there is no
library between modules, and the seam this file sits on is one both of them own
separately. Three responsibilities carry over unchanged:

- **What tools exist.** Asked once per session with the server and kept in the process.
  Nothing is committed and nothing is checked before start: MCP describes itself, so the
  contract travels in the session that uses it (specs/teams-tool-access, "Moduł nie
  trzyma kopii tego, co ogłasza serwer narzędzi").
- **Three outcomes, not two.** A tool that answered "not like that" and a server that did
  not answer at all are different facts (specs/teams-tool-access, "Przekroczenie czasu
  MUST być odróżnialne od odmowy narzędzia").
- **A call never raises into the run.** Every failure of `call` comes back as a
  `ToolOutcome`, so one unreachable tool costs an agent its answer rather than costing
  the run its trace.

**One divergence from the twin, and it is the point of this module's own spec.**
`agent.list_tools()` answers `[]` when the server cannot be asked, because a turn without
tools is a worse answer and still an answer. Here it raises `ToolServerUnavailable`: a
team whose agents were assigned tools and cannot reach them does not degrade into several
agents guessing independently, each guess paid for, and a trace that looks like an
experiment's result without being one (specs/teams-tool-access, "Brak serwera narzędzi
zatrzymuje przebieg, zamiast pozwolić zespołowi zgadywać"). Refusing is `assignment.py`'s
job; raising is how this file reports the fact it needs.

**One constraint on where a session may be opened, found the hard way and worth knowing
before the run loop is written.** The transport holds its halves in anyio task groups, so
a session opened inside a task that then *returns* — a request handler, typically — leaves
those scopes on that task's stack and the next scope exit raises "Attempted to exit a
cancel scope that isn't the current task's current cancel scope", nowhere near the cause.
Open a session in a task that lives as long as the session does. That is why the save-time
check (`assignment.announced_tool_names`) opens one of its own and closes it before
answering, rather than borrowing the long-lived one on `app.state`.
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
from mcp.shared.exceptions import McpError

from ..config import Settings

log = logging.getLogger(__name__)

# What the SDK turns a `404` on `POST /mcp` into. The status never reaches this file:
# `streamable_http.py` sees it, synthesizes this JSON-RPC error into the response stream,
# and `ClientSession` raises it as an `McpError` — so the string is the only handle there
# is. Matching a string from somebody else's library is brittle on purpose rather than by
# accident: `test_tool_server.py` drives a real client against a real server that has
# forgotten the session, so an SDK upgrade that reworded this fails a test instead of
# quietly turning the retry off.
_SESSION_GONE_CODE = 32600
_SESSION_GONE_MESSAGE = "Session terminated"

# FastMCP's own default, and market-mcp does not override it (`server.py`, which builds
# `streamable_http_app()` and wraps it without touching the route).
MCP_PATH = "/mcp"


class ToolAccessError(RuntimeError):
    """Anything that stops a run before an agent is called. Group 7's run start catches
    this one type and refuses the run naming tool access as the cause; the subclasses say
    which of the two things went wrong, for the message and for the trace."""


class ToolServerUnavailable(ToolAccessError):
    """The server could not be asked at all — unconfigured, unreachable, too slow, or it
    refused this module's identity. Nothing is known about the tools either way."""


@dataclass(frozen=True)
class ToolDescriptor:
    """One tool as the server announced it. `input_schema` is JSON Schema and is handed
    to the provider unread — this module does not validate arguments the server already
    describes, and a second opinion here would only be a second thing to keep in step."""

    name: str
    description: str
    input_schema: dict[str, Any]
    # From the server's own `readOnlyHint` — `None` when a tool carries no annotation at
    # all, which `GET /tools` reads as "unknown" rather than guessing (specs/
    # trading-mcp-tools, "Narzędzie zapisujące jest oznaczone jako zmieniające stan").
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


class _ManagedIdentityAuth(httpx.Auth):
    """A bearer token per request rather than per connection.

    The streamable-http transport fixes its headers when the connection opens, and a
    session outliving its token would start failing mid-run for a reason that reads like
    nothing at all. `DefaultAzureCredential` caches internally and only reaches the
    identity endpoint again near expiry, so this is not a round trip per call.
    """

    def __init__(self, credential: DefaultAzureCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    async def async_auth_flow(self, request: httpx.Request):
        token = await self._credential.get_token(self._scope)
        request.headers["Authorization"] = f"Bearer {token.token}"
        yield request


class ToolServer:
    """One MCP session over one server, named by which triplet of `Settings` fields it
    reads.

    `prefix` selects the field group — `"market_mcp"` reads `market_mcp_url` etc., the
    only one that existed before this module had a second server. A `ToolServerRegistry`
    builds one of these per configured server; every call site that predates the
    registry keeps constructing a bare `ToolServer(settings)` and gets exactly the
    market-mcp instance it always did — the default carries the whole of that history so
    nothing already calling it had to change (specs/teams-tool-access, "Moduł MAY być
    skonfigurowany z więcej niż jednym serwerem narzędzi").

    `can_move_the_account` marks the one server whose writes land somewhere this module
    cannot look afterwards. It decides nothing about how a call is made and everything
    about whether a call is an order — the trade row, and the daily count that stops the
    next one. Same field, same name, same meaning as `agent/tools/client.py`'s.
    """

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
        # Guards connecting and reconnecting. A run works several agents at once
        # (specs/teams-runs), so two of them arriving while the session is down must not
        # open two sessions.
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
        """What the server publishes right now, read once per session.

        Raises `ToolServerUnavailable` rather than answering `[]` — see this module's
        docstring. An empty list is still a possible answer and means something different:
        the server was asked and announces nothing.
        """
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
            # Every failure here means the same thing to a caller — the server could not
            # be asked — so they are narrowed into one type rather than sorted. The one
            # exception is the session the server has forgotten, which is worth one
            # reopening: otherwise a server restarted since the last read refuses the run
            # before an agent has been asked anything.
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
        """One logical call, and at most two requests.

        The second request happens only when the server rejected the first as belonging to
        a session it does not know — which it answers **before** looking at which tool was
        asked for, so it proves the call was not handled. That is the whole of the
        licence: a timeout leaves the effect unknown and is never repeated, and the
        distinction is drawn on the server's answer rather than on the tool's name,
        because the gate that produced the answer had not read the name either
        (specs/teams-tool-access, "Wywołanie odrzucone z powodu nieznanej sesji jest
        ponawiane raz").

        A restart on the other side is the ordinary way this happens, and it happened in
        production on 17 August 2026: `trading-mcp` was redeployed, and the first call
        after it — an order — died against a session that no longer existed.
        """
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
            # market-mcp's refusals are written for a reader who can act on them, so its
            # own words travel rather than a summary of them. A refusal has no structured
            # output — the SDK reports it as unstructured prose only.
            return ToolOutcome(ToolOutcomeKind.REFUSED, _text_of(result.content), elapsed())
        # A tool whose return type is a bare list is not one text block but one *per
        # item*, because the SDK's `_convert_to_content` recurses into a list rather than
        # serializing it whole. Joining those blocks hands a reader expecting one JSON
        # document N of them back to back — the production bug `agent` hit on
        # `list_tracked_pairs`. `structuredContent` is the SDK's own well-formed answer,
        # built from the same return value before it was split apart.
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
                    _ManagedIdentityAuth(self._credential, self._scope)
                    if self._credential is not None and self._scope is not None
                    else None
                )
                # `create_mcp_http_client` rather than a bare `httpx.AsyncClient`: the
                # transport relies on defaults it sets (redirects, in particular), and a
                # client built by hand here would be a second place to keep them. `read`
                # is left long — the connection carries the session's own event stream and
                # is meant to stay open between calls; per-call time is bounded by
                # `asyncio.wait_for` at the call sites instead.
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
        it: a server that restarted may be publishing a different set, and holding the old
        one would be this module keeping exactly the copy it is not supposed to."""
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
    """Every tool server this module knows about, by label.

    A registry in place of the one `ToolServer` earlier groups built around — the
    module now has two, and every caller above `client.py` reaches them through this
    rather than naming `market_mcp` or `trading_mcp` itself (specs/teams-tool-access,
    "Moduł MAY być skonfigurowany z więcej niż jednym serwerem narzędzi"). Adding a
    third server later is a line in `from_settings`, not a signature change here or in
    `assignment.py`.
    """

    servers: dict[str, ToolServer]

    @classmethod
    def from_settings(cls, settings: Settings) -> ToolServerRegistry:
        return cls(
            {
                "market-mcp": ToolServer(settings, prefix="market_mcp"),
                "trading-mcp": ToolServer(
                    settings, prefix="trading_mcp", can_move_the_account=True
                ),
            }
        )

    def configured(self) -> list[ToolServer]:
        return [server for server in self.servers.values() if server.configured]

    async def aclose(self) -> None:
        for server in self.servers.values():
            await server.aclose()


def _describe(err: BaseException) -> str:
    """The cause, not the wrapper.

    Both the streamable-http transport and the MCP session run their halves in an anyio
    task group, so a refused connection surfaces as `unhandled errors in a TaskGroup
    (1 sub-exception)` — a sentence that names nothing. It reached a live `agent` run
    before that module's own version of this function existed, and the model was handed it
    verbatim. Groups nest, so this recurses.
    """
    if isinstance(err, BaseExceptionGroup):
        inner = [_describe(sub) for sub in err.exceptions]
        # Deduplicated: a group of five identical connection refusals is one fact.
        unique = list(dict.fromkeys(part for part in inner if part))
        if unique:
            return "; ".join(unique)
    text = str(err).strip()
    return text or type(err).__name__


def _session_is_gone(err: BaseException) -> bool:
    """Whether the server refused this request as belonging to a session it does not know.

    Recurses into groups for `_describe`'s reason: the transport runs its halves in anyio
    task groups, so what reaches a caller is often the error wrapped in one.
    """
    if isinstance(err, BaseExceptionGroup):
        return any(_session_is_gone(sub) for sub in err.exceptions)
    return (
        isinstance(err, McpError)
        and err.error.code == _SESSION_GONE_CODE
        and err.error.message == _SESSION_GONE_MESSAGE
    )


def _text_of(content: list[Any]) -> str:
    """Text blocks only, joined. market-mcp answers in prose by design — its ceilings, its
    aggregation notes and its refusals are all sentences — so a non-text block is
    something new on that side, named here rather than dropped silently."""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(f"[{getattr(block, 'type', 'unknown')} content, not shown]")
    return "\n".join(parts)
