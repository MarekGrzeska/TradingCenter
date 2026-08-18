"""Every refusal the dev runner makes, called directly.

`dev.sh` and `dev.ps1` refused five things before they started anything, and each refusal
was there because of a real failure — a mismatched gateway key taking the whole stack down
with "a service exited", an `.env` still pointing at the Azure server, a leftover process on
8010 that made the wait watch somebody else's service. None of them had a test, because
shell here never did.

Porting them on the eye is how the third drift happened. These are the tests, one per
refusal, each producing exactly the scenario the refusal exists for.
"""

from __future__ import annotations

import pytest

from dev import (
    ADVISORIES,
    REQUIRED_ENV,
    SERVICES,
    Environment,
    advisories,
    database_host,
    env_value,
    is_loopback,
    parse_args,
    preflight,
    services_to_start,
    terminal_command,
)

GOOD_ENV: dict[str, str] = {
    "capital-gateway": "CAPITAL_LOGIN=x\nGATEWAY_API_KEY=shared-secret\n",
    "market-data": "DATABASE_URL=postgresql://market_data:pw@localhost:55432/market_data\n",
    "agent": (
        "DATABASE_URL=postgresql://agent:pw@127.0.0.1:55432/agent\n"
        "OPENAI_API_KEY=sk-test\n"
        "MARKET_MCP_URL=http://127.0.0.1:8040\n"
        "TEAMS_MCP_URL=http://127.0.0.1:8070\n"
        "TRADING_MCP_URL=http://127.0.0.1:8060\n"
    ),
    "teams": (
        "DATABASE_URL=postgresql://teams:pw@localhost:55432/teams\n"
        "OPENAI_API_KEY=sk-test-teams\n"
        "MARKET_MCP_URL=http://127.0.0.1:8040\n"
        "TRADING_MCP_URL=http://127.0.0.1:8060\n"
    ),
    "trading-mcp": "CAPITAL_GATEWAY_API_KEY=shared-secret\n",
}

ON_PATH = {"uv", "docker", "pnpm", "npm"}


def environment(
    *,
    files: dict[str, str] | None = None,
    on_path: set[str] | None = None,
    busy_ports: set[int] | None = None,
    docker_answers: bool = True,
    node_modules: bool = True,
) -> Environment:
    present = ON_PATH if on_path is None else on_path
    contents = dict(GOOD_ENV) if files is None else files
    taken = busy_ports or set()
    return Environment(
        which=lambda name: f"/usr/bin/{name}" if name in present else None,
        read_env=contents.get,
        port_in_use=lambda port: port in taken,
        port_owner=lambda port: f" by uvicorn (pid {1000 + port})",
        docker_daemon_answers=lambda: docker_answers,
        node_modules_present=lambda: node_modules,
    )


def test_a_complete_setup_has_nothing_to_refuse() -> None:
    assert preflight(environment(), start_terminal=True) == []


