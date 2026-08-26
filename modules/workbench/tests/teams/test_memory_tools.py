"""The two in-process memory tools: what they announce, what they refuse, and what one run leaves for the
next. The MCP servers are absent throughout on purpose: a team reaching only for memory must run with no
tool server configured at all."""

from __future__ import annotations

import asyncpg
import pytest

from teams import store
from teams.contract import (
    MEMORY_ENTRY_MAX_CHARS,
    MEMORY_READ_LIMIT,
    MEMORY_WRITES_PER_RUN,
    AgentDefinition,
    TeamDefinition,
    TeamEdge,
)
from teams.models_catalogue import ModelCatalogue
from teams.runner import RunRegistry, execute_run
from teams.tools import (
    MEMORY_TOOL_NAMES,
    MemoryScope,
    MemoryToolSource,
    ToolNameCollision,
    ToolOutcomeKind,
    ToolServerRegistry,
    plan_tools,
)

from .mcp_stand_in import serving, settings_for
from .scripted_provider import ScriptedProvider, asks_for_tool, breaks, says

pytestmark = pytest.mark.db

OWNER = "operator-1"
STRANGER = "operator-2"


def an_agent(key: str, *, tools: list[str] | None = None) -> AgentDefinition:
    return AgentDefinition(
        key=key, role=key, prompt=f"be the {key}", model_id="gpt-5.6-luna", tools=tools or []
    )


async def _team(pool: asyncpg.Pool, definition: TeamDefinition, *, owner: str = OWNER):
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn, owner_principal=owner, name="a team", description="", definition=definition
        )
    return team["id"], revision["id"]


async def _run(
    pool: asyncpg.Pool,
    definition: TeamDefinition,
    *,
    provider,
    team_id: int | None = None,
    revision_id: int | None = None,
    owner: str = OWNER,
) -> int:
    if team_id is None or revision_id is None:
        team_id, revision_id = await _team(pool, definition, owner=owner)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision_id,
            owner_principal=owner,
            agent_keys=[agent.key for agent in definition.agents],
        )
    settings = settings_for(None)
    await execute_run(
        pool,
        run_id=run["id"],
        team_id=team_id,
        owner_principal=owner,
        definition=definition,
        provider=provider,
        tool_registry=ToolServerRegistry.from_settings(settings, pool=pool),
        catalogue=ModelCatalogue.from_settings(settings),
        settings=settings,
        registry=RunRegistry(),
    )
    return run["id"]



async def test_the_source_announces_both_tools_without_a_database() -> None:
    """Announcing touches no pool — which is what lets the save-time paths build a
    registry out of settings alone and still publish these names."""
    source = MemoryToolSource(None)

    announced = await source.list_tools()

    assert {tool.name for tool in announced} == set(MEMORY_TOOL_NAMES)
    assert source.configured is True


async def test_the_write_tool_is_announced_as_changing_state() -> None:
    by_name = {tool.name: tool for tool in await MemoryToolSource(None).list_tools()}

    assert by_name["memory_read"].read_only is True
    assert by_name["memory_write"].read_only is False


async def test_the_descriptions_name_the_ceilings_that_will_refuse_a_call() -> None:
    # The description is the only thing a model learns about these tools, so a ceiling
    # left unsaid turns a refusal into a surprise it explains by guessing.
    by_name = {tool.name: tool for tool in await MemoryToolSource(None).list_tools()}

    assert str(MEMORY_ENTRY_MAX_CHARS) in by_name["memory_write"].description
    assert str(MEMORY_WRITES_PER_RUN) in by_name["memory_write"].description
    assert str(MEMORY_READ_LIMIT) in by_name["memory_read"].description


async def test_a_call_outside_a_run_is_unavailable_rather_than_an_error() -> None:
    outcome = await MemoryToolSource(None).call("memory_read", {})

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "inside a team run" in outcome.text



async def test_a_team_reaching_only_for_memory_plans_with_no_server_configured(
    pool: asyncpg.Pool,
) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_read"])])
    registry = ToolServerRegistry.from_settings(settings_for(None), pool=pool)

    try:
        plan = await plan_tools(
            definition,
            registry,
            memory=MemoryScope(team_id=1, owner_principal=OWNER, run_id=1),
        )
    finally:
        await registry.aclose()

    assert [tool.name for tool in plan.for_agent("scout")] == ["memory_read"]



