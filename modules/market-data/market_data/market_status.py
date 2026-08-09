"""Whether an instrument's market is open, remembered briefly.

This is neither tracking nor HTTP. It exists because reading the tracked-pair list needs
to tell a pair that has stalled from a pair whose market is simply shut, and only the
gateway knows which — but asking it once per read, per pair, forever, is a bill nobody
agreed to pay.

It was a module-level dict inside `app.py` until `slim-market-data-app`. What that cost
was visible in the tests rather than in production: a cache living for the lifetime of a
process is shared by every app built in it, so `test_app.py` had to import a private name
out of the HTTP layer and clear it between cases. A test reaching into a module to tidy
state it did not create is a report about where the state lives.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .errors import GatewayError
from .gateway import GatewayInstruments

# A session changes twice a day, so a minute of staleness costs nothing an operator can
# perceive — and without it a shut market is permanently "late", so every read of the list
# spends a gateway request per closed pair, forever. Measured over a quarter of an hour of
# a weekend: 74 requests about one instrument that had been shut since Friday.
DEFAULT_TTL = timedelta(minutes=1)


class MarketStatus:
    """The gateway's answer about one instrument, held for `ttl`.

    One instance per application, built in `lifespan` and reached through `app.state` like
    every other dependency this module has. A test that needs one builds it.

    It owns the memory and not the gateway: `instruments` is passed to each call rather
    than held. That is deliberate and worth the slightly odd signature — routes in this
    module resolve `app.state.instruments` per request, which is what lets a test swap the
    gateway after the application exists. Capturing it here instead would move when that
    dependency is resolved, and moving it inside a refactor whose whole promise is that
    nothing changes would be smuggling.
    """

    def __init__(self, ttl: timedelta = DEFAULT_TTL) -> None:
        self._ttl = ttl
        self._remembered: dict[str, tuple[datetime, bool | None]] = {}

    async def of(self, instruments: GatewayInstruments, symbol: str) -> tuple[str, bool | None]:
        """Whether this instrument's market is open, from cache when it is fresh enough.

        Returns the symbol alongside the answer so a caller can gather several at once and
        still know which is which.

        A gateway that will not answer is cached as `None` like any other answer: it would
        otherwise be re-asked on every read while it is down, which is when it can least
        afford the traffic.
        """
        now = datetime.now(UTC)
        remembered = self._remembered.get(symbol)
        if remembered is not None and now - remembered[0] < self._ttl:
            return symbol, remembered[1]

        try:
            answer = await instruments.is_market_open(symbol)
        except GatewayError:
            answer = None

        self._remembered[symbol] = (now, answer)
        return symbol, answer
