from __future__ import annotations

from agent.prompt import PROMPT_VERSION, SYSTEM_PROMPT


def test_prompt_version_is_set() -> None:
    assert PROMPT_VERSION


def test_prompt_names_it_has_no_tools() -> None:
    assert "no tools" in SYSTEM_PROMPT.lower()


def test_prompt_disclaims_investment_advice() -> None:
    assert "advice" in SYSTEM_PROMPT.lower() or "recommendation" in SYSTEM_PROMPT.lower()
