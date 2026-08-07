from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from capital_gateway.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that hit the real capital.com demo API (needs credentials)",
    )
    parser.addoption(
        "--run-live-trading",
        action="store_true",
        default=False,
        help="run tests that open, amend and close real positions on the demo account",
    )


# Its own flag rather than a stronger --run-live, because the two differ in kind and not
# in degree: everything under `live` reads, and everything under `live_trading` writes to
# an account. A read that runs by accident costs a request; a trade that runs by accident
# leaves a position open on an account somebody is looking at.
_GATES = (("live", "--run-live"), ("live_trading", "--run-live-trading"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for marker, flag in _GATES:
        if config.getoption(flag):
            continue
        skip = pytest.mark.skip(reason=f"needs {flag} and capital.com demo credentials")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's real .env out of the tests.

    ``Settings`` reads the environment and the .env file, so without this a machine
    holding credentials and a machine without them run different tests.
    """
    for name in (
        "CAPITAL_API_KEY",
        "CAPITAL_IDENTIFIER",
        "CAPITAL_PASSWORD",
        "CAPITAL_BASE_URL",
        "CAPITAL_STREAM_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(_no_ambient_credentials: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Real credentials, for the live suites only.

    Depends on ``_no_ambient_credentials`` explicitly so the order is stated rather than
    inherited: that fixture strips the environment for the whole suite, and this one puts
    back exactly what a live test needs.
    """
    for name in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"):
        value = os.environ.get(name)
        if value:
            monkeypatch.setenv(name, value)
    return Settings()  # type: ignore[call-arg]


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