class TestRefusals:
    def test_a_mismatched_gateway_key_is_refused_before_anything_starts(self) -> None:
        """The one that takes the whole stack down: trading-mcp exits before it listens."""
        files = dict(GOOD_ENV)
        files["trading-mcp"] = "CAPITAL_GATEWAY_API_KEY=something-else\n"

        problems = preflight(environment(files=files), start_terminal=True)

        assert len(problems) == 1
        assert "does not match" in problems[0]
        assert "exit before it listens" in problems[0]

    def test_a_missing_gateway_key_is_refused(self) -> None:
        """The gateway checks X-Gateway-Key on loopback too, so there is no local mode."""
        files = dict(GOOD_ENV)
        files["trading-mcp"] = "SOMETHING_ELSE=1\n"

        problems = preflight(environment(files=files), start_terminal=True)

        assert any("has no CAPITAL_GATEWAY_API_KEY" in p for p in problems)

    @pytest.mark.parametrize("module", ["market-data", "agent", "teams"])
    def test_a_remote_database_url_is_refused(self, module: str) -> None:
        """The quiet disaster: an `.env` still pointing at the Azure server."""
        files = dict(GOOD_ENV)
        files[module] = (
            "DATABASE_URL=postgresql://user:pw@psql-tradingcenter.postgres.database.azure.com"
            ":5432/market_data\nOPENAI_API_KEY=sk-test\n"
        )

        problems = preflight(environment(files=files), start_terminal=True)

        assert any(
            f"modules/{module}/.env's DATABASE_URL points at "
            "'psql-tradingcenter.postgres.database.azure.com'" in p
            for p in problems
        )
        assert any("never a remote database" in p for p in problems)

    def test_a_missing_docker_is_refused(self) -> None:
        problems = preflight(
            environment(on_path=ON_PATH - {"docker"}),
            start_terminal=True,
        )
        assert any("docker is not on PATH" in p for p in problems)

    def test_docker_installed_but_not_answering_is_a_different_message(self) -> None:
        problems = preflight(environment(docker_answers=False), start_terminal=True)
        assert any("the daemon is not answering" in p for p in problems)

    def test_a_missing_uv_is_refused(self) -> None:
        problems = preflight(environment(on_path=ON_PATH - {"uv"}), start_terminal=True)
        assert any("uv is not on PATH" in p for p in problems)

    def test_a_taken_port_is_refused_and_names_the_service(self) -> None:
        """The commonest reason a run appears to hang: the wait watches somebody else."""
        problems = preflight(environment(busy_ports={8060}), start_terminal=True)

        assert len(problems) == 1
        assert "port 8060 is already in use" in problems[0]
        assert "trading-mcp" in problems[0]
        assert "by uvicorn" in problems[0], "the owner is best-effort but useful when present"

    @pytest.mark.parametrize(("module", "_remedy"), REQUIRED_ENV)
    def test_each_required_env_file_is_refused_when_missing(
        self, module: str, _remedy: str
    ) -> None:
        files = {name: text for name, text in GOOD_ENV.items() if name != module}

        problems = preflight(environment(files=files), start_terminal=True)

        assert any(f"modules/{module}/.env is missing" in p for p in problems)

    def test_market_mcp_and_teams_mcp_need_no_env_at_all(self) -> None:
        """Every setting they read has a working loopback default (`config.py`)."""
        required = {module for module, _ in REQUIRED_ENV}
        assert "market-mcp" not in required
        assert "teams-mcp" not in required

    def test_the_terminal_checks_are_skipped_when_it_is_not_started(self) -> None:
        problems = preflight(
            environment(on_path={"uv", "docker"}, node_modules=False),
            start_terminal=False,
        )
        assert problems == []

    def test_a_missing_node_modules_is_refused_when_the_terminal_is_started(self) -> None:
        problems = preflight(environment(node_modules=False), start_terminal=True)
        assert any("node_modules is missing" in p for p in problems)

    def test_every_problem_is_reported_together(self) -> None:
        """Finding out about the second one after two services are running means killing them."""
        files = {"market-data": GOOD_ENV["market-data"]}

        problems = preflight(
            environment(files=files, on_path=set(), busy_ports={8010}),
            start_terminal=True,
        )

        assert len(problems) > 4


class TestAdvisoriesAreNotRefusals:
    """Each is a supported state that looks, from the operator's seat, like a broken module."""

    @pytest.mark.parametrize(("module", "key", "_consequence", "_port"), ADVISORIES)
    def test_a_missing_tool_url_warns_and_does_not_refuse(
        self, module: str, key: str, _consequence: str, _port: str
    ) -> None:
        files = dict(GOOD_ENV)
        files[module] = "\n".join(
            line for line in GOOD_ENV[module].splitlines() if not line.startswith(f"{key}=")
        )
        env = environment(files=files)

        assert preflight(env, start_terminal=True) == [], "an absent tool URL is not a refusal"
        assert any(f"has no {key}" in line for line in advisories(env))

    def test_a_complete_env_says_nothing(self) -> None:
        assert advisories(environment()) == []

    def test_clearing_one_tool_url_leaves_the_others_alone(self) -> None:
        """All three are checked independently — clearing one takes only its tools away."""
        files = dict(GOOD_ENV)
        files["agent"] = files["agent"].replace("TRADING_MCP_URL=http://127.0.0.1:8060\n", "")

        lines = advisories(environment(files=files))

        assert any("agent/.env has no TRADING_MCP_URL" in line for line in lines)
        assert not any("MARKET_MCP_URL" in line for line in lines)
        assert not any("TEAMS_MCP_URL" in line for line in lines)


