"""claude-agent-runtime: a check-in is typed in at its time unless the operator wrote in the last hour; one missed while
the session was down is delivered within the hour, once."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from claude_agent import checkin

NOW = datetime(2026, 11, 5, 8, 30, tzinfo=checkin.ZONE)


def test_the_default_pair_and_none() -> None:
    assert [(c.slot, c.skill) for c in checkin.parse_checkins("")] == [
        ("08:30", "przeglad-rana"),
        ("21:30", "podsumowanie-dnia"),
    ]
    assert checkin.parse_checkins("none") == []


@pytest.mark.parametrize("value", ["8:30 przeglad-rana", "08:30", "08:30 Przeglad Rana", "25:00 x"])
def test_a_malformed_checkin_refuses(value: str) -> None:
    with pytest.raises(ValueError, match="AGENT_CHECKINS"):
        checkin.parse_checkins(value)


@pytest.mark.parametrize(
    ("last", "handled", "up", "expected"),
    [
        (None, set(), True, "send"),
        (NOW - timedelta(minutes=20), set(), True, "skip-active"),
        (NOW - timedelta(hours=2), set(), True, "send"),
        (None, {"2026-11-05 08:30"}, True, "skip-handled"),
        (None, set(), False, "pending"),
    ],
)
def test_slot(last: datetime | None, handled: set[str], up: bool, expected: str) -> None:
    decision = checkin.decide_slot(
        slot="08:30", now=NOW, handled=handled, last_operator=last, session_up=up
    )
    assert decision == expected


@pytest.mark.parametrize(
    ("minutes_later", "up", "expected"),
    [(3, True, "send"), (3, False, "wait"), (61, True, "drop")],
)
def test_pending(minutes_later: int, up: bool, expected: str) -> None:
    pending = {"day": "2026-11-05", "slot": "08:30", "at": NOW.timestamp()}
    decision = checkin.decide_pending(
        pending=pending,
        now=NOW + timedelta(minutes=minutes_later),
        slots=["08:30", "21:30"],
        handled=set(),
        session_up=up,
    )
    assert decision == expected


def _entry(text: str, at: str, **extra: object) -> str:
    message = {"role": "user", "content": text}
    return json.dumps({"type": "user", "timestamp": at, "message": message, **extra})


def test_only_the_operators_messages_count_as_activity(tmp_path: Path) -> None:
    telegram = '<channel source="plugin:telegram:telegram" chat_id="1">jakie mam pozycje</channel>'
    lines = [
        _entry(telegram, "2026-11-05T06:00:00Z", isMeta=True, origin={"kind": "channel"}),
        _entry("/przeglad-rana", "2026-11-05T07:30:00Z", origin={"kind": "human"}),
        _entry("Base directory for this skill: /x", "2026-11-05T07:31:00Z", isMeta=True),
    ]
    (tmp_path / "s.jsonl").write_text("\n".join(lines))
    expected = datetime.fromisoformat("2026-11-05T06:00:00Z")
    assert checkin.last_operator_activity(tmp_path) == expected
