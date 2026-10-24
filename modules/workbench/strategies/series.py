"""A series as the engine holds it: arrays, one row per bar, every bar carrying the moment its values became known. Times
are whole seconds since the epoch, UTC — arithmetic on them is what alignment and the clock of a run are made of."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

PERIOD_SECONDS: dict[str, int] = {
    "MINUTE": 60,
    "MINUTE_5": 300,
    "MINUTE_15": 900,
    "MINUTE_30": 1800,
    "HOUR": 3600,
    "HOUR_4": 14400,
    "DAY": 86400,
    "WEEK": 604800,
}

COLUMNS = ("open", "high", "low", "close", "volume")

# (instrument, resolution)
Context = tuple[str, str]


def epoch(moment: datetime | str) -> int:
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    if moment.tzinfo is None:
        # A moment without a zone is UTC here, as the archive reads one; `timestamp()` would take it as local time.
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp())


def moment(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


@dataclass(frozen=True)
class Series:
    resolution: str
    starts: np.ndarray
    # When each bar's values were known. For a candle, the end of its period: the archive serves only closed bars.
    available: np.ndarray
    columns: dict[str, np.ndarray] = field(default_factory=dict)

    @classmethod
    def from_candles(cls, resolution: str, candles: list[dict[str, Any]]) -> Series:
        """The archive's `CandleOut` rows, ascending and one per period (a repeated period keeps its last answer)."""
        by_start: dict[int, dict[str, Any]] = {epoch(c["time"]): c for c in candles}
        starts = np.array(sorted(by_start), dtype=np.int64)
        columns = {
            name: np.array(
                [np.nan if by_start[s].get(name) is None else float(by_start[s][name]) for s in starts.tolist()],
                dtype=np.float64,
            )
            for name in COLUMNS
        }
        return cls(resolution, starts, starts + PERIOD_SECONDS[resolution], columns)

    def __len__(self) -> int:
        return int(self.starts.size)

    def fingerprint(self) -> dict[str, Any]:
        """Enough to tell two reads of "the same" series apart: how many bars, which span, and a hash of every value."""
        digest = hashlib.sha256(self.starts.tobytes())
        for name in COLUMNS:
            digest.update(np.nan_to_num(self.columns[name], nan=-1.0).tobytes())
        return {
            "bars": len(self),
            "first": int(self.starts[0]) if len(self) else None,
            "last": int(self.starts[-1]) if len(self) else None,
            "sha256": digest.hexdigest(),
        }


def align(source_available: np.ndarray, target_moments: np.ndarray) -> np.ndarray:
    """For each target moment, the index of the last source row known by then, or -1 when none was. The whole of the
    rule "a value is visible from the moment it was available", in one call."""
    return np.searchsorted(source_available, target_moments, side="right") - 1


def pick(values: np.ndarray, index: np.ndarray) -> np.ndarray:
    """`values[index]`, with -1 read as "nothing yet" rather than as the last row."""
    out = values[np.clip(index, 0, None)] if values.size else np.full(index.shape, np.nan)
    if values.dtype == bool:
        return np.where(index >= 0, out, False)
    return np.where(index >= 0, out, np.nan)
