"""What a team remembers between runs; rows are only inserted and deleted. The owner is reached by joining `teams` on
every statement but `list_for_run`, which is asked mid-run about a run this module started."""

from __future__ import annotations

import asyncpg
from tc_runtime.db import Conn

_INSERT_MEMORY = """
    INSERT INTO team_memories (team_id, author_agent_key, run_id, content)
    SELECT $1, $2, $3, $4
      FROM teams t
     WHERE t.id = $1 AND t.owner_principal = $5
 RETURNING id, team_id, author_agent_key, run_id, content, created_at
"""

# Newest first, and `id DESC` behind it: two entries written in the same transaction can share `created_at`
# to the microsecond, and a merely-mostly-defined order would drop a different entry depending on the plan.
_SELECT_MEMORIES = """
    SELECT m.id, m.team_id, m.author_agent_key, m.run_id, m.content, m.created_at
      FROM team_memories m
      JOIN teams t ON t.id = m.team_id
     WHERE m.team_id = $1 AND t.owner_principal = $2
     ORDER BY m.created_at DESC, m.id DESC
     LIMIT $3
"""

_COUNT_MEMORIES = """
    SELECT count(*) AS total
      FROM team_memories m
      JOIN teams t ON t.id = m.team_id
     WHERE m.team_id = $1 AND t.owner_principal = $2
"""

_COUNT_FOR_RUN = "SELECT count(*) AS total FROM team_memories WHERE run_id = $1"

_DELETE_MEMORY = """
    DELETE FROM team_memories m
     USING teams t
     WHERE m.id = $1 AND m.team_id = $2 AND t.id = m.team_id AND t.owner_principal = $3
"""


async def add_memory(
    conn: Conn,
    *,
    team_id: int,
    owner_principal: str,
    author_agent_key: str,
    run_id: int | None,
    content: str,
) -> asyncpg.Record | None:
    """Writes one entry and hands it back, or `None` for a team that does not exist or belongs to somebody else, with the
    owner check inside the `INSERT ... SELECT`. `archived_at` is not consulted: a run already in flight finishes."""
    return await conn.fetchrow(
        _INSERT_MEMORY, team_id, author_agent_key, run_id, content, owner_principal
    )


async def list_memories(
    conn: Conn, *, team_id: int, owner_principal: str, limit: int
) -> tuple[list[asyncpg.Record], int]:
    """This team's newest entries up to `limit`, and how many it has in total. The total comes back beside
    the rows because a cut the reader cannot see is a memory the model believes is complete."""
    rows = list(await conn.fetch(_SELECT_MEMORIES, team_id, owner_principal, limit))
    total = await conn.fetchval(_COUNT_MEMORIES, team_id, owner_principal)
    return rows, int(total or 0)


async def count_memories_for_run(conn: Conn, *, run_id: int) -> int:
    """How many entries this run has written — what the per-run write ceiling counts. Counted in the
    database, because agents in one run work concurrently and a counter in memory lets two pass together."""
    return int(await conn.fetchval(_COUNT_FOR_RUN, run_id) or 0)


async def delete_memory(
    conn: Conn, *, entry_id: int, team_id: int, owner_principal: str
) -> bool:
    """Removes one entry. `False` for an entry that does not exist, belongs to another team, or whose team
    belongs to somebody else — the route answers all three the same way."""
    result = await conn.execute(_DELETE_MEMORY, entry_id, team_id, owner_principal)
    return result.rsplit(" ", 1)[-1] != "0"
