"""One integration test that the real pairing works (CLAUDE.md, rule 5): the alerts package's own client, over the door's
application as the host builds it, lists who can be written to and delivers a message by name — and hears a refusal that
would come again as a final answer. The routing rules and the refusals are tested where they live."""

from __future__ import annotations

import pytest

from alerts.gateway import Gateway
from workbench.telegram_client import telegram_client

from .fakes import FakeBotApi, RecordingWatcher
from .test_sending import ready_destination

pytestmark = pytest.mark.db


async def test_the_alerts_package_over_the_in_process_door_lists_recipients_and_delivers_by_name(
    app, pool, settings, db
) -> None:
    app.state.settings = settings
    app.state.pool = pool
    app.state.telegram = FakeBotApi()
    app.state.watcher = RecordingWatcher()
    destination = await ready_destination(db, "operator")
    assert destination is not None

    async with telegram_client(app, "the alerts package") as client:
        door = Gateway(client)

        assert [one.name for one in await door.recipients()] == ["operator"]
        delivered = await door.send("operator", "hello")
        refused = await door.send("nobody", "hello")

    assert delivered.ok is True
    assert app.state.telegram.sent[0][2] == "hello"
    assert (refused.ok, refused.transient) == (False, False)
