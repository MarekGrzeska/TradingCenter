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

from ..config import Settings

log = logging.getLogger(__name__)

# FastMCP's own default, and market-mcp does not override it (`server.py`, which builds
# `streamable_http_app()` and wraps it without touching the route).
MCP_PATH = "/mcp"

# Where the operator's own credential rides — never `Authorization`, which carries this
# module's identity to whatever authenticator stands in front of the server. The name
# matches what teams-mcp reads (`teams_mcp/operator.py`); it is one contract in two
# repositories' worth of modules and there is no shared constant to import.
OPERATOR_TOKEN_HEADER = "X-Operator-Authorization"


@dataclass(frozen=True)
class ToolDescriptor:
    """One tool as the server announced it. `input_schema` is JSON Schema and is handed
    to the provider unread — this module does not validate arguments the server already
    describes, and a second opinion here would only be a second thing to keep in step."""

    name: str
    description: str
    input_schema: dict[str, Any]
    # From the server's own `readOnlyHint`. `None` means the tool carried no annotation
    # at all, which is not the same as "reads" — see `ToolServer.moves_the_account`,
    # where the difference decides whether a call that never answered is recorded as
    # unknown or as unavailable.
    read_only: bool | None = None


class ToolOutcomeKind(StrEnum):
    OK = "ok"
    # The server answered, and its answer is "not like that". Carries the sentence
    # market-mcp writes for exactly this: what to change so the call would work.
    REFUSED = "refused"
    # The server did not answer at all — unreachable, timed out, refused the identity.
    # Nothing was asked, so nothing about the archive is known either way.
    UNAVAILABLE = "unavailable"
    # The server did not answer *and* the call may have landed anyway. Only ever produced
    # for a call that can change the account, where "nothing was asked" is a claim this
    # module cannot make: a `place_order` that timed out is either no position or one
    # nobody knows about (specs/agent-trading, "Wywołanie ruszające rachunek zostawia
    # ślad przed wysłaniem"). Kept apart from UNAVAILABLE because the two carry opposite
    # advice — retry the read, never the order.
    UNKNOWN = "unknown"


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
    """One MCP session over one server, named by which triplet of `Settings` fields it
    reads.

    `prefix` selects the field group — `"market_mcp"` reads `market_mcp_url` and its
    two neighbours, `"teams_mcp"` the same shape one catalogue over. The default carries
    the whole of this module's history: every call site that predates the second server
    keeps constructing a bare `ToolServer(settings)` and gets exactly the market-mcp
    instance it always did.

    `forwards_operator_token` marks the one server that acts **for a person** rather
    than merely on this module's behalf. Its tools create teams and spend money in an
    operator's name, so a call to it carries their credential; market-mcp reads a shared
    archive and has no use for one (design.md, D2).

    `can_move_the_account` marks the one server whose writes land somewhere this module
    cannot look afterwards. It decides nothing about how a call is made and everything
    about how a call that did not answer is recorded.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        prefix: str = "market_mcp",
        forwards_operator_token: bool = False,
        can_move_the_account: bool = False,
    ) -> None:
        self.label = prefix.replace("_", "-")
        self._env_prefix = prefix.upper()
        self.forwards_operator_token = forwards_operator_token
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

    async def list_tools(self, operator_token: str | None = None) -> list[ToolDescriptor]:
        """What the model may call this turn. An empty list is the answer whenever the
        server is not configured or not reachable — the caller's job is to run the turn
        without tools, not to fail it (specs/agent-tool-access, "Brak serwera narzędzi
        nie odbiera agentowi mowy")."""
        if self._url is None:
            return []
        if self._tools is not None:
            return self._tools
        try:
            async with self._session_for(operator_token) as session:
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
        """Whether a call to `name` could leave the account changed even if nothing comes
        back. Asked *before* the call, because the answer decides that the trace is
        written first.

        A tool this server announced but we hold no descriptor for counts as moving the
        account: the list is dropped whenever a session breaks, so the honest reading of
        "we cannot tell" is the one that writes a row too many rather than none.
        """
        if not self.can_move_the_account:
            return False
        for tool in self._tools or ():
            if tool.name == name:
                return tool.read_only is not True
        return True

    async def call(
        self, name: str, arguments: dict[str, Any], operator_token: str | None = None
    ) -> ToolOutcome:
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
            async with self._session_for(operator_token) as session:
                result = await asyncio.wait_for(
                    session.call_tool(name, arguments), timeout=self._timeout
                )
        except TimeoutError:
            await self._disconnect()
            if may_have_landed:
                return ToolOutcome(
                    ToolOutcomeKind.UNKNOWN,
                    f"the tool server did not answer within {self._timeout:g}s. The call "
                    "may have gone through — do not send it again. Tell the operator the "
                    "outcome is unknown and that they should check the account.",
                    elapsed(),
                )
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"the tool server did not answer within {self._timeout:g}s. The call was "
                "not made — this says nothing about the archive's own data.",
                elapsed(),
            )
        except Exception as err:  # noqa: BLE001 - a broken session is not a broken turn
            log.warning("tool call %s failed against %s: %s", name, self._url, _describe(err))
            await self._disconnect()
            if may_have_landed:
                return ToolOutcome(
                    ToolOutcomeKind.UNKNOWN,
                    f"the tool server could not be reached: {_describe(err)}. The call may "
                    "have gone through — do not send it again. Tell the operator the "
                    "outcome is unknown and that they should check the account.",
                    elapsed(),
                )
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

    @asynccontextmanager
    async def _session_for(self, operator_token: str | None) -> AsyncIterator[ClientSession]:
        """A session to work through, and the reason there are two ways of getting one.

        **A server that acts only on this module's behalf keeps one session** for the
        life of the process: the credential never varies, so a connection can be paid
        for once. That is market-mcp, and it is what this class did before there was
        anything else.

        **A server that acts for a *person* cannot.** Its credential is that person's,
        it arrives per call, and the streamable-http transport fixes its headers when
        the connection opens — so a shared session would carry whichever operator
        happened to open it. A ContextVar does not rescue this either: the transport
        sends from its own anyio task, which copied the context when it was created and
        never sees a value set later. So a session per call, opened and closed inside
        this one coroutine.

        Closing it here is what makes that safe. A session left open by a task that then
        returns strands anyio's cancel scopes on that task's stack, and the next scope
        exit raises "Attempted to exit a cancel scope that isn't the current task's
        current cancel scope" nowhere near the cause. `teams`' own save-time check opens
        and closes one the same way, for the same reason.

        The cost is one connection per tool call against that one server. An operator
        typing in a chat is not a rate worth optimising for, and the alternative is
        acting in the wrong person's name.
        """
        if not self.forwards_operator_token:
            yield await self._connected_session()
            return

        assert self._url is not None
        stack = AsyncExitStack()
        try:
            session = await self._open(stack, operator_token=operator_token)
            yield session
        finally:
            try:
                await stack.aclose()
            except Exception as err:  # noqa: BLE001 - closing a broken stream often raises
                log.debug("%s: closing the per-call session raised: %s", self.label, err)

    async def _connected_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            stack = AsyncExitStack()
            try:
                session = await self._open(stack, operator_token=None)
            except BaseException:
                await stack.aclose()
                raise
            self._stack = stack
            self._session = session
            return session

    async def _open(self, stack: AsyncExitStack, *, operator_token: str | None) -> ClientSession:
        assert self._url is not None
        auth = (
            _ManagedIdentityAuth(self._credential, self._scope)
            if self._credential is not None and self._scope is not None
            else None
        )
        # Two credentials answering two questions, and they travel in two headers:
        # `Authorization` (this module's identity, added by `auth` above) says who is
        # calling, and this one says in whose name (design.md, D2). Never merged.
        headers = (
            {OPERATOR_TOKEN_HEADER: operator_token}
            if self.forwards_operator_token and operator_token
            else None
        )
        # `create_mcp_http_client` rather than a bare `httpx.AsyncClient`: the transport
        # relies on defaults it sets (redirects, in particular), and a client built by
        # hand here would be a second place to keep them. `read` is left long — the
        # connection carries the session's own event stream; per-call time is bounded by
        # `asyncio.wait_for` at the call sites instead.
        http_client = await stack.enter_async_context(
            create_mcp_http_client(
                headers=headers, timeout=httpx.Timeout(self._timeout, read=None), auth=auth
            )
        )
        read, write, _ = await stack.enter_async_context(
            streamable_http_client(f"{self._url}{MCP_PATH}", http_client=http_client)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=self._timeout)
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
