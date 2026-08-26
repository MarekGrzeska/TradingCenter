"""`uv run python -m strategy.backtest` — one run, or several compared. A command rather than a route,
and not part of any suite: a backtest over two years is minutes of somebody's afternoon.

`name@version` names a revision, which makes comparing two revisions of one definition a matter of naming
it twice. The database is reached only when something needs it: coded entries run against the archive alone."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from .. import resolver
from ..archive import Archive, http_client
from ..catalogue import all_entries
from ..config import Settings
from ..errors import StrategyError
from ..resolver import Resolved
from . import run
from .costs import CostModel
from .report import NotComparable, compare


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def named(value: str) -> tuple[str, int | None]:
    """`my_rule@3` as its id and its revision; a bare name as its id and "the newest"."""
    id_, _, version = value.partition("@")
    if not version:
        return id_, None
    if not version.isdigit():
        raise argparse.ArgumentTypeError(
            f"{value!r}: what follows '@' is a revision number, e.g. my_rule@3"
        )
    return id_, int(version)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="strategy.backtest", description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--from", dest="start", required=True, type=_instant)
    parser.add_argument("--to", dest="end", required=True, type=_instant)
    parser.add_argument(
        "--strategy",
        action="append",
        default=None,
        type=named,
        help=(
            "repeat to compare; `name@3` names a revision of a written rule. Omitted runs "
            "every strategy this platform can run, written ones included"
        ),
    )
    # No defaults that flatter: a zero-cost run has to be asked for, and the report says
    # what it assumed either way.
    parser.add_argument("--spread", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--commission-r", type=float, default=0.0)
    parser.add_argument(
        "--daily-loss-r",
        type=float,
        default=None,
        help="stop taking setups for the day after losing this many R",
    )
    parser.add_argument("--json", action="store_true", help="the reports, machine-readable")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="write each report to this module's database, where /backtests reads it",
    )
    return parser.parse_args(argv)


@asynccontextmanager
async def _pool(settings: Settings):
    """A connection of this command's own rather than the running module's: this is a separate process,
    and a backtest must not need the platform to be serving."""
    from tc_runtime.db import pool as make_pool

    async with make_pool(
        settings.database_url,
        user=settings.database_user,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        tenant_id=settings.azure_tenant_id,
    ) as pool:
        yield pool


async def _chosen(settings: Settings, asked: list[tuple[str, int | None]] | None) -> list[Resolved]:
    """What to run, resolved — reaching the database only if something asked for a rule."""
    coded = {spec.id for spec in all_entries()}
    if asked is not None and all(id_ in coded and version is None for id_, version in asked):
        from ..catalogue import get

        return [Resolved(spec=get(id_)) for id_, _ in asked]

    async with _pool(settings) as pool, pool.acquire() as conn:
        if asked is None:
            return await resolver.all_available(conn)
        return [
            await resolver.resolve(conn, id_, version=version) for id_, version in asked
        ]


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()  # type: ignore[call-arg]
    costs = CostModel(
        spread=args.spread, slippage=args.slippage, commission_r=args.commission_r
    )
    chosen = await _chosen(settings, args.strategy)

    async with http_client(settings.market_data_scope) as client:
        archive = Archive(settings.market_data_url, client)
        reports = []
        for one in chosen:
            reports.append(
                await run(
                    archive,
                    one.spec,
                    args.symbol,
                    start=args.start,
                    end=args.end,
                    costs=costs,
                    daily_loss_limit_r=args.daily_loss_r,
                    revision=None if one.revision is None else one.revision.version,
                    revision_id=one.revision_id,
                )
            )

    # Stamped here rather than inside the run: nothing in the replay may read a clock, or
    # the run would stop being reproducible.
    ran_at = datetime.now(tz=UTC)
    reports = [
        type(report)(**{**vars(report), "ran_at": ran_at}) for report in reports
    ]

    if len(reports) > 1:
        # Every run here shares a symbol, a range and a cost model by construction; the check is kept
        # for the day this command grows a way to load a report from disk.
        compare(reports)

    if args.keep:
        await _keep(settings, reports)

    if args.json:
        print(json.dumps([report.as_dict() for report in reports], indent=2))
    else:
        print("\n\n".join(report.summary() for report in reports))
    return 0


async def _keep(settings: Settings, reports: list) -> None:
    """Write each report where `/backtests` reads it."""
    from .. import store

    async with _pool(settings) as pool, pool.acquire() as conn:
        for report in reports:
            await store.record_backtest_run(
                conn,
                strategy_id=report.strategy_id,
                strategy_revision_id=report.strategy_revision_id,
                symbol=report.symbol,
                resolution=report.resolution,
                range_from=report.range_from,
                range_to=report.range_to,
                params=report.params,
                costs=report.costs.as_dict(),
                report=report.as_dict(),
            )


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    try:
        raise SystemExit(asyncio.run(main()))
    except (StrategyError, NotComparable) as err:
        print(f"refused: {err}", file=sys.stderr)
        raise SystemExit(2) from err
