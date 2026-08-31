"""The ticket store on its own — issuing, spending, and expiring. The route and the handshake are
exercised against a real app; what is here is the part that has no HTTP in it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_data.tickets import TicketStore

TTL = timedelta(seconds=30)
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def store_at(clock: list[datetime]) -> TicketStore:
    """A store reading a clock the test moves by hand — a `sleep` would be the same
    assertion, only slower and occasionally wrong."""
    return TicketStore(TTL, now=lambda: clock[0])


def test_an_issued_ticket_can_be_spent() -> None:
    tickets = TicketStore(TTL)

    issued = tickets.issue("operator")

    spent = tickets.spend(issued.value)
    assert spent is not None
    assert spent.issued_to == "operator"


def test_a_ticket_is_spent_only_once() -> None:
    tickets = TicketStore(TTL)
    issued = tickets.issue("operator")

    assert tickets.spend(issued.value) is not None
    assert tickets.spend(issued.value) is None


def test_a_ticket_nobody_issued_is_not_a_ticket() -> None:
    tickets = TicketStore(TTL)

    assert tickets.spend("made-up") is None
    assert tickets.spend("") is None
    assert tickets.spend(None) is None


def test_a_ticket_expires_even_if_it_is_never_spent() -> None:
    clock = [NOW]
    tickets = store_at(clock)
    issued = tickets.issue("operator")

    clock[0] = NOW + TTL

    assert tickets.spend(issued.value) is None


def test_a_ticket_is_still_good_a_moment_before_it_expires() -> None:
    clock = [NOW]
    tickets = store_at(clock)
    issued = tickets.issue("operator")

    clock[0] = NOW + TTL - timedelta(seconds=1)

    assert tickets.spend(issued.value) is not None


def test_expired_tickets_do_not_pile_up() -> None:
    """The store is a dict in a process that stays up for weeks, and a reconnect loop against a refusing
    archive mints one per attempt — so what is never spent has to go on its own."""
    clock = [NOW]
    tickets = store_at(clock)
    for _ in range(10):
        tickets.issue("operator")
    assert len(tickets) == 10

    clock[0] = NOW + TTL
    tickets.issue("operator")

    assert len(tickets) == 1


def test_two_tickets_are_never_the_same_ticket() -> None:
    tickets = TicketStore(TTL)

    values = {tickets.issue("operator").value for _ in range(100)}

    assert len(values) == 100
    # Long enough that guessing is not a strategy — 32 bytes, url-safe.
    assert all(len(value) >= 40 for value in values)
