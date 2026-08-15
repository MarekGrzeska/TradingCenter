"""HTTP-level wiring for the session routes and their SSE stream.

The provider is swapped for a scripted fake after the app's own lifespan has already
built a real pool against the throwaway database — nothing here calls OpenAI.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from agent.app import app
from agent.provider import TextDelta, ToolCallRequest, UsageReport
from agent.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind

pytestmark = pytest.mark.db

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
    "DEFAULT_MODEL_ID": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, db, monkeypatch: pytest.MonkeyPatch) -> None:
    # `db` requested for its TRUNCATE side effect — see test_usage_router.py's twin.
    del db
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


class _FakeProvider:
    def __init__(self, chunks: list) -> None:
        self._chunks = chunks
        self.prompts: list[str] = []

    async def stream(
        self, *, model: str, system_prompt: str, history: list, tools=(), rounds=()
    ):
        self.prompts.append(system_prompt)
        for chunk in self._chunks:
            yield chunk


def _sse_events(text: str) -> list[tuple[str, str]]:
    events = []
    for block in text.strip("\n").split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        lines = block.splitlines()
        event = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((event, data))
    return events


def test_create_session_defaults_to_the_configured_default_model() -> None:
    with TestClient(app) as client:
        response = client.post("/sessions", json={})
    assert response.status_code == 201
    assert response.json()["current_model_id"] == "gpt-5.6-luna"


def test_creating_a_session_with_an_unknown_model_is_refused() -> None:
    # specs/agent-models, "Model spoza katalogu jest odmową, nie podmianą"
    with TestClient(app) as client:
        response = client.post("/sessions", json={"model_id": "not-a-real-model"})
    assert response.status_code == 422
    assert "not-a-real-model" in response.json()["detail"]


def test_a_session_with_no_messages_is_not_listed() -> None:
    with TestClient(app) as client:
        created = client.post("/sessions", json={}).json()
        listed = client.get("/sessions").json()
    assert created["id"] not in [s["id"] for s in listed]


def test_a_foreign_or_missing_session_reads_the_same_404() -> None:
    # specs/agent-browser-access, "Odmowa dostępu do cudzej sesji MUST być
    # nieodróżnialna od odpowiedzi o sesji nieistniejącej" — this suite only has one
    # principal, so a session id that was never created stands in for "someone else's".
    with TestClient(app) as client:
        response = client.get("/sessions/999999")
    assert response.status_code == 404


def test_send_message_streams_fragments_then_completes() -> None:
    with TestClient(app) as client:
        app.state.provider = _FakeProvider(
            [TextDelta("hi "), TextDelta("there"), UsageReport(10, 5, None, None)]
        )
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
        events = _sse_events(response.text)

        messages = client.get(f"/sessions/{session_id}/messages").json()

    assert [kind for kind, _ in events] == ["fragment", "fragment", "complete"]
    assert [m["role"] for m in messages] == ["operator", "agent"]
    assert messages[0]["content"] == "hello"
    assert messages[1]["content"] == "hi there"
    assert messages[1]["incomplete"] is False


def test_first_message_titles_the_session() -> None:
    # specs/agent-chat, "Tytuł powstaje z pierwszego pytania"
    with TestClient(app) as client:
        app.state.provider = _FakeProvider([TextDelta("hi"), UsageReport(1, 1, None, None)])
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/messages", json={"content": "hello there"})
        listed = client.get("/sessions").json()

    assert any(s["id"] == session_id and s["title"] == "hello there" for s in listed)


def test_changing_the_model_is_reflected_on_the_session() -> None:
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.patch(f"/sessions/{session_id}", json={"model_id": "gpt-5.6-luna"})
    assert response.status_code == 200
    assert response.json()["current_model_id"] == "gpt-5.6-luna"


def test_changing_to_an_unknown_model_is_refused() -> None:
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.patch(f"/sessions/{session_id}", json={"model_id": "not-a-real-model"})
    assert response.status_code == 422


# --- renaming ---


def test_renaming_a_session_replaces_the_derived_title() -> None:
    with TestClient(app) as client:
        app.state.provider = _FakeProvider([TextDelta("hi"), UsageReport(1, 1, None, None)])
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/messages", json={"content": "hello there"})
        response = client.patch(f"/sessions/{session_id}", json={"title": "  EURUSD  plan  "})
        listed = client.get("/sessions").json()

    assert response.status_code == 200
    # Collapsed, not stored as typed — a name padded with spaces reads as a different
    # name in a list that trims nothing.
    assert response.json()["title"] == "EURUSD plan"
    assert any(s["id"] == session_id and s["title"] == "EURUSD plan" for s in listed)


def test_a_later_turn_does_not_overwrite_the_operators_name() -> None:
    with TestClient(app) as client:
        app.state.provider = _FakeProvider([TextDelta("hi"), UsageReport(1, 1, None, None)])
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/messages", json={"content": "hello there"})
        client.patch(f"/sessions/{session_id}", json={"title": "EURUSD plan"})
        app.state.provider = _FakeProvider([TextDelta("hi"), UsageReport(1, 1, None, None)])
        client.post(f"/sessions/{session_id}/messages", json={"content": "and another"})
        session = client.get(f"/sessions/{session_id}").json()

    assert session["title"] == "EURUSD plan"


@pytest.mark.parametrize("title", ["", "   ", "x" * 121])
def test_a_blank_or_overlong_title_is_refused(title: str) -> None:
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.patch(f"/sessions/{session_id}", json={"title": title})
    assert response.status_code == 422


def test_a_patch_that_asks_for_nothing_is_refused() -> None:
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.patch(f"/sessions/{session_id}", json={})
    assert response.status_code == 422


def test_model_and_title_can_change_in_one_request() -> None:
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.patch(
            f"/sessions/{session_id}", json={"model_id": "gpt-5.6-luna", "title": "both"}
        )
    assert response.status_code == 200
    assert response.json()["current_model_id"] == "gpt-5.6-luna"
    assert response.json()["title"] == "both"


# --- deleting ---


def test_a_deleted_session_leaves_the_list_and_reads_as_missing() -> None:
    with TestClient(app) as client:
        app.state.provider = _FakeProvider([TextDelta("hi"), UsageReport(1, 1, None, None)])
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/messages", json={"content": "hello there"})

        deleted = client.delete(f"/sessions/{session_id}")
        listed = client.get("/sessions").json()
        read = client.get(f"/sessions/{session_id}")
        transcript = client.get(f"/sessions/{session_id}/messages")
        renamed = client.patch(f"/sessions/{session_id}", json={"title": "too late"})
        continued = client.post(f"/sessions/{session_id}/messages", json={"content": "hello?"})

    assert deleted.status_code == 204
    assert all(s["id"] != session_id for s in listed)
    # Indistinguishable from a session that never existed, exactly like a foreign one
    # (specs/agent-browser-access) — and nothing can be done to it afterwards.
    assert read.status_code == 404
    assert transcript.status_code == 404
    assert renamed.status_code == 404
    assert continued.status_code == 404


def test_deleting_twice_is_a_404_not_a_second_success() -> None:
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        assert client.delete(f"/sessions/{session_id}").status_code == 204
        assert client.delete(f"/sessions/{session_id}").status_code == 404


def test_deleting_a_session_does_not_reduce_the_bill() -> None:
    """specs/agent-usage, "Skasowanie rozmowy nie zmniejsza rachunku" — the money was
    spent whether or not the rozmowa it paid for is still on the list."""
    with TestClient(app) as client:
        app.state.provider = _FakeProvider([TextDelta("hi"), UsageReport(1000, 500, None, None)])
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/messages", json={"content": "hello there"})
        before = client.get("/usage").json()["total_cost"]

        client.delete(f"/sessions/{session_id}")
        after = client.get("/usage").json()["total_cost"]

    assert Decimal(after) == Decimal(before)
    assert Decimal(after) > 0


def test_required_authentication_refuses_before_touching_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # specs/agent-browser-access, "Moduł nie bierze na wiarę warstwy przed sobą" — the
    # refusal must land before the model is ever called, not merely before the reply
    # finishes.
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["id"]

    class _ProviderThatMustNotBeCalled:
        async def stream(
            self, *, model: str, system_prompt: str, history: list, tools=(), rounds=()
        ):
            raise AssertionError("the model must never be called")
            yield  # pragma: no cover - makes this an async generator

    monkeypatch.setenv("REQUIRE_AUTHENTICATED_PRINCIPAL", "true")
    with TestClient(app) as client:
        app.state.provider = _ProviderThatMustNotBeCalled()
        response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
    assert response.status_code == 401


class _ScriptedProvider:
    """One entry per model call, unlike `_FakeProvider`'s single reusable script — a turn
    that asks for a tool calls the model more than once, and a script that repeated itself
    would ask for the same tool forever."""

    def __init__(self, script: list[list]) -> None:
        self._script = script
        self.calls = 0

    async def stream(self, *, model: str, system_prompt: str, history: list, tools=(), rounds=()):
        chunks = self._script[self.calls]
        self.calls += 1
        for chunk in chunks:
            yield chunk


class _FakeToolServer:
    def __init__(self, outcomes: dict[str, ToolOutcome] | None = None) -> None:
        self._outcomes = outcomes or {}

    async def list_tools(self):
        return [
            ToolDescriptor(
                name="get_last_price",
                description="Last price for a symbol.",
                input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
            )
        ]

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        return self._outcomes.get(name, ToolOutcome(ToolOutcomeKind.OK, f"{name} says 29698.2", 63))


def test_a_turn_streams_its_tool_calls_before_it_completes() -> None:
    # specs/agent-chat, "Wywołanie narzędzia dociera w trakcie tury"
    with TestClient(app) as client:
        app.state.provider = _ScriptedProvider(
            [
                [
                    ToolCallRequest("c1", "get_last_price", {"symbol": "US100"}),
                    ToolCallRequest("c2", "get_last_price", {"symbol": "SILVER"}),
                    UsageReport(1, 1, None, None),
                ],
                [TextDelta("both are up"), UsageReport(1, 1, None, None)],
            ]
        )
        app.state.tool_server = _FakeToolServer()
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.post(f"/sessions/{session_id}/messages", json={"content": "how are they"})
        events = _sse_events(response.text)

    kinds = [kind for kind, _ in events]
    assert kinds == ["tool_call", "tool_call", "fragment", "complete"]
    first = json.loads(events[0][1])
    assert first["tool_name"] == "get_last_price"
    assert first["arguments"] == {"symbol": "US100"}
    assert first["outcome"] == "ok"
    assert first["result_text"] == "get_last_price says 29698.2"
    assert first["duration_ms"] == 63
    assert (first["round_index"], first["position"]) == (0, 0)
    assert json.loads(events[1][1])["position"] == 1


def test_a_refused_tool_call_streams_as_a_call_not_as_an_error() -> None:
    # specs/agent-tools, "Odmowa narzędzia jest wynikiem, nie awarią tury"
    with TestClient(app) as client:
        app.state.provider = _ScriptedProvider(
            [
                [ToolCallRequest("c1", "get_last_price", {"symbol": "NOPE"}), UsageReport(1, 1, None, None)],
                [TextDelta("that pair is not tracked"), UsageReport(1, 1, None, None)],
            ]
        )
        app.state.tool_server = _FakeToolServer(
            {"get_last_price": ToolOutcome(ToolOutcomeKind.REFUSED, "no such pair: NOPE", 8)}
        )
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.post(f"/sessions/{session_id}/messages", json={"content": "and NOPE?"})
        events = _sse_events(response.text)
        messages = client.get(f"/sessions/{session_id}/messages").json()

    assert [kind for kind, _ in events] == ["tool_call", "fragment", "complete"]
    assert json.loads(events[0][1])["outcome"] == "refused"
    assert messages[-1]["incomplete"] is False


def test_the_transcript_hands_back_what_the_stream_sent() -> None:
    """specs/agent-tools, "Transkrypt niesie wywołania" — and it is the same shape, so a
    panel that kept the stream's events and one that reloaded cannot disagree."""
    with TestClient(app) as client:
        app.state.provider = _ScriptedProvider(
            [
                [ToolCallRequest("c1", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
                [ToolCallRequest("c2", "get_last_price", {"symbol": "SILVER"}), UsageReport(1, 1, None, None)],
                [TextDelta("both are up"), UsageReport(1, 1, None, None)],
            ]
        )
        app.state.tool_server = _FakeToolServer()
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.post(f"/sessions/{session_id}/messages", json={"content": "how are they"})
        streamed = [json.loads(data) for kind, data in _sse_events(response.text) if kind == "tool_call"]
        messages = client.get(f"/sessions/{session_id}/messages").json()

    assert messages[-1]["tool_calls"] == streamed
    # Two rounds of one call each, which is what the model asked for.
    assert [(c["round_index"], c["position"]) for c in messages[-1]["tool_calls"]] == [(0, 0), (1, 0)]
    # specs/agent-tools, "Wypowiedź bez narzędzi" — the operator's own message says so
    # with an empty list, not by omitting the field.
    assert messages[0]["tool_calls"] == []


def test_a_turn_without_tools_leaves_the_list_empty() -> None:
    with TestClient(app) as client:
        app.state.provider = _FakeProvider([TextDelta("no need to look"), UsageReport(1, 1, None, None)])
        app.state.tool_server = _FakeToolServer()
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
        messages = client.get(f"/sessions/{session_id}/messages").json()

    assert [kind for kind, _ in _sse_events(response.text)] == ["fragment", "complete"]
    assert all(m["tool_calls"] == [] for m in messages)


def test_a_broken_stream_reports_error_and_saves_the_partial_reply() -> None:
    class _BreakingProvider:
        async def stream(
            self, *, model: str, system_prompt: str, history: list, tools=(), rounds=()
        ):
            yield TextDelta("cut ")
            yield TextDelta("off")
            raise RuntimeError("provider broke")

    with TestClient(app) as client:
        app.state.provider = _BreakingProvider()
        session_id = client.post("/sessions", json={}).json()["id"]
        response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
        events = _sse_events(response.text)
        messages = client.get(f"/sessions/{session_id}/messages").json()

    assert [kind for kind, _ in events] == ["fragment", "fragment", "error"]
    assert messages[-1]["content"] == "cut off"
    assert messages[-1]["incomplete"] is True


# --- what the terminal is drawing as it asks -----------------------------------------


def test_a_turn_carrying_a_chart_snapshot_hands_it_to_the_model() -> None:
    # specs/agent-chat, "Tura wie, co terminal właśnie rysuje"
    provider = _FakeProvider([TextDelta("looking"), UsageReport(1, 1, None, None)])
    with TestClient(app) as client:
        app.state.provider = provider
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(
            f"/sessions/{session_id}/messages",
            json={
                "content": "what do you see?",
                "chart": {
                    "symbol": "US100",
                    "resolution": "HOUR",
                    "indicators": [{"id": "ema", "params": {"period": 200}}],
                },
            },
        )
        messages = client.get(f"/sessions/{session_id}/messages").json()

    assert "US100" in provider.prompts[0]
    assert "ema(period=200)" in provider.prompts[0]
    # The transcript is the conversation; what was on screen is not part of it.
    assert [m["content"] for m in messages] == ["what do you see?", "looking"]


def test_a_turn_without_a_snapshot_runs_the_prompt_untouched() -> None:
    provider = _FakeProvider([TextDelta("fine"), UsageReport(1, 1, None, None)])
    with TestClient(app) as client:
        app.state.provider = provider
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
        prompt = client.get("/prompt").json()

    assert provider.prompts[0] in (prompt["with_tools"], prompt["without_tools"])
    assert "currently shows" not in provider.prompts[0]
