"""What a trade costs, stated rather than assumed. The archive holds the bid side, so the spread is
invisible in the data, and a report that does not name its cost model is not a result.

Stated as a parameter per instrument rather than measured, for now: swapping a measurement in later
changes nothing here, because the report names whatever model it was given either way."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CostModel:
    """Costs in the instrument's own price units, except `commission`, which is a fraction of the risk.
    `spread` is the full distance between bid and ask, because that is the number an operator looks up."""

    spread: float = 0.0
    # Per side, on top of the spread: what moving through a thin book actually costs.
    slippage: float = 0.0
    # A round turn, as a fraction of the trade's risk. Zero for the CFD accounts this system trades,
    # where the cost is in the spread; kept because it is not zero everywhere.
    commission_r: float = 0.0

    def __post_init__(self) -> None:
        for name in ("spread", "slippage", "commission_r"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

    @property
    def per_side(self) -> float:
        """What one side of a round turn costs in price units."""
        return self.spread / 2 + self.slippage

    def entry_price(self, price: float, direction: str) -> float:
        """A long buys at the ask and a short sells at the bid, so entering always costs."""
        return price + self.per_side if direction == "long" else price - self.per_side

    def exit_price(self, price: float, direction: str) -> float:
        """And leaving costs again, in the other direction."""
        return price - self.per_side if direction == "long" else price + self.per_side

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any] | None) -> CostModel:
        return cls(**(values or {}))

    def describe(self) -> str:
        return (
            f"spread {self.spread:g}, slippage {self.slippage:g} per side, "
            f"commission {self.commission_r:g}R"
        )


# Deliberately not a default anywhere a report can be produced from it. A zero-cost run is a legitimate
# thing to ask for and an illegitimate thing to arrive at by omission.
FREE = CostModel()
