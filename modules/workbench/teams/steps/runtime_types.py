"""What a recipe sees of the run it is a step of — the engine's step runner is the one implementation."""

from __future__ import annotations

from typing import Any, Protocol

from ..tools import ToolOutcome


class StepContext(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def team_id(self) -> int: ...

    @property
    def owner_principal(self) -> str: ...

    async def call(
        self, name: str, arguments: dict[str, Any], *, attempt_key: str | None = None
    ) -> ToolOutcome:
        """One tool call through the run's plan and trace. A write whose `attempt_key` was used raises
        `store.AttemptAlreadyMade` and does not go out."""
        ...

    async def placed_orders(self, symbol: str) -> list[dict[str, Any]]: ...
