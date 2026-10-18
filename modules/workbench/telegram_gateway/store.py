"""Every statement this module runs against its own database. Plain asyncpg, no ORM: the tables are
handwritten SQL and so are the queries, so a read is the statement it will actually run.

**One rule shapes this whole file**: no function returning a `Bot` selects `token`. Fetching the
credential is its own function with its own name, so a read cannot leak one by accident.
"""

from __future__ import annotations

from datetime import datetime

from tc_runtime.db import Conn, fetch_one

from .models import (
    AccountRecord,
    Binding,
    Bot,
    BotCredential,
    ChatIdentity,
    Destination,
    DestinationState,
    Recipient,
)

# Every column of `bots` except the one. Written once and reused, so that adding a column here is a
# deliberate act rather than something `SELECT *` did on somebody's behalf.
_BOT_COLUMNS = "id, telegram_id, username, title, created_here, added_at"


def _bot(row) -> Bot:
    return Bot(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        title=row["title"],
        created_here=row["created_here"],
        added_at=row["added_at"],
    )


def _destination(row) -> Destination:
    return Destination(
        id=row["id"],
        name=row["name"],
        bot_id=row["bot_id"],
        state=DestinationState(row["state"]),
        chat_id=row["chat_id"],
        bound_at=row["bound_at"],
        blocked_at=row["blocked_at"],
        chat_username=row["chat_username"],
        chat_title=row["chat_title"],
        chat_kind=row["chat_kind"],
    )


async def add_bot(
    conn: Conn,
    *,
    telegram_id: int,
    username: str,
    title: str,
    token: str,
    created_here: bool,
) -> Bot:
    """Idempotent on Telegram's own id: the same bot arriving twice is one row. The token is refreshed
    on conflict, because the operator re-adding a bot is usually how a revoked token is replaced."""
    row = await fetch_one(
        conn,
        f"""
        INSERT INTO bots (telegram_id, username, title, token, created_here)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (telegram_id) DO UPDATE SET
            username = EXCLUDED.username,
            title = EXCLUDED.title,
            token = EXCLUDED.token
        RETURNING {_BOT_COLUMNS}
        """,
        telegram_id,
        username,
        title,
        token,
        created_here,
    )
    return _bot(row)


async def list_bots(conn: Conn) -> list[Bot]:
    rows = await conn.fetch(f"SELECT {_BOT_COLUMNS} FROM bots ORDER BY added_at, id")
    return [_bot(row) for row in rows]


async def bot_by_username(conn: Conn, username: str) -> Bot | None:
    row = await conn.fetchrow(
        f"SELECT {_BOT_COLUMNS} FROM bots WHERE lower(username) = lower($1)", username
    )
    return _bot(row) if row is not None else None


async def bot_by_id(conn: Conn, bot_id: int) -> Bot | None:
    """The bot behind a destination. Its @name is what a response publishes — the row id is this
    module's own bookkeeping and means nothing to a caller."""
    row = await conn.fetchrow(f"SELECT {_BOT_COLUMNS} FROM bots WHERE id = $1", bot_id)
    return _bot(row) if row is not None else None


async def count_bots(conn: Conn) -> int:
    """How many this module holds. Read before speaking to the creator bot, because a refusal after
    the fact still costs an attempt counted against the operator's account."""
    return await conn.fetchval("SELECT count(*) FROM bots") or 0


async def credential_of(conn: Conn, bot_id: int) -> BotCredential | None:
    """The token, on its own. **The only statement in this module that selects it** — called by the
    code about to make a request with it, and by nothing that builds a response."""
    row = await conn.fetchrow("SELECT id, token FROM bots WHERE id = $1", bot_id)
    if row is None:
        return None
    return BotCredential(bot_id=row["id"], token=row["token"])


async def remove_bot(conn: Conn, bot_id: int) -> bool:
    """The bot and everything hanging off it. Its destinations cascade — a destination without a bot
    has nothing to send through, so leaving them would be a row nobody can say the purpose of."""
    result = await conn.execute("DELETE FROM bots WHERE id = $1", bot_id)
    return result.endswith(" 1")


# The columns of a destination, with the recipient's name taken from `recipients`: the copy left in `destinations.name`
# is for the image before this one and is not read.
_DESTINATION_SELECT = (
    "SELECT d.id, r.name, d.bot_id, d.chat_id, d.state, d.bound_at, d.blocked_at, d.chat_username, d.chat_title, "
    "d.chat_kind FROM destinations d JOIN recipients r ON r.id = d.recipient_id"
)


async def create_recipient(conn: Conn, name: str) -> Recipient:
    """The name, once. Asking again for one that exists is not an error: it is the same recipient."""
    row = await fetch_one(
        conn,
        """
        INSERT INTO recipients (name) VALUES ($1)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id, name, created_at
        """,
        name,
    )
    return Recipient(id=row["id"], name=row["name"], created_at=row["created_at"])


