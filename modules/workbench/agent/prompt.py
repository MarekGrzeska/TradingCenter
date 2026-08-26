"""Which of a `PromptRevision`'s two texts a turn runs. The prompt itself is no longer a constant here —
it moved to the `prompt_revisions` table, so an operator can rewrite it without a deploy.

Two texts, one version: which one a turn runs is a fact about the turn — with tools, or without them
because the tool server is unreachable — not a change to the prompt."""

from __future__ import annotations

from .models import PromptRevision


def prompt_text(revision: PromptRevision, *, has_tools: bool) -> str:
    return revision.with_tools_body if has_tools else revision.without_tools_body
