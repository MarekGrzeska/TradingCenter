"""move-from-azure-to-vps, `vps-deployment`: the script behind the deploy key. It is the whole of what that key can do, so
what it refuses is checked by running it — against a temporary application directory and no Docker."""

from __future__ import annotations

import io
import os
import pathlib
import shutil
import subprocess
import tarfile

import pytest

DEPLOY = pathlib.Path(__file__).resolve().parent.parent.parent / "deploy"
SCRIPT = DEPLOY / "scripts" / "deploy.sh"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="needs a POSIX shell")


@pytest.fixture
def app_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "env.required").write_text("# comment\n\nFIRST\nSECOND\n", encoding="utf-8")
    (tmp_path / "www").mkdir()
    (tmp_path / "postgres").mkdir()
    return tmp_path


def run(app_dir: pathlib.Path, command: str, stdin: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    assert SH is not None
    env = {**os.environ, "APP_DIR": str(app_dir), "SSH_ORIGINAL_COMMAND": command}
    return subprocess.run([SH, str(SCRIPT)], input=stdin, capture_output=True, env=env, timeout=30, check=False)


def tar_of(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_a_complete_environment_is_written(app_dir: pathlib.Path) -> None:
    result = run(app_dir, "env", b"FIRST=a\nSECOND=b\nEXTRA=c\n")
    assert result.returncode == 0, result.stderr
    assert (app_dir / ".env").read_text(encoding="utf-8") == "FIRST=a\nSECOND=b\nEXTRA=c\n"


@pytest.mark.skipif(os.name == "nt", reason="file modes are not a Windows notion")
def test_the_environment_is_readable_by_its_owner_alone(app_dir: pathlib.Path) -> None:
    run(app_dir, "env", b"FIRST=a\nSECOND=b\n")
    assert (app_dir / ".env").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("body", [b"FIRST=a\n", b"FIRST=a\nSECOND=\n", b"FIRST=a\n# SECOND=b\n"])
def test_an_environment_missing_a_name_is_refused_and_changes_nothing(app_dir, body) -> None:
    (app_dir / ".env").write_text("FIRST=old\nSECOND=old\n", encoding="utf-8")
    result = run(app_dir, "env", body)
    assert result.returncode != 0
    assert b"SECOND" in result.stderr
    assert (app_dir / ".env").read_text(encoding="utf-8") == "FIRST=old\nSECOND=old\n"


def test_a_refusal_never_prints_a_value(app_dir: pathlib.Path) -> None:
    result = run(app_dir, "env", b"FIRST=hunter2-the-secret\n")
    assert b"hunter2" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "command",
    ["", "reboot", "release", "release abc;touch /tmp/x", "release $(id)", "release ../../etc", "www /etc", "env; id"],
)
def test_anything_but_the_verbs_is_refused(app_dir: pathlib.Path, command: str) -> None:
    assert run(app_dir, command).returncode != 0


def test_a_front_end_is_swapped_in_whole(app_dir: pathlib.Path) -> None:
    (app_dir / "www" / "terminal").mkdir()
    (app_dir / "www" / "terminal" / "stale.js").write_text("old", encoding="utf-8")
    result = run(app_dir, "www terminal", tar_of({"index.html": "<h1>new</h1>", "assets/app.js": "x"}))
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (app_dir / "www" / "terminal").iterdir()) == ["assets", "index.html"]


def test_a_front_end_without_a_page_leaves_the_old_one(app_dir: pathlib.Path) -> None:
    (app_dir / "www" / "pocket").mkdir()
    (app_dir / "www" / "pocket" / "index.html").write_text("old", encoding="utf-8")
    result = run(app_dir, "www pocket", tar_of({"app.js": "x"}))
    assert result.returncode != 0
    assert (app_dir / "www" / "pocket" / "index.html").read_text(encoding="utf-8") == "old"


def test_sync_refuses_an_archive_that_lacks_a_file(app_dir: pathlib.Path) -> None:
    result = run(app_dir, "sync", tar_of({"docker-compose.yml": "x"}))
    assert result.returncode != 0
    assert not (app_dir / "docker-compose.yml").exists()
