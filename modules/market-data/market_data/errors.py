"""What can go wrong between this module and the gateway, named: down, refused, or unreadable — three
failures that look identical in a short series. None of them carries a credential."""

from __future__ import annotations


class GatewayError(RuntimeError):
    """Anything that went wrong between this module and `capital-gateway`."""


class GatewayUnreachable(GatewayError):
    """The gateway did not answer — not running, not resolvable, or the socket died."""


class GatewayRefused(GatewayError):
    """The gateway answered, and the answer was a refusal. Carries whatever it put in `detail`:
    dropping it turns "unknown symbol" into "something failed"."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"the gateway refused with {status_code}: {detail}")


class UnreadablePayload(GatewayError):
    """The gateway answered with something this module cannot read. Distinct from a refusal: that is
    the gateway working correctly, this is the contract between the two modules having drifted."""
