"""What can go wrong between this module and the gateway, named.

Three failures that look identical to a caller reading a short series — the gateway is
down, the gateway refused, the gateway answered something unreadable — and that a
consumer has to tell apart, because only one of them is worth retrying the same way.

None of these carry the *provider's* credential — capital.com's session lives entirely
inside the gateway, and nothing about it reaches this module. This module's own caller
key (config.py's `gateway_api_key`, sent as `X-Gateway-Key`) is a different secret and
travels only in the outbound request header, never in these exceptions: `GatewayRefused`
carries only what the gateway's own error handler put in `detail`, which is never the
key that was checked, right or wrong.
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
