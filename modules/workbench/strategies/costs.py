"""What a trade costs, stated rather than assumed: the archive holds the bid, so the spread is invisible in the data, and a
run that does not name its costs is not a result. Every field is required; a zero is a choice written down."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CostModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # The full distance between bid and ask in price units: one number, or 24 — one per UTC hour, because the spread at
    # night and at an open is not the spread at noon, and on a minute strategy that difference is the result.
    spread: float | list[float]
    # Per side, on top of the spread, for every order that takes the price (market, stop) — not for a limit or a target.
    slippage: float = Field(ge=0)
    # A fraction of the position's value charged (positive) or paid (negative) for each night it is held.
    overnight_long: float
    overnight_short: float
    # The UTC hour the provider settles the day at; crossing it with a position open is one night.
    rollover_hour: int = Field(ge=0, le=23)

    @field_validator("spread")
    @classmethod
    def _spread_is_a_price_distance(cls, value: float | list[float]) -> float | list[float]:
        values = value if isinstance(value, list) else [value]
        if isinstance(value, list) and len(value) != 24:
            raise ValueError(f"an hourly spread profile has 24 values, one per UTC hour; this one has {len(value)}")
        if any(v < 0 for v in values):
            raise ValueError("a spread is a distance and cannot be negative")
        return value

    def spread_at(self, moment: int) -> float:
        if isinstance(self.spread, list):
            return self.spread[(moment // 3600) % 24]
        return self.spread

    def nights(self, entered: int, left: int) -> int:
        """How many times the rollover hour was crossed between two moments — every calendar day counts, weekends too."""
        first = (entered // 86400) * 86400 + self.rollover_hour * 3600
        if first <= entered:
            first += 86400
        return 0 if left < first else (left - first) // 86400 + 1
