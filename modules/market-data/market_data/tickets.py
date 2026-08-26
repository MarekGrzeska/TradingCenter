"""One-time tickets: identity carried into the one place that takes no headers. A token in the URL
would be logged and stay valid for an hour; a ticket that leaks has been spent, or expires in 30s."""

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
    #: Whoever the platform authenticator said was asking. Not used to decide anything today, but it
    #: makes a ticket somebody's rather than an anonymous bearer value.
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
        """The ticket, if it is a live one — and never the same one twice. Removed before it is judged,
        so two presentations racing each other can only have one winner."""
        if not value:
            return None
        ticket = self._issued.pop(value, None)
        if ticket is None:
            return None
        if ticket.expires_at <= self._now():
            return None
        return ticket

    def _forget_expired(self, now: datetime) -> None:
        # Swept when a ticket is issued, because that is the only moment the store can grow. A timer
        # would be a task to start, stop and test for one pass over a few dozen entries.
        for value in [v for v, ticket in self._issued.items() if ticket.expires_at <= now]:
            del self._issued[value]

    def __len__(self) -> int:
        """How many tickets are outstanding. For tests and for a health line, not for
        decisions."""
        return len(self._issued)
