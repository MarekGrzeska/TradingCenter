"""The one tool of this package that asks a model: what a sentence would change in a rule. It saves no rule — the operator
does, on the screen — but it spends tokens, so it is not marked read-only: a read-only tool with a number in its answer
is one the catalogue offers as a value to watch."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .. import proposing
from ..contract import RuleIn
from ._shared import ToolContext

# Not read-only (it costs tokens), not destructive (it changes no rule), and not idempotent (a model answers anew).
PROPOSES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)

APPLY = (
    "The rule has NOT been changed. The operator applies it on the Alerts tab: Edytuj… on the rule, with these values, or "
    "Zmień zdaniem… with the same sentence."
)


class ProposalOut(BaseModel):
    rule_id: int
    understood: str = Field(description="how the sentence was read, in one sentence")
    rule: RuleIn | None = Field(description="the whole rule as it would stand after the change; null when the sentence made no rule")
    defects: list[str] = Field(description="everything wrong with the proposal as it stands, or that the sentence asked for and cannot be had")
    notes: list[str]
    applied: bool = False
    next_step: str = APPLY


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=PROPOSES)
    async def propose_alert_change(rule_id: int, change: str) -> ProposalOut:
        """What an existing notification rule would look like after a change the operator described in words, e.g. "raise the
        threshold to 1.12" or "no more often than every two hours". Takes the rule's id (from alert_rules) and the change.

        Changes nothing: the answer is a proposal, checked the way a saved rule is, with every reason it cannot work as it
        stands. Tell the operator what would change and that they apply it on the Alerts tab. It asks a model and counts
        against a daily token ceiling, so call it once the operator has said what they want changed, not to explore.
        """
        try:
            draft = await proposing.propose(ctx._state, change, rule_id)  # pyright: ignore[reportPrivateUsage]
        except proposing.Refused as err:
            raise ToolError(err.detail) from err
        return ProposalOut(
            rule_id=rule_id,
            understood=draft.understood,
            rule=draft.rule,
            defects=[defect.message for defect in draft.defects],
            notes=draft.notes,
        )
