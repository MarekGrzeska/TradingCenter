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
        delivered = await door.send("operator", None, "hello")
        refused = await door.send("nobody", None, "hello")

    assert delivered.ok is True
    assert app.state.telegram.sent[0][2] == "hello"
    assert (refused.ok, refused.transient) == (False, False)


async def test_the_package_sees_every_bot_a_recipient_is_reached_through_and_delivers_through_the_one_it_names(
    app, pool, settings, db
) -> None:
    from . import builders

    app.state.settings = settings
    app.state.pool = pool
    app.state.telegram = FakeBotApi()
    app.state.watcher = RecordingWatcher()
    first = await builders.bot(db, username="postsbot")
    second = await builders.bot(db, username="filmsbot")
    for bot in (first, second):
        made = await builders.destination(db, name="operator", bot_id=bot.id)
        await db.execute("UPDATE destinations SET chat_id = 5, state = 'ready' WHERE id = $1", made.id)

    async with telegram_client(app, "the alerts package") as client:
        door = Gateway(client)
        (operator,) = await door.recipients()
        guessing = await door.send("operator", None, "hello")
        named = await door.send("operator", "filmsbot", "hello")

    assert operator.bots == ("postsbot", "filmsbot")
    assert (guessing.ok, guessing.transient) == (False, False) and "postsbot" in (guessing.reason or "")
    assert named.ok is True
