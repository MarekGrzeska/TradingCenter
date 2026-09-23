"""What can go wrong on the way to Telegram, as this module's own shapes.

The refusals are types rather than status codes because the caller's next move differs by kind and
not by number: a rate limit is "wait this long and try again", a block is "the recipient has to press
Start again", and a refused name is a mistake in the request. Only the routes turn these into HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass


class GatewayError(Exception):
    """Anything this module refuses to do, or could not."""


@dataclass
class NoSuchDestination(GatewayError):
    """A caller addressed a name this module does not hold."""

    name: str

    def __str__(self) -> str:
        return f"{self.name!r} is not a destination this gateway knows"


@dataclass
class DestinationNotReady(GatewayError):
    """The name exists, but nobody has opened the conversation — or the recipient blocked the bot.

    Distinct from `NoSuchDestination` because the operator's move differs: this one is a start link
    to tap, not a name to correct.
    """

    name: str
    state: str

    def __str__(self) -> str:
        if self.state == "blocked":
            return (
                f"{self.name!r} blocked the bot, so Telegram refuses delivery. It needs to be "
                "bound again — the recipient must start the conversation a second time."
            )
        return (
            f"{self.name!r} has never been bound: a bot cannot open a conversation, so somebody "
            "has to tap its start link first."
        )


@dataclass
class MessageTooLong(GatewayError):
    """Refused rather than truncated. A shortened alert is an alert about something else, and
    nothing in a success response would say so."""

    length: int
    ceiling: int

    def __str__(self) -> str:
        return (
            f"the message is {self.length} characters and Telegram accepts {self.ceiling}. It is "
            "refused rather than shortened: a truncated alert is a different alert."
        )


@dataclass
class RateLimited(GatewayError):
    """Telegram's own back-off, carried through with the wait it asked for.

    There is no queue here, so this reaches the caller — who must not record whatever "already told"
    marker it keeps, or the notification is lost rather than delayed.
    """

    retry_after_seconds: int

    def __str__(self) -> str:
        return (
            f"Telegram is rate limiting this gateway and asks for {self.retry_after_seconds}s "
            "before the next attempt; nothing was delivered"
        )


@dataclass
class Blocked(GatewayError):
    """The recipient blocked the bot. Raised by the send path so the destination can be marked."""

    name: str

    def __str__(self) -> str:
        return f"{self.name!r} has blocked the bot; it must start the conversation again"


@dataclass
class TelegramRefused(GatewayError):
    """Everything else Telegram said no to, with its own description kept intact.

    Kept whole rather than summarised: the caller logs this, and a message this module invented
    would describe the gateway rather than the failure.
    """

    description: str
    status_code: int | None = None

    def __str__(self) -> str:
        return f"Telegram refused: {self.description}"


@dataclass
class TelegramUnreachable(GatewayError):
    """Telegram did not answer at all, or answered with something unreadable."""

    detail: str

    def __str__(self) -> str:
        return f"Telegram could not be reached: {self.detail}"


class CreatingBotsUnavailable(GatewayError):
    """Asked to create a bot with no account session configured — a supported state, not a fault.

    Creating a bot means talking to Telegram's creator bot, and only a user account may, so this
    names the settings rather than failing as though something broke.
    """

    def __str__(self) -> str:
        return (
            "creating a bot needs a Telegram account session, and none is configured. Set "
            "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_SESSION together to enable it — "
            "the gateway sends normally without them."
        )


@dataclass
class TooManyBots(GatewayError):
    """Telegram's ceiling on bots per account, checked before speaking rather than after being told."""

    held: int
    ceiling: int

    def __str__(self) -> str:
        return (
            f"this gateway already holds {self.held} bots and one Telegram account may create "
            f"{self.ceiling}. Nothing was asked of Telegram — a refusal from it would still have "
            "cost an attempt counted against the account."
        )


@dataclass
class CreatorBotUnreadable(GatewayError):
    """The creator bot answered, and there was no token in what it said.

    Its replies are sentences in a natural language, which Telegram may reword without notice, so a
    missing token is reported with the whole reply rather than guessed at.
    """

    reply: str

    def __str__(self) -> str:
        return (
            "Telegram's creator bot answered without a token, so no bot was created. It said: "
            f"{self.reply!r}"
        )
