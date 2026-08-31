"""Adding a bot this module may speak as — two ways in, one row out.

The operator pastes a token, or the module creates one through @BotFather. Both end at `store.add_bot`
with the identity Telegram reported rather than the one somebody typed, because the @name and the
numeric id are facts about the bot and not preferences about it.
"""

from __future__ import annotations

import logging

from tc_runtime.db import Conn

from . import creator, store
from .bot_api import BotApi
from .creator import CreatedBot, CreatorBot
from .models import Bot

log = logging.getLogger(__name__)


async def adopt(conn: Conn, api: BotApi, *, token: str) -> Bot:
    """A token the operator pasted. Telegram is asked who it belongs to rather than being told."""
    identity = await api.get_me(token)
    return await store.add_bot(
        conn,
        telegram_id=int(identity["id"]),
        username=str(identity["username"]),
        title=str(identity.get("first_name") or identity["username"]),
        token=token,
        created_here=False,
    )


async def create(
    conn: Conn,
    bot: CreatorBot,
    *,
    title: str,
    username: str,
    can_create: bool,
    ceiling: int,
) -> Bot:
    """A new bot, through the creator bot.

    The order is the point: the username is validated and the ceiling checked **before** a word is
    sent, because both refusals are free here and expensive there — one against the operator's
    account limits, the other a round of a conversation that fails on a rule Telegram states plainly.
    """
    wanted = creator.usable_username(username)
    creator.guard(can_create=can_create, held=await store.count_bots(conn), ceiling=ceiling)

    reply = await bot.create(title=title, username=wanted)
    created = CreatedBot(username=wanted, token=creator.token_in(reply))

    stored = await store.add_bot(
        conn,
        telegram_id=created.telegram_id,
        username=created.username,
        title=title,
        token=created.token,
        created_here=True,
    )
    # The username, never the token — this is the line that would otherwise put a live credential in
    # a log that gets shipped somewhere.
    log.info("created bot @%s through the creator bot", stored.username)
    return stored


async def destroy(
    conn: Conn,
    bot: CreatorBot,
    *,
    existing: Bot,
    can_create: bool,
) -> None:
    """Removes a bot from Telegram and from here, in that order.

    Telegram first: a row deleted before the conversation succeeds leaves a bot alive that this
    module can no longer name, and it still counts against the account's ceiling of twenty.
    """
    creator.guard(can_create=can_create, held=0, ceiling=1)
    await bot.delete(username=existing.username)
    await store.remove_bot(conn, existing.id)
    log.warning("deleted bot @%s and every destination behind it", existing.username)
