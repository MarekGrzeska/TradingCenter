"""A sentence becomes a proposal and never a rule. The model is a fake that returns what a model would; the point is what is
done with it — that it is checked as hard as a typed rule, that it names what is wrong rather than substituting, and
that it costs what it costs and stops at the ceiling."""

from __future__ import annotations

import json

import pytest

from alerts import drafts
from alerts import known as known_module
from alerts.drafts import Answer, Unusable
from alerts.gateway import Recipient

from .builders import FILM_SCHEMA, known, said

RECIPIENTS = [Recipient("phone", "@bot", True)]
TRACKED = ["EURUSD", "XAUUSD"]


def draft_of(answer: Answer, *, recipients=RECIPIENTS, symbols=TRACKED):
    return drafts.convert(answer, recipients=recipients, known=known(), symbols=symbols)


def fields(draft) -> set[str]:
    return {defect.field for defect in draft.defects}


def test_the_price_sentence_becomes_the_rule_it_describes() -> None:
    draft = draft_of(said())

    assert draft.defects == []
    assert draft.rule is not None
    assert (draft.rule.source.tool_name, draft.rule.source.threshold, draft.rule.cooldown_seconds) == ("get_last_price", "1.10", 3600)


def test_an_instrument_the_archive_does_not_follow_is_named_not_swapped_for_another() -> None:
    draft = draft_of(said(arguments_json=json.dumps({"symbol": "BTCUSD"})))

    assert "source.arguments.symbol" in fields(draft)
    assert draft.rule is not None and draft.rule.source.arguments == {"symbol": "BTCUSD"}


def test_a_sentence_that_names_nobody_gets_the_only_recipient_who_receives_and_says_so() -> None:
    draft = draft_of(said(destination=None))

    assert draft.rule is not None and draft.rule.destination == "phone"
    assert draft.defects == [] and "only one that receives" in draft.notes[0]


def test_with_several_recipients_and_none_named_the_field_is_left_empty_and_called_out() -> None:
    draft = draft_of(said(destination=None), recipients=[*RECIPIENTS, Recipient("tablet", "@bot", True)])

    assert "destination" in fields(draft)
    assert draft.rule is not None and draft.rule.destination == ""


def test_a_draft_is_held_to_the_same_refusals_as_a_typed_rule() -> None:
    draft = draft_of(said(field_path="symbol", poll_interval_seconds=5, template="{nonsense}"))

    assert {"source.field_path", "source.poll_interval_seconds", "template"} <= fields(draft)


def test_what_the_model_could_not_map_comes_back_as_the_sentences_own_problems() -> None:
    draft = draft_of(said(problems=["„Ethereum” nie jest śledzone"], kind="none"))

    assert draft.rule is None
    assert [defect.field for defect in draft.defects] == ["sentence"]


def test_an_event_sentence_becomes_an_event_rule_with_a_filter() -> None:
    answer = said(
        kind="event",
        tool_name=None,
        arguments_json=None,
        field_path=None,
        comparison=None,
        threshold=None,
        poll_interval_seconds=None,
        event_type="youtube.film.read",
        filter=[{"attribute": "impact_score", "op": "gte", "value_json": "8"}],
        cooldown_seconds=None,
    )

    draft = draft_of(answer)

    assert draft.defects == []
    assert draft.rule is not None and draft.rule.source.filter[0].value == 8  # pyright: ignore[reportAttributeAccessIssue]
    assert set(FILM_SCHEMA["properties"]) >= {"impact_score"}


@pytest.mark.parametrize("payload", ["not json", "[]", '{"no": "kind"}'])
def test_an_answer_that_is_not_a_draft_is_unusable(payload) -> None:
    with pytest.raises(Unusable):
        draft_of(Answer(payload, "m", 1, 1))


def test_an_answer_with_arguments_that_are_not_json_is_a_problem_of_the_draft_not_a_crash() -> None:
    draft = draft_of(said(arguments_json="{symbol: EURUSD"))

    assert draft.rule is None and fields(draft) == {"sentence"}


def test_the_prompt_offers_what_exists_and_only_that() -> None:
    from .builders import tool

    prompt = drafts.system_prompt(known(), [tool(), tool("add_channel", read_only=False)], RECIPIENTS, TRACKED)

    assert "get_last_price" in prompt and "add_channel" not in prompt
    assert "youtube.film.read" in prompt and "EURUSD" in prompt and "phone" in prompt


def test_the_tracked_symbols_are_read_out_of_the_tools_answer_however_it_is_wrapped() -> None:
    assert known_module.symbols_from('{"result": [{"symbol": "A", "collection": "x"}, {"symbol": "B"}]}') == ["A", "B"]
    assert known_module.symbols_from('[{"symbol": "A"}]') == ["A"]
    assert known_module.symbols_from("nonsense") == []


@pytest.mark.db
class TestTheRoute:
    async def test_a_sentence_returns_a_draft_stores_nothing_and_counts_its_tokens(self, api, drafter, db) -> None:
        drafter.answers = [said()]

        got = await api.post("/drafts", json={"sentence": "daj znać, gdy EURUSD przebije 1,10 w górę"})

        assert got.status_code == 200
        assert got.json()["rule"]["source"]["threshold"] == "1.10"
        assert await db.fetchval("SELECT count(*) FROM rules") == 0
        assert await db.fetchval("SELECT sum(input_tokens + output_tokens) FROM draft_usage") == 1500
        assert "daj znać" in drafter.asked[0][1] and "get_last_price" in drafter.asked[0][0]

    async def test_without_a_key_it_says_which_setting_and_the_rest_of_the_package_works(self, api, app) -> None:
        app.state.drafter = None

        refused = await api.post("/drafts", json={"sentence": "cokolwiek"})

        assert refused.status_code == 501 and "ALERTS_OPENAI_API_KEY" in refused.json()["detail"]["detail"]
        assert (await api.get("/catalog")).json()["drafting"] is False

    async def test_at_the_daily_ceiling_it_refuses_and_names_it(self, api, drafter, db, app) -> None:
        app.state.settings = app.state.settings.model_copy(update={"draft_daily_token_limit": 1000})
        drafter.answers = [said(), said()]

        first = await api.post("/drafts", json={"sentence": "pierwsze zdanie"})
        second = await api.post("/drafts", json={"sentence": "drugie zdanie"})

        assert first.status_code == 200
        assert second.status_code == 429 and "ALERTS_DRAFT_DAILY_TOKEN_LIMIT" in second.json()["detail"]["detail"]
        assert len(drafter.asked) == 1

    async def test_a_model_that_fails_or_answers_nonsense_is_a_bad_gateway_not_a_crash(self, api, drafter, db) -> None:
        drafter.answers = [RuntimeError("timeout"), Answer("nonsense", "m", 10, 10)]

        down = await api.post("/drafts", json={"sentence": "pierwsze zdanie"})
        nonsense = await api.post("/drafts", json={"sentence": "drugie zdanie"})

        assert (down.status_code, nonsense.status_code) == (502, 502)
        # The second was paid for, the first was not.
        assert await db.fetchval("SELECT count(*) FROM draft_usage") == 1
