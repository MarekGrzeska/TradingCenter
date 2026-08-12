"""The transcript on the wire is the same shape it was before tools existed.

This is the assertion the whole tool-call/message split was made to be able to write.
`modules/terminal/src/agent/agentApi.ts` holds hand-written DTOs against this contract —
there is no generator to fail here — so a field appearing on `MessageOut` would reach
the terminal as an unannounced change and be caught by nothing.

When the change that shows tool calls in the panel lands, this test is the one to edit,
deliberately, in the same commit as the terminal's own DTOs.
"""

from __future__ import annotations

from agent.contract import MessageOut

TRANSCRIPT_FIELDS = {
    "id",
    "role",
    "content",
    "model_id",
    "prompt_version",
    "incomplete",
    "created_at",
}


def test_a_message_on_the_wire_carries_exactly_these_fields() -> None:
    assert set(MessageOut.model_fields) == TRANSCRIPT_FIELDS


def test_nothing_about_tools_reaches_the_transcript() -> None:
    published = " ".join(MessageOut.model_fields)
    assert "tool" not in published
