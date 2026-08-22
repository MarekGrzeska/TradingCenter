"""What this module refuses, and the shape each refusal takes."""

from __future__ import annotations


class StrategyError(Exception):
    """Anything this module refuses on purpose. Never a bare `Exception` to a caller."""


class UnknownStrategy(StrategyError):
    def __init__(self, strategy_id: str) -> None:
        self.strategy_id = strategy_id
        super().__init__(f"no strategy with id {strategy_id!r} in this image's catalogue")


class ParamOutOfRange(StrategyError, ValueError):
    def __init__(self, name: str, value: float, minimum: float, maximum: float) -> None:
        self.name = name
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        super().__init__(
            f"parameter {name!r} = {value!r} is outside [{minimum!r}, {maximum!r}]"
        )


class UnknownFactIndicator(StrategyError):
    """A strategy declared a fact the archive's catalogue does not announce.

    Refused at registration, naming the indicator — `strategy-runtime`, "Fakty pochodzą
    z archiwum, jedną drogą". The alternative is a strategy that runs and silently decides
    on one fact fewer than it was written against.
    """

    def __init__(self, strategy_id: str, indicator: str) -> None:
        self.strategy_id = strategy_id
        self.indicator = indicator
        super().__init__(
            f"strategy {strategy_id!r} declares a fact about indicator {indicator!r}, "
            "which the archive's catalogue does not announce"
        )


class ArchiveUnreachable(StrategyError):
    """The archive did not answer. Never read as "no data": a strategy that cannot see is
    not a strategy that saw nothing (`strategy-runtime`)."""


class ArchiveRefused(StrategyError):
    """The archive answered, and the answer was a refusal — a range over its ceiling, an
    indicator it does not know, a parameter out of range."""
