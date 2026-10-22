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
from typing import Any

from tc_runtime.db import Conn

from .analysis import Reading
from .models import (
    CHANNEL_FOLLOWED,
    CHANNEL_IGNORED,
    DISCOVERED,
    FILTERED_OUT,
    GAVE_UP,
    NO_TRANSCRIPT,
    NOTIFIED,
    QUIET,
    Candidate,
    Channel,
    IgnoredChannel,
    LoopSettings,
    Prompt,
    Topic,
    Video,
)
from .providers.base import ChannelInfo, Transcript, VideoRef

_CHANNEL_COLUMNS = """
    channel_id, title, handle, uploads_playlist_id, language, prompt_id, active,
    added_by, added_at, last_discovery_at, filter
"""
_TOPIC_COLUMNS = """
    id, phrase, language, interval_minutes, max_videos_per_run, active,
    added_by, added_at, last_run_at
"""
_CANDIDATE_COLUMNS = """
    video_id, topic_id, phrase, channel_id, channel_title, title, published_at, duration_seconds, simulated,
    found_at, verdict, reason, screened_by, decision, decided_at
"""
_VIDEO_COLUMNS = """
    video_id, channel_id, channel_title, title, published_at, duration_seconds, live_status, origins,
    audio_language, prompt_id, state, skip_reason, attempts, next_attempt_at, reading_failures,
    simulated, discovered_at, notified_at
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
    conn: Conn, info: ChannelInfo, *, language: str, prompt_id: int, added_by: str, filter: str | None = None
) -> Channel:
    """The channel, inserted — or the one that was already there, untouched: following it again by another spelling of
    its address is not a reason to change what the operator set."""
    await conn.execute(
        """
        INSERT INTO channels (channel_id, title, handle, uploads_playlist_id, language, prompt_id, added_by, filter)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (channel_id) DO NOTHING
        """,
        info.channel_id,
        info.title,
        info.handle,
        info.uploads_playlist_id,
        language,
        prompt_id,
        added_by,
        filter,
    )
    channel = await get_channel(conn, info.channel_id)
    assert channel is not None
    return channel


_UNSET: Any = object()


async def update_channel(
    conn: Conn,
    channel_id: str,
    *,
    prompt_id: int | None = None,
    active: bool | None = None,
    filter: str | None = _UNSET,
) -> Channel | None:
    """`filter` left out keeps the channel's own; `None` takes it off."""
    await conn.execute(
        """
        UPDATE channels SET
            prompt_id = COALESCE($2, prompt_id),
            active = COALESCE($3, active),
            filter = CASE WHEN $4 THEN $5 ELSE filter END
        WHERE channel_id = $1
        """,
        channel_id,
        prompt_id,
        active,
        filter is not _UNSET,
        None if filter is _UNSET else filter,
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
    added_by: str,
) -> Topic:
    """The topic, inserted — or the one that was already there under another spelling of the case, untouched."""
    await conn.execute(
        """
        INSERT INTO topics (phrase, language, interval_minutes, max_videos_per_run, added_by)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (lower(phrase), language) DO NOTHING
        """,
        phrase,
        language,
        interval_minutes,
        max_videos_per_run,
        added_by,
    )
    row = await conn.fetchrow(
        f"SELECT {_TOPIC_COLUMNS} FROM topics WHERE lower(phrase) = lower($1) AND language = $2", phrase, language
    )
    return _topic(row)


async def update_topic(conn: Conn, topic_id: int, *, active: bool | None = None) -> Topic | None:
    await conn.execute("UPDATE topics SET active = COALESCE($2, active) WHERE id = $1", topic_id, active)
    return await get_topic(conn, topic_id)


async def remove_topic(conn: Conn, topic_id: int) -> bool:
    return (await conn.execute("DELETE FROM topics WHERE id = $1", topic_id)) == "DELETE 1"


async def record_topic_run(conn: Conn, topic_id: int, *, at: datetime) -> None:
    await conn.execute("UPDATE topics SET last_run_at = $2 WHERE id = $1", topic_id, at)


# --- loop settings --------------------------------------------------------------------------------------------------


async def get_loop_settings(conn: Conn) -> LoopSettings | None:
    """`None` is the process settings: nothing has been saved."""
    row = await conn.fetchrow(
        "SELECT poll_interval_minutes, topic_interval_minutes, topic_max_videos FROM loop_settings"
    )
    return None if row is None else LoopSettings(**dict(row))


