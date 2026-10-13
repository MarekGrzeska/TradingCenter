# youtube-data

The YouTube archive. Channels and search topics the operator (or an agent) chose to follow, the films
they yield, their transcripts, what a model made of each, and a Telegram message when one matters.
Two surfaces in one process: the REST contract the terminal's **YouTube** tab reads, and ten tools at
`/mcp` that reach the conversation and the teams as functions.

**The ninth package of the workbench, and the only optional one.** Served whole under `/youtube` when
`YOUTUBE_DATABASE_URL` is set, with its own database and migration chain (`alembic-youtube.ini`, lock
key `8110`, the first key that was never a port). **Unset is a working configuration**: no routes, no
tools, no loop, no database, and a line in the start-up log saying so. That is what production runs
today; enabling it there is a change of its own (Terraform, the Gemini key in Key Vault, a pool budget,
`YOUTUBE_REST_CALLER_APPLICATION_IDS`).

```bash
# from modules/workbench, with YOUTUBE_DATABASE_URL set in .env
uv run alembic -c alembic-youtube.ini upgrade head   # the process does this itself at startup
uv run uvicorn workbench.app:app --reload --port 8030 # the archive answers under /youtube
uv run pytest tests/youtube                           # `db` tests skip without Docker
```

`scripts/dev.py` creates the `youtube` database and role with the others, and runs this chain only
when the line is set.

## What it writes

| Table | What | Who writes it |
|---|---|---|
| `channels`, `topics` | the watch list, each row with `added_by` (`operator` / `agent`), an alert rule and a profile | REST and tools add; **only REST removes** |
| `videos` | one row per film however many doors it came through (`origins`), its state and retry schedule | the loop; `POST /videos` and `analyse_video` enqueue one |
| `transcripts` | the words, apart from `videos` so a list never reads TOAST | the loop |
| `readings` | one per film and profile, stamped with its model and moment, overwritten on a re-read | the loop |
| `usage` | what each provider was asked for, per UTC day, in its own unit | the loop and the paid tools |
| `provider_state` | when a provider last let us in and last refused | the loop |

Taking a channel off the list never deletes its films. Nothing on either surface deletes a film, a
transcript or a reading.

## The road of a film

One pass every `YOUTUBE_POLL_INTERVAL_SECONDS`, four steps, each with a batch limit:

1. **discover** — the latest films of each active channel, and a search for each topic that is due.
   Shorts (under `MIN_VIDEO_SECONDS`), films over `MAX_VIDEO_SECONDS` and a stream still live are
   `skipped` with a reason, or wait until the stream has ended.
