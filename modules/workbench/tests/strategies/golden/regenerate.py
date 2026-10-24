"""Records the golden results, refusing a moved or vanished result under the same `ENGINE_VERSION`.
Run: `uv run python -m tests.strategies.golden.regenerate`."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any

import numpy as np

from market_data.indicators.catalogue import Lines
from market_data.indicators.catalogue import get as indicator
from market_data.indicators.catalogue.spec import Series as KernelSeries
from strategies.engine import ENGINE_VERSION

from . import DOCUMENTS, RECORDING, indicator_keys, load, recorded_indicators, run, same, series


def refusal(previous: Mapping[str, Any] | None, fresh: Mapping[str, Any], version: int) -> str | None:
    """Why `fresh` may not replace `previous`, or `None`. A new case is an addition; a changed or removed one is the
    engine's result moving, which only a higher version may do."""
    if previous is None or previous["engine_version"] < version:
        return None
    moved = sorted(
        name for name, result in previous["cases"].items()
        if name not in fresh["cases"] or same(fresh["cases"][name], result) is not None
    )
    if not moved:
        return None
    return f"results moved or vanished for {moved} under engine version {version}; raise ENGINE_VERSION first"


def main() -> int:
    data = series()
    entries = []
    for key in sorted(indicator_keys(), key=repr):
        spec = indicator(key.id)
        if not isinstance(spec.computer, Lines):
            print(f"{key.id} draws {spec.output}; a golden strategy reads line indicators only", file=sys.stderr)
            return 1
        source = data[key.context]
        kernel = KernelSeries(*(source.columns[c] for c in ("open", "high", "low", "close")))
        # Through the archive's own parameter resolution, as `POST /indicators` does, not the raw values.
        lines = spec.computer.fn(kernel, spec.resolve_params(dict(key.params)))
        values = [None if not np.isfinite(v) else float(v) for v in lines[key.line]]
        entries.append({"context": list(key.context), "id": key.id, "params": [list(p) for p in key.params],
                        "line": key.line, "values": values})
    recording: dict[str, Any] = {"engine_version": ENGINE_VERSION, "indicators": entries, "cases": {}}
    indicators = recorded_indicators(recording, data)
    recording["cases"] = {name: run(name, data, indicators) for name in DOCUMENTS}

    refused = refusal(load() if RECORDING.exists() else None, recording, ENGINE_VERSION)
    if refused:
        print(refused, file=sys.stderr)
        return 1
    RECORDING.write_text(json.dumps(recording, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"recorded {len(DOCUMENTS)} golden strategies under engine version {ENGINE_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
