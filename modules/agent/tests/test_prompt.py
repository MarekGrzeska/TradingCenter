from __future__ import annotations

import pytest

from agent.prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_WITH_TOOLS,
    SYSTEM_PROMPT_WITHOUT_TOOLS,
    system_prompt,
)

BOTH = [SYSTEM_PROMPT_WITH_TOOLS, SYSTEM_PROMPT_WITHOUT_TOOLS]


def test_prompt_version_is_set() -> None:
    assert PROMPT_VERSION


def test_the_version_moved_when_the_prompt_did() -> None:
    # v2 was the prompt that said "You have no tools" as a fact about the module rather
    # than about the turn. A transcript answered under it must stay distinguishable from
    # one answered now (specs/agent-chat, "Prompt zmienia się między rozmowami").
    assert PROMPT_VERSION != "v2"


def test_with_tools_the_prompt_does_not_claim_to_have_none() -> None:
    assert "no tools" not in SYSTEM_PROMPT_WITH_TOOLS.lower()
    assert "read-only tools" in SYSTEM_PROMPT_WITH_TOOLS.lower()


def test_with_tools_the_prompt_names_the_three_easy_over_readings() -> None:
    lowered = SYSTEM_PROMPT_WITH_TOOLS.lower()
    # The archive collects chosen pairs, an empty window is not silence, and a price is
    # only as current as its candle — each one a conclusion market-mcp's own answers are
    # shaped to prevent, and each one a model would otherwise reach.
    assert "not the whole market" in lowered
    assert "does not mean the market was quiet" in lowered
    assert "as current as the candle" in lowered


def test_with_tools_the_prompt_says_the_tools_change_nothing() -> None:
    lowered = SYSTEM_PROMPT_WITH_TOOLS.lower()
    assert "read-only" in lowered
    assert "place an order" in lowered


def test_without_tools_the_prompt_says_so_plainly() -> None:
    lowered = SYSTEM_PROMPT_WITHOUT_TOOLS.lower()
    assert "no tools" in lowered
    assert "cannot reach the archive" in lowered


@pytest.mark.parametrize("prompt", BOTH)
def test_both_prompts_disclaim_investment_advice(prompt: str) -> None:
    assert "advice" in prompt.lower() or "recommendation" in prompt.lower()


@pytest.mark.parametrize("prompt", BOTH)
def test_both_prompts_forbid_a_figure_that_was_not_given(prompt: str) -> None:
    # Written before the agent had any figures to be given; the rule only became
    # checkable now that it does.
    assert "never state a price" in prompt.lower()


@pytest.mark.parametrize("prompt", BOTH)
def test_both_prompts_rule_out_what_the_terminal_cannot_draw(prompt: str) -> None:
    """The panel renders a Markdown subset (`terminal/src/agent/MessageBody.tsx`); the
    prompt is the cheap half of keeping the model inside it."""
    lowered = prompt.lower()
    assert "markdown" in lowered
    for unsupported in ("tables", "images", "html", "latex"):
        assert unsupported in lowered


def test_the_two_prompts_differ_only_where_the_world_does() -> None:
    # Same limits, word for word — a drift here is how one of the two quietly loses a
    # rule the other keeps.
    for prompt in BOTH:
        assert "the decision is always theirs" in prompt
        assert "roughly forty characters" in prompt
    assert SYSTEM_PROMPT_WITH_TOOLS != SYSTEM_PROMPT_WITHOUT_TOOLS


def test_the_selector_returns_the_matching_text() -> None:
    assert system_prompt(has_tools=True) == SYSTEM_PROMPT_WITH_TOOLS
    assert system_prompt(has_tools=False) == SYSTEM_PROMPT_WITHOUT_TOOLS
