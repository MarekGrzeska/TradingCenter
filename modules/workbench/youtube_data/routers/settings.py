"""What the loop and a new topic run by. The operator reads and changes it; the agent's tools do not reach it, for the reason
they do not reach the prompts: how much the archive spends is the operator's to say."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from .. import loop_settings, store
from ..contract import Problem, SettingsOut, SettingsPatch
from .deps import connection

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
async def read_settings(request: Request) -> SettingsOut:
    async with connection(request.app.state.pool) as conn:
        saved = await store.get_loop_settings(conn)
        standing = saved or loop_settings.from_process(request.app.state.settings)
    return SettingsOut.of(standing, saved=saved is not None)


@router.patch("/settings", response_model=SettingsOut, responses={422: {"model": Problem}})
async def patch_settings(request: Request, body: SettingsPatch) -> SettingsOut:
    state = request.app.state
    try:
        changed = await loop_settings.update(
            state.pool,
            state.settings,
            poll_interval_minutes=body.poll_interval_minutes,
            topic_interval_minutes=body.topic_interval_minutes,
            topic_max_videos=body.topic_max_videos,
        )
    except loop_settings.SettingsRefused as err:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=Problem(detail=str(err), cause="request").model_dump(),
        ) from err
    state.ingest.interval_changed()
    return SettingsOut.of(changed, saved=True)
