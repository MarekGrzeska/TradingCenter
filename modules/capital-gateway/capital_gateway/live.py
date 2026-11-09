"""What a process on the live account adds to the gateway (`capital-live-account`): the routes it serves, the limits an
order must fit before it leaves for the provider, and the trace every write leaves in the log. One file, because each
of these is a rule the demo process does not have."""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from .dtos import PlaceOrderRequest
from .errors import GatewayError

trace = logging.getLogger("capital_gateway.live_trace")

CLOSE_ALL_PATH = "/positions/close-all"

# Method and path pattern of every route a live process serves. Everything else — the catalogue, candles, history, the
# stream, the top-up and switching the active account — is absent: the archive reads the market from the demo gateway.
_LIVE_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        ("GET", r"/"),
        ("GET", r"/capabilities"),
        ("GET", r"/accounts"),
        ("GET", r"/positions"),
        ("POST", r"/orders"),
        ("POST", re.escape(CLOSE_ALL_PATH)),
        ("PUT", r"/positions/[^/]+"),
        ("DELETE", r"/positions/[^/]+"),
        ("GET", r"/working-orders"),
        ("DELETE", r"/working-orders/[^/]+"),
        ("GET", r"/instruments/[^/]+/terms"),
    )
)


def live_serves(method: str, path: str) -> bool:
    return any(method == m and pattern.fullmatch(path) for m, pattern in _LIVE_ROUTES)


def check_order(limits: dict[str, Decimal], req: PlaceOrderRequest) -> None:
    """Refuses an order outside the limits before anything is sent. Never trims one to fit: an order the caller did not
    ask for is worse than a refusal it can read."""
    limit = limits.get(req.symbol)
    if limit is None:
        allowed = ", ".join(sorted(limits))
        raise GatewayError(
            f"refused by the live account's limits: {req.symbol} is not an instrument this account may trade "
            f"(allowed: {allowed})",
            status_code=422,
        )
    size = Decimal(str(req.size))
    if size > limit:
        raise GatewayError(
            f"refused by the live account's limits: size {size} of {req.symbol} is over the limit of {limit} "
            "for one order",
            status_code=422,
        )
