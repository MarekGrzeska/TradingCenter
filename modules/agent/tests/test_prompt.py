from __future__ import annotations

from datetime import UTC, datetime

from agent.models import PromptRevision
from agent.prompt import prompt_text

_REVISION = PromptRevision(
    version="v9",
    with_tools_body="with-tools text",
    without_tools_body="without-tools text",
    created_at=datetime.now(UTC),
)


def test_with_tools_picks_the_with_tools_body() -> None:
    assert prompt_text(_REVISION, has_tools=True) == "with-tools text"


def test_without_tools_picks_the_without_tools_body() -> None:
    assert prompt_text(_REVISION, has_tools=False) == "without-tools text"
