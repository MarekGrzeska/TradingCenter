"""Runs: queued at once, computed in the background, cancelled on request."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import runs, store
from ..contract import ProblemsOut, RunAcceptedOut, RunCancelledOut
from ..runs import RunIn
from .deps import not_found, pool, queue, refused, settings

router = APIRouter(tags=["runs"])


@router.post(
    "/runs", response_model=RunAcceptedOut, status_code=202,
    responses={404: {"description": "no such strategy or revision"}, 422: {"model": ProblemsOut}},
)
async def enqueue(body: RunIn, db=Depends(pool), run_queue=Depends(queue), config=Depends(settings)):
    """Checked against the revision's parameters and the run's ceiling, then queued — never computed in the request."""
    async with db.acquire() as conn:
        try:
            revision = await store.get_revision(conn, body.strategy_id, body.revision)
        except store.NotFound:
            raise not_found("that strategy or revision") from None
        declared = revision.document.get("params", {})
        problems = runs.check_request(body, declared, config.max_minute_bars)
        if problems:
            return refused("the run cannot be queued", problems)
        params = runs.resolved_params(body, declared)
        run_id = await runs.enqueue(conn, body, revision.n, params)
    run_queue.wake()
    return RunAcceptedOut(id=run_id, strategy_id=body.strategy_id, revision=revision.n, status="queued")


@router.post("/runs/{run_id}/cancel", response_model=RunCancelledOut, responses={404: {"description": "no such run"}})
async def cancel(run_id: int, db=Depends(pool)) -> RunCancelledOut:
    async with db.acquire() as conn:
        was = await runs.cancel(conn, run_id)
        if was is None:
            raise not_found(f"run {run_id}")
        now = await runs.status_of(conn, run_id)
    return RunCancelledOut.model_validate({"id": run_id, "status": now, "was": was})
