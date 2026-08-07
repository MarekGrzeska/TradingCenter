"""What can go wrong between this module and the gateway, named.

Three failures that look identical to a caller reading a short series — the gateway is
down, the gateway refused, the gateway answered something unreadable — and that a
consumer has to tell apart, because only one of them is worth retrying the same way.

None of these carry a credential. There is none to leak on this path: the gateway holds
the provider session, and this module talks to it unauthenticated over localhost.
"""

from __future__ import annotations


class GatewayError(RuntimeError):
    """Anything that went wrong between this module and `capital-gateway`."""


class GatewayUnreachable(GatewayError):
    """The gateway did not answer — not running, not resolvable, or the socket died."""


class GatewayRefused(GatewayError):
    """The gateway answered, and the answer was a refusal.

    Carries the status and whatever the gateway said in `detail`, because its own error
    handler puts the cause there and dropping it turns "unknown symbol" into "something
    failed".
    """

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"the gateway refused with {status_code}: {detail}")


class UnreadablePayload(GatewayError):
    """The gateway answered with something this module cannot read.

    Distinct from a refusal on purpose: a refusal is the gateway working correctly and
    saying no, while this is the contract between the two modules having drifted. The
    second needs a person, and retrying it forever hides that.
    """
