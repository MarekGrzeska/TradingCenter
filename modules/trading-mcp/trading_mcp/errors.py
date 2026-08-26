"""What can go wrong between this module and `capital-gateway`, named — and kept apart from what a
*tool* means by refused. None of these carry the caller key, which travels outbound only."""

from __future__ import annotations


class GatewayError(RuntimeError):
    """Anything that went wrong between this module and `capital-gateway`."""


class GatewayUnavailable(GatewayError):
    """The gateway could not be asked at all. For a write this means the request's effect on the
    account is unknown, not that it failed."""


class GatewayRefused(GatewayError):
    """The gateway answered, and the answer is a refusal. Carries whatever its own error handler put
    in `detail` — never this module's credential, which the gateway never echoes back."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"the gateway refused with {status_code}: {detail}")

    @property
    def is_access_failure(self) -> bool:
        """Whether this answer means "this module could not ask" rather than "the request was wrong".
        Decided once, here, because both seams and the demo guard have to agree about it."""
        return self.status_code >= 500 or self.status_code in _COULD_NOT_ASK


_COULD_NOT_ASK = frozenset({401, 403, 408, 429})


class NotDemoEnvironment(GatewayError):
    """The gateway answered, but named an environment other than `"demo"`. Distinct from a refusal:
    the gateway did nothing wrong, this module's own guard did."""


class ToolRefusal(Exception):
    """Raised by a tool to refuse a request it understood but will not serve as asked. The MCP server
    turns any exception into `isError=True`, so what matters is that the message says what to change."""
