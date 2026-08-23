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


class DefinitionRefused(StrategyError, ValueError):
    """A rule that will not be saved, and the one thing about it that has to change.

    Refused at the moment it is written rather than at the first candle, the way a team
    definition is (`teams/validation.py`): a rule that cannot run is something the operator
    can still see on the screen they wrote it on, and an hour later it is a strategy that
    silently records nothing (`strategy-configurator`, "Definicja jest odrzucana w chwili
    zapisu").
    """


class UnknownDefinition(StrategyError):
    def __init__(self, strategy_id: str) -> None:
        self.strategy_id = strategy_id
        super().__init__(f"no strategy definition with id {strategy_id!r}")


class UnknownRevision(StrategyError):
    def __init__(self, strategy_id: str, version: int) -> None:
        self.strategy_id = strategy_id
        self.version = version
        super().__init__(f"strategy {strategy_id!r} has no revision {version}")


class RevisionMismatch(StrategyError):
    """A parameter set written for one revision, offered to another.

    Named rather than tolerated: a value inside its range under revision 3 may be outside
    it — or have no declaration at all — under revision 4, so silently reusing the set
    would run a strategy on numbers nothing vouches for (`strategy-configurator`,
    "Rewizja jest niezmienna, a obserwacja ją przypina").
    """

    def __init__(self, parameter_set_id: int, belongs_to: int | None, offered_to: int | None) -> None:
        self.parameter_set_id = parameter_set_id
        super().__init__(
            f"parameter set {parameter_set_id} belongs to revision {belongs_to} and was "
            f"offered to revision {offered_to}"
        )
