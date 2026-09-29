"""Whether the process has this package at all is one setting, decided before anything else is read. Absent is a working
configuration; what must never exist is the half-state — mounted, and no database behind it."""

from __future__ import annotations

import pytest

from workbench.config import youtube_enabled


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """`Settings` reads `.env` from the working directory, and a developer's own file must not decide a test."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YOUTUBE_DATABASE_URL", raising=False)


def test_without_a_database_the_package_is_not_part_of_the_process() -> None:
    assert youtube_enabled() is False


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_line_left_blank_is_the_line_not_being_there(monkeypatch, blank: str) -> None:
    monkeypatch.setenv("YOUTUBE_DATABASE_URL", blank)

    assert youtube_enabled() is False


def test_with_a_database_it_is(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_DATABASE_URL", "postgresql://youtube:pw@127.0.0.1:55432/youtube")

    assert youtube_enabled() is True


def test_settings_for_an_absent_package_are_refused_by_name() -> None:
    """The one place `for_youtube` could be reached with nothing behind it is a caller that skipped the question — the
    alembic chain run by hand on a `.env` without the line. It says which line, rather than what pydantic makes of it."""
    from workbench.config import Settings

    with pytest.raises(ValueError, match="YOUTUBE_DATABASE_URL is not set"):
        Settings.model_construct(youtube_database_url=None).for_youtube()
