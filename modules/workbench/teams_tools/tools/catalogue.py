"""The catalogue: what teams exist, what one looks like, how to make one, how to correct one. `create_team` and
`revise_team` are one call each — rebuilding a definition to change one role is three turns in which to drop an agent."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from ..client import TeamsClient
from ..errors import ToolRefusal
from ._shared import READ_ONLY, WRITE, _call


class AgentIn(BaseModel):
    """One role. `key` is what edges point at and what the trace records, so it is a stable identifier
    rather than a label — renaming it in a revision makes a different agent, not a renamed one."""

    key: str
    role: str
    prompt: str
    guidance: str = ""
    model_id: str = Field(description="must be an id from list_models on this same server")
    tools: list[str] = Field(
        default_factory=list,
        description="tool names the team's own agents may call, from list_tools",
    )


class EdgeIn(BaseModel):
    """`to` waits for `from_` and receives its output."""

    from_: str = Field(serialization_alias="from", validation_alias="from")
    to: str

    model_config = {"populate_by_name": True}


class LimitsIn(BaseModel):
    """Strings, because `teams` compares them and never recomputes them. Omitted means no
    limit — the module imposes none of its own."""

    run_limit: str | None = None
    daily_limit: str | None = None


class TeamSummary(BaseModel):
    id: int
    name: str
    description: str
    latest_revision: int


class TeamDetail(BaseModel):
    id: int
    name: str
    description: str
    latest_revision: int
    revision_id: int = Field(description="the id to pin a schedule to, if pinning one")
    agents: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    limits: dict[str, Any]
    trading: dict[str, Any]


class SavedRevision(BaseModel):
    team_id: int
    # `None` only in the one case `create_team` documents: the team was written and the
    # read that follows it was not. Never a sign that nothing was saved.
    revision_id: int | None
    version: int
    agents: list[str] = Field(description="agent keys in the saved revision, in order")
    note: str | None = None


def _definition(
    agents: list[AgentIn], edges: list[EdgeIn], limits: LimitsIn | None
) -> dict[str, Any]:
    return {
        "agents": [agent.model_dump() for agent in agents],
        "edges": [edge.model_dump(by_alias=True) for edge in edges],
        "limits": (limits or LimitsIn()).model_dump(),
    }


def register(mcp: FastMCP, teams: TeamsClient) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_teams(context: Context) -> list[TeamSummary]:
        """Every team belonging to the operator whose chat this is, newest first.

        A team belonging to somebody else is not merely hidden — it is indistinguishable
        from one that never existed, so this list is the whole of what can be acted on.
        """
        rows = await _call(teams, context, "GET", "/teams")
        return [TeamSummary.model_validate(row) for row in rows]

    @mcp.tool(annotations=READ_ONLY)
    async def read_team(context: Context, team_id: int) -> TeamDetail:
        """A team and its current definition — every role with its prompt, the edges
        between them, and the limits a run must respect.

        Read this before revising: `revise_team` patches what you name and keeps the
        rest, and knowing what the rest is, is what stops a correction from being a
        rewrite.
        """
        team = await _call(teams, context, "GET", f"/teams/{team_id}")
        revision = await _call(teams, context, "GET", f"/teams/{team_id}/revisions/latest")
        definition = revision["definition"]
        return TeamDetail(
            id=team["id"],
            name=team["name"],
            description=team["description"],
            latest_revision=team["latest_revision"],
            revision_id=revision["id"],
            agents=definition.get("agents", []),
            edges=definition.get("edges", []),
            limits=definition.get("limits", {}),
            trading=definition.get("trading", {}),
        )

    @mcp.tool(annotations=WRITE)
    async def create_team(
        context: Context,
        name: str,
        agents: list[AgentIn],
        description: str = "",
        edges: list[EdgeIn] | None = None,
        limits: LimitsIn | None = None,
    ) -> SavedRevision:
        """Create a team and its first revision in one call. It belongs to the operator
        whose chat this is and appears in their Teams tab immediately.

        Every `model_id` must be one `list_models` published and every tool name one
        `list_tools` published, or the whole save is refused naming the agent at fault —
        nothing partial is written. The graph must also hold together: unique keys, edges
        pointing at agents that exist, no isolated agent once there is more than one, and
        no cycle.

        Set `limits.daily_limit` unless the operator said otherwise. It is the only thing
        standing between an experiment and a bill nobody approved, and it costs one
        string here.
        """
        body = {
            "name": name,
            "description": description,
            "definition": _definition(agents, edges or [], limits),
        }
        team = await _call(teams, context, "POST", "/teams", json=body)

        # The team exists from here on, and that changes what a failure may say: answering with a failed
        # read would tell the model the team was not created, and it would create it again.
        try:
            revision = await _call(teams, context, "GET", f"/teams/{team['id']}/revisions/latest")
        except ToolRefusal:
            return SavedRevision(
                team_id=team["id"],
                revision_id=None,
                version=team["latest_revision"],
                agents=[agent.key for agent in agents],
                note=(
                    "the team was created; reading its revision back afterwards failed, "
                    "so revision_id is unknown here. Do not create it again — read_team "
                    "gives the id when teams answers."
                ),
            )

        return SavedRevision(
            team_id=team["id"],
            revision_id=revision["id"],
            version=revision["version"],
            agents=[agent["key"] for agent in revision["definition"]["agents"]],
        )

    @mcp.tool(annotations=WRITE)
    async def revise_team(
        context: Context,
        team_id: int,
        replace_agents: list[AgentIn] | None = None,
        remove_agent_keys: list[str] | None = None,
        edges: list[EdgeIn] | None = None,
        limits: LimitsIn | None = None,
    ) -> SavedRevision:
        """Correct a team: name only what changes, and the rest of the current revision
        is carried over unchanged.

        `replace_agents` replaces an agent with the same `key` and appends one whose key
        is new. `remove_agent_keys` drops roles. `edges` and `limits` replace their whole
        section when given and are left alone when omitted — an edge list is small and
        naming it in halves would be ambiguous.

        This appends a revision; the previous one is untouched and every run already
        pointing at it still means what it meant. Nothing is ever overwritten, so a
        correction that turns out worse is undone by revising back.
        """
        if not any([replace_agents, remove_agent_keys, edges, limits]):
            raise ToolRefusal(
                "nothing to change: name at least one of replace_agents, "
                "remove_agent_keys, edges or limits. An empty revision would be a new "
                "version identical to the last one."
            )

        current = await _call(teams, context, "GET", f"/teams/{team_id}/revisions/latest")
        definition = current["definition"]

        agents: list[dict[str, Any]] = list(definition.get("agents", []))
        for key in remove_agent_keys or []:
            if not any(agent["key"] == key for agent in agents):
                raise ToolRefusal(
                    f"this team has no agent {key!r} — its agents are "
                    f"{[agent['key'] for agent in agents]}. Nothing was written."
                )
            agents = [agent for agent in agents if agent["key"] != key]

        for replacement in replace_agents or []:
            incoming = replacement.model_dump()
            for index, agent in enumerate(agents):
                if agent["key"] == incoming["key"]:
                    agents[index] = incoming
                    break
            else:
                agents.append(incoming)

        body = {
            "definition": {
                "agents": agents,
                "edges": (
                    [edge.model_dump(by_alias=True) for edge in edges]
                    if edges is not None
                    else definition.get("edges", [])
                ),
                "limits": (
                    limits.model_dump() if limits is not None else definition.get("limits", {})
                ),
                "trading": definition.get("trading", {}),
            }
        }
        revision = await _call(teams, context, "POST", f"/teams/{team_id}/revisions", json=body)
        return SavedRevision(
            team_id=team_id,
            revision_id=revision["id"],
            version=revision["version"],
            agents=[agent["key"] for agent in revision["definition"]["agents"]],
        )

    @mcp.tool(annotations=READ_ONLY)
    async def list_models(context: Context) -> list[dict[str, Any]]:
        """The models an agent may be assigned, cheapest first. A `model_id` outside this
        list is refused at save time, naming the agent that carried it."""
        return await _call(teams, context, "GET", "/models")

    @mcp.tool(annotations=READ_ONLY)
    async def list_tools(context: Context) -> list[dict[str, Any]]:
        """The tools a team's own agents may be assigned — the market archive, and the
        demo trading account where that server is configured. `read_only=false` marks a
        tool that changes the account.

        These are tools for the *team being built*, not tools for this conversation.
        """
        return await _call(teams, context, "GET", "/tools")