async def put_loop_settings(conn: Conn, value: LoopSettings) -> None:
    await conn.execute(
        """
        INSERT INTO loop_settings (poll_interval_minutes, topic_interval_minutes, topic_max_videos)
        VALUES ($1, $2, $3)
        ON CONFLICT (id) DO UPDATE SET poll_interval_minutes = EXCLUDED.poll_interval_minutes,
            topic_interval_minutes = EXCLUDED.topic_interval_minutes, topic_max_videos = EXCLUDED.topic_max_videos,
            updated_at = now()
        """,
        value.poll_interval_minutes,
        value.topic_interval_minutes,
        value.topic_max_videos,
    )


# --- films ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Discovery:
    """A film a source named, and why we were looking: the door it came in by, and what to do with it once read."""

    ref: VideoRef
    origin: str
    prompt_id: int
    # Set where the channel's filter turned the film away: it is stored, not read, and says why.
    filtered_reason: str | None = None


def unwanted_reason(ref: VideoRef, bounds: tuple[int, int]) -> str | None:
    """Why a film is not worth a transcript, or `None`. Only a film whose length is known and which is not a live stream
    can be too short or too long: a feed cannot say, and guessing would drop good films."""
    minimum, maximum = bounds
    if ref.live_status != "none" or ref.duration_seconds is None:
        return None
    if ref.duration_seconds < minimum:
        return f"shorter than the {minimum}-second floor"
    if ref.duration_seconds > maximum:
        return f"longer than the {maximum // 60}-minute limit"
    return None


