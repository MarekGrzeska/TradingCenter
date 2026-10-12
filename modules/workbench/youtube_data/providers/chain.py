"""Transcript providers in the order the operator listed them. The next one is asked when the one before did not let us
in — and, after "no captions", only a provider that *listens*: a film with no captions is the same answer from every
provider that reads captions, and asking a second one is paying twice for a fact. A provider that listens has not been
asked yet, so for it the film is ordinary work."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from .base import Blocked, NoTranscript, TranscriptProvider, TranscriptRequest, TranscriptResult


@dataclass(frozen=True, slots=True)
class Deferred:
    """Nobody who could answer was asked: the one provider that might is resting, or its day cannot pay for this film.
    Not a fact about the film, so not an attempt — and not a refusal, so the next film is still worth asking about."""

    reason: str


@dataclass(frozen=True, slots=True)
class ChainAnswer:
    """The answer for the film, and what the providers asked before it said on the way — a captions provider refused
    from the cloud must still reach `provider_state` when the one after it succeeded."""

    result: TranscriptResult | Deferred
    passed: tuple[Blocked | NoTranscript, ...] = ()


class TranscriptChain:
    name = "chain"

    def __init__(self, providers: Sequence[TranscriptProvider]) -> None:
        self._providers = tuple(providers)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self._providers)

    @property
    def providers(self) -> tuple[TranscriptProvider, ...]:
        return self._providers

    async def fetch(self, request: TranscriptRequest, *, only: Collection[str] | None = None) -> ChainAnswer:
        """`only` names the providers worth asking about this film — the loop leaves out the ones resting after a
        refusal and the ones whose day cannot pay for it; the chain does not know what a day is."""
        passed: list[Blocked | NoTranscript] = []
        missed: NoTranscript | None = None
        listener_refused: Blocked | None = None
        listener_left_out = False
        for provider in self._providers:
            if missed is not None and not provider.listens:
                continue
            if only is not None and provider.name not in only:
                listener_left_out = listener_left_out or provider.listens
                continue
            try:
                result = await provider.fetch(request)
            except Exception as err:  # noqa: BLE001 - a provider that raised is one that did not let us in
                result = Blocked(provider.name, f"{type(err).__name__}: {err}"[:200])
            if isinstance(result, Blocked):
                passed.append(result)
                if missed is not None:
                    listener_refused = result
                continue
            if isinstance(result, NoTranscript) and not provider.listens:
                passed.append(result)
                missed = result
                continue
            return ChainAnswer(result, tuple(passed))

        refused = listener_refused or next((item for item in reversed(passed) if isinstance(item, Blocked)), None)
        if missed is not None:
            # No captions. Whether that is the film's answer depends on whether somebody who listens had their say.
            if listener_refused is not None:
                return ChainAnswer(listener_refused, _without(passed, listener_refused))
            if listener_left_out:
                return ChainAnswer(Deferred("no captions; the provider that listens cannot be asked now"), tuple(passed))
            return ChainAnswer(missed, _without(passed, missed))
        if refused is not None:
            return ChainAnswer(refused, _without(passed, refused))
        return ChainAnswer(Deferred("no transcript provider can be asked about this film now"))


def _without(passed: list[Blocked | NoTranscript], answer: Blocked | NoTranscript) -> tuple[Blocked | NoTranscript, ...]:
    return tuple(item for item in passed if item is not answer)
