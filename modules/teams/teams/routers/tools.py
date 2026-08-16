"""`GET /tools` — what the tool server announces, so that the picker beside an agent is
built from it and from nothing else (specs/teams-tool-access, "Moduł nie trzyma kopii
tego, co ogłasza serwer narzędzi"; `terminal-teams`, "wybór narzędzi z tego, co moduł
ogłasza").

Three answers, and the difference between the last two is the whole reason this route
does not simply hand back a list:

- **200 with tools** — the server was asked and this is what it publishes;
- **200 with an empty list** — no tool server is configured at all, which is a working
  configuration here (a team whose agents carry no tools runs without one) and reads to
  the operator as "this module announces nothing";
- **503** — a server *is* configured and could not be asked. An outage, not an empty
  catalogue: answering `[]` would tell the operator the tools are gone, which is the one
  thing that has not been established.

The tools already assigned in a saved revision are not affected by any of the three. They
stay in the definition, they stay visible in the panel, and it is starting a run that
refuses when the server cannot confirm them (`tools/assignment.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..contract import ToolOut
from ..tools import ToolServerUnavailable, announced_tools

router = APIRouter()


@router.get("/tools")
async def list_tools(request: Request) -> list[ToolOut]:
    settings = request.app.state.settings
    if settings.market_mcp_url is None:
        return []
    try:
        announced = await announced_tools(settings)
    except ToolServerUnavailable as err:
        raise HTTPException(503, detail=str(err)) from err
    return [ToolOut(name=tool.name, description=tool.description) for tool in announced]
