"""`telegram_report` (`teams-steps`): what is said for each step result as a table, and the recipe around it once."""

from __future__ import annotations

import json
from typing import Any

import pytest

from teams.contract import StepDefinition
from teams.steps.telegram_report import MISSING, compose, execute
from teams.tools import ToolOutcome, ToolOutcomeKind

SIGNAL = {"bar_closed_at": "2026-11-16T14:35:00+00:00", "bar_age_seconds": 4, "order": {"side": "long"}}


def _result(decision: str, **extra: Any) -> dict[str, Any]:
    return {"decision": decision, "reason": None, "summary": "...", "symbol": "US100", "signal": SIGNAL, **extra}


ENTERED = _result("entered", trade={"side": "long", "size": 0.5, "fill_price": 27362.0, "position_id": "deal-9"})
EXITED = _result(
    "exited",
    reason="the engine signals exit",
    position_id="deal-9",
    trade={"side": "long", "size": 0.5, "open_price": 27300.0, "close_price": 27350.0, "points": 50.0,
           "pnl": 25.0, "pnl_approximate": False, "currency": "USD"},
)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        pytest.param(ENTERED, ["WEJŚCIE · US100 · LONG", "Cena wykonania: 27362.0", "15:35 (Warszawa), wiek 4 s"], id="entry"),
        pytest.param(
            EXITED,
            ["WYJŚCIE · US100 · LONG", "Cena otwarcia: 27300.0", "Cena zamknięcia: 27350.0 (+50.00 pkt)", "Wynik: +25.00 USD"],
            id="exit",
        ),
        pytest.param(
            _result("exited", trade={"side": "long", "pnl": None}),
            [f"Cena zamknięcia: {MISSING}", f"Wynik: {MISSING}"],
            id="exit without prices",
        ),
        pytest.param(
            _result("exited", trade={"side": "long", "pnl": -3.2, "pnl_approximate": True, "currency": "USD"}),
            ["Wynik: około -3.20 USD"],
            id="exit with the unrealised result",
        ),
        pytest.param(_result("unknown", reason="timed out"), ["ALERT TECHNICZNY", "Powód: timed out"], id="unknown"),
        pytest.param(_result("skipped", reason="bar too old"), ["POMINIĘTE", "Powód: bar too old"], id="a skip worth telling"),
        pytest.param(None, ["brak wyniku kroku strategii"], id="no step result"),
    ],
)
def test_what_is_said(result: dict | None, expected: list[str]) -> None:
    text = compose(result, "DEMO — US100 5 nóg")
    assert text is not None and text.startswith("DEMO — US100 5 nóg\n")
    for part in expected:
        assert part in text


@pytest.mark.parametrize(
    "result", [_result("no_action"), _result("skipped", same_bar=True)], ids=["no action", "same bar again"]
)
def test_nothing_is_said(result: dict) -> None:
    assert compose(result, None) is None


class Ctx:
    key = "report"
    team_id = 7
    owner_principal = "operator-1"

    def __init__(self, outcome: ToolOutcome) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, dict]] = []

    async def call(self, name: str, arguments: dict, *, attempt_key: str | None = None) -> ToolOutcome:
        self.calls.append((name, arguments))
        return self.outcome

    async def placed_orders(self, symbol: str) -> list[dict]:
        return []


STEP = StepDefinition(key="report", recipe="telegram_report", params={"destination": "operator", "bot": "demo_bot"})


async def test_the_message_goes_once_to_the_destination_and_bot() -> None:
    ctx = Ctx(ToolOutcome(ToolOutcomeKind.OK, "{}", 1))

    out = await execute(STEP, ctx, [("execute", json.dumps(ENTERED)), ("other", "an agent's prose")])

    assert out["sent"] is True
    [(name, arguments)] = ctx.calls
    assert name == "send_telegram_message"
    assert (arguments["destination"], arguments["bot"]) == ("operator", "demo_bot")
    assert "Cena wykonania: 27362.0" in arguments["text"]


async def test_a_failed_send_is_the_step_s_result_not_a_failure() -> None:
    ctx = Ctx(ToolOutcome(ToolOutcomeKind.REFUSED, "bot unknown", 1))

    out = await execute(STEP, ctx, [("execute", json.dumps(EXITED))])

    assert (out["sent"], out["reason"]) == (False, "bot unknown")
    assert len(ctx.calls) == 1