async def upsert_films(
    conn: Conn, discoveries: Sequence[Discovery], *, bounds: tuple[int, int] | None = None
) -> int:
    """The films this pass had not seen before, inserted. A film already here is updated only if it has something new —
    a second door it came in by, a length it lacked, a live stream that ended — and is left alone otherwise, which is the
    usual case by a wide margin. With `bounds` (floor, ceiling in seconds) a film outside them is not stored at all: a
    row for a Short is clutter in every list and every answer, and a film the source lists again and again would be
    stored and dropped on every pass. Returns how many were new."""
    new = 0
    for found in discoveries:
        ref = found.ref
        if bounds is not None and unwanted_reason(ref, bounds) is not None:
            continue
        row = await conn.fetchrow(
            """
            INSERT INTO videos (
                video_id, channel_id, channel_title, title, published_at, duration_seconds, live_status,
                origins, prompt_id, simulated, audio_language, state, skip_reason
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, ARRAY[$8]::text[], $9, $10, $11, $12, $13)
            ON CONFLICT (video_id) DO UPDATE SET
                origins = (SELECT array_agg(DISTINCT o) FROM unnest(videos.origins || EXCLUDED.origins) AS o),
                duration_seconds = COALESCE(videos.duration_seconds, EXCLUDED.duration_seconds),
                audio_language = COALESCE(videos.audio_language, EXCLUDED.audio_language),
                live_status = CASE WHEN videos.state = 'discovered'
                                   THEN EXCLUDED.live_status ELSE videos.live_status END
            WHERE NOT (videos.origins @> EXCLUDED.origins)
               OR (videos.duration_seconds IS NULL AND EXCLUDED.duration_seconds IS NOT NULL)
               OR (videos.audio_language IS NULL AND EXCLUDED.audio_language IS NOT NULL)
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
            found.prompt_id,
            ref.simulated,
            ref.audio_language,
            DISCOVERED if found.filtered_reason is None else FILTERED_OUT,
            found.filtered_reason,
        )
        new += bool(row and row["inserted"])
    return new


async def drop_unwanted(conn: Conn, *, minimum: int, maximum: int) -> int:
    """Films that are not worth a transcript are deleted rather than kept: the ones whose length turned out, after they
    were stored, to be outside the limits (a premiere gets its length late), and any left in the `skipped` state by an
    older version. A film the source lists again is not stored again (`upsert_films` with `bounds`). A film whose length
    is not known is not touched."""
    result = await conn.execute(
        """
        DELETE FROM videos
        WHERE state = 'skipped'
           OR (state = 'discovered' AND live_status = 'none' AND duration_seconds IS NOT NULL
               AND (duration_seconds < $1 OR duration_seconds > $2))
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


async def due_for_transcription(
    conn: Conn, now: datetime, limit: int, *, only: str | None = None
) -> list[Video]:
    """The films waiting for words. `only` is the one film somebody named by hand: asked about now, whatever date its
    last miss set for the next ask — the operator asking is the reason to ask."""
    rows = await conn.fetch(
        f"""
        SELECT {_VIDEO_COLUMNS} FROM videos
        WHERE state IN ('discovered', 'no_transcript') AND live_status = 'none'
          AND ($3::text IS NULL OR video_id = $3)
          AND ($3::text IS NOT NULL OR next_attempt_at IS NULL OR next_attempt_at <= $1)
        ORDER BY published_at DESC LIMIT $2
        """,
        now,
        limit,
        only,
    )
    return [_video(row) for row in rows]


async def save_transcript(conn: Conn, video_id: str, transcript: Transcript) -> None:
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO transcripts (video_id, content, language, provider, automatic, simulated, model)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (video_id) DO UPDATE SET content = EXCLUDED.content, language = EXCLUDED.language,
                provider = EXCLUDED.provider, automatic = EXCLUDED.automatic, simulated = EXCLUDED.simulated,
                model = EXCLUDED.model, fetched_at = now()
            """,
            video_id,
            transcript.text,
            transcript.language,
            transcript.provider,
            transcript.automatic,
            transcript.simulated,
            transcript.model,
        )
        await conn.execute(
            "UPDATE videos SET state = 'transcribed', next_attempt_at = NULL WHERE video_id = $1",
            video_id,
        )


async def record_no_transcript(conn: Conn, video_id: str, *, give_up: bool, retry_at: datetime | None) -> None:
    await conn.execute(
        """
        UPDATE videos SET attempts = attempts + 1, state = $2, next_attempt_at = $3
        WHERE video_id = $1
        """,
        video_id,
        GAVE_UP if give_up else NO_TRANSCRIPT,
        None if give_up else retry_at,
    )


@dataclass(frozen=True, slots=True)
class ToRead:
    video: Video
    transcript: str
    language: str


async def due_for_reading(
    conn: Conn, *, max_failures: int, limit: int, only: str | None = None
) -> list[ToRead]:
    rows = await conn.fetch(
        f"""
        SELECT {", ".join(f"v.{c.strip()}" for c in _VIDEO_COLUMNS.split(","))}, t.content, t.language AS t_language
        FROM videos v JOIN transcripts t USING (video_id)
        WHERE v.state = 'transcribed' AND v.reading_failures < $1 AND ($3::text IS NULL OR v.video_id = $3)
        ORDER BY v.published_at DESC LIMIT $2
        """,
        max_failures,
        limit,
        only,
    )
    return [ToRead(_video(row), row["content"], row["t_language"]) for row in rows]


async def save_reading(
    conn: Conn,
    video_id: str,
    *,
    prompt_id: int,
    prompt_version: int,
    reading: Reading,
    model: str,
    simulated: bool,
    at: datetime | None = None,
) -> None:
    """Overwrites the reading of this film by this prompt. Only the film's own prompt moves it to `analysed`; `at` is the loop's clock."""
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO readings (video_id, prompt_id, prompt_version, result, impact_score, model, simulated, analysed_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, COALESCE($8, now()))
            ON CONFLICT (video_id, prompt_id) DO UPDATE SET result = EXCLUDED.result,
                prompt_version = EXCLUDED.prompt_version, impact_score = EXCLUDED.impact_score,
                model = EXCLUDED.model, simulated = EXCLUDED.simulated, analysed_at = EXCLUDED.analysed_at
            """,
            video_id,
            prompt_id,
            prompt_version,
            json.dumps(reading.model_dump(mode="json")),
            reading.impact_score,
            model,
            simulated,
            at,
        )
        await conn.execute(
            "UPDATE videos SET state = 'analysed' WHERE video_id = $1 AND prompt_id = $2 AND state = 'transcribed'",
            video_id,
            prompt_id,
        )


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
        UPDATE videos SET live_status = $2, duration_seconds = COALESCE(duration_seconds, $3),
            audio_language = COALESCE(audio_language, $4)
        WHERE video_id = $1 AND state = 'discovered'
        """,
        ref.video_id,
        ref.live_status,
        ref.duration_seconds,
        ref.audio_language,
    )


async def release_filtered(conn: Conn, video_id: str, *, prompt_id: int | None) -> bool:
    """A film the channel's filter turned away, put back on the road by somebody who looked at it. It keeps the prompt its
    channel gave it unless one is named. False where it is not (or no longer) filtered out."""
    released = await conn.fetchval(
        """
        UPDATE videos SET state = 'discovered', skip_reason = NULL, prompt_id = COALESCE($2, prompt_id),
            origins = (SELECT array_agg(DISTINCT o) FROM unnest(origins || ARRAY['manual']) AS o)
        WHERE video_id = $1 AND state = 'filtered_out'
        RETURNING true
        """,
        video_id,
        prompt_id,
    )
    return bool(released)


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
    # The phrase of the first topic that found this film, if one did — what a rule filters a topic's films by.
    topic: str | None = None
    # The name of the prompt that read it, which a rule may filter by.
    prompt: str = ""


async def analysed_for_alert(conn: Conn, *, limit: int) -> list[ToAnnounce]:
    rows = await conn.fetch(
        f"""
        SELECT {", ".join(f"v.{c.strip()}" for c in _VIDEO_COLUMNS.split(","))}, r.result - 'text' AS result, r.simulated AS r_simulated, p.name AS prompt_name,
               (SELECT t.phrase FROM topics t WHERE 'topic:' || t.id::text = ANY (v.origins) ORDER BY t.id LIMIT 1) AS topic_phrase
        FROM videos v JOIN readings r ON r.video_id = v.video_id AND r.prompt_id = v.prompt_id
        JOIN prompts p ON p.id = r.prompt_id
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
            row["topic_phrase"],
            row["prompt_name"],
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
class ReadingRow:
    """One reading of a film, with the prompt that made it. `result` carries the text only where it was asked for."""

    prompt_id: int
    prompt_name: str
    prompt_version: int
    result: dict
    model: str
    analysed_at: datetime
    simulated: bool


