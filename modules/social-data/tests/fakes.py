"""Stand-ins for what this module reaches outward to: a source, and a model."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from social_data.models import RawPost
from social_data.providers import SourceUnreachable


class FakeSource:
    """A source that answers from a script and records what it was asked for."""

    def __init__(
        self,
        posts: Sequence[RawPost] = (),
        *,
        name: str = "truth_social",
        fails_with: str | None = None,
        by_day: dict[date, Sequence[RawPost]] | None = None,
    ) -> None:
        self._posts = list(posts)
        self._name = name
        self._fails_with = fails_with
        self._by_day = by_day
        self.asked: list[date] = []

    @property
    def name(self) -> str:
        return self._name

    async def fetch(self, day: date) -> list[RawPost]:
        self.asked.append(day)
        if self._fails_with is not None:
            raise SourceUnreachable(self._fails_with)
        if self._by_day is not None:
            return list(self._by_day.get(day, ()))
        return list(self._posts)


class FakeModel:
    """The model, answering from a script. Counts calls, because the ceiling on how many posts one
    pass may enrich is a rule with a cost behind it."""

    def __init__(
        self,
        *,
        translation: str = "CŁA NADCHODZĄ.",
        topics: Sequence[str] = ("tariffs", "china"),
        score: int = 8,
        raises: Exception | None = None,
        raises_once: Exception | None = None,
    ) -> None:
        self.translation = translation
        self.topics = tuple(topics)
        self.score = score
        self._raises = raises
        self._raises_once = raises_once
        self.translations = 0
        self.analyses = 0

    def _maybe_raise(self) -> None:
        if self._raises_once is not None:
            err, self._raises_once = self._raises_once, None
            raise err
        if self._raises is not None:
            raise self._raises

    async def translate(self, text: str):
        from social_data.enrichment import Translation

        self.translations += 1
        self._maybe_raise()
        return Translation(
            text=self.translation, model="fake-translator", input_tokens=10, output_tokens=4
        )

    async def analyse(self, text: str):
        from social_data.enrichment import Analysis

        self.analyses += 1
        self._maybe_raise()
        return Analysis(
            topics=self.topics,
            score=self.score,
            model="fake-analyst",
            input_tokens=12,
            output_tokens=6,
        )
