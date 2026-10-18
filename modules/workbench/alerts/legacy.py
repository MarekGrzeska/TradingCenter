"""What the operator had already set, as rules. Before this package, who was told about a film or a post was decided in three
places — an assignment of a purpose to a recipient in the door to Telegram, an alert rule on each followed channel and topic,
and a score threshold in `.env` — and this reads all three and says the same thing as rules.

Pure: it is given what the neighbours hold and returns the rules, so what a conversion will do is a thing a test can show
without a database. Reaching the neighbours is the assembly's (`LegacySource`)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .contract import EventSource, FilterTerm, RuleIn

YOUTUBE_FILM = "youtube.film.read"
SOCIAL_POST = "social.post.read"
# The purposes the two producers used to send under; a purpose is `<these>.<slug of the source>`.
YOUTUBE_PURPOSE = "youtube.film"
SOCIAL_PURPOSE = "social.post"

# What the rules need to stand on until the producers announce their own. Only the attributes the converted rules filter on:
# the producer's announcement replaces this whole, and a rule that used something not in it is flagged then.
PLACEHOLDER_TYPES: dict[str, tuple[str, dict]] = {
    YOUTUBE_FILM: (
        "A film the model read (announced by the conversion of the old alert rules, until the YouTube archive announces it)",
        {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "channel_slug": {"type": "string"},
                "topic": {"type": "string"},
                "impact_score": {"type": "integer"},
            },
        },
    ),
    SOCIAL_POST: (
        "A post the model read (announced by the conversion of the old alert rules, until the post archive announces it)",
        {
            "type": "object",
            "properties": {
                "author": {"type": "string"},
                "author_slug": {"type": "string"},
                "impact_score": {"type": "integer"},
            },
        },
    ),
}


@dataclass(frozen=True)
class WatchedChannel:
    title: str
    alert_rule: str  # always | threshold | never
    active: bool


@dataclass(frozen=True)
class WatchedTopic:
    phrase: str
    alert_rule: str
    active: bool


@dataclass(frozen=True)
class Legacy:
    """Everything the old way of deciding held. A producer that is not part of the process is `None` and yields no rules."""

    # purpose key (a purpose, a prefix of one, or `*`) -> the recipient's name
    assignments: Mapping[str, str] = field(default_factory=dict)
    channels: list[WatchedChannel] | None = None
    topics: list[WatchedTopic] = field(default_factory=list)
    youtube_min_score: int = 8
    # The post archive's threshold, or `None` when the post archive is not part of the process.
    social_min_score: int | None = None


class LegacySource(Protocol):
    """The neighbours, asked. `None` means they could not be asked and the conversion should try again at the next start; an
    empty `Legacy` means there was nothing to convert."""

    async def read(self) -> Legacy | None: ...


def slug(text: str) -> str:
    """A name as one segment of a purpose — the producers' own rule, written again here because this is the only place that
    still needs to speak the old language, and it is gone with the old language."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_")[:60]
    return cleaned or "unknown"


def recipient_of(purpose: str, assignments: Mapping[str, str]) -> str | None:
    """Who heard this purpose: the longest key that is the purpose or a prefix of it cut at a dot, then `*`."""
    parts = purpose.split(".")
    for end in range(len(parts), 0, -1):
        key = ".".join(parts[:end])
        if key in assignments:
            return assignments[key]
    return assignments.get("*")


def plan(old: Legacy) -> list[RuleIn]:
    return [*_youtube(old), *_social(old)]


def _youtube(old: Legacy) -> list[RuleIn]:
    if old.channels is None:
        return []
    rules: list[RuleIn] = []
    by_channel: dict[tuple[str, str], list[str]] = {}
    for channel in old.channels:
        if not channel.active or channel.alert_rule == "never":
            continue
        who = recipient_of(f"{YOUTUBE_PURPOSE}.{slug(channel.title)}", old.assignments)
        if who is not None:
            by_channel.setdefault((who, channel.alert_rule), []).append(channel.title)
    for (who, how), titles in sorted(by_channel.items()):
        rules.append(_films(who, how, "channel", sorted(titles), old.youtube_min_score, f"kanały ({len(titles)})"))

    by_topic: dict[tuple[str, str], list[str]] = {}
    who = recipient_of(YOUTUBE_PURPOSE, old.assignments)
    for topic in old.topics:
        if who is not None and topic.active and topic.alert_rule != "never":
            by_topic.setdefault((who, topic.alert_rule), []).append(topic.phrase)
    for (who, how), phrases in sorted(by_topic.items()):
        rules.append(_films(who, how, "topic", sorted(phrases), old.youtube_min_score, f"tematy ({len(phrases)})"))
    return rules


def _films(who: str, how: str, attribute: str, values: list[str], min_score: int, what: str) -> RuleIn:
    terms = [FilterTerm(attribute=attribute, op="in", value=values)]
    if how == "threshold":
        terms.append(FilterTerm(attribute="impact_score", op="gte", value=min_score))
    suffix = "wszystkie filmy" if how == "always" else f"od oceny {min_score}"
    return RuleIn(
        name=f"Filmy — {what}, {suffix}"[:80],
        source=EventSource(event_type=YOUTUBE_FILM, filter=terms),
        destination=who,
        mode="repeat",
    )


def _social(old: Legacy) -> list[RuleIn]:
    if old.social_min_score is None:
        return []
    floor = FilterTerm(attribute="impact_score", op="gte", value=old.social_min_score)
    rules: list[RuleIn] = []
    specific: dict[str, str] = {}
    prefix = f"{SOCIAL_PURPOSE}."
    for key, who in sorted(old.assignments.items()):
        if key.startswith(prefix) and "." not in key[len(prefix) :]:
            specific[key[len(prefix) :]] = who
    for author_slug, who in specific.items():
        rules.append(
            RuleIn(
                name=f"Posty — {author_slug}, od oceny {old.social_min_score}"[:80],
                source=EventSource(
                    event_type=SOCIAL_POST,
                    filter=[FilterTerm(attribute="author_slug", op="eq", value=author_slug), floor],
                ),
                destination=who,
                mode="repeat",
            )
        )
    # Who heard an author nobody named: what the prefixes and `*` say, once the authors with a key of their own are set aside.
    named = {f"{prefix}{author}" for author in specific}
    general = recipient_of(SOCIAL_PURPOSE, {key: who for key, who in old.assignments.items() if key not in named})
    if general is not None:
        others = [FilterTerm(attribute="author_slug", op="ne", value=author_slug) for author_slug in sorted(specific)]
        rules.append(
            RuleIn(
                name=f"Posty — pozostali autorzy, od oceny {old.social_min_score}"[:80],
                source=EventSource(event_type=SOCIAL_POST, filter=[floor, *others]),
                destination=general,
                mode="repeat",
            )
        )
    return rules
