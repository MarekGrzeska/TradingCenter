"""What this module answers with — the published shape of a bot, a destination and a delivery.

**No model here carries a token**, and that is the rule the whole file is arranged around: `BotOut` is
built from `Bot`, which has no token to give, so a route that forgets the rule has nothing to leak.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .bot_api import Delivered
from .models import Bot, Destination


class Problem(BaseModel):
    """One refusal shape for every route, so a caller handles one thing.

    `cause` names who said no and `retry_after_seconds` carries Telegram's own wait — the caller
    decides from these two whether to record its "already told" marker, and a generic message would
    leave it guessing.
    """

    detail: str
    cause: Literal["module", "telegram", "request"] = "module"
    retryable: bool = False
    retry_after_seconds: int | None = Field(
        default=None,
        description="how long Telegram asked this gateway to wait; present only on a rate limit",
    )


class SendRequest(BaseModel):
    """A message, addressed by name. There is no `chat_id` and no bot here on purpose: a number
    every caller keeps its own copy of is invalidated for all of them the day the bot is replaced."""

    destination: str = Field(description="the name the destination was bound under")
    text: str


class Sent(BaseModel):
    """What Telegram said about a message it accepted. Nothing is kept after the response — this is
    the whole of what this gateway can ever say about a message."""

    destination: str
    message_id: int = Field(description="Telegram's own identifier for the delivered message")
    chat_id: int

    @classmethod
    def of(cls, name: str, delivered: Delivered) -> Sent:
        return cls(
            destination=name, message_id=delivered.message_id, chat_id=delivered.chat_id
        )


class BotOut(BaseModel):
    """A bot as every read publishes it: who it is on Telegram, and nothing to send with."""

    telegram_id: int = Field(description="the bot's own id on Telegram")
    username: str = Field(description="its @name, without the @ — how routes address it")
    title: str
    created_here: bool = Field(
        description="true when this gateway created it through Telegram's creator bot"
    )
    added_at: datetime | None = None

    @classmethod
    def of(cls, bot: Bot) -> BotOut:
        return cls(
            telegram_id=bot.telegram_id,
            username=bot.username,
            title=bot.title,
            created_here=bot.created_here,
            added_at=bot.added_at,
        )


class AdoptBotRequest(BaseModel):
    """A token the operator pasted. Telegram is asked whose it is rather than being told — the @name
    and the numeric id are facts about the bot, not preferences about it."""

    token: str


class NewBotRequest(BaseModel):
    """A bot to create through Telegram's creator bot. Available only where an account session is
    configured, which `/state` says out loud."""

    title: str = Field(description="the display name; the creator bot accepts anything readable")
    username: str = Field(description="must end in 'bot' — Telegram's rule, checked before asking")


class DestinationOut(BaseModel):
    """Somewhere this gateway can send, and how far along it is.

    `receives` is the question every caller actually has, and it is not the same as existing: a bot
    may not open a conversation, so a destination is an intention until somebody taps its link.
    """

    name: str
    bot: str = Field(description="the @name of the bot messages to this destination go through")
    state: Literal["pending", "ready", "blocked"] = Field(
        description="pending — nobody has tapped the start link yet; blocked — the recipient "
        "blocked the bot and it must be bound again"
    )
    receives: bool
    bound_at: datetime | None = None
    blocked_at: datetime | None = None

    @classmethod
    def of(cls, destination: Destination, bot_username: str) -> DestinationOut:
        return cls(
            name=destination.name,
            bot=bot_username,
            state=destination.state.value,  # pyright: ignore[reportArgumentType]
            receives=destination.receives,
            bound_at=destination.bound_at,
            blocked_at=destination.blocked_at,
        )


class NewDestinationRequest(BaseModel):
    name: str = Field(description="what callers will address; it survives a change of bot")
    bot: str = Field(description="the @name of the bot that will carry it")


class StartLinkOut(BaseModel):
    """The one tap that binds a destination, and how long it is worth tapping.

    The link carries a one-shot secret, so it is as good as the destination until it is used —
    which is why it expires and why nothing logs it.
    """

    destination: DestinationOut
    start_link: str = Field(description="hand this to the person who is to receive the alerts")
    expires_in_seconds: int


class StateOut(BaseModel):
    """What this gateway is able to do at all. Read before concluding it is broken: a gateway with
    no destination and one that cannot reach Telegram answer the same nothing without this."""

    account_session_configured: bool = Field(
        description="whether creating bots is available; false is a supported configuration, and "
        "sending works either way"
    )
    bots: int
    destinations: int
    destinations_ready: int = Field(
        description="how many can actually receive — the rest are waiting on a tap or blocked"
    )