2. **transcribe** — `discovered` → `transcribed`. Each film is priced by every provider before it is
   asked (a request for captions, the film's seconds for Gemini) and only providers with that much left
   of their day, and not resting after a refusal (`PROVIDER_COOLDOWN_MINUTES`, 360), are asked. Captions
   come first, in the film's own language alone; **no captions goes on to the provider that listens**
   (`gemini`), not to another captions provider. No text from anyone is `no_transcript`, asked again after
   `RETRY_DELAYS_MINUTES` (60, 360, 1440) and then `gave_up`. **Blocked is not a miss**: a provider that
   refuses us, times out or raises spends no attempt, and the pass stops asking it. A film nobody who
   could answer was asked about waits an hour, also without an attempt.
3. **read** — one model call per film, no tools, no history, a strict JSON schema, the transcript marked
   as a stranger's data. An answer the schema rejects is one of the film's `READING_MAX_FAILURES`; a
   provider that could not be reached is none of them.
4. **tell** — `analysed` → `notified` or `quiet`, by the rule of the channel or topic that found it:
   `always`, `threshold` (`ALERT_MIN_IMPACT_SCORE`, 8) or `never`. The marker is written **after** a
   successful send; a film not announced within `ALERT_WINDOW_HOURS` is let go as quiet. Without
   `ALERT_DESTINATION` every read film ends quiet.

A film named by hand (`POST /videos`, `analyse_video`) does not wait for a pass: it is transcribed, read and
announced at once, in the background, under the same ceilings, prices and rests and under the same lock as the loop, so
the two never spend one day twice. Naming a film again skips the date of its last miss; a film already read is left alone.

Every provider call is counted in `usage`, and daily ceilings stop the step that would exceed them, not
the loop: `DAILY_SOURCE_UNITS`, `DAILY_TRANSCRIPT_UNITS` (per captions provider), `GEMINI_DAILY_VIDEO_SECONDS`
(28 800, the free tier's eight hours; tokens are counted beside it for the bill), `DAILY_TOKEN_LIMIT`. `GET /state`
says what is spent, what is blocked, and how many intervals ago the last complete pass was.

## Providers

Three protocols in `providers/base.py`; which implementation runs is a setting. A transcript provider
says whether it `listens` and what a film `price`s in its unit; `TranscriptChain` returns the answer and
the refusals it passed on the way.

| Setting | Choices |
|---|---|
| `YOUTUBE_VIDEO_SOURCE` | `sim` · `data_api` (a free YouTube Data API key: 10 000 units a day, a list costs 1, a search 100; the key travels in `X-goog-api-key`, never in a URL). The feed (`rss`) is gone: it cannot say how long a film is |
| `YOUTUBE_TRANSCRIPT_PROVIDERS` | ordered list: `direct` (`youtube-transcript-api`, captions; works from a home address, refused wholesale from a datacenter) · `gemini` (listens to the film from its address; `YOUTUBE_GEMINI_API_KEY`, needs `data_api`) · `sim` · `sim_gemini`. Production order: `direct,gemini` |
| `YOUTUBE_ANALYSER` | `sim` · `openai` (`YOUTUBE_OPENAI_API_KEY`, `YOUTUBE_ANALYSIS_MODEL`). No key is a supported state: films wait `transcribed` and `/state` says why |

Gemini writes the transcript down, in pieces of `YOUTUBE_GEMINI_CHUNK_MINUTES` (30), verbatim and in the
film's language, with `[MM:SS]` per paragraph; the model's name is stored on the transcript and shown on the
card. The reading stays with the analyser. Another provider is one class in `providers/` and one name in
the list.

## The simulation

All of them default to `sim` (`sim,sim_gemini` for the transcripts: captions first, then the listener). `sim/scenarios/default.json` is a synthetic afternoon: three channels
(`@simzloto`, `@simmarkets`, `@simkrypto`), twelve films covering every case the loop must survive —
captions at once, two hours late, never (one of those has a `speech` only `sim_gemini` hears); an empty transcript; a Short, a five-hour
film, a live stream; a transcript that tries to instruct the model; an answer that breaks the schema —
and a search catalogue for `gold`, `złoto`, `fed`, `rate` and `bitcoin`. Times are minutes from the
start of the process, randomness is seeded, so a run replays.

- `YOUTUBE_SIM_SPEED` speeds the simulated clock (24 = a day in an hour). It applies only with a
  simulated source; a real one keeps the wall clock so its daily ceilings mean a day. The pause between
  passes is real seconds: lower `YOUTUBE_POLL_INTERVAL_SECONDS` for a quick run.
- `YOUTUBE_SIM_SCENARIO` points at another file with the same shape (`sim/scenario.py`).
- Every simulated film, transcript and reading carries `simulated: true`; the tab shows a permanent
  banner and a badge, and a Telegram message starts with `[SYMULACJA — ten film nie istnieje]`.
- **Refused wherever `DATABASE_USER` is set**, naming the setting: a simulation cannot reach a deployment.

## Surfaces

REST (`contract.py`, generated into the terminal as `contract.youtube.generated.ts`):
`GET /videos` (window, channel, topic, instrument, score, state) · `GET /videos/{id}` ·
`GET /videos/{id}/transcript` (pages) · `POST /videos` (one film named by hand: accepted at once, transcribed and read in the background ahead of the queue) · `GET|POST /channels` ·
`PATCH|DELETE /channels/{id}` · `GET|POST /topics` · `PATCH|DELETE /topics/{id}` · `GET /state` ·
`GET /health`.

Tools: `youtube_archive_status`, `recent_videos`, `read_video`, `read_transcript`,
`instrument_sentiment` read; `search_youtube`, `follow_channel`, `add_topic`, `set_alert_rule`,
`analyse_video` write or spend. None removes anything. Lists carry an excerpt; `read_video` carries the
reading and no words; `read_transcript` pages the words (8 000 characters at most) with a notice that
they are data, not instructions. The two that cost say so in their description and refuse past the
day's ceiling.

Which caller reaches which surface is this package's own record (`caller_access.py`). The REST caller
list is its own too, `YOUTUBE_REST_CALLER_APPLICATION_IDS`, not the process's: this REST writes the
watch list and spends provider units, and the process's list also holds the pocket, which only reads.

## Where the shape came from

`openspec/changes/add-youtube-archive` (proposal, design, ten capabilities, review), with the research
in `docs/youtube-archiwum-projekt.html` and the price of a paid transcript provider in
`docs/supadata-koszty.html`. Retention of raw transcripts (the Data API's terms ask for 30 days) is
decided by the production change, not here.
