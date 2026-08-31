"""Sending one message: name to destination, destination to bot, bot to Telegram.

Nothing here queues, retries or records. What the caller gets back is what Telegram said, and the
caller decides — `telegram-gateway-delivery` names the price of that and `social-data-alerts` shows
the shape that pays it: record your own marker only after a success, and a failure retries itself.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tc_runtime.db import Conn

from . import store
from .bot_api import BotApi, Delivered
from .errors import (
    Blocked,
    DestinationNotReady,
    MessageTooLong,
    NoSuchDestination,
    TelegramUnreachable,
)


async def send(
    conn: Conn,
    api: BotApi,
    *,
    name: str,
    text: str,
    max_chars: int,
) -> Delivered:
    """One message to one named destination, now.

    The length is checked before anything else: a refusal that costs no request is worth having, and
    Telegram's own answer to an over-long message is a 400 that reads like a bug in this module.
    """
    if len(text) > max_chars:
        raise MessageTooLong(length=len(text), ceiling=max_chars)

    destination = await store.destination_by_name(conn, name)
    if destination is None:
        raise NoSuchDestination(name)
    if not destination.receives:
        # One refusal for "never bound" and "blocked", told apart by the state it carries: the
        # operator's move differs, and both are a start link rather than a retry.
        raise DestinationNotReady(name=name, state=destination.state.value)

    credential = await store.credential_of(conn, destination.bot_id)
    if credential is None:
        # The bot is gone but the destination is not — only reachable if the two were deleted
        # apart, which the schema's cascade prevents. Named rather than left as an AttributeError.
        raise TelegramUnreachable(f"the bot behind {name!r} is no longer configured")

    assert destination.chat_id is not None  # `receives` is exactly this, checked above
    try:
        return await api.send_message(
            credential.token, chat_id=destination.chat_id, text=text
        )
    except Blocked as err:
        # Telegram knows the chat, not the name. Marked here so the next send refuses without
        # spending a request, and re-raised carrying the name the caller actually used.
        await store.mark_blocked(conn, destination.id, datetime.now(UTC))
        raise Blocked(name=name) from err
