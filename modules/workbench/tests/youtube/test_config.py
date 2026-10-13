"""The refusals that keep a misconfigured package from starting, and the absence that is not one."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from youtube_data.config import Settings
from youtube_data.providers.build import build


def settings(**overrides) -> Settings:
    return Settings(database_url="postgresql://localhost:5432/youtube", _env_file=None, **overrides)


def test_a_source_that_was_asked_for_and_has_no_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="DATA_API_KEY"):
        settings(video_source="data_api")


@pytest.mark.parametrize(
    "overrides",
    [{"video_source": "vimeo"}, {"transcript_providers": "direct,whisper"}, {"transcript_providers": " , "}],
)
def test_a_provider_this_package_does_not_have_is_named_in_the_refusal(overrides) -> None:
    with pytest.raises(ValidationError):
        settings(**overrides)


def test_a_missing_model_key_is_a_supported_state_and_a_blank_one_is_a_missing_one() -> None:
    assert settings(analyser="openai").model_configured is False
    assert settings(analyser="openai", openai_api_key="   ").model_configured is False
    assert settings(analyser="openai", openai_api_key="sk-test").model_configured is True


def test_without_a_model_the_package_still_has_a_source_and_a_transcript_chain() -> None:
    import httpx

    real = settings(video_source="rss", transcript_providers="direct", analyser="openai")
    providers = build(real, httpx.AsyncClient())

    assert providers.analyser is None
    assert providers.source.name == "rss"
    assert providers.transcripts.names == ("direct",)


def test_a_faster_clock_is_the_simulated_sources_alone() -> None:
    """With a real source, a day that turns every hour would reset the ceilings on a quota that turns once a day."""
    import httpx

    from youtube_data.clock import SystemClock

    mixed = settings(video_source="rss", transcript_providers="direct", analyser="sim", sim_speed=24)

    assert isinstance(build(mixed, httpx.AsyncClient()).clock, SystemClock)
