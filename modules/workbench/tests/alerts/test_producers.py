"""The two ends of the hand-over, held against each other. Each package tests its own end in its own suite (what it publishes,
when it writes its marker); what no single package can show is that they agree — that what a producer publishes fits the type
it announced, and that the alerts package takes it."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from social_data import alerts as social
from social_data.models import Post

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def test_what_a_post_publishes_fits_the_schema_it_announced() -> None:
    from jsonschema import Draft202012Validator

    post = Post(
        id=1,
        source="truth_social",
        external_id="1",
        author="Donald J. Trump (@realDonaldTrump)",
        content="TARIFFS.",
        published_at=NOW,
        fetched_at=NOW,
        topics=("tariffs",),
        impact_score=9,
    )

    attributes = social.attributes_of(post)

    assert list(Draft202012Validator(social.EVENT_SCHEMA).iter_errors(attributes)) == []
    assert set(attributes) <= set(social.EVENT_SCHEMA["properties"])


@pytest.mark.db
async def test_a_producer_announces_and_publishes_through_the_alerts_package_itself(api, inside, app, db) -> None:
    """The real routes, over the real database, through the clients the packages are given."""
    from tc_runtime.caller_access import in_process

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=in_process(app, "the post archive")), base_url="http://alerts")
    publisher = social.Publisher(client)
    await publisher.announce()
    rule = {
        "name": "posts",
        "source": {"kind": "event", "event_type": social.EVENT_TYPE, "filter": [{"attribute": "impact_score", "op": "gte", "value": 8}]},
        "destination": "phone",
    }
    assert (await api.post("/rules", json=rule)).status_code == 201

    await publisher.publish(
        source_key="1",
        attributes={"author": "x", "author_slug": "x", "impact_score": 9, "topics": [], "url": "", "translated": True},
        text="a post",
    )
    await publisher.publish(
        source_key="2",
        attributes={"author": "x", "author_slug": "x", "impact_score": 3, "topics": [], "url": "", "translated": True},
        text="a quiet post",
    )

    assert [row["text"] for row in await db.fetch("SELECT text FROM fires")] == ["a post"]
