"""Records the golden results. Refuses to change a recorded result under the same `ENGINE_VERSION`: a moved result is a
change to the engine, and every report carries the number that says which engine made it.

    uv run python -m tests.strategies.golden.regenerate
"""

from __future__ import annotations

import json
import sys

import numpy as np

from market_data.indicators.catalogue import get as indicator
from market_data.indicators.catalogue.spec import Series as KernelSeries
from strategies.engine import ENGINE_VERSION

from . import DOCUMENTS, RECORDING, indicator_keys, load, recorded_indicators, run, series


def main() -> int:
    data = series()
    entries = []
    for key in sorted(indicator_keys(), key=repr):
        source = data[key.context]
        kernel = KernelSeries(*(source.columns[c] for c in ("open", "high", "low", "close")))
        lines = indicator(key.id).computer.fn(kernel, dict(key.params))  # type: ignore[union-attr]
        values = [None if not np.isfinite(v) else float(v) for v in lines[key.line]]
        entries.append({"context": list(key.context), "id": key.id, "params": [list(p) for p in key.params],
                        "line": key.line, "values": values})
    recording = {"engine_version": ENGINE_VERSION, "indicators": entries, "cases": {}}
    indicators = recorded_indicators(recording, data)
    recording["cases"] = {name: run(name, data, indicators) for name in DOCUMENTS}

    if RECORDING.exists():
        previous = load()
        moved = [n for n in DOCUMENTS if previous["cases"].get(n) != recording["cases"][n]]
        if moved and previous["engine_version"] >= ENGINE_VERSION:
            print(
                f"results moved for {moved} under engine version {ENGINE_VERSION}; raise ENGINE_VERSION in "
                "strategies/engine.py first", file=sys.stderr,
            )
            return 1
    RECORDING.write_text(json.dumps(recording, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"recorded {len(DOCUMENTS)} golden strategies under engine version {ENGINE_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
