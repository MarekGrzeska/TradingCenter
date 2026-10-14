"""move-from-azure-to-vps, `vps-deployment` — the dumps: made, kept for a while, offered read-only, and missed out loud.
The database is a stand-in that behaves like `pg_dump`'s host; the real one is exercised by the restore rehearsal."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import time

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent.parent / "deploy" / "scripts"
SH = shutil.which("sh")
DBS = "agent teams"

pytestmark = pytest.mark.skipif(SH is None, reason="needs a POSIX shell")


@pytest.fixture
def box(tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    backups = tmp_path / "backups"
    backups.mkdir()
    alerts = tmp_path / "alerts.log"
    # Records what it was told, so a test reads the alert instead of sending one.
    alert = tmp_path / "alert"
    alert.write_text(f'#!/bin/sh\necho "$1" >> "{alerts.as_posix()}"\n', encoding="utf-8", newline="\n")
    alert.chmod(0o755)
    # `pg_dump -U postgres -Fc <db>` stand-in: a body that names the database, or a failure for one called "broken".
    pg = tmp_path / "pg"
    pg.write_text(
        '#!/bin/sh\nfor last; do :; done\n[ "$last" = broken ] && exit 1\nprintf "DUMP-OF-%s" "$last"\n',
        encoding="utf-8",
        newline="\n",
    )
    pg.chmod(0o755)
    return {"backups": backups, "alerts": alerts, "alert": alert, "pg": pg, "ack": tmp_path / "ack" / "last-ack"}


def run(script: str, box: dict[str, pathlib.Path], **env: str) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    merged = {
        **os.environ,
        "BACKUP_DIR": str(box["backups"]),
        "ACK_FILE": str(box["ack"]),
        "ALERT": box["alert"].as_posix(),
        "PG_EXEC": box["pg"].as_posix(),
        "DATABASES": DBS,
        **env,
    }
    # `PG_EXEC` runs as "$PG_EXEC pg_dump -U postgres -Fc <db>" — the stand-in only needs the last word.
    return subprocess.run([SH, str(SCRIPTS / script)], capture_output=True, text=True, env=merged, check=False, timeout=30)


def age(path: pathlib.Path, days: float) -> None:
    moment = time.time() - days * 86400
    os.utime(path, (moment, moment))


def alerts(box: dict[str, pathlib.Path]) -> str:
    return box["alerts"].read_text(encoding="utf-8") if box["alerts"].exists() else ""


def dumps(box: dict[str, pathlib.Path]) -> list[str]:
    return sorted(p.name for p in box["backups"].glob("*.dump"))


def test_every_database_gets_a_dump_with_its_own_content(box) -> None:
    result = run("backup.sh", box)
    assert result.returncode == 0, result.stderr
    names = dumps(box)
    assert [n.split("-")[0] for n in names] == ["agent", "teams"]
    assert (box["backups"] / names[0]).read_text(encoding="utf-8") == "DUMP-OF-agent"
    assert alerts(box) == ""


def test_no_half_written_dump_is_left_behind_or_listed(box) -> None:
    run("backup.sh", box, DATABASES="agent broken")
    assert [p.name for p in box["backups"].iterdir() if p.name.startswith(".")] == []
    assert all(n.startswith("agent-") for n in dumps(box))


def test_a_failing_database_is_named_and_does_not_stop_the_others(box) -> None:
    result = run("backup.sh", box, DATABASES="broken agent")
    assert result.returncode == 1
    assert any(n.startswith("agent-") for n in dumps(box))
    assert alerts(box).strip() == "backup failed for: broken"


def test_an_empty_dump_is_a_failure_not_a_backup(box) -> None:
    box["pg"].write_text('#!/bin/sh\nexit 0\n', encoding="utf-8", newline="\n")
    result = run("backup.sh", box)
    assert result.returncode == 1
    assert dumps(box) == []


def test_old_dumps_go_and_the_newest_of_a_database_never_does(box) -> None:
    # A database whose dump fails tonight (and every night): its history ages, and the last good one must outlast the rest.
    for stamp, days in (("20200101T000000Z", 40), ("20200201T000000Z", 30)):
        old = box["backups"] / f"broken-{stamp}.dump"
        old.write_text("old", encoding="utf-8")
        age(old, days)
    run("backup.sh", box, DATABASES="broken")
    assert dumps(box) == ["broken-20200201T000000Z.dump"]


def test_dumps_within_the_retention_window_are_kept(box) -> None:
    recent = box["backups"] / "agent-20200101T000000Z.dump"
    recent.write_text("last week", encoding="utf-8")
    age(recent, 5)
    run("backup.sh", box)
    assert recent.name in dumps(box)


def serve(box, command: str, **env: str) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    merged = {**os.environ, "BACKUP_DIR": str(box["backups"]), "ACK_FILE": str(box["ack"]), "SSH_ORIGINAL_COMMAND": command, **env}
    return subprocess.run([SH, str(SCRIPTS / "backup-serve.sh")], capture_output=True, text=True, env=merged, check=False, timeout=30)


def test_list_names_each_dump_with_its_size(box) -> None:
    (box["backups"] / "agent-20261013T020000Z.dump").write_text("12345", encoding="utf-8")
    (box["backups"] / "notes.txt").write_text("not a dump", encoding="utf-8")
    assert serve(box, "list").stdout.split("\n")[:-1] == ["agent-20261013T020000Z.dump 5"]


def test_get_returns_the_dump_byte_for_byte(box) -> None:
    payload = bytes(range(256))
    (box["backups"] / "agent-20261013T020000Z.dump").write_bytes(payload)
    assert SH is not None
    env = {**os.environ, "BACKUP_DIR": str(box["backups"]), "SSH_ORIGINAL_COMMAND": "get agent-20261013T020000Z.dump"}
    result = subprocess.run([SH, str(SCRIPTS / "backup-serve.sh")], capture_output=True, env=env, check=False, timeout=30)
    assert result.stdout == payload


@pytest.mark.parametrize(
    "command",
    ["", "reboot", "get", "get ../../etc/passwd", "get /etc/passwd", "get agent-1.dump;id", "get .hidden.dump", "get notes.txt", "put x", "list; id"],
)
def test_the_window_refuses_everything_but_its_three_verbs(box, command: str) -> None:
    (box["backups"] / "notes.txt").write_text("secret", encoding="utf-8")
    result = serve(box, command)
    assert result.returncode != 0 or command.startswith("list")
    assert "secret" not in result.stdout


def test_ack_leaves_a_mark_the_morning_check_can_age(box) -> None:
    assert not box["ack"].exists()
    assert serve(box, "ack").returncode == 0
    assert box["ack"].exists()


def test_the_morning_check_is_silent_when_all_is_well(box) -> None:
    run("backup.sh", box)
    serve(box, "ack")
    assert run("backup-check.sh", box).returncode == 0
    assert alerts(box) == ""


def test_a_database_without_a_recent_dump_is_named(box) -> None:
    run("backup.sh", box, DATABASES="agent")
    serve(box, "ack")
    run("backup-check.sh", box)
    assert alerts(box).strip() == "no dump from the last day for: teams"


def test_dumps_nobody_collected_for_three_days_are_an_alert(box) -> None:
    run("backup.sh", box)
    # The server has been holding a dump for four days with no collection, though it keeps dumping.
    held = box["backups"] / "agent-20200101T000000Z.dump"
    held.write_text("held", encoding="utf-8")
    age(held, 4)
    run("backup-check.sh", box)
    assert "collected no backups for 3 days" in alerts(box)


def test_a_collection_three_days_ago_is_an_alert_and_yesterdays_is_not(box) -> None:
    run("backup.sh", box)
    serve(box, "ack")
    run("backup-check.sh", box)
    assert alerts(box) == ""
    age(box["ack"], 4)
    run("backup-check.sh", box)
    assert "collected no backups for 3 days" in alerts(box)


def test_a_new_server_that_has_not_been_collected_from_yet_is_not_an_emergency(box) -> None:
    run("backup.sh", box)
    run("backup-check.sh", box)
    assert alerts(box) == ""
