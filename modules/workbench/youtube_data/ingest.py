"""The loop: discover films, get their words, have a model read them, tell the operator. One pass per interval, four steps in
that order, each with a limit of its own.

Three things here are decisions rather than mechanics. **A film's state is a row, not a memory of the loop**: a restart
resumes where the archive says it was, and a film that will never have captions has an end (`gave_up`) instead of a pass a
day for ever. **Blocked is not a miss**: a provider that refuses us says nothing about the film, so it neither spends an
attempt nor lets the pass go on asking. And **the day is counted here**, in the provider's own unit, against ceilings that
are settings — a dashboard that says no says it after the money is gone."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from tc_runtime.liveness import LoopHeartbeat

from . import budget, store
from .analysis import Film
from .config import Settings
from .providers.base import (
    Blocked,
    ChannelInfo,
    NoTranscript,
    QuotaExceeded,
    ReadingUnusable,
    SourceError,
    Transcript,
    TranscriptRequest,
)
from .providers.build import Providers
from .providers.chain import ChainAnswer, Deferred

log = logging.getLogger(__name__)

# A topic with no earlier search looks back this far: a day of films is what an operator adding a topic expects to see.
FIRST_SEARCH_LOOKBACK = timedelta(days=1)

Announce = Callable[[datetime], Awaitable[object]]


class Ingest:
    def __init__(
        self,
        pool,
        providers: Providers,
        settings: Settings,
        *,
        announce: Announce | None = None,
        heartbeat: LoopHeartbeat | None = None,
    ) -> None:
        self._pool = pool
        self._providers = providers
        self._settings = settings
        self._announce = announce
        # `None` in a test that drives `tick()` itself: what the loop reports is the loop's.
        self._heartbeat = heartbeat
        self._clock = providers.clock
        self._task: asyncio.Task | None = None
        # One thing spends the providers' day at a time: the loop's pass, or a film somebody named by hand.
        self._busy = asyncio.Lock()
        self._named: set[asyncio.Task] = set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="youtube-ingest")

    async def stop(self) -> None:
        for task in list(self._named):
            task.cancel()
        await asyncio.gather(*self._named, return_exceptions=True)
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def start_now(self, video_id: str) -> None:
        """A film named by hand, processed now and in the background: the caller is told it is accepted, not what became
        of it — a model that listens to a film takes minutes."""
        task = asyncio.create_task(self.process_now(video_id), name=f"youtube-named-{video_id}")
        self._named.add(task)
        task.add_done_callback(self._named.discard)

    async def process_now(self, video_id: str) -> None:
        """Words, reading and announcement for this one film, without waiting for the loop and without touching the rest
        of its queue. The same ceilings, prices and rests as a pass — and the same lock, so the two cannot spend one
        day twice."""
        async with self._busy:
            try:
                await self._transcribe(only=video_id)
                await self._read(only=video_id)
                await self._tell()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Nobody is waiting on this: what failed is for the log, and the film stays where the loop will find it.
                log.exception("the film %s named by hand could not be processed", video_id)
            finally:
                await self._flush()

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad round is not the end of the archive.
                log.exception("a round failed")
            else:
                # After the pass and only after it: a round that raised did not happen, and a heartbeat beaten
                # regardless would report a stopped loop as healthy.
                if self._heartbeat is not None:
                    self._heartbeat.beat()
            await asyncio.sleep(self._settings.poll_interval_seconds)

    async def tick(self) -> None:
        """One pass. A step that fails does not stop the ones after it — a source that will not answer costs the
        discovery, not the readings of what is already waiting — but the pass is then reported as failed, so the age the
        heartbeat publishes keeps growing."""
        errors: list[Exception] = []
        steps: tuple[tuple[str, Callable[[], Awaitable[None]]], ...] = (
            ("discover", self._discover),
            ("transcribe", self._transcribe),
            ("read", self._read),
            ("announce", self._tell),
        )
        async with self._busy:
            for name, step in steps:
                try:
                    await step()
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    log.exception("the %s step failed", name)
                    errors.append(err)
                finally:
                    await self._flush()
        if errors:
            raise errors[0]

    @property
    def _bounds(self) -> tuple[int, int]:
        """The shortest and longest film worth a transcript, in seconds."""
        return self._settings.min_video_seconds, self._settings.max_video_seconds

    # --- the day -----------------------------------------------------------------------------------------------------

    def _day(self):
        return budget.utc_day(self._clock.now())

    async def _flush(self) -> None:
        """What the providers were asked for since the last look, written down — even when the call that spent it ended
        in an exception, which is when it matters."""
        spent = self._providers.meter.drain()
        if spent:
            async with self._pool.acquire() as conn:
                await store.add_usage(conn, spent, day=self._day())

    async def _remaining(self, ceiling: budget.Ceiling) -> int:
        await self._flush()
        async with self._pool.acquire() as conn:
            return await budget.remaining(conn, ceiling, day=self._day())

    # --- discover ----------------------------------------------------------------------------------------------------

    async def _discover(self) -> None:
        now = self._clock.now()
        source = self._providers.source
        ceiling = budget.Ceiling(source.name, source.unit, self._settings.daily_source_units)

        async with self._pool.acquire() as conn:
            channels = (await store.list_channels(conn, active_only=True))[: self._settings.discover_batch_limit]
            topics = [
                topic
                for topic in await store.list_topics(conn, active_only=True)
                if topic.last_run_at is None or now - topic.last_run_at >= timedelta(minutes=topic.interval_minutes)
            ][: self._settings.discover_batch_limit]

        left = await self._remaining(ceiling)
        for channel in channels:
            if left <= 0:
                log.warning("the %s source's day is spent; discovery waits for tomorrow", source.name)
                break
            info = ChannelInfo(
                channel_id=channel.channel_id,
                title=channel.title,
                handle=channel.handle,
                uploads_playlist_id=channel.uploads_playlist_id,
            )
            try:
                films = await source.latest_videos(info)
            except QuotaExceeded:
                log.warning("the %s source says its quota is spent", source.name)
                left = 0
                break
            except SourceError as err:
                # The archive is left as it was; the channel is asked again next pass.
                log.warning("channel %s could not be listed: %s", channel.channel_id, err)
                left = await self._remaining(ceiling)
                continue
            async with self._pool.acquire() as conn:
                await store.upsert_films(
                    conn,
                    [
                        store.Discovery(film, f"channel:{channel.channel_id}", channel.profile, channel.alert_rule)
                        for film in films
                    ],
                    bounds=self._bounds,
                )
                await store.record_discovery(conn, channel.channel_id, at=now)
            left = await self._remaining(ceiling)

        for topic in topics:
            if left < source.search_cost:
                log.warning("topic %r waits: the %s source's day cannot pay for a search", topic.phrase, source.name)
                break
            try:
                films = await source.search(
                    topic.phrase,
                    language=topic.language,
                    published_after=topic.last_run_at or now - FIRST_SEARCH_LOOKBACK,
                    limit=topic.max_videos_per_run,
                )
            except QuotaExceeded:
                log.warning("the %s source says its quota is spent", source.name)
                break
            except SourceError as err:
                log.warning("topic %r could not be searched: %s", topic.phrase, err)
                left = await self._remaining(ceiling)
                continue
            async with self._pool.acquire() as conn:
                await store.upsert_films(
                    conn,
                    [store.Discovery(film, f"topic:{topic.id}", topic.profile, topic.alert_rule) for film in films],
                    bounds=self._bounds,
                )
                await store.record_topic_run(conn, topic.id, at=now)
            left = await self._remaining(ceiling)

        async with self._pool.acquire() as conn:
            await store.drop_unwanted(
                conn, minimum=self._settings.min_video_seconds, maximum=self._settings.max_video_seconds
            )
            live = await store.live_pending(conn, self._settings.discover_batch_limit)
        if live and left > 0:
            await self._refresh_live(live)

    async def _refresh_live(self, video_ids: list[str]) -> None:
        """A stream listed as live is asked about until it is not: it may have dropped out of the channel's latest fifteen
        while it was still running, and would otherwise wait for ever."""
        try:
            films = await self._providers.source.video_details(video_ids)
        except SourceError:
            # A source that will not answer is asked again next pass.
            return
        async with self._pool.acquire() as conn:
            for film in films:
                await store.refresh_film(conn, film)
            await store.drop_unwanted(
                conn, minimum=self._settings.min_video_seconds, maximum=self._settings.max_video_seconds
            )

    # --- transcribe --------------------------------------------------------------------------------------------------

    async def _available(self, now: datetime) -> dict[str, int]:
        """What is left of each provider's day, for the ones worth asking at all: not resting after a refusal younger than
        the cooldown, and with something left. Read once per film, since every answer spends."""
        await self._flush()
        async with self._pool.acquire() as conn:
            states = await store.provider_states(conn)
            spent = await store.usage_on(conn, self._day())
        left: dict[str, int] = {}
        for provider in self._providers.transcripts.providers:
            state = states.get(provider.name)
            minutes = (
                self._settings.listener_cooldown_minutes if provider.listens else self._settings.provider_cooldown_minutes
            )
            rest = timedelta(minutes=minutes)
            if state is not None and state.blocked and state.last_blocked_at and now - state.last_blocked_at < rest:
                continue
            ceiling = budget.transcript_ceiling(self._settings, provider)
            remaining = ceiling.limit - spent.get((ceiling.provider, ceiling.unit), 0)
            if remaining > 0:
                left[provider.name] = remaining
        return left

    async def _transcribe(self, only: str | None = None) -> None:
        now = self._clock.now()
        chain = self._providers.transcripts
        async with self._pool.acquire() as conn:
            # Here as well as after discovery: a discovery that raised half way must not send a five-hour film on.
            await store.drop_unwanted(
                conn, minimum=self._settings.min_video_seconds, maximum=self._settings.max_video_seconds
            )
            films = await store.due_for_transcription(conn, now, self._settings.transcribe_batch_limit, only=only)

        for film in films:
            left = await self._available(self._clock.now())
            if not left:
                log.warning("no transcript provider can be asked now (resting, or its day is spent); transcription waits")
                break
            request = TranscriptRequest.for_film(
                film.video_id,
                duration_seconds=film.duration_seconds,
                audio_language=film.audio_language,
                fallback=self._settings.languages,
            )
            # Priced before asking: a film the day cannot pay for waits for tomorrow rather than spending what is left.
            askable = [
                provider.name
                for provider in chain.providers
                if left.get(provider.name, 0) >= max(provider.price(request), 1)
            ]
            answer = await chain.fetch(request, only=askable)
            await self._flush()
            # The moment of this answer, not of the pass: a refusal after a success in the same pass must read as later.
            if await self._settle(film, answer, self._clock.now()):
                break

    async def _settle(self, film, answer: ChainAnswer, now: datetime) -> bool:
        """Records what the providers said about a film. True means the pass should stop asking: the provider would not
        let us in, and the next film would get the same answer at the same price."""
        result = answer.result
        async with self._pool.acquire() as conn:
            for said in answer.passed:
                if isinstance(said, Blocked):
                    await store.note_provider(conn, said.provider, ok=False, at=now, reason=said.reason)
                else:
                    await store.note_provider(conn, said.provider, ok=True, at=now)
            if isinstance(result, Transcript):
                await store.save_transcript(conn, film.video_id, result)
                await store.note_provider(conn, result.provider, ok=True, at=now)
            elif isinstance(result, NoTranscript):
                await store.note_provider(conn, result.provider, ok=True, at=now)
                misses = film.attempts + 1
                delays = self._settings.retry_delays
                give_up = misses > len(delays)
                await store.record_no_transcript(
                    conn,
                    film.video_id,
                    give_up=give_up,
                    retry_at=None if give_up else now + timedelta(minutes=delays[misses - 1]),
                )
            elif isinstance(result, Deferred):
                # Nothing was learnt about the film, so nothing is written: it stays as it is and the next pass asks again,
                # as soon as a provider has finished resting or a day has turned. (Writing a date here once made a
                # fifteen-minute rest an hour.)
                pass
            else:
                await store.note_provider(conn, result.provider, ok=False, at=now, reason=result.reason)
                log.warning("transcripts blocked (%s: %s); this pass stops asking", result.provider, result.reason)
                return True
        return False

    # --- read --------------------------------------------------------------------------------------------------------

    async def _read(self, only: str | None = None) -> None:
        analyser = self._providers.analyser
        if analyser is None:
            return
        ceiling = budget.Ceiling(budget.ANALYSER, budget.TOKENS, self._settings.daily_token_limit)
        async with self._pool.acquire() as conn:
            waiting = await store.due_for_reading(
                conn,
                max_failures=self._settings.reading_max_failures,
                limit=self._settings.analyse_batch_limit,
                only=only,
            )

        for item in waiting:
            if await self._remaining(ceiling) <= 0:
                log.warning("the day's tokens are spent; readings wait for tomorrow")
                break
            video = item.video
            film = Film(
                video_id=video.video_id,
                title=video.title,
                channel_title=video.channel_title,
                published_on=video.published_at.date(),
                language=item.language,
            )
            try:
                analysis = await analyser.read(film, item.transcript, profile=video.profile)
            except asyncio.CancelledError:
                raise
            except ReadingUnusable as err:
                # An answer about this film that will not be stored: paid for, and one of the film's attempts.
                self._providers.meter.record(budget.ANALYSER, budget.TOKENS, err.tokens)
                log.warning("reading %s is unusable: %s", video.video_id, err)
                async with self._pool.acquire() as conn:
                    await store.record_reading_failure(conn, video.video_id)
                continue
            except Exception as err:  # noqa: BLE001 - whatever a model provider raises must not stop the batch
                # A key, a quota, a rate limit or a dropped connection says nothing about the film, so it spends none of
                # the film's attempts — an hour's outage would otherwise strand every film it touched for good.
                log.warning("reading %s failed: %s", video.video_id, err)
                continue
            self._providers.meter.record(budget.ANALYSER, budget.TOKENS, analysis.input_tokens + analysis.output_tokens)
            async with self._pool.acquire() as conn:
                await store.save_reading(
                    conn,
                    video.video_id,
                    profile=video.profile,
                    reading=analysis.reading,
                    model=analysis.model,
                    simulated=analysis.simulated or video.simulated,
                    at=self._clock.now(),
                )

    # --- tell --------------------------------------------------------------------------------------------------------

    async def _tell(self) -> None:
        if self._announce is not None:
            await self._announce(self._clock.now())
            return
        # Nobody to tell: a read film ends as quiet rather than waiting for an adresat that may come months later and
        # find a backlog to announce.
        async with self._pool.acquire() as conn:
            await store.settle_analysed(conn)
