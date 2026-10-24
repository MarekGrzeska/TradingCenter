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
from typing import NamedTuple

from tc_runtime.liveness import LoopHeartbeat

from . import budget, loop_settings, store
from .analysis import Film
from .config import Settings
from .models import (
    DAY_SPENT,
    FAILED,
    FOUND,
    MODEL_FAILED,
    NO_MODEL,
    NO_VERDICT,
    NOTHING_NEW,
    PROPOSED,
    REJECTED,
    SKIPPED,
    UNSCREENED,
    UNUSABLE,
)
from .providers.base import (
    Blocked,
    ChannelInfo,
    NoTranscript,
    QuotaExceeded,
    ReadingUnusable,
    SourceError,
    SourceRefused,
    Transcript,
    TranscriptRequest,
    TranscriptResult,
    VideoRef,
)
from .providers.build import Providers
from .screening import Screener, Screening

log = logging.getLogger(__name__)

# A topic with no earlier search looks back this far: a day of films is what an operator adding a topic expects to see.
FIRST_SEARCH_LOOKBACK = timedelta(days=1)

# Answers about one film that carried no usable verdict before a filtered channel stops paying to ask: it is then kept
# `filtered_out` saying so, for the operator to take or leave. A model nobody could reach is not an answer and counts none.
JUDGE_MAX_FAILURES = 3

Announce = Callable[[datetime], Awaitable[object]]


