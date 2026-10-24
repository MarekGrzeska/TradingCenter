"""A worker that never answers on its own — what a run past its time, or one being cancelled, looks like from outside.
Its own module because a spawned process imports its target by name."""

from __future__ import annotations

import time


def main(job, pipe) -> None:
    time.sleep(120)
