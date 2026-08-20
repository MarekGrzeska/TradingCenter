"""Where the operator put each agent.

Mutable, beside the revisions rather than inside them: dragging a node MUST NOT mint a
revision (specs/terminal-teams, "Przesunięcie nie jest zmianą definicji"). The owner is
reached through the team, which is also what makes a stranger's write a no-op rather than
a refusal in a second place.
"""

from __future__ import annotations

from collections.abc import Sequence

import asyncpg
from tc_runtime.db import Conn

from . import catalogue

_SELECT_LAYOUT = """
    SELECT l.agent_key, l.x, l.y
      FROM team_layouts l
      JOIN teams t ON t.id = l.team_id
     WHERE l.team_id = $1 AND t.owner_principal = $2
     ORDER BY l.agent_key
"""

# The whole layout arrives at once and replaces what was there: the canvas knows where
# every node it drew stands, and an agent deleted from the definition has to lose its row
# rather than sit in the way of a key reused later.
_DELETE_LAYOUT = "DELETE FROM team_layouts WHERE team_id = $1"

_UPSERT_PLACE = """
    INSERT INTO team_layouts (team_id, agent_key, x, y)
    VALUES ($1, $2, $3, $4)
"""


async def get_layout(
    conn: Conn, *, team_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SELECT_LAYOUT, team_id, owner_principal))


async def save_layout(
    conn: Conn, *, team_id: int, owner_principal: str, places: Sequence[tuple[str, float, float]]
) -> bool:
    """Replaces this team's layout. `False` for a team that does not exist or belongs to
    somebody else — the route answers that the same way it answers a missing team.

    `updated_at` on the team is deliberately not touched: the catalogue's "moment ostatniej
    zmiany" is about the definition, and a column that moved because a node was nudged
    would make the list reorder itself for nothing.
    """
    async with conn.transaction():
        # Through the catalogue's own read rather than a second copy of its statement:
        # `archived_at IS NULL` rides on that one, so a retired team stops accepting
        # layout writes for the same reason it stops answering reads.
        team = await catalogue.get_team(conn, team_id=team_id, owner_principal=owner_principal)
        if team is None:
            return False
        await conn.execute(_DELETE_LAYOUT, team_id)
        for agent_key, x, y in places:
            await conn.execute(_UPSERT_PLACE, team_id, agent_key, x, y)
    return True
