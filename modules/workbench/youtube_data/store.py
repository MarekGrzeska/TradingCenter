"""Every statement this package runs against its own database. Plain asyncpg, no ORM: the tables are handwritten SQL and so
are the queries, so a read is the statement it will actually run.

Two things about the shape of the writes. A film seen again writes **nothing** unless it has something new to say — a
channel's fifteen latest uploads are re-listed every pass, and an upsert that touched each of them would be four hundred
dead rows a day for no change. And the queue is read through the partial index on `(state, next_attempt_at)`, which holds
only the states that still have work in them."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from tc_runtime.db import Conn

from .analysis import Reading
from .models import (
    GAVE_UP,
    NO_TRANSCRIPT,
    NOTIFIED,
    QUIET,
    Channel,
    Topic,
    Video,
)
from .providers.base import ChannelInfo, Transcript, VideoRef

_CHANNEL_COLUMNS = """
    channel_id, title, handle, uploads_playlist_id, language, profile, alert_rule, active,
    added_by, added_at, last_discovery_at
"""
_TOPIC_COLUMNS = """
    id, phrase, language, interval_minutes, max_videos_per_run, profile, alert_rule, active,
    added_by, added_at, last_run_at
"""
_VIDEO_COLUMNS = """
    video_id, channel_id, channel_title, title, published_at, duration_seconds, live_status, origins,
    profile, alert_rule, state, skip_reason, attempts, next_attempt_at, reading_failures,
    job_provider, job_id, simulated, discovered_at, notified_at
