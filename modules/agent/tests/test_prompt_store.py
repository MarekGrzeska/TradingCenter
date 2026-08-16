"""`prompt_revisions`: the migration's seed row, and what `store.create_prompt_revision`
does to the version and the history when an operator edits it
(specs/agent-prompt-management)."""

from __future__ import annotations

import pytest

from agent import store

pytestmark = pytest.mark.db


async def test_migration_seeds_the_current_text(db) -> None:
    revision = await store.latest_prompt_revision(db)
    # `v7` names the drawing tools; `v6` is still in the table below it, which is what a
    # transcript stamped `"v6"` reads back against.
    assert revision.version == "v7"
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


async def test_with_tools_says_the_tools_change_nothing(db) -> None:
    revision = await store.latest_prompt_revision(db)
    lowered = revision.with_tools_body.lower()
    assert "read-only" in lowered
    assert "place an order" in lowered


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
    assert updated.version == "v8"
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
    assert second.version == "v9"


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
