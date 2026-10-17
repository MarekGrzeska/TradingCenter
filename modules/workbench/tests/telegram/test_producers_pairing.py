"""One integration test that the real pairing works (CLAUDE.md, rule 5): a producer's own gateway client, over the door's
application as the host builds it, hears "nobody receives this" as a state and not as a refusal, and a message under
the same purpose arrives once the operator has assigned it. The matching rule and the refusals are tested where they live."""

from __future__ import annotations

import pytest

from social_data.alerts import Gateway, GatewayUnassigned
from telegram_gateway import store
from workbench.telegram_client import telegram_client

from .fakes import FakeBotApi, RecordingWatcher
from .test_sending import ready_destination

pytestmark = pytest.mark.db


async def test_a_producer_over_the_in_process_door_waits_until_the_purpose_is_assigned(
    app, pool, settings, db
) -> None:
    app.state.settings = settings
    app.state.pool = pool
    app.state.telegram = FakeBotApi()
    app.state.watcher = RecordingWatcher()
    destination = await ready_destination(db, "operator")
    assert destination is not None

    async with telegram_client(app, "the post archive") as client:
        door = Gateway(client)
        await door.describe("social.post", "A post the model scored high")

        with pytest.raises(GatewayUnassigned):
            await door.send(purpose="social.post.someone", text="hello")

        await store.assign(db, key="social", destination_id=destination.id)
        await door.send(purpose="social.post.someone", text="hello")

    assert {one.name for one in await store.list_purposes(db)} == {"social.post", "social.post.someone"}
    assert app.state.telegram.sent[0][2] == "hello"