@dataclass(frozen=True, slots=True)
class Film:
    """A film, the reading made by the film's own prompt when there is one — and, for one film asked for by id, every
    reading it has, that one first."""

    video: Video
    reading: ReadingRow | None
    readings: tuple[ReadingRow, ...] = ()


_READING_COLUMNS = """
    r.prompt_id AS r_prompt_id, p.name AS r_prompt_name, r.prompt_version AS r_version, r.model AS r_model,
    r.analysed_at AS r_at, r.simulated AS r_simulated
"""
# A list never carries the text of a reading: it is up to twenty kilobytes a film, and a screen opens one at a time.
_FILM_SELECT = f"""
    SELECT {", ".join(f"v.{c.strip()}" for c in _VIDEO_COLUMNS.split(","))},
           {_READING_COLUMNS}, r.result - 'text' AS r_result
    FROM videos v
    LEFT JOIN readings r ON r.video_id = v.video_id AND r.prompt_id = v.prompt_id
    LEFT JOIN prompts p ON p.id = r.prompt_id
"""


def _reading_row(row) -> ReadingRow | None:
    if row["r_result"] is None:
        return None
    return ReadingRow(
        prompt_id=row["r_prompt_id"],
        prompt_name=row["r_prompt_name"],
        prompt_version=row["r_version"],
        result=_json(row["r_result"]),
        model=row["r_model"],
        analysed_at=row["r_at"],
        simulated=row["r_simulated"],
    )


def _film(row) -> Film:
    reading = _reading_row(row)
    return Film(video=_video(row), reading=reading, readings=() if reading is None else (reading,))


