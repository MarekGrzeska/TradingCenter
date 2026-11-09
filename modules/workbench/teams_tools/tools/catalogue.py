"""The catalogue: what teams exist, what one looks like, how to make one, how to correct one. `create_team` and
`revise_team` are one call each — rebuilding a definition to change one role is three turns in which to drop an agent."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from ..client import TeamsClient
from ..errors import ToolRefusal
from ._shared import READ_ONLY, WRITE, _call


# Sent by the run itself when the agent cannot answer; the agent must carry send_telegram_message.
class FallbackNoticeIn(BaseModel):
    destination: str
    bot: str | None = None
    prefix: str = ""


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
    fallback_notice: FallbackNoticeIn | None = None


class StepIn(BaseModel):
    key: str
    recipe: str
    params: dict[str, Any] = Field(default_factory=dict)


class TradingIn(BaseModel):
    environment: Literal["demo", "live"] = "demo"
    account_id: str | None = None
    max_order_size: str | None = None
    orders_per_run: int | None = None
    orders_per_day: int | None = None


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
    steps: list[dict[str, Any]]
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
    steps: list[str] = Field(default_factory=list, description="step keys in the saved revision")
    note: str | None = None


def _definition(
    agents: list[AgentIn],
    steps: list[StepIn],
    edges: list[EdgeIn],
    limits: LimitsIn | None,
    trading: TradingIn | None,
) -> dict[str, Any]:
    definition: dict[str, Any] = {
        "agents": [agent.model_dump() for agent in agents],
        "steps": [step.model_dump() for step in steps],
        "edges": [edge.model_dump(by_alias=True) for edge in edges],
        "limits": (limits or LimitsIn()).model_dump(),
    }
    if trading is not None:
        definition["trading"] = _demo_trading(trading)
    return definition


_LIVE_IS_THE_TERMINALS = (
    "the live account is set in the terminal's Teams tab, by the operator, never from a chat. Nothing was written."
)


def _demo_trading(trading: TradingIn) -> dict[str, Any]:
    if trading.environment != "demo":
        raise ToolRefusal(f"refused: {_LIVE_IS_THE_TERMINALS}")
    return trading.model_dump()


def _keys(definition: dict[str, Any], section: str) -> list[str]:
    return [node["key"] for node in definition.get(section, [])]


def _patched(
    current: list[dict[str, Any]],
    replace: list[AgentIn] | list[StepIn] | None,
    remove: list[str] | None,
    kind: str,
) -> list[dict[str, Any]]:
    """One section of the definition with the named nodes dropped, replaced by key or appended; the rest as it was."""
    nodes = list(current)
    for key in remove or []:
        if not any(node["key"] == key for node in nodes):
            raise ToolRefusal(
                f"this team has no {kind} {key!r} — its {kind}s are "
                f"{[node['key'] for node in nodes]}. Nothing was written."
            )
        nodes = [node for node in nodes if node["key"] != key]
    for replacement in replace or []:
        incoming = replacement.model_dump()
        for index, node in enumerate(nodes):
            if node["key"] == incoming["key"]:
                nodes[index] = incoming
                break
        else:
            nodes.append(incoming)
    return nodes


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
            steps=definition.get("steps", []),
            edges=definition.get("edges", []),
            limits=definition.get("limits", {}),
            trading=definition.get("trading", {}),
        )

    @mcp.tool(annotations=WRITE)
    async def create_team(
        context: Context,
        name: str,
        agents: list[AgentIn] | None = None,
        description: str = "",
        steps: list[StepIn] | None = None,
        edges: list[EdgeIn] | None = None,
        limits: LimitsIn | None = None,
        trading: TradingIn | None = None,
    ) -> SavedRevision:
        """Create a team and its first revision in one call. It belongs to the operator
        whose chat this is and appears in their Teams tab immediately.

        A team holds agents (a model each) and steps (a recipe from list_step_recipes, no model),
        wired by `edges`; a step's JSON result is what its successors read. `trading` sets the
        team's demo account and order limits; the live account is set in the terminal only.

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
            "definition": _definition(agents or [], steps or [], edges or [], limits, trading),
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
                agents=[agent.key for agent in agents or []],
                steps=[step.key for step in steps or []],
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
            agents=_keys(revision["definition"], "agents"),
            steps=_keys(revision["definition"], "steps"),
        )

    @mcp.tool(annotations=WRITE)
    async def rename_team(
        context: Context, team_id: int, name: str | None = None, description: str | None = None
    ) -> TeamSummary:
        """Change a team's name or description, not a revision. Do it when a revision
        changes what the team does."""
        if name is None and description is None:
            raise ToolRefusal("nothing to change: name a new name, description or both.")
        body = {"name": name, "description": description}
        return TeamSummary.model_validate(
            await _call(teams, context, "PATCH", f"/teams/{team_id}", json=body)
        )

    @mcp.tool(annotations=WRITE)
    async def revise_team(
        context: Context,
        team_id: int,
        replace_agents: list[AgentIn] | None = None,
        remove_agent_keys: list[str] | None = None,
        replace_steps: list[StepIn] | None = None,
        remove_step_keys: list[str] | None = None,
        edges: list[EdgeIn] | None = None,
        limits: LimitsIn | None = None,
        trading: TradingIn | None = None,
    ) -> SavedRevision:
        """Correct a team: name only what changes, and the rest of the current revision
        is carried over unchanged.

        `replace_agents` replaces an agent with the same `key` and appends one whose key
        is new. `remove_agent_keys` drops roles; `replace_steps` and `remove_step_keys` do the
        same for steps. `edges`, `limits` and `trading` replace their whole section when given
        and are left alone when omitted — an edge list is small and naming it in halves would
        be ambiguous. A team on the live account keeps its `trading` as it is.

        This appends a revision; the previous one is untouched and every run already
        pointing at it still means what it meant. Nothing is ever overwritten, so a
        correction that turns out worse is undone by revising back.
        """
        if not any(
            [replace_agents, remove_agent_keys, replace_steps, remove_step_keys, edges, limits, trading]
        ):
            raise ToolRefusal(
                "nothing to change: name at least one of replace_agents, remove_agent_keys, "
                "replace_steps, remove_step_keys, edges, limits or trading. An empty revision "
                "would be a new version identical to the last one."
            )

        current = await _call(teams, context, "GET", f"/teams/{team_id}/revisions/latest")
        definition = current["definition"]

        current_trading = definition.get("trading", {})
        if trading is not None and current_trading.get("environment") == "live":
            raise ToolRefusal(f"refused: this team trades on the live account, and {_LIVE_IS_THE_TERMINALS}")

        agents = _patched(definition.get("agents", []), replace_agents, remove_agent_keys, "agent")
        steps = _patched(definition.get("steps", []), replace_steps, remove_step_keys, "step")

        body = {
            "definition": {
                "agents": agents,
                "steps": steps,
                "edges": (
                    [edge.model_dump(by_alias=True) for edge in edges]
                    if edges is not None
                    else definition.get("edges", [])
                ),
                "limits": (
                    limits.model_dump() if limits is not None else definition.get("limits", {})
                ),
                "trading": _demo_trading(trading) if trading is not None else current_trading,
            }
        }
        revision = await _call(teams, context, "POST", f"/teams/{team_id}/revisions", json=body)
        return SavedRevision(
            team_id=team_id,
            revision_id=revision["id"],
            version=revision["version"],
            agents=_keys(revision["definition"], "agents"),
            steps=_keys(revision["definition"], "steps"),
        )

    @mcp.tool(annotations=READ_ONLY)
    async def list_step_recipes(context: Context) -> list[dict[str, Any]]:
        """The recipes a step may run, with their parameters and the tools they call. A step
        calls no model: it does the same thing every run, and its JSON result (decision,
        reason, summary) is what the agents after it read."""
        return await _call(teams, context, "GET", "/teams/step-recipes")

    @mcp.tool(annotations=READ_ONLY)
    async def list_models(context: Context) -> list[dict[str, Any]]:
        """The models an agent may be assigned, cheapest first. A `model_id` outside this
        list is refused at save time, naming the agent that carried it."""
        return await _call(teams, context, "GET", "/teams/models")

    @mcp.tool(annotations=READ_ONLY)
    async def list_tools(context: Context) -> list[dict[str, Any]]:
        """The tools a team's own agents may be assigned — the market archive, and the
        demo trading account where that server is configured. `read_only=false` marks a
        tool that changes the account.

        These are tools for the *team being built*, not tools for this conversation.
        """
        return await _call(teams, context, "GET", "/tools")
