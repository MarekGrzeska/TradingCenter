"""Transcript providers in the order the operator listed them. The next one is tried only when the one before did not let
us in: a film with no captions is the same answer from every provider, and asking a second one about it is paying twice
for a fact."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from .base import Blocked, TranscriptProvider, TranscriptResult


class TranscriptChain:
    name = "chain"

    def __init__(self, providers: Sequence[TranscriptProvider]) -> None:
        self._providers = tuple(providers)
        self._by_name = {provider.name: provider for provider in self._providers}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self._providers)

    @property
    def providers(self) -> tuple[TranscriptProvider, ...]:
        return self._providers

    async def fetch(
        self, video_id: str, languages: Sequence[str], *, only: Collection[str] | None = None
    ) -> TranscriptResult:
        """`only` names the providers still worth asking — the loop leaves out the ones whose day is spent, and the
        chain does not know what a day is."""
        refused: Blocked | None = None
        for provider in self._providers:
            if only is not None and provider.name not in only:
                continue
            result = await provider.fetch(video_id, languages)
            if isinstance(result, Blocked):
                refused = result
                continue
            return result
        return refused or Blocked(self.name, "no transcript provider is configured")

    async def poll(self, provider: str, job_id: str) -> TranscriptResult:
        """A job belongs to the provider that took it; asking another would be asking a stranger for someone's order."""
        known = self._by_name.get(provider)
        if known is None:
            return Blocked(provider, f"{provider} is no longer a configured transcript provider")
        return await known.poll(job_id)
