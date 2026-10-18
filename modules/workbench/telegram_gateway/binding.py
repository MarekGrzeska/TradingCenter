"""Turning a tap into a destination.

A bot cannot open a conversation, so no amount of configuration makes a destination receive: a person
has to press Start. What this module can do is make that one tap instead of six — it issues
`t.me/<bot>?start=<nonce>`, watches for the nonce coming back, and binds the chat that sent it.

Long-polling rather than a webhook, and the reason is the platform rather than taste: Telegram holds
no Entra identity, so its POST is refused by Easy Auth before this module sees it. Making a webhook
work would mean exempting that path — a third hole beside `/` and `/ws/stream`, and the first that
accepts content from the internet.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime, timedelta

from tc_runtime.db import Conn

from . import store
from .bot_api import BotApi
from .errors import GatewayError
from .models import Bot, ChatIdentity, Destination, Recipient

log = logging.getLogger(__name__)

# How long a start link is worth tapping. Long enough to walk to a phone, short enough that a link
# left in a chat log is not a standing invitation to bind somebody else's conversation.
NONCE_LIFETIME = timedelta(minutes=30)

# Bytes of randomness in a nonce. It travels in a URL and in a Telegram message, and it is the only
# thing standing between a stranger who saw the link and a destination bound to their chat.
NONCE_BYTES = 16

# How long Telegram holds a poll open with nothing to say. Its own ceiling is 50; this leaves room
# under the client's request timeout so the poll ends rather than the connection.
POLL_SECONDS = 30

# What a failing poll waits before trying again, so a bot whose token was revoked does not spin.
POLL_BACKOFF_SECONDS = 15.0


def start_link(bot: Bot, nonce: str) -> str:
    """Where the person taps. The nonce rides in Telegram's own `start` parameter, which it hands
    back verbatim as the argument of the `/start` command."""
    return f"{bot.start_link}?start={nonce}"


async def offer(
    conn: Conn, *, recipient: Recipient, bot: Bot, now: datetime | None = None
) -> tuple[Destination, str]:
    """Reaches a recipient through a bot and hands back the link that will bind it.

    The binding exists immediately and cannot receive yet: that gap is the honest shape of a platform where a bot may not
    speak first. Asking again for the same recipient and bot issues a fresh secret and makes no second binding.
    """
    moment = now or datetime.now(UTC)
    destination = await store.create_destination(conn, recipient=recipient, bot_id=bot.id)

    nonce = secrets.token_urlsafe(NONCE_BYTES)
    await store.issue_nonce(
        conn,
        nonce=nonce,
        destination_id=destination.id,
        expires_at=moment + NONCE_LIFETIME,
    )
    return destination, start_link(bot, nonce)


def identity_of(chat: dict, sender: dict | None = None) -> ChatIdentity:
    """Who a chat is, from Telegram's own description of it: for a person their @name and full name, for a group or a
    channel its title and its public @name if it has one."""
    kind = chat.get("type")
    if kind == "private":
        source = sender or chat
        full = " ".join(part for part in (source.get("first_name"), source.get("last_name")) if part)
        return ChatIdentity(username=source.get("username") or chat.get("username"), title=full or None, kind=kind)
    return ChatIdentity(username=chat.get("username"), title=chat.get("title"), kind=kind)


def _start_payload(update: dict) -> tuple[int, str, ChatIdentity] | None:
    """`(chat_id, payload, who)` from an update that is a `/start` carrying an argument, else `None`.

    Every other update is ignored rather than parsed: this module reads Telegram for exactly one
    reason, and `telegram-gateway-upstream-access` keeps it that way.
    """
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith("/start"):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        # A bare `/start` — somebody opened the bot without a link. Nothing to bind it to.
        return None
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    # A group start arrives as `/start@thebot <payload>`: the payload is still the last word.
    return int(chat_id), parts[1].strip().split()[-1], identity_of(chat, message.get("from"))


async def consume(conn: Conn, bot: Bot, updates: list[dict], *, now: datetime | None = None) -> int:
    """Binds whatever these updates bind, and moves the cursor past all of them.

    The cursor advances over updates that bound nothing too. Leaving them unacknowledged would have
    Telegram redeliver the same unusable message for as long as it keeps it.
    """
    moment = now or datetime.now(UTC)
    bound = 0
    highest = 0
    for update in updates:
        highest = max(highest, int(update.get("update_id", 0)))
        start = _start_payload(update)
        if start is None:
            continue
        chat_id, payload, who = start
        destination = await store.bind_destination(
            conn, nonce=payload, chat_id=chat_id, moment=moment, who=who
        )
        if destination is None:
            # Expired, already spent, or never issued. Not logged with the payload: it is a secret,
            # and one that failed here is exactly the kind somebody is guessing at.
            log.info("a start command arrived with a link this gateway cannot bind")
            continue
        log.info("destination %s is bound", destination.name)
        bound += 1
    if highest:
        await store.note_offset(conn, bot.id, highest + 1)
    return bound


class Watcher:
    """One long-poll per bot, for as long as the module runs.

    Each bot gets its own task because each has its own token and its own cursor; there is no
    multiplexed form of `getUpdates`. The ceiling on bots is therefore also the ceiling on these.
    """

    def __init__(self, pool, api: BotApi, *, poll_seconds: int = POLL_SECONDS) -> None:
        self._pool = pool
        self._api = api
        self._poll_seconds = poll_seconds
        self._tasks: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        async with self._pool.acquire() as conn:
            bots = await store.list_bots(conn)
        for bot in bots:
            self.watch(bot)

    def watch(self, bot: Bot) -> None:
        """Begins watching a bot, now rather than at the next restart — a bot created through this
        module is usually followed immediately by somebody tapping its link."""
        if bot.id in self._tasks:
            return
        task = asyncio.create_task(self._run(bot), name=f"telegram-watch-{bot.username}")
        self._tasks[bot.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(bot.id, None))

    def forget(self, bot_id: int) -> None:
        task = self._tasks.pop(bot_id, None)
        if task is not None:
            task.cancel()

    async def stop(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        for task in list(self._tasks.values()):
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    async def _run(self, bot: Bot) -> None:
        while True:
            try:
                await self.poll_once(bot)
            except asyncio.CancelledError:
                raise
            except GatewayError as err:
                # A revoked token or an unreachable Telegram. Waiting rather than spinning, and the
                # message is already redacted by the time it gets here.
                log.warning("watching %s failed: %s", bot.username, err)
                await asyncio.sleep(POLL_BACKOFF_SECONDS)
            except Exception:
                log.exception("watching %s failed unexpectedly", bot.username)
                await asyncio.sleep(POLL_BACKOFF_SECONDS)

    async def poll_once(self, bot: Bot) -> int:
        """One long poll and whatever it binds. Separated from the loop so a test can drive it."""
        async with self._pool.acquire() as conn:
            offset = await store.next_offset(conn, bot.id)
            credential = await store.credential_of(conn, bot.id)
        if credential is None:
            # The bot was removed while its watcher was between polls.
            return 0

        updates = await self._api.get_updates(
            credential.token, offset=offset, timeout=self._poll_seconds
        )
        if not updates:
            return 0

        async with self._pool.acquire() as conn:
            return await consume(conn, bot, updates)


async def backfill_identities(pool, api) -> int:
    """Asks Telegram who each bound destination is, for the ones bound before that was recorded. Best effort and once,
    at start: a destination Telegram will not describe stays as it is, and is still somebody to send to."""
    from .errors import GatewayError

    async with pool.acquire() as conn:
        missing = await store.destinations_without_identity(conn)
    filled = 0
    for destination in missing:
        async with pool.acquire() as conn:
            credential = await store.credential_of(conn, destination.bot_id)
        if credential is None or destination.chat_id is None:
            continue
        try:
            chat = await api.get_chat(credential.token, chat_id=destination.chat_id)
        except GatewayError as err:
            log.info("could not ask Telegram who %s is: %s", destination.name, err)
            continue
        async with pool.acquire() as conn:
            await store.note_identity(conn, destination.id, identity_of(chat))
        filled += 1
    return filled
