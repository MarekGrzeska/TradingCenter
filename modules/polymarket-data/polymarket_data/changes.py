"""Change over a window, computed when somebody asks.

The application this module replaces kept a second worker, a table of upserts, per-window
matching margins and a notification-deduplication table — all so a Telegram bot would not
repeat itself. Without the bot none of it has an audience, and what is left is one query per
window over history this module already holds.

What does carry over is the tolerance, and it carries over because it was measured rather
than guessed: the provider's own spacing wobbles between 57 and 63 seconds inside one series
and widens on its own for older ranges. A base point demanded at an exact instant would
report "no data" on a series that plainly has some.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tc_runtime.db import Conn

from . import store
from .contract import OutcomeChanges, WindowChange

# Dense near now, sparse further out, and asymmetric on purpose. Seven were chosen before
# anybody had seen them on a screen; after a day of the terminal's tab the operator named the
# five they actually read (`five-windows-are-enough`). The two that went — 15m and 12h — were
# not wrong, they were unread, and each one is a separate base-point query **per outcome** on
# every read: a two-outcome event asked fourteen where ten will do, and a 128-market event
# asked hundreds. A prediction market moves slowly enough that a second quarter-hour window
# says what the first one said.
WINDOWS: tuple[tuple[str, timedelta], ...] = (
    ("5m", timedelta(minutes=5)),
    ("1h", timedelta(hours=1)),
    ("4h", timedelta(hours=4)),
    ("24h", timedelta(hours=24)),
    ("7d", timedelta(days=7)),
)

# The shortest window is five minutes and the sampler ticks each minute, so a base point may
# legitimately sit a couple of ticks off the mark. Beyond a tenth of the window it is not the
# spacing wobbling any more — it is a hole, and a change measured across it is a change over
# a longer window than the one it is labelled with.
MIN_TOLERANCE = timedelta(minutes=3)
TOLERANCE_FRACTION = 0.1


def tolerance_for(window: timedelta) -> timedelta:
    return max(MIN_TOLERANCE, window * TOLERANCE_FRACTION)


async def changes_for_outcome(
    conn: Conn, outcome_id: int, name: str, *, now: datetime | None = None
) -> OutcomeChanges:
    """Every window for one outcome, from the history the archive already has."""
    moment = now or datetime.now(UTC)
    latest = await store.sample_at_or_before(conn, outcome_id, moment)
    current = latest.midpoint if latest else None

    windows: list[WindowChange] = []
    for label, span in WINDOWS:
        windows.append(
            await _one_window(conn, outcome_id, label, span, moment, current)
        )
    return OutcomeChanges(
        outcome_id=outcome_id,
        name=name,
        price=float(current) if current is not None else None,
        windows=windows,
    )


async def _one_window(
    conn: Conn,
    outcome_id: int,
    label: str,
    span: timedelta,
    now: datetime,
    current: Decimal | None,
) -> WindowChange:
    target = now - span

    if current is None:
        return WindowChange(
            window=label,  # type: ignore[arg-type]
            unavailable="there is no current price for this outcome",
        )

    baseline = await store.sample_at_or_before(conn, outcome_id, target)
    if baseline is None or baseline.midpoint is None:
        # Not zero, and deliberately not a change measured from the oldest point that does
        # exist. The first would be a claim about the market; the second would be a change
        # over a longer window than the label says.
        return WindowChange(
            window=label,  # type: ignore[arg-type]
            unavailable="the collected history does not reach back this far",
        )

    drift = target - baseline.observed_at
    if drift > tolerance_for(span):
        return WindowChange(
            window=label,  # type: ignore[arg-type]
            unavailable=(
                "the nearest collected point is "
                f"{int(drift.total_seconds() // 60)} minutes older than the window, which "
                "is a gap in collection rather than the provider's usual spacing"
            ),
            baseline_at=baseline.observed_at,
        )

    return WindowChange(
        window=label,  # type: ignore[arg-type]
        change=float(current - baseline.midpoint),
        baseline_at=baseline.observed_at,
    )
