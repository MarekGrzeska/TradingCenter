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
    """Asked to create, delete or rotate a bot with no usable owner account — a supported state, not a fault.

    Those acts are a conversation with Telegram's creator bot, which only a logged-in user account can hold.
    `reason` says which part is missing, so the operator is sent to the right step rather than to a setting.
    """

    def __init__(self, reason: str = "no Telegram account is logged in") -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return (
            f"creating, deleting or rotating a bot needs the owner account logged in, and {self.reason}. "
            "Log it in from the terminal's Telegram tab — the gateway sends normally without it."
        )


@dataclass
class LoginUnavailable(GatewayError):
    """A login that cannot start because a setting is missing. Refused before Telegram is spoken to, with the
    setting named: a code sent to a phone for a login that could never be saved is a wasted attempt."""

    setting: str

    def __str__(self) -> str:
        return f"the account cannot be logged in: {self.setting} is not set. Nothing was asked of Telegram."


class LoginNotInProgress(GatewayError):
    """A code or a password with no login to give it to — never started, expired, or lost to a restart."""

    def __str__(self) -> str:
        return (
            "no login is in progress (it expired after ten minutes, or the process restarted). "
            "Start again from the phone number."
        )


@dataclass
class LoginRefused(GatewayError):
    """Telegram said no to a step of the login, in its own words. The step stays open: a wrong code is
    followed by another code, not by starting over."""

    detail: str

    def __str__(self) -> str:
        return f"Telegram refused the login: {self.detail}"


class SessionRejected(GatewayError):
    """Telegram no longer honours the stored session — ended from the phone, or the account was reset."""

    def __str__(self) -> str:
        return (
            "Telegram rejected the stored session, so the account has to be logged in again. "
            "Nothing was done to any bot."
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


@dataclass
class InvalidPurpose(GatewayError):
    """A purpose that is not a dotted lowercase name. Refused before anything is stored or sent."""

    name: str
    shape: str

    def __str__(self) -> str:
        return f"{self.name!r} is not a purpose: it must be {self.shape}"


@dataclass
class PurposeUnassigned(GatewayError):
    """No assignment matches the purpose, so nobody has asked to hear about it.

    A refusal of its own and not a flavour of `NoSuchDestination`: the producer's move is to leave its
    "already told" marker unset and carry on, and the operator's is to assign it in the terminal.
    """

    purpose: str

    def __str__(self) -> str:
        return (
            f"nobody receives {self.purpose!r}: no assignment matches it, and there is no default. "
            "Nothing was sent."
        )


@dataclass
class StillAssigned(GatewayError):
    """A bot or a destination that is still somebody's recipient. Named keys, so the operator knows
    which assignments to move before the removal can go through."""

    what: str
    keys: list[str]

    def __str__(self) -> str:
        return (
            f"{self.what} still receives {', '.join(repr(k) for k in self.keys)}. Move those "
            "assignments to another destination first — removing it now would stop those "
            "notifications without a single refusal anyone would see."
        )
