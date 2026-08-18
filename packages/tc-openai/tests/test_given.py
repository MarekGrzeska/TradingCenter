"""The one difference between the two callers, now that it is a type.

`Conversation` and `Briefing` are not two spellings of the same thing. A team has no
transcript to replay and teams' own copy of this provider deliberately had no `history`
parameter for one to grow in; collapsing both into a single argument would have undone
that quietly. These tests are what stops the union from being flattened back later by
somebody who reads it as redundant.
"""

from __future__ import annotations

import pytest

from tc_openai import Briefing, Conversation


def test_a_briefing_has_nothing_to_append_to() -> None:
    given = Briefing(text="you are the analyst; here is what came before")

    assert not hasattr(given, "turns")
    assert not hasattr(given, "history")
    assert not hasattr(given, "append")


def test_a_conversation_carries_its_turns_in_order() -> None:
    given = Conversation(turns=[("operator", "what is US100 at?"), ("agent", "21000.5")])

    assert [role for role, _ in given.turns] == ["operator", "agent"]


def test_neither_can_be_mutated_after_it_is_built() -> None:
    """Both are frozen: the provider is handed what to send, not something to edit."""
    conversation = Conversation(turns=[("operator", "hello")])
    briefing = Briefing(text="hello")

    with pytest.raises(AttributeError):
        conversation.turns = []  # type: ignore[misc]
    with pytest.raises(AttributeError):
        briefing.text = "something else"  # type: ignore[misc]
