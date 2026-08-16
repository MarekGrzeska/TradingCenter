"""`GET /tools` — what every configured tool server announces, so that the picker
beside an agent is built from it and from nothing else (specs/teams-tool-access, "Moduł
nie trzyma kopii tego, co ogłasza serwer narzędzi"; `terminal-teams`, "wybór narzędzi z
tego, co moduł ogłasza"). Each entry names whether it changes the account
(specs/trading-mcp-tools, "Narzędzie zapisujące jest oznaczone jako zmieniające stan").

Three answers, and the difference between the last two is the whole reason this route
does not simply hand back a list:

- **200 with tools** — every configured server was asked and this is the union of what
  they publish;
- **200 with an empty list** — no tool server is configured at all, which is a working
  configuration here (a team whose agents carry no tools runs without one) and reads to
  the operator as "this module announces nothing";
- **503** — at least one configured server could not be asked. An outage, not a partial
  catalogue: answering with only what could be confirmed would tell the operator less
  than they think they were told.

The tools already assigned in a saved revision are not affected by any of the three. They
stay in the definition, they stay visible in the panel, and it is starting a run that
refuses when a server cannot confirm them (`tools/assignment.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..contract import ToolOut
from ..tools import ToolServerUnavailable, announced_tools_by_server

router = APIRouter()


@router.get("/tools")
async def list_tools(request: Request) -> list[ToolOut]:
    settings = request.app.state.settings
    try:
        announced = await announced_tools_by_server(settings)
    except ToolServerUnavailable as err:
        raise HTTPException(503, detail=str(err)) from err
    return [
        ToolOut(name=tool.name, description=tool.description, read_only=tool.read_only)
        for tool in announced
    ]
