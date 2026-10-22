"""The rules and what became of them. Both tools read; neither takes a rule's id as a way to change it."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import known, rules, store
from ..contract import ConditionSource
from ..template import CONDITION_DEFAULT, EVENT_DEFAULT
from ._shared import READ_ONLY, ToolContext

MAX_FIRES = 30
TEXT_CHARS = 280


class RuleOut(BaseModel):
    id: int
    name: str
    kind: Literal["condition", "event"]
    watches: str = Field(description="the rule in one line: what it looks at and when it goes off")
    destination: str
    bot: str | None = Field(default=None, description="the bot the message goes through; null is the recipient's only bot")
    message_template: str = Field(
        description="the message as the rule is set to send it now, with {slots} — an event rule's default {text} is the ready "
        "message the announcing part wrote, so what the operator reads is that text, not this template"
    )
    uses_default_message: bool = Field(description="true when the rule sets no template of its own")
    cooldown_seconds: int
    mode: str = Field(description="repeat, or once (it tells a single time and then stops)")
    max_per_hour: int | None = None
    enabled: bool
    disabled_reason: str | None = None
    problems: list[str] = Field(default_factory=list, description="what is wrong with the rule now, if anything")
    last_checked_at: datetime | None = Field(default=None, description="a value rule's last look; null for an event rule")
    last_fired_at: datetime | None = None


class RulesOut(BaseModel):
    rules: list[RuleOut]


class FireOut(BaseModel):
    at: datetime
    state: str = Field(description="pending, delivered, refused, abandoned, throttled or undeliverable")
    reason: str | None = None
    text: str


class CheckOut(BaseModel):
    at: datetime
    what: str = Field(description="unavailable (the tool could not be read), refused (the tool said no) or cooldown")
    reason: str


class FiresOut(BaseModel):
    rule_id: int
    fires: list[FireOut]
    checks: list[CheckOut] = Field(description="the times the rule could not look, or crossed inside its cool-down")


def describe(row) -> str:
    source = rules.source_of(row)
    if isinstance(source, ConditionSource):
        arguments = ", ".join(f"{name}={value}" for name, value in source.arguments.items())
        return f"{source.tool_name}({arguments}).{source.field_path} {source.comparison} {source.threshold}, looked at every {source.poll_interval_seconds} s"
    terms = " and ".join(f"{term.attribute} {term.op} {term.value}" for term in source.filter)
    return f"every {source.event_type}" + (f" where {terms}" if terms else "")


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def alert_rules() -> RulesOut:
        """Every notification rule the operator has set, with what it watches, who it tells and whether it is working.

        `message_template` is what the rule sends *now*, read from the rule as it stands; `alert_fires` shows what was sent
        in the past, which may predate a change. For what a message looked like, use the template; for what arrived, the history.

        `problems` is what is wrong with a rule now — its recipient is gone, or an event type no longer carries what it
        filters on. A rule with problems is quiet for a reason that is not the market's.
        """
        recipients = await known.recipients_if_possible(ctx._state)  # pyright: ignore[reportPrivateUsage]
        async with ctx.pool.acquire() as conn:
            found = await store.list_rules(conn)
        out = []
        for row in found:
            shown = rules.out(row, recipients=recipients)
            out.append(
                RuleOut(
                    id=row["id"],
                    name=row["name"],
                    kind=row["kind"],
                    watches=describe(row),
                    destination=row["destination"],
                    bot=row["bot"],
                    message_template=row["template"],
                    uses_default_message=row["template"] == (CONDITION_DEFAULT if row["kind"] == "condition" else EVENT_DEFAULT),
                    cooldown_seconds=row["cooldown_seconds"],
                    mode=row["mode"],
                    max_per_hour=row["max_per_hour"],
                    enabled=row["enabled"],
                    disabled_reason=row["disabled_reason"],
                    problems=[defect.message for defect in shown.defects],
                    last_checked_at=row["last_checked_at"],
                    last_fired_at=row["last_fired_at"],
                )
            )
        return RulesOut(rules=out)

    @mcp.tool(annotations=READ_ONLY)
    async def alert_fires(rule_id: int, limit: int = 10) -> FiresOut:
        """What became of a rule lately: every time it went off and whether the message arrived, and every time it could not
        look at its value or crossed its level inside the cool-down. The place to look when an alert did not come.

        Newest first, at most 30 of each. The text is the message as it was sent, cut to a line.
        """
        wanted = max(1, min(limit, MAX_FIRES))
        async with ctx.pool.acquire() as conn:
            fired = await store.recent_fires(conn, rule_id, wanted)
            looked = await store.recent_checks(conn, rule_id, wanted)
        return FiresOut(
            rule_id=rule_id,
            fires=[
                FireOut(at=row["created_at"], state=row["state"], reason=row["reason"], text=" ".join(row["text"].split())[:TEXT_CHARS])
                for row in fired
            ],
            checks=[CheckOut(at=row["checked_at"], what=row["outcome"], reason=row["reason"]) for row in looked],
        )