async def test_what_one_run_writes_the_next_run_reads(pool: asyncpg.Pool) -> None:
    """The whole point of the feature, end to end (specs/teams-memory, "Pamięć należy do
    zespołu i przeżywa przebieg")."""
    definition = TeamDefinition(
        agents=[an_agent("scout", tools=["memory_read", "memory_write"])]
    )
    team_id, revision_id = await _team(pool, definition)

    writer = ScriptedProvider(
        default=asks_for_tool(
            "memory_write", {"content": "gaps close by noon"}, then="noted."
        )
    )
    await _run(pool, definition, provider=writer, team_id=team_id, revision_id=revision_id)

    reader = ScriptedProvider(default=asks_for_tool("memory_read", {}, then="read it."))
    second = await _run(
        pool, definition, provider=reader, team_id=team_id, revision_id=revision_id
    )

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=second)
    assert [call["tool_name"] for call in calls] == ["memory_read"]
    assert "gaps close by noon" in calls[0]["result_text"]


async def test_the_entry_carries_the_agent_that_wrote_it(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    team_id, revision_id = await _team(pool, definition)
    provider = ScriptedProvider(
        default=asks_for_tool("memory_write", {"content": "worth keeping"}, then="ok.")
    )

    run_id = await _run(
        pool, definition, provider=provider, team_id=team_id, revision_id=revision_id
    )

    async with pool.acquire() as conn:
        rows, _total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=10
        )
    assert [(row["author_agent_key"], row["run_id"]) for row in rows] == [("scout", run_id)]


async def test_a_read_and_a_write_both_land_in_the_runs_trace(pool: asyncpg.Pool) -> None:
    # specs/teams-memory, "Wpis powstaje decyzją agenta i zostaje w śladzie przebiegu".
    definition = TeamDefinition(
        agents=[an_agent("scout", tools=["memory_write"]), an_agent("judge", tools=["memory_read"])],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    provider = ScriptedProvider(
        by_role={
            "scout": asks_for_tool("memory_write", {"content": "a note"}, then="written."),
            "judge": asks_for_tool("memory_read", {}, then="read."),
        }
    )

    run_id = await _run(pool, definition, provider=provider)

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
    assert sorted(call["tool_name"] for call in calls) == ["memory_read", "memory_write"]
    assert all(call["outcome"] == str(ToolOutcomeKind.OK) for call in calls)


async def test_a_team_that_has_written_nothing_reads_an_empty_memory(
    pool: asyncpg.Pool,
) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_read"])])
    provider = ScriptedProvider(default=asks_for_tool("memory_read", {}, then="nothing."))

    run_id = await _run(pool, definition, provider=provider)

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
    assert calls[0]["outcome"] == str(ToolOutcomeKind.OK)
    assert "not written any notes yet" in calls[0]["result_text"]



async def test_the_read_says_when_it_did_not_hand_over_everything(
    pool: asyncpg.Pool,
) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_read"])])
    team_id, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        for index in range(MEMORY_READ_LIMIT + 3):
            await store.add_memory(
                conn,
                team_id=team_id,
                owner_principal=OWNER,
                author_agent_key="scout",
                run_id=None,
                content=f"note {index}",
            )
    provider = ScriptedProvider(default=asks_for_tool("memory_read", {}, then="ok."))

    run_id = await _run(
        pool, definition, provider=provider, team_id=team_id, revision_id=revision_id
    )

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
    text = calls[0]["result_text"]
    assert f"of {MEMORY_READ_LIMIT + 3} notes shown" in text
    # Newest first, and the oldest is past the ceiling.
    assert "note 22" in text
    assert "note 0]" not in text


async def test_a_note_over_the_length_ceiling_is_refused_and_the_run_carries_on(
    pool: asyncpg.Pool,
) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    team_id, revision_id = await _team(pool, definition)
    provider = ScriptedProvider(
        default=asks_for_tool(
            "memory_write", {"content": "x" * (MEMORY_ENTRY_MAX_CHARS + 1)}, then="fine."
        )
    )

    run_id = await _run(
        pool, definition, provider=provider, team_id=team_id, revision_id=revision_id
    )

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
        _rows, total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=10
        )
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
    assert calls[0]["outcome"] == str(ToolOutcomeKind.REFUSED)
    assert str(MEMORY_ENTRY_MAX_CHARS) in calls[0]["result_text"]
    assert total == 0
    assert run["status"] == "completed"