class Judged(NamedTuple):
    """A screening's verdicts. `answered` is whether a model said anything (a refusal is something, no model is not)."""

    verdicts: dict[str, tuple[str, str]]
    model: str | None
    answered: bool
    why: str | None


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
        # Set when the operator saves a new interval, so a wait already running is cut or stretched to it.
        self._interval_changed = asyncio.Event()
        self._named: set[asyncio.Task] = set()
        # Readings ordered by hand and not yet done, so a second click on the same one is not a second bill.
        self._ordered: set[tuple[str, int]] = set()
        # Answers without a verdict, by film of a filtered channel. In memory on purpose: a film nobody could judge has no row,
        # and a restart costing a few more answers is cheaper than a row for every film still waiting.
        self._unjudged: dict[str, int] = {}

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
            await self._rest(await self._interval())

    async def _interval(self) -> float:
        """The seconds between passes as they stand now — the operator's, or the process's while nothing is saved. The
        heartbeat's own notion of late follows it, or a shortened loop would be judged by the old, longer one."""
        try:
            async with self._pool.acquire() as conn:
                seconds = (await loop_settings.current(conn, self._settings)).poll_interval_seconds
        except Exception:
            log.exception("the loop's interval could not be read; the process's stands")
            seconds = self._settings.poll_interval_seconds
        if self._heartbeat is not None:
            self._heartbeat.expected_seconds = seconds
        return seconds

    def interval_changed(self) -> None:
        self._interval_changed.set()

    async def _rest(self, interval: float) -> None:
        """Waits out `interval` from the end of the pass. A new interval restarts the count from the same moment with its
        own length, so shortening it after the wait is already longer ends the wait now, and nothing runs a pass of its own."""
        loop = asyncio.get_running_loop()
        began = loop.time()
        while True:
            self._interval_changed.clear()
            left = began + interval - loop.time()
            if left <= 0:
                return
            try:
                await asyncio.wait_for(self._interval_changed.wait(), left)
            except TimeoutError:
                return
            interval = await self._interval()

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
                if (topic.last_run_at is None or now - topic.last_run_at >= timedelta(minutes=topic.interval_minutes))
                and (topic.retry_at is None or now >= topic.retry_at)
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
            discoveries = await self._through_filter(channel, films)
            async with self._pool.acquire() as conn:
                await store.upsert_films(conn, discoveries, bounds=self._bounds)
                await store.record_discovery(conn, channel.channel_id, at=now)
            left = await self._remaining(ceiling)

        spent = False
        for index, topic in enumerate(topics):
            if spent or left < source.search_cost:
                log.warning("topic %r waits: the %s source's day cannot pay for a search", topic.phrase, source.name)
                for waiting in topics[index:]:
                    await self._note_run(
                        store.RunReport(
                            waiting.id,
                            waiting.phrase,
                            now,
                            SKIPPED,
                            error=f"the {source.name} source's day cannot pay for a search",
                        )
                    )
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
                await self._note_run(
                    store.RunReport(topic.id, topic.phrase, now, FAILED, error=f"the {source.name} source reports its quota spent")
                )
                await self._hold(topic, now)
                # The topics after it are then skipped by the check above, and written down as such.
                spent = True
                continue
            except SourceError as err:
                log.warning("topic %r could not be searched: %s", topic.phrase, err)
                # A refusal was paid for, and asking again on the next pass would pay again; no answer cost nothing.
                if isinstance(err, SourceRefused):
                    await self._hold(topic, now)
                await self._note_run(store.RunReport(topic.id, topic.phrase, now, FAILED, error=str(err)[:300] or type(err).__name__))
                left = await self._remaining(ceiling)
                continue
            await self._propose(topic, films, now)
            left = await self._remaining(ceiling)

        async with self._pool.acquire() as conn:
            await store.drop_unwanted(
                conn, minimum=self._settings.min_video_seconds, maximum=self._settings.max_video_seconds
            )
            live = await store.live_pending(conn, self._settings.discover_batch_limit)
        if live and left > 0:
            await self._refresh_live(live)

    async def _through_filter(self, channel, films: list[VideoRef]) -> list[store.Discovery]:
        """A channel's latest films as discoveries. Where the channel has a filter, the films the archive has not seen are
        judged against it in one call: one that passes is stored as any film, one that does not is stored `filtered_out`
        with the reason — so it is judged once — and one nobody could judge is not stored at all, and comes back with the
        next listing. Passing it unjudged would pay for the very transcript the filter is there to save. A stream still
        running, a premiere and a film of unknown length wait unjudged too: what is judged is the film that will be read."""
        origin = f"channel:{channel.channel_id}"
        if channel.filter is None:
            return [store.Discovery(film, origin, channel.prompt_id) for film in films]
        async with self._pool.acquire() as conn:
            stored = await store.in_archive(conn, [film.video_id for film in films])
        unseen = [film for film in films if film.video_id not in stored]
        fresh = [
            film
            for film in unseen
            if film.live_status == "none"
            and film.duration_seconds is not None
            and store.unwanted_reason(film, self._bounds) is None
        ]
        unseen_ids = {film.video_id for film in unseen}
        fresh_ids = {film.video_id for film in fresh}
        judged = await self._screen(
            channel.title, fresh, lambda screener: screener.screen_channel(channel.filter or "", fresh)
        )
        verdicts, answered = judged.verdicts, judged.answered
        discoveries: list[store.Discovery] = []
        waiting = 0
        for film in films:
            if film.video_id not in unseen_ids:
                discoveries.append(store.Discovery(film, origin, channel.prompt_id))
            elif film.video_id not in fresh_ids:
                # Out of bounds is dropped by the upsert as for any channel; live or of unknown length, it waits.
                if store.unwanted_reason(film, self._bounds) is not None:
                    discoveries.append(store.Discovery(film, origin, channel.prompt_id))
            elif film.video_id not in verdicts:
                misses = self._unjudged.get(film.video_id, 0) + int(answered)
                if misses >= JUDGE_MAX_FAILURES:
                    self._unjudged.pop(film.video_id, None)
                    reason = f"could not be judged: the model gave no verdict {misses} times"
                    discoveries.append(store.Discovery(film, origin, channel.prompt_id, filtered_reason=reason))
                else:
                    self._unjudged[film.video_id] = misses
                    waiting += 1
            elif verdicts[film.video_id][0] == PROPOSED:
                discoveries.append(store.Discovery(film, origin, channel.prompt_id))
            else:
                reason = verdicts[film.video_id][1] or "outside the channel's criteria"
                discoveries.append(store.Discovery(film, origin, channel.prompt_id, filtered_reason=reason))
            if film.video_id in verdicts:
                self._unjudged.pop(film.video_id, None)
        if waiting:
            log.warning("channel %s: %d film(s) wait to be judged against its filter", channel.channel_id, waiting)
        return discoveries

    async def _hold(self, topic, now: datetime) -> None:
        """A topic whose search was paid for and failed waits its own interval, so it costs no more than one that works."""
        async with self._pool.acquire() as conn:
            await store.hold_topic(conn, topic.id, until=now + timedelta(minutes=topic.interval_minutes))

    async def _note_run(self, report: store.RunReport) -> None:
        """A run written down. Never the reason a pass fails: the history describes the loop and must not be able to stop it."""
        try:
            async with self._pool.acquire() as conn:
                await store.add_run(conn, report)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("the run of topic %r could not be written down", report.phrase)

    async def _propose(self, topic, films: list[VideoRef], now: datetime) -> None:
        """What a search found, offered to the operator instead of sent to be read: the results the archive and the operator
        have not already settled, screened by a model on their metadata in one call, and stored as candidates."""
        async with self._pool.acquire() as conn:
            known = await store.already_known(conn, [film.video_id for film in films])
            settled = await store.settled_channels(conn, [film.channel_id for film in films if film.channel_id])
        # A stream still live or a premiere not yet run is offered like any film: a search never returns it again once it
        # is over, and the operator's analysis waits for its end.
        already = [film for film in films if film.video_id in known or film.channel_id in settled]
        fresh = [
            film
            for film in films
            if film.video_id not in known
            and film.channel_id not in settled
            and store.unwanted_reason(film, self._bounds) is None
        ]
        judged = await self._screen(topic.phrase, fresh, lambda screener: screener.screen(topic.phrase, fresh))
        verdicts, model = judged.verdicts, judged.model
        async with self._pool.acquire() as conn:
            await store.add_candidates(
                conn,
                topic.id,
                topic.phrase,
                [
                    store.Screened(film, *verdicts.get(film.video_id, (UNSCREENED, None)), model=model if film.video_id in verdicts else None)
                    for film in fresh
                ],
                at=now,
            )
            await store.record_topic_run(conn, topic.id, at=now)
        counts = {PROPOSED: 0, REJECTED: 0, UNSCREENED: 0}
        for film in fresh:
            verdict = verdicts.get(film.video_id, (UNSCREENED, ""))[0]
            counts[verdict if verdict in counts else UNSCREENED] += 1
        # A model that answered and left some films out is a different silence from one that was not asked.
        why = judged.why or (NO_VERDICT if counts[UNSCREENED] else None)
        await self._note_run(
            store.RunReport(
                topic.id,
                topic.phrase,
                now,
                FOUND if fresh else NOTHING_NEW,
                results=len(films),
                known=len(already),
                out_of_bounds=len(films) - len(already) - len(fresh),
                proposed=counts[PROPOSED],
                rejected=counts[REJECTED],
                unscreened=counts[UNSCREENED],
                unscreened_reason=why if counts[UNSCREENED] else None,
            )
        )

    async def _screen(
        self, label: str, films: list[VideoRef], ask: Callable[[Screener], Awaitable[Screening]]
    ) -> Judged:
        """The verdicts for these films, and why there are none where a model could not give them. What the caller does with
        a film nobody judged is the caller's — a topic offers it unscreened, a channel's filter holds it back."""
        screener = self._providers.screener
        if not films:
            return Judged({}, None, False, None)
        if screener is None:
            return Judged({}, None, False, NO_MODEL)
        ceiling = budget.Ceiling(budget.ANALYSER, budget.TOKENS, self._settings.daily_token_limit)
        if await self._remaining(ceiling) <= 0:
            log.warning("the day's tokens are spent; %r is not screened", label)
            return Judged({}, None, False, DAY_SPENT)
        try:
            screening = await ask(screener)
        except asyncio.CancelledError:
            raise
        except ReadingUnusable as err:
            self._providers.meter.record(budget.ANALYSER, budget.TOKENS, err.tokens)
            log.warning("screening %r is unusable: %s", label, err)
            return Judged({}, None, True, UNUSABLE)
        except Exception as err:  # noqa: BLE001 - whatever a model provider raises must not stop the pass
            log.warning("screening %r failed: %s", label, err)
            return Judged({}, None, False, MODEL_FAILED)
        self._providers.meter.record(budget.ANALYSER, budget.TOKENS, screening.input_tokens + screening.output_tokens)
        return Judged(screening.verdicts, screening.model, True, None)

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

    async def _left_today(self, now: datetime) -> int | None:
        """What is left of the transcriber's day, or `None` while it rests after a refusal younger than the cooldown.
        Read once per film, since every answer spends."""
        await self._flush()
        transcriber = self._providers.transcriber
        async with self._pool.acquire() as conn:
            state = (await store.provider_states(conn)).get(transcriber.name)
            spent = await store.usage_on(conn, self._day())
        rest = timedelta(minutes=self._settings.transcriber_cooldown_minutes)
        if state is not None and state.blocked and state.last_blocked_at and now - state.last_blocked_at < rest:
            return None
        ceiling = budget.transcript_ceiling(self._settings, transcriber)
        return ceiling.limit - spent.get((ceiling.provider, ceiling.unit), 0)

    async def _transcribe(self, only: str | None = None) -> None:
        now = self._clock.now()
        transcriber = self._providers.transcriber
        async with self._pool.acquire() as conn:
            # Here as well as after discovery: a discovery that raised half way must not send a five-hour film on.
            await store.drop_unwanted(
                conn, minimum=self._settings.min_video_seconds, maximum=self._settings.max_video_seconds
            )
            films = await store.due_for_transcription(conn, now, self._settings.transcribe_batch_limit, only=only)

        for film in films:
            left = await self._left_today(self._clock.now())
            if left is None or left <= 0:
                log.warning("the transcriber is resting or its day is spent; transcription waits")
                break
            request = TranscriptRequest(film.video_id, film.duration_seconds, film.audio_language)
            if left < max(transcriber.price(request), 1):
                # Priced before asking: a film the day cannot pay for waits for tomorrow, and a shorter one may still fit.
                continue
            try:
                result = await transcriber.fetch(request)
            except Exception as err:  # noqa: BLE001 - a transcriber that raised is one that did not let us in
                result = Blocked(transcriber.name, f"{type(err).__name__}: {err}"[:200])
            await self._flush()
            # The moment of this answer, not of the pass: a refusal after a success in the same pass must read as later.
            if await self._settle(film, result, self._clock.now()):
                break

    async def _settle(self, film, result: TranscriptResult, now: datetime) -> bool:
        """Records what the transcriber said about a film. True means the pass should stop asking: it would not let us
        in, and the next film would get the same answer."""
        async with self._pool.acquire() as conn:
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
            await self._read_with(item.video, item.transcript, item.language, item.video.prompt_id)

    async def read_with(self, video_id: str, prompt_id: int) -> None:
        """One more reading of a film already transcribed, by a prompt somebody chose, under the loop's own lock."""
        if self._providers.analyser is None:
            return
        ceiling = budget.Ceiling(budget.ANALYSER, budget.TOKENS, self._settings.daily_token_limit)
        async with self._busy:
            try:
                # Checked again here: the order was accepted while another pass held the lock, and so were others.
                if await self._remaining(ceiling) <= 0:
                    log.warning("the day's tokens are spent; the reading of %s by another prompt waits", video_id)
                    return
                async with self._pool.acquire() as conn:
                    found = await store.reading_input(conn, video_id)
                if found is not None:
                    await self._read_with(*found, prompt_id, counts=False)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("the film %s could not be read again", video_id)
            finally:
                await self._flush()

    def start_reading(self, video_id: str, prompt_id: int) -> None:
        key = (video_id, prompt_id)
        if key in self._ordered:
            return
        self._ordered.add(key)
        task = asyncio.create_task(self.read_with(video_id, prompt_id), name=f"youtube-reading-{video_id}")
        self._named.add(task)
        task.add_done_callback(self._named.discard)
        task.add_done_callback(lambda _: self._ordered.discard(key))

    async def _read_with(self, video, transcript: str, language: str, prompt_id: int, *, counts: bool = True) -> None:
        analyser = self._providers.analyser
        assert analyser is not None
        film = Film(
            video_id=video.video_id,
            title=video.title,
            channel_title=video.channel_title,
            published_on=video.published_at.date(),
            language=language,
        )
        async with self._pool.acquire() as conn:
            version, prompt = await store.prompt_to_read_with(conn, prompt_id)
        try:
            analysis = await analyser.read(film, transcript, prompt=prompt)
        except asyncio.CancelledError:
            raise
        except ReadingUnusable as err:
            # An answer about this film that will not be stored: paid for, and one of the film's attempts.
            self._providers.meter.record(budget.ANALYSER, budget.TOKENS, err.tokens)
            log.warning("reading %s is unusable: %s", video.video_id, err)
            # The film's failures are the loop's: a reading ordered by hand is not one of its attempts.
            if counts:
                async with self._pool.acquire() as conn:
                    await store.record_reading_failure(conn, video.video_id)
            return
        except Exception as err:  # noqa: BLE001 - whatever a model provider raises must not stop the batch
            # A key, a quota, a rate limit or a dropped connection says nothing about the film, so it spends none of
            # the film's attempts — an hour's outage would otherwise strand every film it touched for good.
            log.warning("reading %s failed: %s", video.video_id, err)
            return
        self._providers.meter.record(budget.ANALYSER, budget.TOKENS, analysis.input_tokens + analysis.output_tokens)
        async with self._pool.acquire() as conn:
            await store.save_reading(
                conn,
                video.video_id,
                prompt_id=prompt_id,
                prompt_version=version,
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
