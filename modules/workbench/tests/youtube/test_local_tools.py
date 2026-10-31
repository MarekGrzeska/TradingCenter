"""The tools as the conversation and the teams reach them: as functions in this process, with the package's own refusals."""

from __future__ import annotations

import json

import pytest

from workbench.local_tools import ConversationLocalTools, TeamsLocalTools

from .harness import GOLD, Rig

pytestmark = pytest.mark.db


@pytest.fixture
async def server(app, pool):
    rig = Rig(pool)
    app.state.pool = rig.pool
    app.state.settings = rig.settings
    app.state.providers = rig.providers
    app.state.alerts = None
    return app.state.local_mcp_server


async def test_both_registries_see_the_same_eight_tools_and_know_which_of_them_write(server) -> None:
    conversation = await ConversationLocalTools("youtube-data", server).list_tools()
    teams = await TeamsLocalTools("youtube-data", server).list_tools()

    assert {t.name for t in conversation} == {t.name for t in teams}
    assert len(conversation) == 8
    writers = {t.name for t in conversation if t.read_only is False}
    assert writers == {"follow_channel", "add_topic", "analyse_video"}
    assert ConversationLocalTools("youtube-data", server).moves_the_account("follow_channel") is False


async def test_a_call_through_either_registry_reaches_the_package_and_a_refusal_keeps_its_words(server) -> None:
    conversation = ConversationLocalTools("youtube-data", server)

    followed = await conversation.call("follow_channel", {"reference": "@simzloto"})
    refused = await TeamsLocalTools("youtube-data", server).call("read_video", {"video_id": "nothing"})

    # A tool that may answer with a refusal or a result publishes a union, which arrives under `result`.
    assert followed.kind.value == "ok" and json.loads(followed.text)["result"]["channel"]["channel_id"] == GOLD
    assert refused.kind.value == "ok", "a refusal the package writes is an answer, not a failed call"
    assert "no film" in json.loads(refused.text)["result"]["refused"]
