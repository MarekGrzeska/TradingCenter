"""Which of a `PromptRevision`'s two texts a turn runs — the prompt itself moved to the table, so an operator can
rewrite it without a deploy. Two texts, one version: which one runs is a fact about the turn, not about the prompt."""

from __future__ import annotations

from .models import PromptRevision


def prompt_text(revision: PromptRevision, *, has_tools: bool) -> str:
    return revision.with_tools_body if has_tools else revision.without_tools_body
