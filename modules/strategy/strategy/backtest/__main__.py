"""`uv run python -m strategy.backtest` — one run, or several compared.

A command rather than a route, and not part of any test suite: a backtest over two years
is minutes of somebody's afternoon, and the repository's own rule is that no performance
work belongs in the unit suite. What *is* tested is everything it calls.

    uv run python -m strategy.backtest --symbol US100 --from 2025-01-01 --to 2026-01-01
    uv run python -m strategy.backtest --symbol US100 --from ... --to ... \\
        --strategy baseline_ma_cross --strategy something_else --spread 1.5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime

from ..archive import Archive, http_client
from ..catalogue import all_entries
from ..config import Settings
from ..errors import StrategyError
from . import run
from .costs import CostModel
from .report import NotComparable, compare


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="strategy.backtest", description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--from", dest="start", required=True, type=_instant)
    parser.add_argument("--to", dest="end", required=True, type=_instant)
    parser.add_argument(
        "--strategy",
        action="append",
        default=None,
        help="repeat to compare; omitted runs every strategy in the catalogue",
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


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()  # type: ignore[call-arg]
    costs = CostModel(
        spread=args.spread, slippage=args.slippage, commission_r=args.commission_r
    )
    strategies = args.strategy or [spec.id for spec in all_entries()]

    async with http_client(settings.market_data_scope) as client:
        archive = Archive(settings.market_data_url, client)
        reports = []
        for strategy_id in strategies:
            reports.append(
                await run(
                    archive,
                    strategy_id,
                    args.symbol,
                    start=args.start,
                    end=args.end,
                    costs=costs,
                    daily_loss_limit_r=args.daily_loss_r,
                )
            )

    # Stamped here rather than inside the run: nothing in the replay may read a clock, or
    # the run would stop being reproducible.
    ran_at = datetime.now(tz=UTC)
    reports = [
        type(report)(**{**vars(report), "ran_at": ran_at}) for report in reports
    ]

    if len(reports) > 1:
        # Every run here shares a symbol, a range and a cost model by construction; the
        # check is kept anyway, because the day this command grows a way to load a report
        # from disk is the day it stops being true by construction.
        compare(reports)

    if args.keep:
        await _keep(settings, reports)

    if args.json:
        print(json.dumps([report.as_dict() for report in reports], indent=2))
    else:
        print("\n\n".join(report.summary() for report in reports))
    return 0


async def _keep(settings: Settings, reports: list) -> None:
    """Write each report where `/backtests` reads it.

    Its own connection rather than the running module's: this command is a separate
    process, and a backtest must not need the platform to be up to be run.
    """
    from tc_runtime.db import pool as make_pool

    from .. import store

    async with make_pool(
        settings.database_url,
        user=settings.database_user,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        tenant_id=settings.azure_tenant_id,
    ) as pool, pool.acquire() as conn:
        for report in reports:
            await store.record_backtest_run(
                conn,
                strategy_id=report.strategy_id,
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
