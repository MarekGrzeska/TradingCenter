"""Waiting for a run working in the background, from a synchronous test: `TestClient` drives the app from a portal
thread while the run lives on the event loop. `time.sleep` releases the GIL, which is what lets that loop move the run."""

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
