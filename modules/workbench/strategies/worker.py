"""What runs in the worker process: arrays in, trades and a report out, through a pipe. No database, no HTTP client and no
settings here — the process holds nothing but its arguments (design D5)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from multiprocessing.connection import Connection
from typing import Any

import numpy as np

from .costs import CostModel
from .document import Checked
from .engine import ENGINE_VERSION, simulate
from .requirements import IndicatorKey
from .series import Context, Series
from .vocabulary import Indicator


@dataclass(frozen=True)
class Job:
    checked: Checked
    params: dict[str, float]
    catalogue: dict[str, Indicator]
    series: dict[Context, Series]
    indicators: dict[IndicatorKey, np.ndarray]
    costs: CostModel
    capital: float
    range_from: int
    range_to: int
    seed: int
    repetitions: int


def compute(job: Job) -> dict[str, Any]:
    result = simulate(
        job.checked, job.params, job.catalogue, job.series, job.indicators, job.costs, job.capital,
        job.range_from, job.range_to,
    )
    trades = [asdict(t) for t in result.trades]
    report = {"trades": len(trades), "rejected_entries": result.rejected_entries, "decision_bars": result.decision_bars}
    return {"engine_version": ENGINE_VERSION, "report": report, "trades": trades}


def main(job: Job, pipe: Connection) -> None:
    """The process's whole life: compute, send, end. An exception is sent as text, so the run fails with its reason."""
    try:
        pipe.send(("done", compute(job)))
    except Exception as err:  # noqa: BLE001 — anything ends the run with its name, never a silently dead worker
        pipe.send(("failed", f"{type(err).__name__}: {err}"))
    finally:
        pipe.close()
