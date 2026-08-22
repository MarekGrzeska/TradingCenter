"""The schema this module deploys, against a real PostgreSQL.

The advisory lock itself is `tc-runtime`'s and is tested there; what is tested here is the
pairing — that this module's chain reaches head and that the schema check agrees it did —
and the constraints this module wrote itself.
"""

from __future__ import annotations

import asyncpg
import pytest
from tc_runtime import schema_version

from strategy.runtime import MIGRATIONS

pytestmark = pytest.mark.db


async def test_the_chain_reaches_head_and_the_check_agrees(db: asyncpg.Connection) -> None:
    """A migration that reported success without arriving is the accident this check
    exists for, and it is the one the App Service control plane cannot see."""
    await schema_version.verify(db, MIGRATIONS)


async def test_a_trade_without_its_levels_is_refused(db: asyncpg.Connection) -> None:
    """A trade carries direction, entry, stop and target or it is not a trade.

    Stated in the row as well as in the dataclass, because a row is what a later reader
    actually has — and a decision read back a month later has to be complete enough to
    argue with.
    """
    params_id = await db.fetchval(
        "INSERT INTO parameter_sets (strategy_id, version, params) "
        "VALUES ('baseline', 1, '{}'::jsonb) RETURNING id"
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            "INSERT INTO decisions (strategy_id, symbol, parameter_set_id, as_of, action, "
            "direction, facts) VALUES ('baseline', 'US100', $1, now(), 'trade', 'long', "
            "'{}'::jsonb)",
            params_id,
        )


async def test_one_decision_per_bar(db: asyncpg.Connection) -> None:
    """The loop re-reads the last closed bar on every wake and after every restart. Writing
    a second row for it would turn a restart into a second setup — so the bar is the key,
    and the loop is idempotent because the table says so."""
    params_id = await db.fetchval(
        "INSERT INTO parameter_sets (strategy_id, version, params) "
        "VALUES ('baseline', 1, '{}'::jsonb) RETURNING id"
    )
    insert = (
        "INSERT INTO decisions (strategy_id, symbol, parameter_set_id, as_of, action, "
        "reason, reason_kind, facts) VALUES ('baseline', 'US100', $1, "
        "'2026-08-22T10:00:00Z', 'no_trade', 'nothing here', 'strategy', '{}'::jsonb)"
    )
    await db.execute(insert, params_id)
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(insert, params_id)


async def test_a_parameter_set_version_is_unique_per_strategy(db: asyncpg.Connection) -> None:
    """Versions are append-only and a decision names one. Two rows claiming to be version 1
    would make "which parameters was this decided under" unanswerable."""
    insert = (
        "INSERT INTO parameter_sets (strategy_id, version, params) "
        "VALUES ('baseline', 1, '{}'::jsonb)"
    )
    await db.execute(insert)
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(insert)
