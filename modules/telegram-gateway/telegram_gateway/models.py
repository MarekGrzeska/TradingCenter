"""What this module holds, as its own shapes. The one to read twice is `Bot`: it exists in two forms on
purpose, and only one of them can carry the token."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DestinationState(str, Enum):
    """Where a destination is between "the operator asked for it" and "it receives".

    `BLOCKED` is not a deleted destination: the name, the bot and the history of the intention all
    stand, and what is gone is the recipient's consent. It comes back with a second start.
    """

    PENDING = "pending"
    READY = "ready"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Bot:
    """A bot this module may speak as — **without its token**.

    This is the shape every read returns and every response is built from. The token lives in
    `BotCredential` and is fetched only by the code about to make a request with it, so a route that
    forgets the rule has nothing to leak.
    """

    id: int
    telegram_id: int
    username: str
    title: str
    created_here: bool
    added_at: datetime | None = None

    @property
    def start_link(self) -> str:
        """Where a person taps to open the conversation. The nonce is appended by the caller."""
        return f"https://t.me/{self.username}"


@dataclass(frozen=True, slots=True)
class BotCredential:
    """A bot's token, fetched on its own and never as part of a `Bot`.

    Separate type rather than an optional field: an optional field is one forgotten `exclude` away
    from a response, and this is the class of mistake that looks like a working feature.
    """

    bot_id: int
    token: str


@dataclass(frozen=True, slots=True)
class Destination:
    """Somewhere this module can send. `chat_id` is absent until a person has opened the conversation
    — a bot cannot speak first, so a destination is an intention before it is an address."""

    id: int
    name: str
    bot_id: int
    state: DestinationState
    chat_id: int | None = None
    bound_at: datetime | None = None
    blocked_at: datetime | None = None

    @property
    def receives(self) -> bool:
        return self.state is DestinationState.READY and self.chat_id is not None


@dataclass(frozen=True, slots=True)
class Binding:
    """A one-shot secret, and what it was issued for. Kept after it is used so that the same secret
    arriving twice is answered "already used" rather than "never existed"."""

    nonce: str
    destination_id: int
    expires_at: datetime
    used_at: datetime | None = None

    def usable_at(self, moment: datetime) -> bool:
        return self.used_at is None and moment < self.expires_at
