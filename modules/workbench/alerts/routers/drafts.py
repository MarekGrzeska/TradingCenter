"""A sentence in, a proposed rule out. Nothing is stored but the tokens it cost."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request, status

from .. import drafts, known, store
from ..contract import DraftIn, DraftOut, Problem
from ..gateway import GatewayUnreachable
from . import deps

log = logging.getLogger(__name__)

router = APIRouter(tags=["drafts"])

@router.post(
    "/drafts",
    response_model=DraftOut,
    responses={429: {"model": Problem}, 501: {"model": Problem}, 502: {"model": Problem}, 503: {"model": Problem}},
)
async def draft(request: Request, body: DraftIn) -> DraftOut:
    state = request.app.state
    if state.drafter is None:
        raise deps.refusal(
            status.HTTP_501_NOT_IMPLEMENTED,
            "drafting rules from a sentence is not set up: ALERTS_OPENAI_API_KEY is not set. Rules can still be written in the form.",
        )

    now = datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with deps.connection(state.pool) as conn:
        spent = await store.draft_tokens_since(conn, day)
        if spent >= state.settings.draft_daily_token_limit:
            raise deps.refusal(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"today's drafts have used {spent} tokens of the {state.settings.draft_daily_token_limit} ALERTS_DRAFT_DAILY_TOKEN_LIMIT "
                "allows; the form still works",
            )
        try:
            everything = await known.known(state, conn)
            recipients = await known.recipients_of(state.gateway) or []
        except GatewayUnreachable as err:
            raise deps.refusal(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err

    tools = await known.tools_of(state.tools)
    symbols = await known.symbols(state)
    prompt = drafts.system_prompt(everything, tools, recipients, symbols)
    try:
        answer = await state.drafter.draft(prompt, body.sentence)
    except Exception as err:
        log.warning("the model could not draft a rule: %s", err)
        raise deps.refusal(status.HTTP_502_BAD_GATEWAY, f"the model could not be asked: {err}") from err

    # Counted before the answer is read: the tokens were spent whether or not it makes a rule.
    async with deps.connection(state.pool) as conn:
        await store.record_draft_usage(
            conn, model=answer.model, input_tokens=answer.input_tokens, output_tokens=answer.output_tokens, now=now
        )
    try:
        return drafts.convert(answer, recipients=recipients, known=everything, symbols=symbols)
    except drafts.Unusable as err:
        raise deps.refusal(status.HTTP_502_BAD_GATEWAY, str(err)) from err
