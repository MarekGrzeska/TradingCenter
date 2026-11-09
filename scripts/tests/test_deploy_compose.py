"""move-from-azure-to-vps, `vps-edge`: what the edge owes the applications is checked where it can be read — the Compose
file and the Caddyfile — because the applications trust a marker only the proxy writes, and that is true exactly as long
as nothing else is reachable from outside."""

from __future__ import annotations

import pathlib
import re

import yaml

DEPLOY = pathlib.Path(__file__).resolve().parent.parent.parent / "deploy"
COMPOSE = yaml.safe_load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))
CADDYFILE = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
SERVICES: dict[str, dict] = COMPOSE["services"]

# Written by the deploy itself beside `.env`, never by an operator, so `env.required` does not list them.
FROM_TAGS_FILE = re.compile(r"_TAG$")


def required_names() -> set[str]:
    lines = (DEPLOY / "env.required").read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}


def test_only_the_proxy_publishes_a_port() -> None:
    published = {name for name, service in SERVICES.items() if "ports" in service}
    assert published == {"caddy"}


def test_the_database_is_on_a_network_with_no_way_in_or_out() -> None:
    networks = COMPOSE["networks"]
    assert networks["data"]["internal"] is True
    assert SERVICES["postgres"]["networks"] == ["data"]


def test_the_proxy_reaches_only_the_applications_it_publishes() -> None:
    assert SERVICES["caddy"]["networks"] == ["edge", "english", "live-core"]
    on_edge = {name for name, service in SERVICES.items() if "edge" in service.get("networks", [])}
    assert on_edge == {"caddy", "gateway", "workbench", "trading-mcp"}


def test_the_live_account_runs_only_in_its_profile_and_the_workbench_never_reaches_its_gateway() -> None:
    """capital-live-account, "Workbench próbuje sięgnąć bramy konta realnego": the gateway is on live-core with its tool
    server and the proxy; the workbench, which holds the tool server's key, is on live-tools only."""
    for name in ("gateway-live", "trading-mcp-live"):
        assert SERVICES[name]["profiles"] == ["live"]
    on_core = {name for name, service in SERVICES.items() if "live-core" in service.get("networks", [])}
    on_tools = {name for name, service in SERVICES.items() if "live-tools" in service.get("networks", [])}
    assert on_core == {"caddy", "gateway-live", "trading-mcp-live"}
    assert on_tools == {"workbench", "trading-mcp-live"}
    assert SERVICES["gateway-live"]["networks"] == ["live-core"]
    assert SERVICES["gateway-live"]["environment"]["CAPITAL_ENVIRONMENT"] == "live"
    assert SERVICES["trading-mcp-live"]["environment"]["EXPECTED_ENVIRONMENT"] == "live"


def test_the_english_network_is_external_and_holds_only_caddy() -> None:
    """AgenticEnglish's web app: the one network shared with that project, internal and created outside both."""
    assert COMPOSE["networks"]["english"] == {"external": True, "name": "agentic-english-edge"}
    on_english = {name for name, service in SERVICES.items() if "english" in service.get("networks", [])}
    assert on_english == {"caddy"}


OPERATOR_CLIENTS = "${CLAUDE_CODE_APPLICATION_ID:?},${AGENT_APPLICATION_ID:?}"


def test_the_tool_server_admits_from_outside_only_the_operators_clients() -> None:
    """operator-mcp-access: on the edge, with a gateway token of a named application — Claude Code at the desk and the
    agent on the server (operator-agent-on-telegram); the workbench still reaches it with the key on `services`."""
    trading = SERVICES["trading-mcp"]
    assert trading["networks"] == ["edge", "services"]
    environment = trading["environment"]
    assert environment["EXTERNAL_CALLER_APPLICATION_IDS"] == OPERATOR_CLIENTS
    assert environment["ENTRA_AUDIENCES"] == "${GATEWAY_ENTRA_AUDIENCES:?}"


def test_the_tool_surfaces_answer_the_operators_clients_and_no_browser() -> None:
    callers = SERVICES["workbench"]["environment"]["TOOL_CALLER_APPLICATION_IDS"]
    assert callers == OPERATOR_CLIENTS


# Each would hand the agent a door the operator's desk client does not have (operator-agent-on-telegram).
SYSTEM_SECRETS = re.compile(r"PASSWORD|API_KEY|OPENAI|SESSION_KEY|DATABASE_URL")


def test_the_agent_has_its_own_network_and_no_secret_of_the_system() -> None:
    """It reaches the system through the public address and Caddy, like the operator at the desk — never by name."""
    agent = SERVICES["claude-agent"]
    assert agent["networks"] == ["claude-agent"]
    assert COMPOSE["networks"]["claude-agent"] == {}
    others = {name for name, service in SERVICES.items() if "claude-agent" in service.get("networks", [])}
    assert others == {"claude-agent"}
    assert [name for name in agent["environment"] if SYSTEM_SECRETS.search(name)] == []
    assert not any(SYSTEM_SECRETS.search(str(value)) for value in agent["environment"].values())


