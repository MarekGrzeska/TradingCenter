"""The rule that keeps Telegram's two surfaces from swapping roles.

`telegram-gateway-upstream-access` says a notification MUST go out as the bot even where an account
session is configured, and that the session MUST serve the creator-bot conversation and nothing
else. Both held by construction and by nothing else until this file: the miss is quiet and it leaves
this system — an alert sent from the operator's own account is indistinguishable from one they wrote
themselves, and every such send is charged against a private account's limits.

Read from the AST rather than by importing, so an import inside a function counts. That matters here:
`creator.py` imports telethon inside its methods precisely so a deployment with no session never
loads it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "telegram_gateway"

# The account session's one door. Everything about MTProto lives behind this module, and `bots.py`
# is the only caller because creating and deleting are the only things it is for.
CREATOR_MODULE = "creator"

# The path a notification travels, end to end: both surfaces, the send itself, and the client that
# puts it on the wire. None of these may know the account session exists.
SENDING_PATH = (
    "sending.py",
    "bot_api.py",
    "routers/messages.py",
    "tools/messages.py",
    "binding.py",
)

# MTProto, by the name it is imported under. The bot channel is plain HTTP and needs none of it.
MTPROTO_PACKAGES = {"telethon"}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _own_modules_imported(tree: ast.AST) -> set[str]:
    """Which modules of this package a file imports, however the import is spelled."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0 and node.module:
                names.add(node.module.split(".")[0])
            elif node.level > 0 and node.module is None:
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif node.module and node.module.split(".")[0] == "telegram_gateway":
                parts = node.module.split(".")
                if len(parts) > 1:
                    names.add(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "telegram_gateway" and len(parts) > 1:
                    names.add(parts[1])
    return names


def _top_level_packages_imported(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _sources() -> list[Path]:
    return sorted(path for path in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in path.parts)


@pytest.mark.parametrize("name", SENDING_PATH, ids=lambda n: n)
def test_the_sending_path_cannot_reach_the_account_session(name: str) -> None:
    path = PACKAGE_ROOT / name
    reached = _own_modules_imported(_tree(path))
    assert CREATOR_MODULE not in reached, (
        f"{name} imports {CREATOR_MODULE}. A notification goes out as the bot; the moment the "
        "sending path can reach the account session, an alert can arrive as the operator."
    )


@pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
def test_mtproto_lives_in_one_file(path: Path) -> None:
    """The session is a credential to a personal account. One importer is one place to read to know
    everything it is used for."""
    reached = _top_level_packages_imported(_tree(path)) & MTPROTO_PACKAGES
    if path.name == "creator.py":
        return
    assert not reached, f"{path.name} imports {', '.join(sorted(reached))}"


def test_the_account_session_has_one_importer_besides_the_route() -> None:
    """`bots.py` holds the two acts the session is for, and the route hands it the conversation.
    Anything else reaching for it is a use nobody asked this gateway to make."""
    importers = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _sources()
        if path.name != "creator.py" and CREATOR_MODULE in _own_modules_imported(_tree(path))
    }
    assert importers == {"bots.py", "routers/bots.py"}, importers


def test_the_creator_bot_is_a_constant_and_not_a_setting() -> None:
    """A configurable peer here is a way to send an account's credentials at somebody else's bot."""
    settings = (PACKAGE_ROOT / "config.py").read_text(encoding="utf-8")
    assert "BotFather" not in settings
    from telegram_gateway import creator

    assert creator.CREATOR_BOT == "BotFather"


def test_the_conversation_reaches_no_peer_but_the_creator_bot() -> None:
    """Every `conversation(...)` in this module opens against the one constant. A second peer would
    be the session doing something this gateway was never asked for."""
    tree = _tree(PACKAGE_ROOT / "creator.py")
    peers = [
        node.args[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "conversation"
        and node.args
    ]
    assert peers, "no conversation is opened at all — this test is watching the wrong call"
    assert all(isinstance(peer, ast.Name) and peer.id == "CREATOR_BOT" for peer in peers)


def test_nothing_creates_a_bot_on_its_own_initiative() -> None:
    """`telegram-gateway-bots`: the module MUST NOT create a bot at start-up, when it holds none, or
    when a send failed. Automating a personal account is what Telegram limits accounts for, so every
    conversation MUST follow an explicit request — which means the route, and only the route."""
    callers = set()
    for path in _sources():
        for node in ast.walk(_tree(path)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("create", "destroy")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "bots"
            ):
                callers.add(path.relative_to(PACKAGE_ROOT).as_posix())
    assert callers == {"routers/bots.py"}, callers
