"""Which of a `PromptRevision`'s two texts a turn runs.

The prompt itself is no longer a constant in this file — `agent-prompt-management`
moved it to the `prompt_revisions` table (`store.latest_prompt_revision`,
`store.create_prompt_revision`), so an operator can read and rewrite it from the
terminal without a deploy. What used to be the module-level `PROMPT_VERSION` is now
`PromptRevision.version`; what used to be `SYSTEM_PROMPT_WITH_TOOLS` /
`SYSTEM_PROMPT_WITHOUT_TOOLS` are `PromptRevision.with_tools_body` /
`.without_tools_body`. Migration `0003_prompt_revisions` seeds the row `"v4"` with the
exact text this file held right before that move, so a transcript already stamped
`"v4"` has something in the database to agree with.

Two texts, one version, unchanged: which one a turn runs is a fact about the turn —
with tools, or without them because the tool server is unreachable — not a change to
the prompt, and this function is the whole of that choice.
"""

from __future__ import annotations

from .models import PromptRevision


def prompt_text(revision: PromptRevision, *, has_tools: bool) -> str:
    return revision.with_tools_body if has_tools else revision.without_tools_body
