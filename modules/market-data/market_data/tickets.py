"""One-time tickets: identity carried into the one place that takes no headers.

A browser cannot put a header on a WebSocket handshake — the API has no room for one —
so the operator's token has no way of reaching `/ws/candles`. Putting the token in the
URL instead would work and would be wrong: URLs are logged, by App Service and by
Application Insights, and a token stays valid for the better part of an hour after the
log line is written.

A ticket is that token's one-use shadow. It is issued over HTTP, where headers work and
the platform authenticator has already said who is asking, and it is spent on the
handshake, where they do not. A ticket that leaks out of a log has already been spent; a
ticket that was never spent expires in half a minute.

**The store is a dict in this process, and that is a constraint rather than an
oversight.** `market-data` runs as a single always-on instance with `worker_count = 1`
(`infra/app-service.tf`), so the process that issued a ticket is the process asked to
honour it. With a second worker or a second instance, a ticket issued by one and
presented to the other is refused — and the symptom is a stream that fails to connect
now and then, for no reason visible in either process. If that day comes, this module is
the one to move into Postgres, and nothing outside it needs to know.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# 32 bytes from the OS's entropy, url-safe. Guessing is not a strategy against it, and it
# still fits in a query string without comment.
TICKET_BYTES = 32


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Ticket:
    """One handshake's worth of permission, and who it was minted for."""

    value: str
    #: Whoever the platform authenticator said was asking. Not used to decide anything
    #: today — there is one operator — but it makes a ticket somebody's rather than an
    #: anonymous bearer value, and it is what a refusal can be logged against.
    issued_to: str
    expires_at: datetime


class TicketStore:
    """Issues tickets, and spends each of them exactly once."""

    def __init__(self, ttl: timedelta, now: Callable[[], datetime] = _utcnow) -> None:
        self._ttl = ttl
        self._now = now
        self._issued: dict[str, Ticket] = {}

    @property
    def ttl(self) -> timedelta:
        return self._ttl

    def issue(self, issued_to: str) -> Ticket:
        now = self._now()
        self._forget_expired(now)
        ticket = Ticket(secrets.token_urlsafe(TICKET_BYTES), issued_to, now + self._ttl)
        self._issued[ticket.value] = ticket
        return ticket

    def spend(self, value: str | None) -> Ticket | None:
        """The ticket, if it is a live one — and never the same one twice.

        Removed before it is judged, not after: an expired ticket is then gone on the
        first presentation rather than lingering to be refused repeatedly, and two
        presentations of the same ticket racing each other can only have one winner,
        because only one of them finds it in the dict.
        """
        if not value:
            return None
        ticket = self._issued.pop(value, None)
        if ticket is None:
            return None
        if ticket.expires_at <= self._now():
            return None
        return ticket

    def _forget_expired(self, now: datetime) -> None:
        # Swept when a ticket is issued, because that is the only moment the store can
        # grow. A timer would be a task to start, stop and test for what one pass over a
        # dict of at most a few dozen entries does.
        for value in [v for v, ticket in self._issued.items() if ticket.expires_at <= now]:
            del self._issued[value]

    def __len__(self) -> int:
        """How many tickets are outstanding. For tests and for a health line, not for
        decisions."""
        return len(self._issued)