async def list_recipients(conn: Conn) -> list[Recipient]:
    rows = await conn.fetch("SELECT id, name, created_at FROM recipients ORDER BY created_at, id")
    return [Recipient(id=row["id"], name=row["name"], created_at=row["created_at"]) for row in rows]


async def recipient_by_name(conn: Conn, name: str) -> Recipient | None:
    row = await conn.fetchrow("SELECT id, name, created_at FROM recipients WHERE name = $1", name)
    if row is None:
        return None
    return Recipient(id=row["id"], name=row["name"], created_at=row["created_at"])


async def remove_recipient(conn: Conn, name: str) -> bool:
    """The recipient and, by the cascade, every binding of it. The bots stand."""
    result = await conn.execute("DELETE FROM recipients WHERE name = $1", name)
    return result.endswith(" 1")


async def create_destination(conn: Conn, *, recipient: Recipient, bot_id: int) -> Destination:
    """The intention to reach a recipient through a bot. It cannot receive yet: a bot may not speak first, so what makes
    this an address is a person opening the conversation, recorded by `bind_destination` below. Asking again for the same
    pair returns the one that exists."""
    await conn.execute(
        """
        INSERT INTO destinations (recipient_id, name, bot_id) VALUES ($1, $2, $3)
        ON CONFLICT (recipient_id, bot_id) DO NOTHING
        """,
        recipient.id,
        recipient.name,
        bot_id,
    )
    found = await destination_of(conn, recipient.name, bot_id)
    assert found is not None
    return found


async def list_destinations(conn: Conn) -> list[Destination]:
    rows = await conn.fetch(f"{_DESTINATION_SELECT} ORDER BY d.created_at, d.id")
    return [_destination(row) for row in rows]


async def destinations_of(conn: Conn, name: str) -> list[Destination]:
    """Every way a recipient can be reached, in the order they were added."""
    rows = await conn.fetch(f"{_DESTINATION_SELECT} WHERE r.name = $1 ORDER BY d.created_at, d.id", name)
    return [_destination(row) for row in rows]


async def destination_of(conn: Conn, name: str, bot_id: int) -> Destination | None:
    row = await conn.fetchrow(f"{_DESTINATION_SELECT} WHERE r.name = $1 AND d.bot_id = $2", name, bot_id)
    return _destination(row) if row is not None else None


async def count_destinations(conn: Conn, *, receiving: bool = False) -> int:
    """How many there are, or how many can actually receive. The two differ by every destination
    whose link nobody has tapped yet, which is the difference a state route exists to report."""
    if not receiving:
        return await conn.fetchval("SELECT count(*) FROM destinations") or 0
    return (
        await conn.fetchval(
            "SELECT count(*) FROM destinations WHERE state = 'ready' AND chat_id IS NOT NULL"
        )
        or 0
    )


async def remove_destination(conn: Conn, name: str, bot_id: int) -> bool:
    """One binding, and only that. The bot stands, and so do the recipient's other bindings."""
    result = await conn.execute(
        "DELETE FROM destinations d USING recipients r WHERE r.id = d.recipient_id AND r.name = $1 AND d.bot_id = $2",
        name,
        bot_id,
    )
    return result.endswith(" 1")


async def issue_nonce(
    conn: Conn, *, nonce: str, destination_id: int, expires_at: datetime
) -> Binding:
    row = await fetch_one(
        conn,
        """
        INSERT INTO binding_nonces (nonce, destination_id, expires_at)
        VALUES ($1, $2, $3)
        RETURNING nonce, destination_id, expires_at, used_at
        """,
        nonce,
        destination_id,
        expires_at,
    )
    return Binding(
        nonce=row["nonce"],
        destination_id=row["destination_id"],
        expires_at=row["expires_at"],
        used_at=row["used_at"],
    )


async def binding_for(conn: Conn, nonce: str) -> Binding | None:
    row = await conn.fetchrow(
        "SELECT nonce, destination_id, expires_at, used_at FROM binding_nonces WHERE nonce = $1",
        nonce,
    )
    if row is None:
        return None
    return Binding(
        nonce=row["nonce"],
        destination_id=row["destination_id"],
        expires_at=row["expires_at"],
        used_at=row["used_at"],
    )