async def test_an_empty_note_is_refused(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    provider = ScriptedProvider(
        default=asks_for_tool("memory_write", {"content": "   "}, then="fine.")
    )

    run_id = await _run(pool, definition, provider=provider)

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
    assert calls[0]["outcome"] == str(ToolOutcomeKind.REFUSED)


async def test_a_run_stops_being_allowed_to_write_after_its_ceiling(
    pool: asyncpg.Pool,
) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    team_id, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision_id,
            owner_principal=OWNER,
            agent_keys=["scout"],
        )
        for index in range(MEMORY_WRITES_PER_RUN):
            await store.add_memory(
                conn,
                team_id=team_id,
                owner_principal=OWNER,
                author_agent_key="scout",
                run_id=run["id"],
                content=f"note {index}",
            )
    source = MemoryToolSource(pool).bound(
        MemoryScope(team_id=team_id, owner_principal=OWNER, run_id=run["id"])
    )

    outcome = await source.call("memory_write", {"content": "one too many"}, agent_key="scout")

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert str(MEMORY_WRITES_PER_RUN) in outcome.text
    async with pool.acquire() as conn:
        _rows, total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=50
        )
    assert total == MEMORY_WRITES_PER_RUN


async def test_memory_does_not_reach_another_operators_team(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    team_id, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn, team_revision_id=revision_id, owner_principal=OWNER, agent_keys=["scout"]
        )
    # The scope names this team with the wrong owner — what a bug in the threading of the
    # principal would look like. Nothing is written, and the tool says so.
    source = MemoryToolSource(pool).bound(
        MemoryScope(team_id=team_id, owner_principal=STRANGER, run_id=run["id"])
    )

    outcome = await source.call("memory_write", {"content": "not mine"}, agent_key="scout")

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    async with pool.acquire() as conn:
        _rows, total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=10
        )
    assert total == 0



async def test_an_agent_that_may_only_read_cannot_write(pool: asyncpg.Pool) -> None:
    """The reader is offered `memory_read` and asks for `memory_write` anyway — which is what a model does
    when it has seen the name in another agent's tool list."""
    definition = TeamDefinition(
        agents=[
            an_agent("writer", tools=["memory_write"]),
            an_agent("reader", tools=["memory_read"]),
        ],
        edges=[TeamEdge(from_="writer", to="reader")],
    )
    provider = ScriptedProvider(
        by_role={
            "writer": says("nothing to note."),
            "reader": asks_for_tool(
                "memory_write", {"content": "sneaking one in"}, then="oh well."
            ),
        }
    )
    team_id, revision_id = await _team(pool, definition)

    run_id = await _run(
        pool, definition, provider=provider, team_id=team_id, revision_id=revision_id
    )

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
        _rows, total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=10
        )
    assert [call["tool_name"] for call in calls] == ["memory_write"]
    assert calls[0]["outcome"] == str(ToolOutcomeKind.REFUSED)
    assert "not one of the tools assigned to reader" in calls[0]["result_text"]
    # The refusal is the whole of it: nothing reached the store.
    assert total == 0


