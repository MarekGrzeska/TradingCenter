"""Builders for the shapes the tests need, so setup stays out of the assertions."""

from __future__ import annotations

from itertools import count

from telegram_gateway import store

_ids = count(1)

# Shaped like a real one — `<telegram id>:<35 characters>` — because the code that recognises a token
# in the creator bot's reply matches on that shape rather than on the sentence around it.
def token_for(telegram_id: int) -> str:
    return f"{telegram_id}:" + "A" * 35


async def bot(
    conn, *, username: str | None = None, created_here: bool = False, telegram_id: int | None = None
):
    telegram_id = telegram_id or next(_ids) * 1000
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
    """A recipient reached through a bot: the recipient is made if it is new."""
    if bot_id is None:
        bot_id = (await bot(conn)).id
    recipient = await store.create_recipient(conn, name or f"operator-{next(_ids)}")
    return await store.create_destination(conn, recipient=recipient, bot_id=bot_id)


async def offer(conn, *, name: str, bot, now=None):
    """What the operator's request does: the recipient is made if it is new, then the bot is added to it."""
    from telegram_gateway import binding

    recipient = await store.create_recipient(conn, name)
    return await binding.offer(conn, recipient=recipient, bot=bot, now=now)


async def only_binding(conn, name: str):
    """The one binding a recipient has, or none."""
    found = await store.destinations_of(conn, name)
    assert len(found) <= 1, f"{name!r} has several bindings"
    return found[0] if found else None
