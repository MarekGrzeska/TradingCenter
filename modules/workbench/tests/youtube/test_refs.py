"""What a person types to name a channel or a film, refused before it costs a request."""

from __future__ import annotations

import pytest

from youtube_data.providers.base import UnsupportedReference
from youtube_data.providers.refs import channel_ref, uploads_playlist, video_id

from .builders import CHANNEL_ID, VIDEO_ID


@pytest.mark.parametrize(
    ("given", "kind", "value"),
    [
        (CHANNEL_ID, "id", CHANNEL_ID),
        ("@somechannel", "handle", "@somechannel"),
        (f"https://www.youtube.com/channel/{CHANNEL_ID}", "id", CHANNEL_ID),
        (f"youtube.com/channel/{CHANNEL_ID}/videos", "id", CHANNEL_ID),
        ("https://www.youtube.com/@somechannel", "handle", "@somechannel"),
        ("  @somechannel ", "handle", "@somechannel"),
    ],
)
def test_a_channel_is_reduced_to_an_id_or_a_handle(given: str, kind: str, value: str) -> None:
    ref = channel_ref(given)

    assert (ref.kind, ref.value) == (kind, value)


@pytest.mark.parametrize(
    "given", ["https://www.youtube.com/c/oldname", "https://www.youtube.com/user/oldname", "hello", "@ab"]
)
def test_what_is_not_a_channel_is_refused_by_name(given: str) -> None:
    with pytest.raises(UnsupportedReference, match="channel"):
        channel_ref(given)


@pytest.mark.parametrize(
    "given",
    [
        VIDEO_ID,
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42s",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
    ],
)
def test_a_film_address_is_reduced_to_its_id(given: str) -> None:
    assert video_id(given) == VIDEO_ID


def test_what_is_not_a_film_is_refused() -> None:
    with pytest.raises(UnsupportedReference):
        video_id("https://example.com/watch?v=" + VIDEO_ID)


def test_the_uploads_playlist_is_the_channel_id_with_its_prefix_swapped() -> None:
    assert uploads_playlist(CHANNEL_ID) == "UU" + CHANNEL_ID[2:]