async def list_films(
    conn: Conn,
    *,
    start: datetime,
    end: datetime,
    channel_id: str | None = None,
    origin: str | None = None,
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
          AND ($5::int IS NULL OR r.impact_score >= $5)
          AND CASE WHEN $6::text IS NULL THEN v.state <> 'filtered_out' ELSE v.state = $6 END
        ORDER BY v.published_at DESC LIMIT $7
        """,
        start,
        end,
        channel_id,
        origin,
        min_score,
        state,
        limit,
    )
    return [_film(row) for row in rows]


async def get_film(conn: Conn, video_id: str) -> Film | None:
    """One film with every reading it has, the film's own prompt's first, each with its whole text."""
    row = await conn.fetchrow(f"SELECT {_VIDEO_COLUMNS} FROM videos WHERE video_id = $1", video_id)
    if row is None:
        return None
    video = _video(row)
    rows = await conn.fetch(
        f"""
        SELECT {_READING_COLUMNS}, r.result AS r_result
        FROM readings r JOIN prompts p ON p.id = r.prompt_id
        WHERE r.video_id = $1
        ORDER BY (r.prompt_id = $2) DESC, r.analysed_at DESC
        """,
        video_id,
        video.prompt_id,
    )
    readings = tuple(found for found in (_reading_row(r) for r in rows) if found is not None)
    own = next((found for found in readings if found.prompt_id == video.prompt_id), None)
    return Film(video=video, reading=own, readings=readings)


@dataclass(frozen=True, slots=True)
class TranscriptPage:
    text: str
    total_chars: int
    language: str
    provider: str
    automatic: bool
    simulated: bool
    model: str | None = None


# `substr` takes an int4: an offset past it is past the end of any transcript, and must say so rather than overflow.
_PAST_ANY_TRANSCRIPT = 2**31 - 2


async def transcript_page(conn: Conn, video_id: str, *, offset: int, limit: int) -> TranscriptPage | None:
    """A slice of a transcript, cut by the database so a page of a hundred kilobytes is not read to be thrown away."""
    offset = min(offset, _PAST_ANY_TRANSCRIPT)
    row = await conn.fetchrow(
        """
        SELECT substr(content, $2 + 1, $3) AS text, length(content) AS total, language, provider, automatic, simulated,
               model
        FROM transcripts WHERE video_id = $1
        """,
        video_id,
        offset,
        limit,
    )
    if row is None:
        return None
    return TranscriptPage(
        row["text"], row["total"], row["language"], row["provider"], row["automatic"], row["simulated"], row["model"]
    )


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


# --- prompts ---------------------------------------------------------------------------------------------------------

_PROMPT_SELECT = """
    SELECT p.id, p.name, p.seeded, p.created_at, v.version, v.body, v.created_at AS updated_at
    FROM prompts p
    JOIN LATERAL (
        SELECT version, body, created_at FROM prompt_versions WHERE prompt_id = p.id ORDER BY version DESC LIMIT 1
    ) v ON true
"""


def _prompt(row) -> Prompt:
    return Prompt(**{name: row[name] for name in Prompt.__dataclass_fields__})


async def list_prompts(conn: Conn) -> list[Prompt]:
    rows = await conn.fetch(_PROMPT_SELECT + " WHERE p.deleted_at IS NULL ORDER BY p.seeded DESC, lower(p.name)")
    return [_prompt(row) for row in rows]


async def get_prompt(conn: Conn, prompt_id: int) -> Prompt | None:
    row = await conn.fetchrow(_PROMPT_SELECT + " WHERE p.id = $1 AND p.deleted_at IS NULL", prompt_id)
    return None if row is None else _prompt(row)


async def prompt_named(conn: Conn, name: str) -> Prompt | None:
    row = await conn.fetchrow(
        _PROMPT_SELECT + " WHERE lower(p.name) = lower($1) AND p.deleted_at IS NULL", name.strip()
    )
    return None if row is None else _prompt(row)


async def seeded_prompt(conn: Conn) -> Prompt:
    row = await conn.fetchrow(_PROMPT_SELECT + " WHERE p.seeded")
    assert row is not None, "the migration seeds one prompt, and nothing deletes it"
    return _prompt(row)


async def prompt_to_read_with(conn: Conn, prompt_id: int) -> tuple[int, str]:
    """The latest version of a prompt and its words — also of one deleted since a film was queued with it: the film still
    has to be read by something, and what the operator wrote is still there."""
    row = await conn.fetchrow(
        "SELECT version, body FROM prompt_versions WHERE prompt_id = $1 ORDER BY version DESC LIMIT 1", prompt_id
    )
    assert row is not None, "a prompt always has a version"
    return row["version"], row["body"]


async def create_prompt(conn: Conn, *, name: str, body: str) -> Prompt:
    async with conn.transaction():
        row = await conn.fetchrow("INSERT INTO prompts (name) VALUES ($1) RETURNING id", name)
        assert row is not None
        prompt_id = row["id"]
        await conn.execute("INSERT INTO prompt_versions (prompt_id, version, body) VALUES ($1, 1, $2)", prompt_id, body)
    found = await get_prompt(conn, prompt_id)
    assert found is not None
    return found


async def update_prompt(conn: Conn, prompt_id: int, *, name: str | None, body: str | None) -> Prompt | None:
    """A new name replaces the old one; new words make a new version, and an edit that changes no word makes none."""
    async with conn.transaction():
        # One writer at a time per prompt: two saves would otherwise both take the next version number.
        await conn.execute("SELECT 1 FROM prompts WHERE id = $1 FOR UPDATE", prompt_id)
        if name is not None:
            await conn.execute("UPDATE prompts SET name = $2 WHERE id = $1 AND deleted_at IS NULL", prompt_id, name)
        if body is not None:
            await conn.execute(
                """
                INSERT INTO prompt_versions (prompt_id, version, body)
                SELECT $1, version + 1, $2 FROM prompt_versions
                WHERE prompt_id = $1 AND body <> $2
                  AND version = (SELECT max(version) FROM prompt_versions WHERE prompt_id = $1)
                """,
                prompt_id,
                body,
            )
    return await get_prompt(conn, prompt_id)


async def delete_prompt(conn: Conn, prompt_id: int) -> bool:
    """Taken off offer, not out of the database — and only while no channel reads by it, checked in the same statement."""
    return (
        await conn.execute(
            "UPDATE prompts SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL AND NOT seeded "
            "AND NOT EXISTS (SELECT 1 FROM channels WHERE prompt_id = $1)",
            prompt_id,
        )
    ) == "UPDATE 1"


async def prompt_assignments(conn: Conn) -> dict[int, list[str]]:
    """For every prompt in use, the channels whose new films it reads."""
    found: dict[int, list[str]] = {}
    for row in await conn.fetch("SELECT prompt_id, title FROM channels ORDER BY title"):
        found.setdefault(row["prompt_id"], []).append(row["title"])
    return found


async def reading_input(conn: Conn, video_id: str) -> tuple[Video, str, str] | None:
    """A film with its transcript and the transcript's language, for a reading ordered by hand."""
    columns = ", ".join(f"v.{c.strip()}" for c in _VIDEO_COLUMNS.split(","))
    row = await conn.fetchrow(
        f"SELECT {columns}, t.content, t.language AS t_language "
        "FROM videos v JOIN transcripts t USING (video_id) WHERE v.video_id = $1",
        video_id,
    )
    return None if row is None else (_video(row), row["content"], row["t_language"])


async def has_transcript(conn: Conn, video_id: str) -> bool:
    return bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM transcripts WHERE video_id = $1)", video_id))


