"""The system prompt as versioned data, global to the module rather than scoped to an owner. Append-only
by construction: a write inserts a new revision and never touches one that already exists."""

from __future__ import annotations

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import PromptRevision

_SELECT_LATEST_PROMPT_REVISION = """
    SELECT version, with_tools_body, without_tools_body, created_at, source
      FROM prompt_revisions
     ORDER BY id DESC
     LIMIT 1
"""

# `source` stated rather than left to the column default: the two writers of this table have to be told
# apart by what they say, not by which of them remembered to say it.
_INSERT_PROMPT_REVISION = """
    INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body, source)
    VALUES ($1, $2, $3, 'operator')
    RETURNING version, with_tools_body, without_tools_body, created_at, source
"""


def _prompt_revision_from_row(row: asyncpg.Record) -> PromptRevision:
    return PromptRevision(**dict(row))


def _next_prompt_version(current: str) -> str:
    """`"v4"` -> `"v5"` — the migration seeds the first row `"v4"`, matching the last
    version the code-constant scheme used, so this only ever has to add one."""
    return f"v{int(current.removeprefix('v')) + 1}"


async def latest_prompt_revision(conn: Conn) -> PromptRevision:
    row = await fetch_one(conn, _SELECT_LATEST_PROMPT_REVISION)
    return _prompt_revision_from_row(row)


async def create_prompt_revision(
    conn: Conn, *, with_tools_body: str, without_tools_body: str
) -> PromptRevision:
    """Always a new row — an edit is never applied to the one it replaces. Blank text is refused at the
    contract layer, not here; this function trusts what it is given."""
    async with conn.transaction():
        current = await fetch_one(conn, _SELECT_LATEST_PROMPT_REVISION)
        next_version = _next_prompt_version(current["version"])
        row = await fetch_one(
            conn, _INSERT_PROMPT_REVISION, next_version, with_tools_body, without_tools_body
        )
    return _prompt_revision_from_row(row)
