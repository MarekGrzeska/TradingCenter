"""Every statement this module runs against its own database. Plain asyncpg, no ORM: the tables are
handwritten SQL and so are the queries, so a read is the statement it will actually run.

**One rule shapes this whole file**: no function returning a `Bot` selects `token`. Fetching the
credential is its own function with its own name, so a read cannot leak one by accident.
"""

from __future__ import annotations

from datetime import datetime

from tc_runtime.db import Conn, fetch_one

from .models import Binding, Bot, BotCredential, Destination, DestinationState

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


async def create_destination(conn: Conn, *, name: str, bot_id: int) -> Destination:
    """The intention. It cannot receive yet: a bot may not speak first, so what makes this an address
    is a person opening the conversation, recorded by `bind_destination` below."""
    row = await fetch_one(
        conn,
        """
        INSERT INTO destinations (name, bot_id)
        VALUES ($1, $2)
        RETURNING id, name, bot_id, chat_id, state, bound_at, blocked_at
        """,
        name,
        bot_id,
    )
    return _destination(row)


async def list_destinations(conn: Conn) -> list[Destination]:
    rows = await conn.fetch(
        "SELECT id, name, bot_id, chat_id, state, bound_at, blocked_at "
        "FROM destinations ORDER BY created_at, id"
    )
    return [_destination(row) for row in rows]


async def destination_by_name(conn: Conn, name: str) -> Destination | None:
    row = await conn.fetchrow(
        "SELECT id, name, bot_id, chat_id, state, bound_at, blocked_at "
        "FROM destinations WHERE name = $1",
        name,
    )
    return _destination(row) if row is not None else None


async def count_destinations(conn: Conn) -> int:
    return await conn.fetchval("SELECT count(*) FROM destinations") or 0


async def remove_destination(conn: Conn, name: str) -> bool:
    """The binding, and only the binding. The bot stands: it may be carrying other destinations."""
    result = await conn.execute("DELETE FROM destinations WHERE name = $1", name)
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
    conn: Conn, *, nonce: str, chat_id: int, moment: datetime
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
            UPDATE destinations
            SET chat_id = $2, state = 'ready', bound_at = $3, blocked_at = NULL
            WHERE id = $1
            RETURNING id, name, bot_id, chat_id, state, bound_at, blocked_at
            """,
            spent["destination_id"],
            chat_id,
            moment,
        )
    return _destination(row)


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
