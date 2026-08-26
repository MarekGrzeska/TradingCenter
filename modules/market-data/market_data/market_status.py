"""Whether an instrument's market is open, remembered briefly. Reading the tracked-pair list must tell
a stalled pair from a shut market, and only the gateway knows — but not once per read, per pair, forever."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .errors import GatewayError
from .gateway import GatewayInstruments

# A session changes twice a day, so a minute of staleness costs nothing perceptible — and without it
# a shut market is permanently late. Measured over a weekend quarter-hour: 74 requests about one pair.
DEFAULT_TTL = timedelta(minutes=1)


class MarketStatus:
    """The gateway's answer about one instrument, held for `ttl`. It owns the memory and not the
    gateway: `instruments` is passed per call, which is what lets a test swap it after the app exists."""

    def __init__(self, ttl: timedelta = DEFAULT_TTL) -> None:
        self._ttl = ttl
        self._remembered: dict[str, tuple[datetime, bool | None]] = {}

    async def of(self, instruments: GatewayInstruments, symbol: str) -> tuple[str, bool | None]:
        """Whether this instrument's market is open, from cache when it is fresh enough. Returns the
        symbol alongside so a caller gathering several still knows which is which."""
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
