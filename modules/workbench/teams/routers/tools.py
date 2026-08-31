"""`GET /tools` — what every configured tool server announces, so the picker is built from it and nothing else. Three
answers, because an empty list is a working configuration here while a 503 means a server could not be asked."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..contract import ToolOut
from ..tools import ToolServerUnavailable, announced_tools_by_server

router = APIRouter()


@router.get("/tools")
async def list_tools(request: Request) -> list[ToolOut]:
    settings = request.app.state.teams.settings
    try:
        announced = await announced_tools_by_server(settings)
    except ToolServerUnavailable as err:
        raise HTTPException(503, detail=str(err)) from err
    return [
        ToolOut(name=tool.name, description=tool.description, read_only=tool.read_only)
        for tool in announced
    ]