class TestStartOrder:
    def test_the_order_is_the_one_both_scripts_claimed_to_have(self) -> None:
        """All three documented drifts were a difference between this list and itself."""
        assert [service.name for service in SERVICES] == [
            "capital-gateway",
            "market-data",
            "market-mcp",
            "trading-mcp",
            "teams",
            "teams-mcp",
            "agent",
            "terminal",
        ]

    def test_ports_are_the_fixed_ones(self) -> None:
        assert {service.name: service.port for service in SERVICES} == {
            "capital-gateway": 8010,
            "market-data": 8020,
            "agent": 8030,
            "market-mcp": 8040,
            "teams": 8050,
            "trading-mcp": 8060,
            "teams-mcp": 8070,
            "terminal": 5173,
        }

    def test_every_back_end_is_waited_for(self) -> None:
        """A service started and not waited for is what `dev.ps1` did to teams-mcp."""
        for service in SERVICES:
            if service.name == "terminal":
                continue
            assert service.health_path, f"{service.name} has no health path to wait on"

    def test_every_service_has_its_reason_recorded(self) -> None:
        for service in SERVICES:
            assert len(service.why) > 30, f"{service.name}'s position has no reason with it"

    def test_no_terminal_drops_exactly_one_service(self) -> None:
        full = services_to_start(start_terminal=True)
        backend = services_to_start(start_terminal=False)
        assert len(full) - len(backend) == 1
        assert "terminal" not in {service.name for service in backend}

    def test_every_service_directory_exists(self) -> None:
        for service in SERVICES:
            assert service.directory.is_dir(), f"{service.module} is not a module directory"

    def test_the_log_prefixes_line_up_and_are_distinct(self) -> None:
        prefixes = [service.log_prefix for service in SERVICES]
        assert len(set(prefixes)) == len(prefixes)
        assert len({len(prefix) for prefix in prefixes}) == 1, "a ragged prefix column"


class TestArgumentParsing:
    def test_both_spellings_of_the_one_flag_agree(self) -> None:
        """`dev.ps1` documents -NoTerminal, `dev.sh` documents --no-terminal.

        The wrappers pass their arguments through, so this is the last place a difference
        between the two platforms could appear.
        """
        assert parse_args(["--no-terminal"]).start_terminal is False
        assert parse_args(["-NoTerminal"]).start_terminal is False

    def test_the_default_starts_everything(self) -> None:
        assert parse_args([]).start_terminal is True

    def test_an_unknown_flag_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--no-database"])


class TestTerminalCommand:
    def test_pnpm_is_preferred(self) -> None:
        assert terminal_command(environment())[0] == "pnpm"

    def test_npm_alone_is_enough(self) -> None:
        """Refusing over the choice of package manager helps nobody."""
        assert terminal_command(environment(on_path={"uv", "docker", "npm"}))[0] == "npx"


class TestEnvReading:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("KEY=value", "value"),
            ("  KEY=value  ", "value"),
            ("OTHER=1\nKEY=value\n", "value"),
            ("KEY=", ""),
            ("PREFIX_KEY=value", None),
            ("", None),
            ("# KEY=commented", None),
        ],
    )
    def test_env_value(self, text: str, expected: str | None) -> None:
        assert env_value(text, "KEY") == expected

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("postgresql://u:p@localhost:55432/db", "localhost"),
            ("postgresql+asyncpg://u:p@127.0.0.1:55432/db", "127.0.0.1"),
            ("postgresql://localhost/db", "localhost"),
            ("postgresql://u:p@psql-x.postgres.database.azure.com:5432/db", "psql-x.postgres.database.azure.com"),
        ],
    )
    def test_database_host(self, url: str, expected: str) -> None:
        assert database_host(f"DATABASE_URL={url}") == expected

    def test_no_database_url_is_not_a_host(self) -> None:
        assert database_host("OPENAI_API_KEY=sk-test") is None

    @pytest.mark.parametrize("host", [None, "", "localhost", "127.0.0.1", "127.1.2.3", "::1"])
    def test_loopback_hosts(self, host: str | None) -> None:
        assert is_loopback(host)

    @pytest.mark.parametrize("host", ["psql-x.postgres.database.azure.com", "10.0.0.5", "db"])
    def test_non_loopback_hosts(self, host: str) -> None:
        assert not is_loopback(host)
