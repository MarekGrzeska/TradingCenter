"""Change over a window, computed when somebody asks — one query per window over history this module
already holds. The tolerance carries over because it was measured: the provider's spacing wobbles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tc_runtime.db import Conn

from . import store
from .contract import OutcomeChanges, WindowChange

# Dense near now, sparse further out, and asymmetric on purpose. Seven were chosen before anybody saw
# them; the two that went were unread, and each is a base-point query *per outcome* on every read.
WINDOWS: tuple[tuple[str, timedelta], ...] = (
    ("5m", timedelta(minutes=5)),
    ("1h", timedelta(hours=1)),
    ("4h", timedelta(hours=4)),
    ("24h", timedelta(hours=24)),
    ("7d", timedelta(days=7)),
)

# The shortest window is five minutes and the sampler ticks each minute, so a base point may sit a
# couple of ticks off. Beyond a tenth of the window it is a hole, and the change spans more than its label.
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
        # Not zero, and deliberately not a change measured from the oldest point that does exist.
        # The first would be a claim about the market; the second a change over a longer window.
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