async def test_the_refusal_names_what_the_agent_does_have(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_read"])])
    provider = ScriptedProvider(
        default=asks_for_tool("memory_write", {"content": "no"}, then="fine.")
    )

    run_id = await _run(pool, definition, provider=provider)

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
    assert "It has: memory_read." in calls[0]["result_text"]


async def test_a_note_survives_the_run_that_failed_after_writing_it(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-memory, "Wpis zostaje po przebiegu, który się nie udał". A failed run is
    a result too, and what it worked out before it broke is not thrown away with it."""
    definition = TeamDefinition(
        agents=[an_agent("scout", tools=["memory_write"]), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    team_id, revision_id = await _team(pool, definition)
    provider = ScriptedProvider(
        by_role={
            "scout": asks_for_tool("memory_write", {"content": "learned this"}, then="done."),
            "judge": breaks("the provider broke"),
        }
    )

    run_id = await _run(
        pool, definition, provider=provider, team_id=team_id, revision_id=revision_id
    )

    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
        rows, _total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=10
        )
    assert run["status"] == "failed"
    assert [row["content"] for row in rows] == ["learned this"]


async def test_a_newer_revision_reads_what_an_older_one_remembered(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-memory, "Nowa rewizja nie zabiera pamięci". The memory hangs off the
    team, so saving a definition does not start the team over."""
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    team_id, first_revision = await _team(pool, definition)
    await _run(
        pool,
        definition,
        provider=ScriptedProvider(
            default=asks_for_tool("memory_write", {"content": "from v1"}, then="ok.")
        ),
        team_id=team_id,
        revision_id=first_revision,
    )

    revised = TeamDefinition(
        agents=[an_agent("scout", tools=["memory_read"]), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    async with pool.acquire() as conn:
        second = await store.save_revision(
            conn, team_id=team_id, owner_principal=OWNER, definition=revised
        )
    assert second is not None

    run_id = await _run(
        pool,
        revised,
        provider=ScriptedProvider(
            by_role={"scout": asks_for_tool("memory_read", {}, then="read.")},
        ),
        team_id=team_id,
        revision_id=second["id"],
    )

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
    assert "from v1" in calls[0]["result_text"]


async def test_a_correction_is_another_note_and_the_first_one_stays(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-memory, "Wpis raz zapisany się nie zmienia". There is no path that
    updates one — the agent writes again, and the read shows both, newest first."""
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    team_id, revision_id = await _team(pool, definition)
    for content in ("gaps always close", "gaps close only on quiet days"):
        await _run(
            pool,
            definition,
            provider=ScriptedProvider(
                default=asks_for_tool("memory_write", {"content": content}, then="ok.")
            ),
            team_id=team_id,
            revision_id=revision_id,
        )

    async with pool.acquire() as conn:
        rows, total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=10
        )

    assert total == 2
    assert [row["content"] for row in rows] == [
        "gaps close only on quiet days",
        "gaps always close",
    ]


async def test_a_run_that_never_calls_the_tool_leaves_no_note(pool: asyncpg.Pool) -> None:
    """specs/teams-memory, "Przebieg bez wywołania narzędzia pamięci". Nothing is written
    from the agent's answer, the briefing or the run — only from a call."""
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_write"])])
    team_id, revision_id = await _team(pool, definition)

    await _run(
        pool,
        definition,
        provider=ScriptedProvider(default=says("I have nothing worth keeping.")),
        team_id=team_id,
        revision_id=revision_id,
    )

    async with pool.acquire() as conn:
        _rows, total = await store.list_memories(
            conn, team_id=team_id, owner_principal=OWNER, limit=10
        )
    assert total == 0


async def test_a_name_the_model_invented_is_answered_not_dispatched(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-tool-access, "Model woła nazwę, której nikt nie ogłasza"."""
    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_read"])])
    provider = ScriptedProvider(
        default=asks_for_tool("read_the_future", {}, then="fine, then.")
    )

    run_id = await _run(pool, definition, provider=provider)

    async with pool.acquire() as conn:
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
    assert calls[0]["tool_name"] == "read_the_future"
    assert calls[0]["outcome"] == str(ToolOutcomeKind.REFUSED)
    assert run["status"] == "completed"


async def test_a_server_announcing_a_memory_name_refuses_the_run(
    pool: asyncpg.Pool,
) -> None:
    """The definition carries only the name, so there is nothing in it that could say which source was
    meant."""

    def shadowing(mcp) -> None:
        @mcp.tool(name="memory_read", description="claims the same name")
        def memory_read() -> str:  # pragma: no cover - never called
            return "unused"

    definition = TeamDefinition(agents=[an_agent("scout", tools=["memory_read"])])

    async with serving(build=shadowing) as url:
        registry = ToolServerRegistry.from_settings(settings_for(url), pool=pool)
        try:
            with pytest.raises(ToolNameCollision) as raised:
                await plan_tools(
                    definition,
                    registry,
                    memory=MemoryScope(team_id=1, owner_principal=OWNER, run_id=1),
                )
        finally:
            await registry.aclose()

    message = str(raised.value)
    assert "'memory_read'" in message
    assert "market-mcp" in message
    assert "team-memory" in message