async def count_prompts(conn: Conn) -> int:
    return int(await conn.fetchval("SELECT count(*) FROM prompts WHERE deleted_at IS NULL") or 0)


# --- candidates -----------------------------------------------------------------------------------------------------


def _candidate(row) -> Candidate:
    return Candidate(**{name: row[name] for name in Candidate.__dataclass_fields__})


async def already_known(conn: Conn, video_ids: Sequence[str]) -> set[str]:
    """Which of these films the archive has, or has already offered: a search result that is either is not offered again."""
    rows = await conn.fetch(
        "SELECT video_id FROM videos WHERE video_id = ANY($1::text[]) "
        "UNION SELECT video_id FROM candidates WHERE video_id = ANY($1::text[])",
        list(video_ids),
    )
    return {row["video_id"] for row in rows}


async def in_archive(conn: Conn, video_ids: Sequence[str]) -> set[str]:
    """Which of these films have a row, whatever its state — judged, read or turned away. Not the candidates: an offer is
    not a film, and a channel followed since may still want it."""
    rows = await conn.fetch("SELECT video_id FROM videos WHERE video_id = ANY($1::text[])", list(video_ids))
    return {row["video_id"] for row in rows}


@dataclass(frozen=True, slots=True)
class Screened:
    """A search result with what the screening made of it. `verdict` is `unscreened` where nothing could."""

    ref: VideoRef
    verdict: str
    reason: str | None
    model: str | None