"""


def _channel(row) -> Channel:
    return Channel(**{name: row[name] for name in Channel.__dataclass_fields__})


def _topic(row) -> Topic:
    return Topic(**{name: row[name] for name in Topic.__dataclass_fields__})


def _video(row) -> Video:
    values = {name: row[name] for name in Video.__dataclass_fields__ if name != "origins"}
    return Video(origins=tuple(row["origins"]), **values)


# --- the watch list -------------------------------------------------------------------------------------------------


async def count_channels(conn: Conn) -> int:
    return int(await conn.fetchval("SELECT count(*) FROM channels") or 0)


async def get_channel(conn: Conn, channel_id: str) -> Channel | None:
    row = await conn.fetchrow(f"SELECT {_CHANNEL_COLUMNS} FROM channels WHERE channel_id = $1", channel_id)
    return None if row is None else _channel(row)


async def list_channels(conn: Conn, *, active_only: bool = False) -> list[Channel]:
    rows = await conn.fetch(
        f"SELECT {_CHANNEL_COLUMNS} FROM channels WHERE active OR NOT $1 "
        "ORDER BY last_discovery_at NULLS FIRST, added_at",
        active_only,
    )
    return [_channel(row) for row in rows]


async def add_channel(
    conn: Conn, info: ChannelInfo, *, language: str, profile: str, alert_rule: str, added_by: str
) -> Channel:
    """The channel, inserted — or the one that was already there, untouched: following it again by another spelling of
    its address is not a reason to change what the operator set."""
    await conn.execute(
        """
        INSERT INTO channels (channel_id, title, handle, uploads_playlist_id, language, profile, alert_rule, added_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (channel_id) DO NOTHING
        """,
        info.channel_id,
        info.title,
        info.handle,
        info.uploads_playlist_id,
        language,
        profile,
        alert_rule,
        added_by,
    )
    channel = await get_channel(conn, info.channel_id)
    assert channel is not None
    return channel


async def update_channel(
    conn: Conn,
    channel_id: str,
    *,
    alert_rule: str | None = None,
    profile: str | None = None,
    active: bool | None = None,
) -> Channel | None:
    await conn.execute(
        """
        UPDATE channels SET
            alert_rule = COALESCE($2, alert_rule),
            profile = COALESCE($3, profile),
            active = COALESCE($4, active)
        WHERE channel_id = $1
        """,
        channel_id,
        alert_rule,
        profile,
        active,
    )
    return await get_channel(conn, channel_id)


async def remove_channel(conn: Conn, channel_id: str) -> bool:
    """Only the reason we looked. Nothing references a channel, so its films and readings stay."""
    return (await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)) == "DELETE 1"


async def record_discovery(conn: Conn, channel_id: str, *, at: datetime) -> None:
    await conn.execute("UPDATE channels SET last_discovery_at = $2 WHERE channel_id = $1", channel_id, at)


async def count_topics(conn: Conn) -> int:
    return int(await conn.fetchval("SELECT count(*) FROM topics") or 0)


async def get_topic(conn: Conn, topic_id: int) -> Topic | None:
    row = await conn.fetchrow(f"SELECT {_TOPIC_COLUMNS} FROM topics WHERE id = $1", topic_id)
    return None if row is None else _topic(row)


async def list_topics(conn: Conn, *, active_only: bool = False) -> list[Topic]:
    rows = await conn.fetch(
        f"SELECT {_TOPIC_COLUMNS} FROM topics WHERE active OR NOT $1 ORDER BY last_run_at NULLS FIRST, id",
        active_only,
    )
    return [_topic(row) for row in rows]


async def add_topic(
    conn: Conn,
    *,
    phrase: str,
    language: str,
    interval_minutes: int,
    max_videos_per_run: int,
    profile: str,
    alert_rule: str,
    added_by: str,
) -> Topic:
    """The topic, inserted — or the one that was already there under another spelling of the case, untouched."""
    await conn.execute(
        """
        INSERT INTO topics (phrase, language, interval_minutes, max_videos_per_run, profile, alert_rule, added_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (lower(phrase), language) DO NOTHING
        """,
        phrase,
        language,
        interval_minutes,
        max_videos_per_run,
        profile,
        alert_rule,
        added_by,
    )
    row = await conn.fetchrow(
        f"SELECT {_TOPIC_COLUMNS} FROM topics WHERE lower(phrase) = lower($1) AND language = $2", phrase, language
    )
    return _topic(row)


async def update_topic(
    conn: Conn, topic_id: int, *, alert_rule: str | None = None, active: bool | None = None
) -> Topic | None:
    await conn.execute(
        "UPDATE topics SET alert_rule = COALESCE($2, alert_rule), active = COALESCE($3, active) WHERE id = $1",
        topic_id,
        alert_rule,
        active,
    )
    return await get_topic(conn, topic_id)


async def remove_topic(conn: Conn, topic_id: int) -> bool:
    return (await conn.execute("DELETE FROM topics WHERE id = $1", topic_id)) == "DELETE 1"


async def record_topic_run(conn: Conn, topic_id: int, *, at: datetime) -> None:
    await conn.execute("UPDATE topics SET last_run_at = $2 WHERE id = $1", topic_id, at)


# --- films ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Discovery:
    """A film a source named, and why we were looking: the door it came in by, and what to do with it once read."""

    ref: VideoRef
    origin: str
    profile: str
    alert_rule: str


async def upsert_films(conn: Conn, discoveries: Sequence[Discovery]) -> int:
    """The films this pass had not seen before, inserted. A film already here is updated only if it has something new —
    a second door it came in by, a length it lacked, a live stream that ended — and is left alone otherwise, which is the
    usual case by a wide margin. Returns how many were new."""
    new = 0
    for found in discoveries:
        ref = found.ref
        row = await conn.fetchrow(
            """
            INSERT INTO videos (
                video_id, channel_id, channel_title, title, published_at, duration_seconds, live_status,
                origins, profile, alert_rule, simulated
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, ARRAY[$8]::text[], $9, $10, $11)
            ON CONFLICT (video_id) DO UPDATE SET
                origins = (SELECT array_agg(DISTINCT o) FROM unnest(videos.origins || EXCLUDED.origins) AS o),
                duration_seconds = COALESCE(videos.duration_seconds, EXCLUDED.duration_seconds),
                live_status = CASE WHEN videos.state = 'discovered'
                                   THEN EXCLUDED.live_status ELSE videos.live_status END
            WHERE NOT (videos.origins @> EXCLUDED.origins)
               OR (videos.duration_seconds IS NULL AND EXCLUDED.duration_seconds IS NOT NULL)
               OR (videos.state = 'discovered' AND videos.live_status <> EXCLUDED.live_status)
            RETURNING (xmax = 0) AS inserted
            """,
            ref.video_id,
            ref.channel_id,
            ref.channel_title,
            ref.title,
            ref.published_at,
            ref.duration_seconds,
            ref.live_status,
            found.origin,
            found.profile,
            found.alert_rule,
            ref.simulated,
        )
        new += bool(row and row["inserted"])
    return new


async def skip_unwanted(conn: Conn, *, minimum: int, maximum: int) -> int:
    """Films whose length is known and outside the limits leave the queue, saying why. A film whose length is not known
    is not touched: a feed cannot say, and guessing would skip good films."""
    result = await conn.execute(
        """
        UPDATE videos SET state = 'skipped',
            skip_reason = CASE WHEN duration_seconds < $1
                               THEN 'shorter than the ' || $1 || '-second floor'
                               ELSE 'longer than the ' || ($2 / 60) || '-minute limit' END
        WHERE state = 'discovered' AND live_status = 'none' AND duration_seconds IS NOT NULL
          AND (duration_seconds < $1 OR duration_seconds > $2)
        """,
        minimum,
        maximum,
    )
    return int(result.split()[-1])


async def get_video(conn: Conn, video_id: str) -> Video | None:
    row = await conn.fetchrow(f"SELECT {_VIDEO_COLUMNS} FROM videos WHERE video_id = $1", video_id)
    return None if row is None else _video(row)


async def live_pending(conn: Conn, limit: int) -> list[str]:
    """Films that were live when last seen and have not been read: the ones a listing may no longer mention."""
    rows = await conn.fetch(
        "SELECT video_id FROM videos WHERE state = 'discovered' AND live_status <> 'none' "
        "ORDER BY published_at DESC LIMIT $1",
        limit,
    )
    return [row["video_id"] for row in rows]


async def due_for_transcription(conn: Conn, now: datetime, limit: int) -> list[Video]:
    rows = await conn.fetch(
        f"""
        SELECT {_VIDEO_COLUMNS} FROM videos
        WHERE state IN ('discovered', 'no_transcript') AND live_status = 'none'
          AND (next_attempt_at IS NULL OR next_attempt_at <= $1)
        ORDER BY published_at DESC LIMIT $2
        """,
        now,
        limit,
    )
    return [_video(row) for row in rows]


async def save_transcript(conn: Conn, video_id: str, transcript: Transcript) -> None:
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO transcripts (video_id, content, language, provider, automatic, simulated)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (video_id) DO UPDATE SET content = EXCLUDED.content, language = EXCLUDED.language,
                provider = EXCLUDED.provider, automatic = EXCLUDED.automatic, simulated = EXCLUDED.simulated,
                fetched_at = now()
            """,
            video_id,
            transcript.text,
            transcript.language,
            transcript.provider,
            transcript.automatic,
            transcript.simulated,
        )
        await conn.execute(
            "UPDATE videos SET state = 'transcribed', job_provider = NULL, job_id = NULL, "
            "next_attempt_at = NULL WHERE video_id = $1",
            video_id,
        )


async def record_no_transcript(conn: Conn, video_id: str, *, give_up: bool, retry_at: datetime | None) -> None:
    await conn.execute(
        """
        UPDATE videos SET attempts = attempts + 1, job_provider = NULL, job_id = NULL,
            state = $2, next_attempt_at = $3
        WHERE video_id = $1
        """,
        video_id,
        GAVE_UP if give_up else NO_TRANSCRIPT,
        None if give_up else retry_at,
    )


async def record_job(conn: Conn, video_id: str, *, provider: str, job_id: str) -> None:
    await conn.execute(
        "UPDATE videos SET job_provider = $2, job_id = $3 WHERE video_id = $1", video_id, provider, job_id
    )


@dataclass(frozen=True, slots=True)
class ToRead:
    video: Video
    transcript: str
    language: str


async def due_for_reading(conn: Conn, *, max_failures: int, limit: int) -> list[ToRead]:
    rows = await conn.fetch(
        f"""
        SELECT {", ".join(f"v.{c.strip()}" for c in _VIDEO_COLUMNS.split(","))}, t.content, t.language AS t_language
        FROM videos v JOIN transcripts t USING (video_id)
        WHERE v.state = 'transcribed' AND v.reading_failures < $1
        ORDER BY v.published_at DESC LIMIT $2
        """,
        max_failures,
        limit,
    )
    return [ToRead(_video(row), row["content"], row["t_language"]) for row in rows]


async def save_reading(
    conn: Conn, video_id: str, *, profile: str, reading: Reading, model: str, simulated: bool
) -> None:
    """Overwrites the reading of this film under this profile: the history is the film, not what a model thought of it."""
    instruments = sorted(
        {name.lower() for view in reading.instruments for name in (view.name, view.epic) if name}
    )
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO readings (video_id, profile, result, impact_score, instruments, model, simulated)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
            ON CONFLICT (video_id, profile) DO UPDATE SET result = EXCLUDED.result,
                impact_score = EXCLUDED.impact_score, instruments = EXCLUDED.instruments,
                model = EXCLUDED.model, simulated = EXCLUDED.simulated, analysed_at = now()
            """,
            video_id,
            profile,
            json.dumps(reading.model_dump(mode="json")),
            reading.impact_score,
            instruments,
            model,
            simulated,
        )
        await conn.execute("UPDATE videos SET state = 'analysed' WHERE video_id = $1", video_id)


async def record_reading_failure(conn: Conn, video_id: str) -> int:
    return int(
        await conn.fetchval(
            "UPDATE videos SET reading_failures = reading_failures + 1 WHERE video_id = $1 "
            "RETURNING reading_failures",
            video_id,
        )
        or 0
    )


async def set_outcome(conn: Conn, video_id: str, state: str, *, at: datetime | None = None) -> None:
    """`notified` or `quiet`: where an analysed film ends. `notified_at` is written only for the first."""
    assert state in (NOTIFIED, QUIET)
    await conn.execute(
        "UPDATE videos SET state = $2, notified_at = $3 WHERE video_id = $1 AND state = 'analysed'",
        video_id,
        state,
        at if state == NOTIFIED else None,
    )


async def count_by_state(conn: Conn) -> dict[str, int]:
    rows = await conn.fetch("SELECT state, count(*) AS n FROM videos GROUP BY state")
    return {row["state"]: row["n"] for row in rows}


# --- what was spent, and who lets us in -----------------------------------------------------------------------------


async def add_usage(conn: Conn, spent: dict[tuple[str, str], int], *, day: date) -> None:
    for (provider, unit), amount in spent.items():
        await conn.execute(
            """
            INSERT INTO usage (day, provider, unit, amount) VALUES ($1, $2, $3, $4)
            ON CONFLICT (day, provider, unit) DO UPDATE SET amount = usage.amount + EXCLUDED.amount
            """,
            day,
            provider,
            unit,
            amount,
        )


async def usage_on(conn: Conn, day: date) -> dict[tuple[str, str], int]:
    rows = await conn.fetch("SELECT provider, unit, amount FROM usage WHERE day = $1", day)
    return {(row["provider"], row["unit"]): row["amount"] for row in rows}


async def note_provider(conn: Conn, provider: str, *, ok: bool, at: datetime, reason: str | None = None) -> None:
    """A provider answered (`ok`), or would not let us in. Kept apart from any film: what it says is about us."""
    if ok:
        await conn.execute(
            """
            INSERT INTO provider_state (provider, last_ok_at) VALUES ($1, $2)
            ON CONFLICT (provider) DO UPDATE SET last_ok_at = EXCLUDED.last_ok_at
            """,
            provider,
            at,
        )
    else:
        await conn.execute(
            """
            INSERT INTO provider_state (provider, last_blocked_at, blocked_reason) VALUES ($1, $2, $3)
            ON CONFLICT (provider) DO UPDATE SET last_blocked_at = EXCLUDED.last_blocked_at,
                blocked_reason = EXCLUDED.blocked_reason
            """,
            provider,
            at,
            reason,
        )


@dataclass(frozen=True, slots=True)
class ProviderState:
    provider: str
    last_ok_at: datetime | None
    last_blocked_at: datetime | None
    blocked_reason: str | None

    @property
    def blocked(self) -> bool:
        """Blocked *now*: refused, and not answered since."""
        if self.last_blocked_at is None:
            return False
        return self.last_ok_at is None or self.last_blocked_at > self.last_ok_at


async def provider_states(conn: Conn) -> dict[str, ProviderState]:
    rows = await conn.fetch("SELECT provider, last_ok_at, last_blocked_at, blocked_reason FROM provider_state")
    return {row["provider"]: ProviderState(**dict(row)) for row in rows}


async def refresh_film(conn: Conn, ref: VideoRef) -> None:
    """What a source now says of a film we are still waiting on: a live stream that has ended, a length it lacked."""
    await conn.execute(
        """
        UPDATE videos SET live_status = $2, duration_seconds = COALESCE(duration_seconds, $3)
        WHERE video_id = $1 AND state = 'discovered'
        """,
        ref.video_id,
        ref.live_status,
        ref.duration_seconds,
    )


async def clear_job(conn: Conn, video_id: str) -> None:
    await conn.execute("UPDATE videos SET job_provider = NULL, job_id = NULL WHERE video_id = $1", video_id)


async def settle_analysed(conn: Conn) -> int:
    """Read films that nobody will be told about — no adresat, or a channel that never alerts — leave the queue as
    `quiet`, so the day an adresat is set does not announce the whole backlog."""
    result = await conn.execute("UPDATE videos SET state = 'quiet' WHERE state = 'analysed'")
    return int(result.split()[-1])


@dataclass(frozen=True, slots=True)
class ToAnnounce:
    video: Video
    reading: dict
    simulated: bool


async def analysed_for_alert(conn: Conn, *, limit: int) -> list[ToAnnounce]:
    rows = await conn.fetch(
        f"""
        SELECT {", ".join(f"v.{c.strip()}" for c in _VIDEO_COLUMNS.split(","))}, r.result, r.simulated AS r_simulated
        FROM videos v JOIN readings r ON r.video_id = v.video_id AND r.profile = v.profile
        WHERE v.state = 'analysed'
        ORDER BY r.impact_score DESC, v.published_at DESC LIMIT $1
        """,
        limit,
    )
    return [
        ToAnnounce(
            _video(row),
            _json(row["result"]),
            row["r_simulated"],
        )
        for row in rows
    ]


async def expire_unannounced(conn: Conn, *, before: datetime) -> int:
    """Films that were read and never announced, from before the window, are let go as quiet: a gateway that was down for
    three days must not announce three days of films the moment it returns."""
    result = await conn.execute(
        """
        UPDATE videos v SET state = 'quiet'
        WHERE v.state = 'analysed'
          AND (SELECT max(r.analysed_at) FROM readings r WHERE r.video_id = v.video_id) < $1
        """,
        before,
    )
    return int(result.split()[-1])


# --- what a screen or a tool reads ----------------------------------------------------------------------------------


def _json(value):
    """A jsonb column as the document it holds: asyncpg hands it back as text unless a codec says otherwise."""
    return value if isinstance(value, dict) else json.loads(value)


@dataclass(frozen=True, slots=True)
class Film:
    """A film and its one reading under the film's own profile, when there is one."""

    video: Video
    reading: dict | None
    reading_model: str | None
    analysed_at: datetime | None
    reading_simulated: bool | None


_FILM_SELECT = f"""
    SELECT {", ".join(f"v.{c.strip()}" for c in _VIDEO_COLUMNS.split(","))},
           r.result AS r_result, r.model AS r_model, r.analysed_at AS r_at, r.simulated AS r_simulated
    FROM videos v LEFT JOIN readings r ON r.video_id = v.video_id AND r.profile = v.profile
"""


def _film(row) -> Film:
    return Film(
        video=_video(row),
        reading=None if row["r_result"] is None else _json(row["r_result"]),
        reading_model=row["r_model"],
        analysed_at=row["r_at"],
        reading_simulated=row["r_simulated"],
    )


async def list_films(
    conn: Conn,
    *,
    start: datetime,
    end: datetime,
    channel_id: str | None = None,
    origin: str | None = None,
    instrument: str | None = None,
    min_score: int | None = None,
    state: str | None = None,
    limit: int,
) -> list[Film]:
    """A window of films, newest first, narrowed by whatever was asked. The window is what the index serves; the rest
    filters inside it, which is why a window is always part of the question."""
    rows = await conn.fetch(
        _FILM_SELECT
        + """
        WHERE v.published_at >= $1 AND v.published_at <= $2
          AND ($3::text IS NULL OR v.channel_id = $3)
          AND ($4::text IS NULL OR v.origins @> ARRAY[$4]::text[])
          AND ($5::text IS NULL OR r.instruments @> ARRAY[$5]::text[])
          AND ($6::int IS NULL OR r.impact_score >= $6)
          AND ($7::text IS NULL OR v.state = $7)
        ORDER BY v.published_at DESC LIMIT $8
        """,
        start,
        end,
        channel_id,
        origin,
        instrument,
        min_score,
        state,
        limit,
    )
    return [_film(row) for row in rows]


async def get_film(conn: Conn, video_id: str) -> Film | None:
    row = await conn.fetchrow(_FILM_SELECT + " WHERE v.video_id = $1", video_id)
    return None if row is None else _film(row)


@dataclass(frozen=True, slots=True)
class TranscriptPage:
    text: str
    total_chars: int
    language: str
    provider: str
    automatic: bool
    simulated: bool


async def transcript_page(conn: Conn, video_id: str, *, offset: int, limit: int) -> TranscriptPage | None:
    """A slice of a transcript, cut by the database so a page of a hundred kilobytes is not read to be thrown away."""
    row = await conn.fetchrow(
        """
        SELECT substr(content, $2 + 1, $3) AS text, length(content) AS total, language, provider, automatic, simulated
        FROM transcripts WHERE video_id = $1
        """,
        video_id,
        offset,
        limit,
    )
    if row is None:
        return None
    return TranscriptPage(row["text"], row["total"], row["language"], row["provider"], row["automatic"], row["simulated"])


@dataclass(frozen=True, slots=True)
class StateCounts:
    waiting: dict[str, int]
    recent: dict[str, int]


_QUEUE_STATES = ("discovered", "no_transcript", "transcribed", "analysed")


async def state_counts(conn: Conn, *, since: datetime) -> StateCounts:
    """Films by state, in the two ways that stay cheap however deep the archive gets. What is still waiting is counted
    exactly, off the partial index that holds only those states; what is finished is counted over a recent window. A
    count over every film ever kept would grow with the archive and run on every poll of the screen."""
    waiting = await conn.fetch(
        "SELECT state, count(*) AS n FROM videos WHERE state = ANY($1::text[]) GROUP BY state", list(_QUEUE_STATES)
    )
    recent = await conn.fetch(
        "SELECT state, count(*) AS n FROM videos WHERE published_at > $1 GROUP BY state", since
    )
    return StateCounts(
        waiting={row["state"]: row["n"] for row in waiting},
        recent={row["state"]: row["n"] for row in recent},
    )


@dataclass(frozen=True, slots=True)
class InstrumentView:
    video_id: str
    title: str
    channel_title: str
    published_at: datetime
    sentiment: str
    conviction: int
    horizon: str
    impact_score: int
    simulated: bool


async def instrument_views(
    conn: Conn, instrument: str, *, start: datetime, end: datetime, limit: int
) -> list[InstrumentView]:
    """Every direction a reading in the window gives an instrument, by name or by ticker. The GIN index on the lifted
    names finds the readings; the document is opened only for those."""
    wanted = instrument.strip().lower()
    rows = await conn.fetch(
        """
        SELECT v.video_id, v.title, v.channel_title, v.published_at, r.simulated, r.impact_score,
               i->>'sentiment' AS sentiment, (i->>'conviction')::int AS conviction, i->>'horizon' AS horizon
        FROM videos v
        JOIN readings r ON r.video_id = v.video_id AND r.profile = v.profile
        CROSS JOIN LATERAL jsonb_array_elements(r.result->'instruments') AS i
        WHERE v.published_at >= $1 AND v.published_at <= $2
          AND r.instruments @> ARRAY[$3]::text[]
          AND (lower(i->>'name') = $3 OR lower(i->>'epic') = $3)
        ORDER BY v.published_at DESC LIMIT $4
        """,
        start,
        end,
        wanted,
        limit,
    )
    return [
        InstrumentView(
            video_id=row["video_id"],
            title=row["title"],
            channel_title=row["channel_title"],
            published_at=row["published_at"],
            sentiment=row["sentiment"],
            conviction=row["conviction"],
            horizon=row["horizon"],
            impact_score=row["impact_score"],
            simulated=row["simulated"],
        )
        for row in rows
    ]
