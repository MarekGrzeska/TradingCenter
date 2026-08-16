"""What can go wrong between this module and `capital-gateway`, named — and kept apart
from what a *tool* means by refused, which group 3's tool functions build on top of
these (specs/trading-mcp-tools, "Odmowa narzędzia jest odróżnialna od awarii dostępu").

`GatewayUnavailable` and `GatewayRefused` look identical to a caller reading a short
error, but only one of them is worth retrying — and per `trading-mcp-execution`,
neither ever triggers a retry of a request that changes the account: this module does
not know whether an unanswered write reached the provider, so repeating it risks a
second position rather than confirming the first.

None of these carry `capital_gateway_api_key` — the header travels only on the outbound
request, never back out through an exception (specs/trading-mcp-upstream-access,
"Poświadczenie do gatewaya nie wychodzi poza moduł").
"""

from __future__ import annotations


class GatewayError(RuntimeError):
    """Anything that went wrong between this module and `capital-gateway`."""


class GatewayUnavailable(GatewayError):
    """The gateway could not be asked at all — unreachable, timed out, or the request
    never got a response. For a write, this means the request's effect on the account
    is unknown, not that it failed."""


class GatewayRefused(GatewayError):
    """The gateway answered, and the answer is a refusal. Carries the status and
    whatever the gateway's own error handler put in `detail` — never this module's own
    credential, which the gateway never echoes back."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"the gateway refused with {status_code}: {detail}")

    @property
    def is_access_failure(self) -> bool:
        """Whether this answer means "this module could not ask" rather than "the
        request was wrong" — the one distinction every tool in this module is built to
        keep (specs/trading-mcp-tools, "Odmowa narzędzia jest odróżnialna od awarii
        dostępu"). Decided once, here, because both seams in `tools/_shared.py` and the
        demo guard's cache all have to agree about it.

        `5xx` is the obvious half. The named `4xx` are the ones that look like a
        refusal and are not:

        - **401 / 403** — this module's own `X-Gateway-Key` was rejected, or the
          gateway's provider session was. Either way nobody looked at what was asked
          for, and an agent told "refused" would spend its rounds re-editing an order
          that was never the problem;
        - **408 / 429** — the gateway ran out of time or out of its rate budget
          (`capital_gateway/app.py` forwards a provider's own status, so both can
          arrive from a layer further out). The request was not served, which is not
          the same as being wrong.

        Everything else `4xx` stays a refusal: a 404 for a position id that is gone and
        a 422 for a size the gateway would not take are answers *about the request*,
        and they name what to change.
        """
        return self.status_code >= 500 or self.status_code in _COULD_NOT_ASK


_COULD_NOT_ASK = frozenset({401, 403, 408, 429})


class NotDemoEnvironment(GatewayError):
    """The gateway answered, but named an environment other than `"demo"`. Distinct
    from a refusal: the gateway did nothing wrong, this module's own guard did
    (specs/trading-mcp-upstream-access, "Moduł pracuje wyłącznie na rachunku
    demonstracyjnym")."""


class ToolRefusal(Exception):
    """Raised by a tool to refuse a request it understood but will not serve as
    asked — the shape group 3's tools raise it in, mirroring `market_mcp/errors.py`.
    The MCP server turns any exception a tool raises into `isError=True`, so what
    matters is the message: it MUST say what to change for the request to succeed
    (specs/trading-mcp-tools, "Odmowa narzędzia jest odróżnialna od awarii dostępu").

    Distinct from every `GatewayError` above: those are what this module tells
    *itself* about a call to the gateway, and a tool decides from them whether to
    raise this instead — a `GatewayUnavailable` becomes a message naming an access
    failure, not this."""
