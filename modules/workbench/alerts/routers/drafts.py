"""A sentence in, a proposed rule out — a new one, or an existing one as the sentence would change it. Nothing is stored but
the tokens it cost."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import proposing
from ..contract import DraftIn, DraftOut, Problem
from . import deps

router = APIRouter(tags=["drafts"])


@router.post(
    "/drafts",
    response_model=DraftOut,
    responses={404: {"model": Problem}, 429: {"model": Problem}, 501: {"model": Problem}, 502: {"model": Problem}, 503: {"model": Problem}},
)
async def draft(request: Request, body: DraftIn) -> DraftOut:
    try:
        return await proposing.propose(request.app.state, body.sentence, body.rule_id)
    except proposing.Refused as err:
        raise deps.refusal(err.code, err.detail) from err
