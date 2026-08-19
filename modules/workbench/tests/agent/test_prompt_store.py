"""`prompt_revisions`: the migration's seed row, and what `store.create_prompt_revision`
does to the version and the history when an operator edits it
(specs/agent-prompt-management)."""

from __future__ import annotations

import pytest

from agent import store

pytestmark = pytest.mark.db


async def test_migration_seeds_the_current_text(db) -> None:
    revision = await store.latest_prompt_revision(db)
    # `v11` names the trading tools; every revision under it is still in the table, which
    # is what a transcript stamped `"v7"` or `"v8"` reads back against.
    assert revision.version == "v11"
    assert revision.with_tools_body != revision.without_tools_body


async def test_with_tools_does_not_claim_to_have_none(db) -> None:
    revision = await store.latest_prompt_revision(db)
    lowered = revision.with_tools_body.lower()
    assert "no tools" not in lowered
    assert "read-only tools" in lowered


async def test_with_tools_names_the_easy_over_readings(db) -> None:
    revision = await store.latest_prompt_revision(db)
    lowered = revision.with_tools_body.lower()
    # The archive collects chosen pairs, an empty window is not silence, a price is only
    # as current as its candle, and volume is not reliable enough to reason from — each
    # one a conclusion market-mcp's own answers are shaped to prevent, and each one a
    # model would otherwise reach.
    assert "not the whole market" in lowered
    assert "does not mean the market was quiet" in lowered
    assert "as current as the candle" in lowered
    assert "volume" in lowered
    assert "not reliable" in lowered


async def test_with_tools_says_the_archive_tools_change_nothing(db) -> None:
    revision = await store.latest_prompt_revision(db)
    lowered = revision.with_tools_body.lower()
    assert "read-only" in lowered
    assert "cannot start collecting a pair" in lowered


async def test_no_seeded_text_still_claims_the_agent_cannot_place_an_order(db) -> None:
    """Every prompt from `v4` to `v10` said the model could not place an order. It can now,
    and a prompt asserting otherwise makes it refuse a request it has the tool for."""
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        lowered = body.lower()
        assert "or place an order" not in lowered
        assert "you cannot start collecting a pair, delete data, or place an order" not in lowered


async def test_without_tools_says_the_archive_is_out_of_reach(db) -> None:
    revision = await store.latest_prompt_revision(db)
    lowered = revision.without_tools_body.lower()
    # Not "you have no tools" any more: the chart tool is this module's own and is
    # offered whether or not market-mcp answers. What this variant must still say is
    # that no market data can be read.
    assert "cannot reach the archive" in lowered
    assert "cannot see candles" in lowered


async def test_both_seeded_texts_disclaim_investment_advice(db) -> None:
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "advice" in body.lower() or "recommendation" in body.lower()


async def test_both_seeded_texts_forbid_a_figure_that_was_not_given(db) -> None:
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "never state a price" in body.lower()


async def test_both_seeded_texts_rule_out_what_the_terminal_cannot_draw(db) -> None:
    """The panel renders a Markdown subset (`terminal/src/agent/MessageBody.tsx`); the
    prompt is the cheap half of keeping the model inside it."""
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        lowered = body.lower()
        assert "markdown" in lowered
        for unsupported in ("tables", "images", "html", "latex"):
            assert unsupported in lowered


async def test_the_two_seeded_texts_differ_only_where_the_world_does(db) -> None:
    # Same limits, word for word — a drift here is how one of the two quietly loses a
    # rule the other keeps. True of the seed; an operator's own edit is theirs to keep
    # this way or not — `agent-prompt-management`'s Non-Goals.
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "the decision is always theirs" in body
        assert "roughly forty characters" in body
    assert revision.with_tools_body != revision.without_tools_body


async def test_create_prompt_revision_bumps_the_version(db) -> None:
    updated = await store.create_prompt_revision(
        db, with_tools_body="new with-tools text", without_tools_body="new without-tools text"
    )
    assert updated.version == "v12"
    assert updated.with_tools_body == "new with-tools text"
    assert updated.without_tools_body == "new without-tools text"