async def bind_destination(
    conn: Conn,
    *,
    nonce: str,
    chat_id: int,
    moment: datetime,
    who: ChatIdentity | None = None,
) -> Destination | None:
    """Spends the secret and turns the intention into an address, or neither.

    One transaction, and the `used_at IS NULL` in the update is what makes it one-shot: two arrivals
    of the same secret race here rather than in Python, and the loser updates no row.
    """
    async with conn.transaction():
        spent = await conn.fetchrow(
            """
            UPDATE binding_nonces SET used_at = $2
            WHERE nonce = $1 AND used_at IS NULL AND expires_at > $2
            RETURNING destination_id
            """,
            nonce,
            moment,
        )
        if spent is None:
            return None
        row = await fetch_one(
            conn,
            """
            WITH bound AS (
                UPDATE destinations
                SET chat_id = $2, state = 'ready', bound_at = $3, blocked_at = NULL,
                    chat_username = $4, chat_title = $5, chat_kind = $6
                WHERE id = $1
                RETURNING id, recipient_id, bot_id, chat_id, state, bound_at, blocked_at, chat_username, chat_title,
                          chat_kind
            )
            SELECT b.id, r.name, b.bot_id, b.chat_id, b.state, b.bound_at, b.blocked_at, b.chat_username,
                   b.chat_title, b.chat_kind
              FROM bound b JOIN recipients r ON r.id = b.recipient_id
            """,
            spent["destination_id"],
            chat_id,
            moment,
            who.username if who else None,
            who.title if who else None,
            who.kind if who else None,
        )
    return _destination(row)


async def note_identity(conn: Conn, destination_id: int, who: ChatIdentity) -> None:
    """Who a destination bound before this was recorded turns out to be — asked of Telegram once, after the fact."""
    await conn.execute(
        "UPDATE destinations SET chat_username = $2, chat_title = $3, chat_kind = $4 WHERE id = $1",
        destination_id,
        who.username,
        who.title,
        who.kind,
    )


async def destinations_without_identity(conn: Conn) -> list[Destination]:
    rows = await conn.fetch(f"{_DESTINATION_SELECT} WHERE d.chat_id IS NOT NULL AND d.chat_kind IS NULL")
    return [_destination(row) for row in rows]


async def mark_blocked(conn: Conn, destination_id: int, moment: datetime) -> None:
    """The recipient blocked the bot. Not a deletion: the name and the intention stand, and what is
    gone is consent — which comes back with a second start rather than with a retry."""
    await conn.execute(
        "UPDATE destinations SET state = 'blocked', blocked_at = $2 WHERE id = $1",
        destination_id,
        moment,
    )


async def next_offset(conn: Conn, bot_id: int) -> int:
    return await conn.fetchval("SELECT next_offset FROM update_offsets WHERE bot_id = $1", bot_id) or 0


async def note_offset(conn: Conn, bot_id: int, offset: int) -> None:
    """Telegram's long-poll cursor, kept across restarts. Forgetting it re-reads updates already acted
    on, and a start command replayed that way would rebuild a destination the operator had removed."""
    await conn.execute(
        """
        INSERT INTO update_offsets (bot_id, next_offset) VALUES ($1, $2)
        ON CONFLICT (bot_id) DO UPDATE SET
            next_offset = GREATEST(update_offsets.next_offset, EXCLUDED.next_offset),
            updated_at = now()
        """,
        bot_id,
        offset,
    )


# --- the account that owns the bots ----------------------------------------------------------------


async def get_account(conn: Conn) -> AccountRecord | None:
    """Who is logged in. **Not the session**: that is `encrypted_session`, alone, like a bot's token."""
    row = await conn.fetchrow(
        "SELECT username, phone_masked, logged_in_at, rejected_at FROM account_session WHERE id = 1"
    )
    if row is None:
        return None
    return AccountRecord(
        username=row["username"],
        phone_masked=row["phone_masked"],
        logged_in_at=row["logged_in_at"],
        rejected_at=row["rejected_at"],
    )


async def encrypted_session(conn: Conn) -> str | None:
    """The stored session, still encrypted. The only statement in this module that selects it."""
    return await conn.fetchval("SELECT session_encrypted FROM account_session WHERE id = 1")


async def save_account(
    conn: Conn, *, session_encrypted: str, username: str, phone_masked: str
) -> None:
    """One account: a second login replaces the first, and clears a rejection."""
    await conn.execute(
        """
        INSERT INTO account_session (id, session_encrypted, username, phone_masked)
        VALUES (1, $1, $2, $3)
        ON CONFLICT (id) DO UPDATE SET
            session_encrypted = EXCLUDED.session_encrypted,
            username = EXCLUDED.username,
            phone_masked = EXCLUDED.phone_masked,
            logged_in_at = now(),
            rejected_at = NULL
        """,
        session_encrypted,
        username,
        phone_masked,
    )


async def delete_account(conn: Conn) -> bool:
    result = await conn.execute("DELETE FROM account_session WHERE id = 1")
    return result.endswith(" 1")


async def mark_account_rejected(conn: Conn) -> None:
    """Telegram refused the session when it was used. Kept as a fact so the state route can say so without
    asking Telegram again."""
    await conn.execute("UPDATE account_session SET rejected_at = now() WHERE id = 1")
