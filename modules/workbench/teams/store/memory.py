"""What a team remembers between runs.

Mutable and keyed by team, beside the revisions rather than inside them — the reasoning
is in migration `0008_team_memories`. Rows are only ever inserted and deleted; nothing
here updates one (specs/teams-memory, "Wpis raz zapisany się nie zmienia").

The owner is reached by joining `teams` on every statement, including the delete, so a
stranger's entry answers exactly like an entry that was never written. The one read that
does *not* join is `list_for_run`, which counts a run's own writes: it is asked mid-run
about a run this module started itself, so there is no caller identity to filter by and
nothing about the answer that a stranger could learn.
"""

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

# Newest first, and `id DESC` behind it: two entries written in the same transaction can
# share `created_at` to the microsecond, and an order that is only *mostly* defined would
# make the read ceiling drop a different entry depending on the plan.
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
    """Writes one entry and hands it back, or `None` for a team that does not exist or
    belongs to somebody else.

    The owner check rides inside the `INSERT ... SELECT` rather than a read before it: a
    run holds no lock on its team, and a team archived between the two statements would
    otherwise leave an entry behind on a check that had already passed. Note that
    `archived_at` is deliberately *not* consulted — a retired team stops being offered for
    a run, but a run already in flight finishes, and an entry it refuses to write here
    would be work the operator paid for and cannot read.
    """
    return await conn.fetchrow(
        _INSERT_MEMORY, team_id, author_agent_key, run_id, content, owner_principal
    )


async def list_memories(
    conn: Conn, *, team_id: int, owner_principal: str, limit: int
) -> tuple[list[asyncpg.Record], int]:
    """This team's newest entries up to `limit`, and how many it has in total.

    The total comes back beside the rows because both the tool and the route have to say
    that there is more than was handed over — a cut the reader cannot see is a memory the
    model believes is complete (specs/teams-memory, "Odczyt oddaje najnowsze wpisy, a nie
    całą pamięć").
    """
    rows = list(await conn.fetch(_SELECT_MEMORIES, team_id, owner_principal, limit))
    total = await conn.fetchval(_COUNT_MEMORIES, team_id, owner_principal)
    return rows, int(total or 0)


async def count_memories_for_run(conn: Conn, *, run_id: int) -> int:
    """How many entries this run has written — what the per-run write ceiling counts.

    Counted in the database rather than held in the runner, because agents in one run work
    concurrently and a counter in memory would let two of them pass the ceiling together.
    """
    return int(await conn.fetchval(_COUNT_FOR_RUN, run_id) or 0)


async def delete_memory(
    conn: Conn, *, entry_id: int, team_id: int, owner_principal: str
) -> bool:
    """Removes one entry. `False` for an entry that does not exist, belongs to another
    team, or whose team belongs to somebody else — the route answers all three the same
    way (specs/teams-browser-access)."""
    result = await conn.execute(_DELETE_MEMORY, entry_id, team_id, owner_principal)
    return result.rsplit(" ", 1)[-1] != "0"
