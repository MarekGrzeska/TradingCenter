"""Builders for the shapes the tests need, so setup stays out of the assertions."""

from __future__ import annotations

from itertools import count

from telegram_gateway import store

_ids = count(1)

# Shaped like a real one — `<telegram id>:<35 characters>` — because the code that recognises a token
# in the creator bot's reply matches on that shape rather than on the sentence around it.
def token_for(telegram_id: int) -> str:
    return f"{telegram_id}:" + "A" * 35


async def bot(conn, *, username: str | None = None, created_here: bool = False):
    telegram_id = next(_ids) * 1000
    name = username or f"alerts{telegram_id}bot"
    return await store.add_bot(
        conn,
        telegram_id=telegram_id,
        username=name,
        title=name.title(),
        token=token_for(telegram_id),
        created_here=created_here,
    )


async def destination(conn, *, name: str | None = None, bot_id: int | None = None):
    if bot_id is None:
        bot_id = (await bot(conn)).id
    return await store.create_destination(
        conn, name=name or f"operator-{next(_ids)}", bot_id=bot_id
    )
