"""The configurator's surface: a happy path, an error and a refusal per view.

What this file is really about is the second half of every write — the refusal. A rule that
cannot run is something the operator can still see on the screen they wrote it on, and an
hour later it is a strategy that silently records nothing.
"""

from __future__ import annotations

import pytest
from fakes import FakeArchive

from strategy.errors import ArchiveUnreachable

pytestmark = pytest.mark.db


@pytest.fixture
def api_with_archive(api, app):
    app.state.archive = FakeArchive()
    return api


def a_rule(*, period: float | str = 20, line: str = "ema") -> dict:
    """A rule the fake archive's catalogue accepts, with one piece swappable."""
    return {
        "resolution": "HOUR",
        "unsettled_reason": "the average has not settled",
        "no_setup_reason": "price is not above the average",
        "facts": [
            {"key": "ma", "indicator": "ema", "resolution": "HOUR", "params": {"period": period}}
        ],
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 2, "max": 200},
        ],
        "setups": [
            {
                "when": {
                    "node": "compare",
                    "op": ">",
                    "left": {"node": "bar", "field": "close"},
                    "right": {"node": "fact", "key": "ma", "line": line},
                },
                "direction": "long",
                "entry": {"node": "bar", "field": "close"},
                "stop": {"node": "fact", "key": "ma", "line": line},
                "target": {"node": "const", "value": 200.0},
                "reason": "price closed above the average",
            }
        ],
    }


async def write(api, strategy_id="above_the_average", **overrides):
    body = {
        "strategy_id": strategy_id,
        "name": "Above the average",
        "description": "a rule somebody clicked together",
        "definition": a_rule(),
        **overrides,
    }
    return await api.post("/definitions", json=body)


class TestWritingOne:
    async def test_a_rule_is_saved_as_its_first_revision(self, api_with_archive) -> None:
        response = await write(api_with_archive)

        assert response.status_code == 201
        body = response.json()
        assert (body["strategy_id"], body["version"]) == ("above_the_average", 1)

    async def test_an_id_a_coded_entry_already_carries_is_refused(self, api_with_archive) -> None:
        """One namespace, and reviewed code owns it: a row shadowing a coded entry would be
        a strategy whose rule cannot be found by reading the repository."""
        response = await write(api_with_archive, strategy_id="baseline_ma_cross")

        assert response.status_code == 422
        assert "baseline_ma_cross" in response.json()["detail"]

    async def test_a_rule_naming_an_indicator_the_archive_does_not_have_is_refused(
        self, api_with_archive
    ) -> None:
        rule = a_rule()
        rule["facts"][0]["indicator"] = "sorcery"

        response = await write(api_with_archive, definition=rule)

        assert response.status_code == 422
        assert "sorcery" in response.json()["detail"]

    async def test_a_rule_is_not_saved_when_the_archive_cannot_be_asked(
        self, api, app, pool
    ) -> None:
        """Refused rather than waved through: a definition nobody could check is worse than
        no definition, and the operator has exactly one move to make."""
        app.state.archive = FakeArchive(
            catalogue_raises=ArchiveUnreachable("the archive did not answer")
        )

        response = await write(api)

        assert response.status_code == 504
        assert "was not saved" in response.json()["detail"]
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM strategy_definitions") == 0

    async def test_a_second_definition_under_the_same_id_is_refused(
        self, api_with_archive
    ) -> None:
        await write(api_with_archive)

        response = await write(api_with_archive)

        assert response.status_code == 422
        assert "next revision" in response.json()["detail"]


class TestReadingThem:
    async def test_the_list_carries_the_newest_revision_of_each(self, api_with_archive) -> None:
        await write(api_with_archive)
        await api_with_archive.post(
            "/definitions/above_the_average/revisions", json={"definition": a_rule(period=50)}
        )

        response = await api_with_archive.get("/definitions")

        assert [(row["strategy_id"], row["latest_version"]) for row in response.json()] == [
            ("above_the_average", 2)
        ]

    async def test_a_definition_nobody_wrote_is_a_404(self, api_with_archive) -> None:
        response = await api_with_archive.get("/definitions/nothing_here")

        assert response.status_code == 404

    async def test_the_coded_entries_are_not_in_this_list(self, api_with_archive) -> None:
        """`/strategies` lists both kinds; this route is about what can be edited, and a
        coded entry cannot be."""
        response = await api_with_archive.get("/definitions")

        assert "baseline_ma_cross" not in {row["strategy_id"] for row in response.json()}


class TestRevisions:
    async def test_the_previous_revision_stays_as_it_was(self, api_with_archive) -> None:
        await write(api_with_archive)
        await api_with_archive.post(
            "/definitions/above_the_average/revisions", json={"definition": a_rule(period=50)}
        )

        first = await api_with_archive.get("/definitions/above_the_average/revisions/1")

        assert first.json()["definition"]["facts"][0]["params"]["period"] == 20

    async def test_a_revision_of_a_definition_nobody_wrote_is_a_404(
        self, api_with_archive
    ) -> None:
        response = await api_with_archive.post(
            "/definitions/nothing_here/revisions", json={"definition": a_rule()}
        )

        assert response.status_code == 404

    async def test_a_revision_reading_a_line_the_indicator_does_not_publish_is_refused(
        self, api_with_archive
    ) -> None:
        await write(api_with_archive)

        response = await api_with_archive.post(
            "/definitions/above_the_average/revisions",
            json={"definition": a_rule(line="signal")},
        )

        assert response.status_code == 422
        assert "signal" in response.json()["detail"]


class TestRenaming:
    async def test_a_new_title_does_not_mint_a_revision(self, api_with_archive) -> None:
        """A decision points at a revision, and provenance that shifted because somebody
        fixed a typo in a title is provenance nobody could trust."""
        await write(api_with_archive)

        renamed = await api_with_archive.patch(
            "/definitions/above_the_average", json={"name": "Above the mean"}
        )

        assert renamed.json()["name"] == "Above the mean"
        assert renamed.json()["latest_version"] == 1

    async def test_renaming_something_nobody_wrote_is_a_404(self, api_with_archive) -> None:
        response = await api_with_archive.patch(
            "/definitions/nothing_here", json={"name": "x"}
        )

        assert response.status_code == 404

    async def test_an_empty_title_is_refused(self, api_with_archive) -> None:
        await write(api_with_archive)

        response = await api_with_archive.patch(
            "/definitions/above_the_average", json={"name": ""}
        )

        assert response.status_code == 422
