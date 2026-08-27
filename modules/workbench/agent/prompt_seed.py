"""How a migration seeds the system prompt without overwriting what a person wrote, here rather than inside a migration
so the next one does not write this `WHERE` from memory: a seed lands only when the newest revision is itself a seed."""

from __future__ import annotations

import sqlalchemy as sa

_SEED = sa.text(
    """
    INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body, source)
    SELECT :version, :with_tools, :without_tools, 'seed'
     WHERE NOT EXISTS (SELECT 1 FROM prompt_revisions)
        OR (SELECT source FROM prompt_revisions ORDER BY id DESC LIMIT 1) = 'seed'
    """
)


def seed_prompt(connection, *, version: str, with_tools: str, without_tools: str) -> bool:
    """Insert this seed unless the operator has written since the last one. Returns whether it went in, so
    a migration can log the skip rather than leave the operator wondering."""
    result = connection.execute(
        _SEED, {"version": version, "with_tools": with_tools, "without_tools": without_tools}
    )
    return result.rowcount > 0
