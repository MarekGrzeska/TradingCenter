"""`CLAUDE.md` is a running cost, so it has a ceiling — and a floor.

The repository already gives the MCP tool surface a written character ceiling with a test,
because a tool schema is paid for in every turn of a conversation
(`market-data/tests/test_tools_surface.py`, specs/market-data-tools, "Powierzchnia narzędzi ma
zapisany sufit"). The guide is the same kind of cost, paid in every agent session, and it had
no ceiling at all: it reached 531 lines and 37 470 characters, roughly 8 900 tokens spent
before a single question was asked.

Two things keep this from being the character budget rule 8 of "How much test is enough"
forbids. It is on an **aggregate with headroom**, never on one sentence — a per-paragraph
budget is what turns every edit red. And it is paired with tests that read the *source of
truth* rather than the prose, so shrinking the file by deleting facts fails as loudly as
growing it: a guide kept under its ceiling by saying nothing would be cheap and useless.
"""

from __future__ import annotations

from pathlib import Path

import dev

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "CLAUDE.md"

# Characters of the whole file, which is what an agent reads before its first tool call. In
# characters rather than tokens so the test needs no tokenizer: the ratio measured on this
# material with `cl100k_base` is a steady 4,2, so the ceiling below is ~5 000 tokens.
# Raising it is a deliberate edit of this line, never a side effect of adding a paragraph —
# that is the whole point of writing it down.
GUIDE_CEILING_CHARS = 21_000

# Measured 17 831 characters on 20 August 2026, immediately after the prose diet: 37 470
# before it, so 52% went. The headroom is deliberate and is 15% — enough that a genuinely new
# trap can be written down without touching this file, not enough for the essays to come
# back. Written down so the next reader can tell headroom from a ceiling raised to fit.


def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_the_guide_stays_under_its_ceiling() -> None:
    measured = len(guide())
    assert measured <= GUIDE_CEILING_CHARS, (
        f"CLAUDE.md is {measured} characters, above the {GUIDE_CEILING_CHARS} ceiling. "
        "Move the detail to the module README or docs/ that owns it and leave a pointer, "
        "or raise the ceiling on purpose."
    )


def test_every_module_and_package_is_on_the_map() -> None:
    """The drift this file is really written against.

    The guide's whole job is to be the map, and the way a map goes wrong is not that a
    sentence ages — it is that something is built and never added. Read off the filesystem
    rather than a list kept here, because a hand-maintained list of what to check is the
    thing that goes stale (the same reasoning `scripts/pyproject.toml` gives pyright).
    """
    text = guide()
    directories = sorted(
        path
        for parent in ("modules", "packages")
        for path in (REPO_ROOT / parent).iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    assert directories, "found no modules or packages to check the map against"

    missing = [f"{d.parent.name}/{d.name}" for d in directories if d.name not in text]
    assert not missing, (
        f"CLAUDE.md's map does not name {', '.join(missing)}. A module or package the guide "
        "does not mention is one the next session does not know exists."
    )


def test_every_port_the_dev_runner_starts_is_named() -> None:
    """The ports are the one fact here whose absence costs an hour rather than a minute.

    A `.env` pointing at a port nobody serves reads as a tool server being down, and the
    guide names the three retired ones for exactly that reason. Checked against `dev.py`'s
    own service table — the source of truth both dev scripts already read — so a service
    that moves port cannot leave the guide behind.
    """
    text = guide()
    missing = [
        f"{service.name} ({service.port})"
        for service in dev.SERVICES
        if str(service.port) not in text
    ]
    assert not missing, (
        f"CLAUDE.md does not name the port for {', '.join(missing)}. dev.py's service table "
        "is the source of truth; the guide has to agree with it."
    )


def test_the_retired_ports_stay_written_down() -> None:
    """8040, 8050 and 8070 belonged to modules that no longer exist, and an `.env` copied
    before they went still points at them. The symptom is a tool server that reads as down,
    which is why the guide says whose they were rather than dropping them once the module
    was deleted."""
    text = guide()
    live = {str(service.port) for service in dev.SERVICES}
    retired = [port for port in ("8040", "8050", "8070") if port not in live]
    assert retired, "expected 8040, 8050 and 8070 to be served by nothing"

    missing = [port for port in retired if port not in text]
    assert not missing, (
        f"CLAUDE.md no longer names the retired port(s) {', '.join(missing)}. They are the "
        "cheapest trap in the repository to walk into and the cheapest to warn about."
    )