def test_account_writes_are_off_unless_the_environment_says_otherwise() -> None:
    assert SERVICES["claude-agent"]["environment"]["AGENT_ACCOUNT_WRITES"] == "${AGENT_ACCOUNT_WRITES:-off}"
    assert SERVICES["claude-agent"]["environment"]["AGENT_LIVE_ACCOUNT_WRITES"] == "${AGENT_LIVE_ACCOUNT_WRITES:-off}"


def test_no_service_takes_the_whole_environment_file() -> None:
    """Each gets the names it uses and no others: a compromised process learns its own secrets, not the system's."""
    assert [name for name, service in SERVICES.items() if "env_file" in service] == []


def test_every_name_the_compose_file_demands_is_one_the_deploy_checks() -> None:
    text = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    demanded = {n for n in re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", text) if not FROM_TAGS_FILE.search(n)}
    assert demanded == required_names()


def test_the_optional_names_are_blank_by_default_and_not_required() -> None:
    text = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    optional = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):-\}", text))
    assert optional == {
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_KEY",
        "AGENT_TELEGRAM_OWNER_CHAT_ID",
        "AGENT_CHECKINS",
        "LIVE_TRADING_MCP_URL",
        "LIVE_GATEWAY_API_KEY",
        "LIVE_CAPITAL_API_KEY",
        "LIVE_CAPITAL_IDENTIFIER",
        "LIVE_CAPITAL_PASSWORD",
        "LIVE_ACCOUNT_ID",
        "LIVE_ORDER_LIMITS",
    }
    assert not optional & required_names()


def test_the_front_ends_are_served_through_their_parent_directory() -> None:
    """A front end is swapped in by renaming its directory; a bind mount of that directory would keep the old one."""
    volumes = SERVICES["caddy"]["volumes"]
    assert "./www:/srv/www:ro" in volumes
    assert not [v for v in volumes if v.startswith("./www/")]
    assert "root * /srv/www/terminal" in CADDYFILE and "root * /srv/www/pocket" in CADDYFILE


def test_every_service_rotates_its_logs() -> None:
    assert [name for name, service in SERVICES.items() if "logging" not in service] == []


def _reverse_proxy_blocks() -> list[str]:
    """The text of each `reverse_proxy` block, braces matched by depth rather than guessed by regex."""
    blocks = []
    for match in re.finditer(r"reverse_proxy\s+\S+\s*\{", CADDYFILE):
        depth, index = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(CADDYFILE[index], 0)
            index += 1
        blocks.append(CADDYFILE[match.end() : index])
    return blocks


def test_every_proxied_request_is_marked_as_coming_from_outside() -> None:
    blocks = _reverse_proxy_blocks()
    # gateway, workbench, trading-mcp, AgenticEnglish's web app, and the live account's gateway and trading-mcp
    assert len(blocks) == 6
    assert all("import edge_headers" in block for block in blocks)


def test_the_marker_is_written_not_forwarded_and_identity_headers_are_removed() -> None:
    snippet = CADDYFILE.split("(edge_headers) {", 1)[1].split("\n}\n", 1)[0]
    assert "header_up X-TC-Edge 1" in snippet
    for header in ("", "-ID", "-NAME", "-IDP"):
        assert f"header_up -X-MS-CLIENT-PRINCIPAL{header}\n" in snippet + "\n"


def _site(name: str) -> str:
    start = CADDYFILE.index("{$" + name + "} {")
    depth, index = 0, CADDYFILE.index("{", start + len(name) + 3)
    while True:
        depth += {"{": 1, "}": -1}.get(CADDYFILE[index], 0)
        index += 1
        if depth == 0:
            return CADDYFILE[start:index]


def test_the_gateway_host_carries_neither_its_stream_nor_a_tool_surface() -> None:
    gateway = _site("GATEWAY_HOST")
    assert "respond @stream 404" in gateway and "import no_tool_surface" in gateway


def test_the_api_host_carries_the_tool_surfaces_and_trading_mcp_under_its_prefix() -> None:
    """operator-mcp-access: the processes decide who gets in; the edge only routes and marks."""
    api = _site("API_HOST")
    assert "no_tool_surface" not in api
    assert "handle_path /trading/*" in api and "reverse_proxy trading-mcp:80" in api


def test_the_stream_marker_header_name_is_the_one_the_applications_read() -> None:
    from_edge = re.search(r"header_up (X-TC-[A-Za-z]+) 1", CADDYFILE)
    assert from_edge is not None
    # `packages/tc-entra-auth/tc_entra_auth/edge.py` — EDGE_HEADER, in bytes and lower-case.
    source = (DEPLOY.parent / "packages/tc-entra-auth/tc_entra_auth/edge.py").read_text(encoding="utf-8")
    assert f'EDGE_HEADER = b"{from_edge.group(1).lower()}"' in source


def test_the_english_host_only_carries_traffic_to_agentic_english() -> None:
    """No compression (it would buffer the tutor's event stream) and no CORS: the app calls its own host only."""
    english = _site("ENGLISH_HOST")
    assert "reverse_proxy agentic-english-web:8081" in english
    assert "flush_interval -1" in english
    assert "encode" not in english
    assert "import cors" not in english
