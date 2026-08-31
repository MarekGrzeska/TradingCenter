"""Creating a bot without opening Telegram.

There is no API for this. A bot is created by talking to @BotFather, which is an ordinary bot on a
chat — and a bot may not talk to a bot, so the conversation has to be held by a *user account*. That
is why this file needs MTProto and a session string, and why the whole capability is optional: the
credential it wants is the operator's personal Telegram account, which is not a reasonable condition
of starting a service.

Two rules here are not politeness. This module never speaks to the creator bot on its own initiative
— automating a personal account is exactly what Telegram limits accounts for — and it checks its own
ceiling before speaking, because a refusal from Telegram still costs an attempt counted against that
account.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from .errors import CreatingBotsUnavailable, CreatorBotUnreadable, TooManyBots

log = logging.getLogger(__name__)

# Who to talk to. A constant rather than a setting: there is one of it, and a configurable value here
# would be a way to send an account's credentials at somebody else's bot.
CREATOR_BOT = "BotFather"

# A token's shape, which is the contract. The creator bot's replies are sentences in a natural
# language that Telegram may reword without notice, so what is looked for is the token itself.
_TOKEN = re.compile(r"(\d{5,}:[A-Za-z0-9_-]{30,})")

# Telegram requires it, and finding out by being refused costs a round of the conversation.
_USERNAME_SUFFIX = "bot"


@dataclass(frozen=True, slots=True)
class CreatedBot:
    """What came back. `token` leaves this module only into the database."""

    username: str
    token: str

    @property
    def telegram_id(self) -> int:
        """The bot's own id, which is the part of the token before the colon. Read rather than asked
        for: `getMe` would be a second round trip for a number already in hand."""
        return int(self.token.split(":", 1)[0])


class CreatorBot(Protocol):
    """The conversation with @BotFather, as the rest of this module needs it. A protocol because the
    real implementation needs a Telegram account, and CI is never getting one."""

    async def create(self, *, title: str, username: str) -> str:
        """Sends the create-a-bot exchange and returns @BotFather's final reply, verbatim."""
        ...

    async def delete(self, *, username: str) -> str: ...


def token_in(reply: str) -> str:
    """The token from a reply, or a refusal carrying the whole reply.

    Success is "there is a token in what it said", never "it did not look like an error". A reply
    this module cannot read is reported with its text so the operator can see what Telegram actually
    answered — guessing that it probably worked would leave a bot nobody has the token for.
    """
    found = _TOKEN.search(reply)
    if found is None:
        raise CreatorBotUnreadable(reply=reply)
    return found.group(1)


def usable_username(username: str) -> str:
    """Telegram's rule, applied here rather than learned from a refusal mid-conversation."""
    cleaned = username.strip().lstrip("@")
    if not cleaned.lower().endswith(_USERNAME_SUFFIX):
        raise ValueError(
            f"{username!r} cannot be a bot username: Telegram requires one ending in "
            f"{_USERNAME_SUFFIX!r}"
        )
    return cleaned


def guard(*, can_create: bool, held: int, ceiling: int) -> None:
    """Everything checked before a word is sent to Telegram.

    Both refusals are cheap and both would otherwise be expensive: one is a stack trace about a
    missing setting, the other is an attempt counted against the operator's account.
    """
    if not can_create:
        raise CreatingBotsUnavailable()
    if held >= ceiling:
        raise TooManyBots(held=held, ceiling=ceiling)


def from_settings(settings) -> CreatorBot | None:
    """The conversation, or `None` where no account session is configured.

    `None` rather than a raising stub: the absence is a supported state, and the refusal that names
    the missing settings belongs to `guard`, which every path already passes through.
    """
    if not settings.can_create_bots:
        return None
    return TelethonCreatorBot(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session=settings.telegram_session,
    )


class TelethonCreatorBot:
    """The real conversation, over MTProto.

    Telethon is imported inside the methods rather than at module scope: it is the one dependency
    that exists solely for the optional half, and a module that cannot be imported without it would
    turn "no account session" from a supported state into a failure to start.
    """

    def __init__(self, *, api_id: int, api_hash: str, session: str) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._session = session

    async def _converse(self, lines: list[str]) -> str:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(self._session), self._api_id, self._api_hash)
        await client.connect()
        try:
            reply = ""
            async with client.conversation(CREATOR_BOT, timeout=60) as chat:
                for line in lines:
                    await chat.send_message(line)
                    reply = (await chat.get_response()).raw_text
            return reply
        finally:
            await client.disconnect()  # type: ignore[misc]

    async def create(self, *, title: str, username: str) -> str:
        # The exchange is three messages and each answer is a prompt for the next; only the last one
        # carries the token, which is why every step's reply is kept but only the final is returned.
        return await self._converse(["/newbot", title, username])

    async def delete(self, *, username: str) -> str:
        # The creator bot asks for a confirmation phrase it names itself, and it is this one.
        return await self._converse(["/deletebot", f"@{username}", "Yes, I am totally sure."])