async def add_candidates(conn: Conn, topic_id: int, phrase: str, found: Sequence[Screened], *, at: datetime) -> None:
    """The candidates this search had not offered before. A film offered twice stays as it was first offered."""
    await conn.executemany(
        """
        INSERT INTO candidates (
            video_id, topic_id, phrase, channel_id, channel_title, title, published_at, duration_seconds,
            simulated, found_at, verdict, reason, screened_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (video_id) DO NOTHING
        """,
        [
            (
                item.ref.video_id,
                topic_id,
                phrase,
                item.ref.channel_id,
                item.ref.channel_title,
                item.ref.title,
                item.ref.published_at,
                item.ref.duration_seconds,
                item.ref.simulated,
                at,
                item.verdict,
                item.reason,
                item.model,
            )
            for item in found
        ],
    )



async def list_candidates(
    conn: Conn, *, view: str = "open", sort: str = "found", topic_id: int | None = None, limit: int = 100
) -> list[Candidate]:
    """`open` is what is on offer: not rejected by the model and not yet decided about. The two orders each have a partial
    index over exactly that set."""
    where = {
        # A channel followed some other way since the film was found is no longer a question to ask.
        "open": "decision IS NULL AND verdict <> 'rejected' "
        "AND (channel_id IS NULL OR channel_id NOT IN (SELECT channel_id FROM channels))",
        "rejected": "decision IS NULL AND verdict = 'rejected'",
        "decided": "decision IS NOT NULL",
    }[view]
    order = {"found": "found_at DESC", "published": "published_at DESC"}[sort]
    rows = await conn.fetch(
        f"SELECT {_CANDIDATE_COLUMNS} FROM candidates WHERE {where} AND ($1::bigint IS NULL OR topic_id = $1) "
        f"ORDER BY {order}, video_id LIMIT $2",
        topic_id,
        limit,
    )
    return [_candidate(row) for row in rows]


async def get_candidate(conn: Conn, video_id: str) -> Candidate | None:
    row = await conn.fetchrow(f"SELECT {_CANDIDATE_COLUMNS} FROM candidates WHERE video_id = $1", video_id)
    return None if row is None else _candidate(row)


async def decide_candidate(conn: Conn, video_id: str, decision: str, *, at: datetime) -> Candidate | None:
    """The decision on one candidate. Only a candidate nobody decided about takes one: the first decision stands."""
    row = await conn.fetchrow(
        f"UPDATE candidates SET decision = $2, decided_at = $3 WHERE video_id = $1 AND decision IS NULL "
        f"RETURNING {_CANDIDATE_COLUMNS}",
        video_id,
        decision,
        at,
    )
    return None if row is None else _candidate(row)


async def decide_channel_candidates(conn: Conn, channel_id: str, decision: str, *, at: datetime) -> int:
    """What a decision about a channel means for the rest of its candidates: they are decided the same way, so the list
    does not go on offering a channel the operator has settled."""
    assert decision in (CHANNEL_FOLLOWED, CHANNEL_IGNORED)
    result = await conn.execute(
        "UPDATE candidates SET decision = $2, decided_at = $3 WHERE channel_id = $1 AND decision IS NULL",
        channel_id,
        decision,
        at,
    )
    return int(result.split()[-1])


async def settled_channels(conn: Conn, channel_ids: Sequence[str]) -> set[str]:
    """Which of these channels are followed or ignored: their films are not offered."""
    rows = await conn.fetch(
        "SELECT channel_id FROM channels WHERE channel_id = ANY($1::text[]) "
        "UNION SELECT channel_id FROM ignored_channels WHERE channel_id = ANY($1::text[])",
        list(channel_ids),
    )
    return {row["channel_id"] for row in rows}


async def list_ignored_channels(conn: Conn) -> list[IgnoredChannel]:
    rows = await conn.fetch("SELECT channel_id, channel_title, ignored_at FROM ignored_channels ORDER BY ignored_at DESC")
    return [IgnoredChannel(**dict(row)) for row in rows]


async def ignore_channel(conn: Conn, channel_id: str, title: str) -> None:
    await conn.execute(
        "INSERT INTO ignored_channels (channel_id, channel_title) VALUES ($1, $2) ON CONFLICT (channel_id) DO NOTHING",
        channel_id,
        title,
    )


async def unignore_channel(conn: Conn, channel_id: str) -> bool:
    return (await conn.execute("DELETE FROM ignored_channels WHERE channel_id = $1", channel_id)) == "DELETE 1"