async def test_create_prompt_revision_is_append_only(db) -> None:
    before = await store.latest_prompt_revision(db)
    await store.create_prompt_revision(db, with_tools_body="a", without_tools_body="b")

    rows = await db.fetch("SELECT version, with_tools_body FROM prompt_revisions ORDER BY id")
    versions = [row["version"] for row in rows]
    assert before.version in versions
    kept = next(row for row in rows if row["version"] == before.version)
    assert kept["with_tools_body"] == before.with_tools_body


async def test_repeated_edits_keep_incrementing(db) -> None:
    await store.create_prompt_revision(db, with_tools_body="a1", without_tools_body="b1")
    second = await store.create_prompt_revision(db, with_tools_body="a2", without_tools_body="b2")
    assert second.version == "v13"


async def test_both_seeded_texts_name_the_chart_tool(db) -> None:
    # A tool the prompt does not mention is a tool the model does not reach for — and the
    # chart tool is offered in both variants, because it does not need the archive.
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "set_chart" in body


async def test_both_seeded_texts_name_the_focus_field(db) -> None:
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        lowered = body.lower()
        assert "focus" in lowered
        assert "last_bars" in lowered


async def test_both_seeded_texts_name_the_drawing_tools(db) -> None:
    # Both variants, because `list_chart_drawings` reads this module's own table and
    # `draw_on_chart` says for itself when it cannot check a symbol — neither one goes
    # away with the archive (specs/agent-tools, "Brak serwera narzędzi").
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "draw_on_chart" in body
        assert "list_chart_drawings" in body


async def test_the_drawing_paragraph_tells_a_drawing_apart_from_a_computed_level(db) -> None:
    # The one confusion the paragraph exists to prevent: `levels_near_price` computes
    # support and resistance from the archive on every call, and a drawing is what the
    # operator asked to keep. A model that conflates them reads one when asked about the
    # other (design.md, "Prompt dostaje rewizję i jedno zdanie o rozróżnieniu").
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "levels_near_price" in body


async def test_the_drawing_paragraph_says_it_is_incremental(db) -> None:
    # The inversion of set_chart's rule, and the one a model carries over by habit if the
    # prompt does not say otherwise (specs/agent-chart-drawings, "Agent nie kasuje przez
    # pominięcie").
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        lowered = body.lower()
        assert "incremental, not declarative" in lowered
        assert "remove" in lowered


async def test_the_drawing_paragraph_no_longer_promises_the_indicator_palette(db) -> None:
    # `draw_on_chart` stopped accepting indicator tokens, so a prompt still pointing at
    # "the same palette set_chart's indicators use" sends the model to pick a colour it
    # will then be refused (specs/agent-chart-drawings, "Paleta rysunków MUST być
    # odrębna").
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "same palette set_chart" not in body
        assert "drawing palette" in body


async def test_the_drawing_paragraph_says_hiding_is_undoable_and_removing_is_not(db) -> None:
    # A model that does not know hiding exists deletes to clear the chart, which is the
    # loss this whole change exists to prevent (specs/agent-chart-drawings, "Agent gasi
    # rysunek zamiast go kasować").
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        lowered = body.lower()
        assert "`hide`" in lowered
        assert "`show`" in lowered
        assert "undoable" in lowered


async def test_both_seeded_texts_name_the_trading_tools(db) -> None:
    # A tool the prompt does not mention is a tool the model does not reach for. Both
    # variants, for the reason `0012` gives: the three tool servers fail independently, so
    # an unreachable archive says nothing about whether the account can be reached.
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        for tool in ("get_positions", "get_balance", "place_order", "close_position"):
            assert tool in body


async def test_both_seeded_texts_forbid_resending_a_call_of_unknown_outcome(db) -> None:
    # specs/agent-trading, "Agent nie potwierdza zlecenia, którego skutku nie zna" — the
    # one failure this paragraph is really written for: a retry is a second position.
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        lowered = body.lower()
        assert "outcome is unknown" in lowered
        assert "never send it again" in lowered
        assert "second position, not a retry" in lowered


async def test_both_seeded_texts_say_the_account_is_a_demo_one(db) -> None:
    revision = await store.latest_prompt_revision(db)
    for body in (revision.with_tools_body, revision.without_tools_body):
        assert "demo account" in body.lower()
