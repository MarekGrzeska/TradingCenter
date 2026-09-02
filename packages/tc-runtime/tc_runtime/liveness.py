"""When each of a module's loops last finished a pass, and the metric an alert reads it through.

A loop that stops is the failure mode nothing here reported: it holds no connection, answers no
request and raises nothing, so the process stays up, `/ping` stays green and the archive quietly
stops growing. Measured on 24 August 2026 in market-data — one stream room silent for fourteen
hours — and fixed there alone. This is that fix as one thing, for every module with a loop.

Deliberately **not** on `/ping`: that route says the process is alive, not that its work is going
well, and a probe that reddens when a loop is late is a health check wearing a liveness name. The
age goes to a metric, an alert reads the metric, and `/health` may carry it for a person.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

log = logging.getLogger(__name__)

# Reported for a loop that has not finished a pass since the process started. Not zero, which reads
# as "just ran", and not `None`, which an alert rule cannot compare: a large number is the honest
# answer to "how long since it last worked", and it resolves itself on the first pass.
NEVER_RAN = 10**6


class LoopHeartbeat:
    """One loop's last completed pass. `beat()` after the work, never before: a pass that raised
    is a pass that did not happen, and the whole point is to notice."""

    def __init__(self, name: str, *, expected_seconds: float) -> None:
        self.name = name
        # What "late" means for this loop, in its own terms. A sampling pass every minute and a
        # collection every hour are both healthy; one threshold for the two would be wrong twice.
        self.expected_seconds = expected_seconds
        self._last: datetime | None = None

    def beat(self, now: datetime | None = None) -> None:
        self._last = now or datetime.now(UTC)

    @property
    def has_run(self) -> bool:
        return self._last is not None

    def age_seconds(self, now: datetime | None = None) -> float:
        if self._last is None:
            return float(NEVER_RAN)
        return max(0.0, ((now or datetime.now(UTC)) - self._last).total_seconds())

    def passes_late(self, now: datetime | None = None) -> float:
        """The age in passes of this loop's own interval, which is the unit an alert can share
        across modules — the same reason market-data's candle age is reported in periods."""
        if self.expected_seconds <= 0:
            return 0.0
        return self.age_seconds(now) / self.expected_seconds


class Heartbeats:
    """Every loop in one module, so a lifespan builds them once and a router can read them."""

    def __init__(self, *heartbeats: LoopHeartbeat) -> None:
        self._by_name = {heartbeat.name: heartbeat for heartbeat in heartbeats}

    def __iter__(self) -> Iterator[LoopHeartbeat]:
        return iter(self._by_name.values())

    def __getitem__(self, name: str) -> LoopHeartbeat:
        return self._by_name[name]

    def as_dict(self, now: datetime | None = None) -> dict[str, dict[str, float | bool]]:
        """For an authenticated route to answer with. Not for `/ping` — see this module's docstring."""
        return {
            heartbeat.name: {
                "ran": heartbeat.has_run,
                "age_seconds": round(heartbeat.age_seconds(now), 1),
                "expected_seconds": heartbeat.expected_seconds,
            }
            for heartbeat in self
        }


def register_metrics(module: str, heartbeats: Heartbeats) -> None:
    """One observable gauge per module, one observation per loop. An observable gauge's callback
    cannot await, which is why a heartbeat holds a timestamp rather than asking anything."""
    from opentelemetry import metrics
    from opentelemetry.metrics import CallbackOptions, Observation

    meter = metrics.get_meter(module)

    def observe(options: CallbackOptions) -> list[Observation]:
        now = datetime.now(UTC)
        return [
            Observation(heartbeat.passes_late(now), {"loop": heartbeat.name})
            for heartbeat in heartbeats
        ]

    meter.create_observable_gauge(
        f"{module}.loop_passes_late",
        callbacks=[observe],
        description=(
            "How many of its own intervals have passed since each loop last finished a pass. "
            "1 is one pass late and normal; an alert fires higher up. A loop that has never "
            f"finished one reports {NEVER_RAN} intervals rather than zero."
        ),
    )
