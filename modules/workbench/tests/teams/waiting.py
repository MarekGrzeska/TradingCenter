"""Waiting for a run that is working in the background, from a synchronous test.

`TestClient` drives the application from a portal thread while a run's task lives on the
event loop, so a test has to hand that loop time rather than ask again as fast as it can.
Both helpers here used to be a bare `for _ in range(60)` with no pause — one in
`test_runs_routes.py`, one in `test_usage_route.py`, the same loop written twice.

That loop is bounded by *round trips*, not by time, and it is a race the test can lose:
sixty requests can be served and answered before the run's task is scheduled at all. It
survived every local run and failed once on CI, on the pull request that added two more
suites of database tests beside it — the extra load did not break it, it made the existing
race visible.

Bounded by a deadline and paused between attempts instead. `time.sleep` releases the GIL,
which is the part the busy loop never did: it is what lets the loop thread actually move
the run along.
"""

from __future__ import annotations

import time
from collections.abc import Container

from fastapi.testclient import TestClient

FINISHED = frozenset({"completed", "failed", "cancelled"})

# Long enough for a run of a scripted provider on a loaded CI runner, short enough that a
# run which will never finish fails the test rather than the job's own time limit.
_TIMEOUT_SECONDS = 20.0
_PAUSE_SECONDS = 0.02


def wait_for_status(
    client: TestClient,
    run_id: int,
    wanted: Container[str] = FINISHED,
    *,
    headers: dict[str, str],
    timeout: float = _TIMEOUT_SECONDS,
) -> dict:
    """Polls the run's own route until its status is one of `wanted`, or fails saying what
    it was still reading when it gave up."""
    deadline = time.monotonic() + timeout
    while True:
        run = client.get(f"/runs/{run_id}", headers=headers).json()
        if run["status"] in wanted:
            return run
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"run {run_id} was still {run['status']!r} after {timeout:g}s, waiting for "
                f"one of {sorted(wanted) if isinstance(wanted, frozenset | set) else wanted}"
            )
        time.sleep(_PAUSE_SECONDS)
