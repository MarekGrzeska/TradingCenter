"""Asking the model for a proposal — a new rule or the change of one — and paying for it. One place for what the route and
the conversation's tool both do, so the ceiling and the checks cannot differ between them."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from . import drafts, known, rules, store
from .contract import DraftOut
from .gateway import GatewayUnreachable
from .routers import deps

log = logging.getLogger(__name__)


class Refused(Exception):
    """The proposal could not be made, with the HTTP code a route answers it with and words the operator can act on."""

    def __init__(self, code: int, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


async def propose(state, sentence: str, rule_id: int | None = None) -> DraftOut:
    if state.drafter is None:
        raise Refused(
            501, "drafting rules from a sentence is not set up: ALERTS_OPENAI_API_KEY is not set. Rules can still be written in the form."
        )

    now = datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with deps.connection(state.pool) as conn:
        spent = await store.draft_tokens_since(conn, day)
        if spent >= state.settings.draft_daily_token_limit:
            raise Refused(
                429,
                f"today's drafts have used {spent} tokens of the {state.settings.draft_daily_token_limit} ALERTS_DRAFT_DAILY_TOKEN_LIMIT "
                "allows; the form still works",
            )
        current = None
        if rule_id is not None:
            row = await store.get_rule(conn, rule_id)
            if row is None:
                raise Refused(404, f"there is no rule {rule_id}")
            current = rules.as_input(row)
        try:
            everything = await known.known(state, conn)
            recipients = await known.recipients_of(state.gateway) or []
        except GatewayUnreachable as err:
            raise Refused(503, str(err)) from err

    tools = await known.tools_of(state.tools)
    symbols = await known.symbols(state)
    prompt = drafts.system_prompt(everything, tools, recipients, symbols, current)
    try:
        answer = await state.drafter.draft(prompt, sentence)
    except Exception as err:
        log.warning("the model could not draft a rule: %s", err)
        raise Refused(502, f"the model could not be asked: {err}") from err

    # Counted before the answer is read: the tokens were spent whether or not it makes a rule.
    async with deps.connection(state.pool) as conn:
        await store.record_draft_usage(
            conn, model=answer.model, input_tokens=answer.input_tokens, output_tokens=answer.output_tokens, now=now
        )
    try:
        return drafts.convert(answer, recipients=recipients, known=everything, symbols=symbols, current=current)
    except drafts.Unusable as err:
        raise Refused(502, str(err)) from err
