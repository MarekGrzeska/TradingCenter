"""The e2e stack's promise that it cannot spend: what reaches its workbench, and what the committed settings point at."""

from __future__ import annotations

from e2e import E2E, child_environment, read_env_file

SETTINGS = read_env_file((E2E / "workbench.env").read_text(encoding="utf-8"))
NOWHERE = "127.0.0.1:9"


def test_a_key_in_the_developers_shell_never_reaches_the_workbench() -> None:
    parent = {"PATH": "/bin", "OPENAI_API_KEY": "sk-real", "AGENT_OPENAI_API_KEY": "sk-real", "UV_CACHE_DIR": "/c"}

    environment = child_environment(parent, {"AGENT_OPENAI_API_KEY": "sk-e2e-does-not-pay"})

    assert environment == {"PATH": "/bin", "UV_CACHE_DIR": "/c", "AGENT_OPENAI_API_KEY": "sk-e2e-does-not-pay"}


def test_a_json_value_is_read_whole() -> None:
    assert read_env_file('# note\nMODELS=[{"a":"b=c"}]\n') == {"MODELS": '[{"a":"b=c"}]'}


def test_every_model_key_is_a_dummy_and_every_paid_address_leads_nowhere() -> None:
    keys = {name: value for name, value in SETTINGS.items() if name.endswith("OPENAI_API_KEY")}
    assert keys and all(value == "" or value.startswith("sk-e2e-") for value in keys.values())
    assert NOWHERE in SETTINGS["OPENAI_BASE_URL"] and NOWHERE in SETTINGS["GATEWAY_BASE_URL"]
    assert SETTINGS["TRADING_MCP_URL"] == ""


def test_every_database_is_the_e2e_container() -> None:
    urls = [value for name, value in SETTINGS.items() if name.endswith("_DATABASE_URL") and value]
    assert urls and all("@127.0.0.1:55442/" in url for url in urls)
