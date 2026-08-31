"""The guide is paid for in every session, so it has a ceiling — and tests that read the
source of truth, so shrinking it by deleting facts fails as loudly as growing it."""

from __future__ import annotations

import subprocess
from pathlib import Path

import dev

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "CLAUDE.md"

# Characters rather than tokens so the test needs no tokenizer: the measured ratio here is 4,2,
# so this is ~5 500 tokens. Raised from 21 000 on 26 August 2026 to fit the comment rule, and from
# 22 000 on 31 August 2026 for the eighth module: a door out of the system that three callers reach
# two different ways does not fit in a table row.
GUIDE_CEILING_CHARS = 23_000

# 22 438 characters on 31 August 2026; the headroom is deliberate, and is enough for a new trap
# but not for the essays to come back.


def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_the_guide_stays_under_its_ceiling() -> None:
    measured = len(guide())
    assert measured <= GUIDE_CEILING_CHARS, (
        f"CLAUDE.md is {measured} characters, above the {GUIDE_CEILING_CHARS} ceiling. "
        "Move the detail to the module README or docs/ that owns it and leave a pointer, "
        "or raise the ceiling on purpose."
    )


def tracked_directories() -> list[str]:
    """Git, not the filesystem: a working copy keeps directories `git rm` already removed, and
    four deleted modules passed this guard on their leftover names."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "modules", "packages"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({"/".join(path.split("/")[:2]) for path in out.split("\0") if path})


def test_every_module_and_package_is_on_the_map() -> None:
    """Read off the repository, because a hand-kept list is what goes stale. Matched as the full
    `modules/<name>` path, so a name occurring in a settings example cannot satisfy it."""
    text = guide()
    directories = tracked_directories()
    assert directories, "found no modules or packages to check the map against"

    missing = [d for d in directories if d not in text]
    assert not missing, (
        f"CLAUDE.md's map does not name {', '.join(missing)}. A module or package the guide "
        "does not mention is one the next session does not know exists."
    )


def test_every_port_the_dev_runner_starts_is_named() -> None:
    """Checked against `dev.py`'s service table, the source of truth both dev scripts read, so a
    service that moves port cannot leave the guide behind."""
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
    """An `.env` copied before a module went still points at its port, and the symptom is a tool
    server that reads as down."""
    text = guide()
    live = {str(service.port) for service in dev.SERVICES}
    retired = [port for port in ("8040", "8050", "8070") if port not in live]
    assert retired, "expected 8040, 8050 and 8070 to be served by nothing"

    missing = [port for port in retired if port not in text]
    assert not missing, (
        f"CLAUDE.md no longer names the retired port(s) {', '.join(missing)}. They are the "
        "cheapest trap in the repository to walk into and the cheapest to warn about."
    )
