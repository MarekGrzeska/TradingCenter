"""What runs in the worker process: arrays in, trades and a report out, through a pipe. No database, no HTTP client and no
settings here — the process holds nothing but its arguments (design D5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from multiprocessing.connection import Connection
from typing import Any

import numpy as np

from . import reports
from .costs import CostModel
from .document import Checked
from .engine import ENGINE_VERSION, simulate
from .evaluate import Evaluator
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
    margin_factor: float | None = None


def compute(job: Job) -> tuple[dict[str, Any], Callable[[], dict[str, Any] | None]]:
    """The run's own result, and the benchmark as a step after it — sent separately, so a benchmark that runs out of
    time costs the benchmark and never the result."""
    d = job.checked.document
    evaluator = Evaluator(job.checked, job.params, job.catalogue, job.series, job.indicators)
    args = {
        "checked": job.checked, "params": job.params, "catalogue": job.catalogue, "series": job.series,
        "indicators": job.indicators, "costs": job.costs, "capital": job.capital,
        "range_from": job.range_from, "range_to": job.range_to, "margin_factor": job.margin_factor,
    }
    result = simulate(**args, evaluator=evaluator)
    report = reports.build(
        result, decision=job.series[(d.symbol, d.timeframe)], minute=job.series[(d.symbol, "MINUTE")],
        costs=job.costs, capital=job.capital, range_from=job.range_from, range_to=job.range_to, random_entry=None,
    )
    outcome = {"engine_version": ENGINE_VERSION, "report": report,
               "trades": [reports.finite(asdict(t)) for t in result.trades]}

    def benchmark() -> dict[str, Any] | None:
        found = reports.random_entry(
            result, simulate_args=args, evaluator=evaluator, seed=job.seed, repetitions=job.repetitions
        )
        return reports.finite(found)

    return outcome, benchmark


def main(job: Job, pipe: Connection) -> None:
    """The process's whole life: the result, then the benchmark, then the end. An exception is sent as text, so the run
    fails with its reason."""
    try:
        outcome, benchmark = compute(job)
        pipe.send(("result", outcome))
        pipe.send(("benchmark", benchmark()))
    except Exception as err:  # noqa: BLE001 — anything ends the run with its name, never a silently dead worker
        pipe.send(("failed", f"{type(err).__name__}: {err}"))
    finally:
        pipe.close()
