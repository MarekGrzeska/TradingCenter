"""The rules. Written, replaced, switched and deleted by the operator alone — a rule decides who is told what, and a
route a conversation could reach would let it decide that too."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, Response, status

from .. import known, rules, store
from ..contract import CheckOut, FireOut, HistoryOut, Problem, RuleIn, RuleOut, RulePatch
from ..gateway import GatewayUnreachable
from ..reach import Reach
from ..validation import validate
from . import deps

router = APIRouter(tags=["rules"])

HISTORY_ROWS = 30

_REFUSED: dict[int | str, dict[str, Any]] = {404: {"model": Problem}, 422: {"model": Problem}, 503: {"model": Problem}}


@router.get("/rules", response_model=list[RuleOut])
async def list_rules(request: Request) -> list[RuleOut]:
    """Every rule with what is wrong with it now. The recipients are asked once for the whole list, and a door that does
    not answer leaves the list drawn and unchecked rather than empty."""
    state = request.app.state
    recipients = await known.recipients_if_possible(state)
    async with deps.connection(state.pool) as conn:
        found = await store.list_rules(conn)
    return [rules.out(row, recipients=recipients) for row in found]


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED, responses=_REFUSED)
async def create(request: Request, body: RuleIn) -> RuleOut:
    state = request.app.state
    async with deps.connection(state.pool) as conn:
        what = await _checked(state, conn, body)
        created = await store.insert_rule(conn, body, created_by="operator", now=datetime.now(UTC))
    return rules.out(created, recipients=what)


@router.put("/rules/{rule_id}", response_model=RuleOut, responses=_REFUSED)
async def replace(request: Request, rule_id: int, body: RuleIn) -> RuleOut:
    state = request.app.state
    async with deps.connection(state.pool) as conn:
        if await store.get_rule(conn, rule_id) is None:
            raise deps.not_found(f"there is no rule {rule_id}")
        what = await _checked(state, conn, body)
        replaced = await store.replace_rule(conn, rule_id, body, now=datetime.now(UTC))
    assert replaced is not None  # it was there a moment ago, and only the operator deletes
    return rules.out(replaced, recipients=what)


@router.patch("/rules/{rule_id}", response_model=RuleOut, responses={404: {"model": Problem}})
async def switch(request: Request, rule_id: int, body: RulePatch) -> RuleOut:
    state = request.app.state
    recipients = await known.recipients_if_possible(state)
    async with deps.connection(state.pool) as conn:
        switched = await store.set_enabled(conn, rule_id, body.enabled, now=datetime.now(UTC))
    if switched is None:
        raise deps.not_found(f"there is no rule {rule_id}")
    return rules.out(switched, recipients=recipients)


@router.get("/rules/{rule_id}/history", response_model=HistoryOut, responses={404: {"model": Problem}})
async def history(request: Request, rule_id: int) -> HistoryOut:
    """What became of the rule lately — the first place to look when an alert did not come."""
    async with deps.connection(request.app.state.pool) as conn:
        if await store.get_rule(conn, rule_id) is None:
            raise deps.not_found(f"there is no rule {rule_id}")
        fired = await store.recent_fires(conn, rule_id, HISTORY_ROWS)
        looked = await store.recent_checks(conn, rule_id, HISTORY_ROWS)
    return HistoryOut(
        fires=[FireOut(at=row["created_at"], state=row["state"], reason=row["reason"], text=row["text"]) for row in fired],
        checks=[CheckOut(at=row["checked_at"], outcome=row["outcome"], reason=row["reason"]) for row in looked],
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": Problem}})
async def delete(request: Request, rule_id: int) -> Response:
    async with deps.connection(request.app.state.pool) as conn:
        if not await store.delete_rule(conn, rule_id):
            raise deps.not_found(f"there is no rule {rule_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _checked(state, conn, body: RuleIn) -> Reach | None:
    """The rule against everything that exists, or the refusal naming each thing wrong with it. Returns who the door knows,
    for the answer — asked once, here."""
    try:
        everything = await known.known(state, conn)
    except GatewayUnreachable as err:
        raise deps.door_down(err) from err
    defects = validate(body, everything)
    if defects:
        raise deps.refused_rule(defects)
    return everything.destinations
