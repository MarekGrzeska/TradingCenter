# youtube-data

The YouTube archive. Channels the operator (or an agent) chose to follow, the films
they yield, their transcripts, the prompts a model reads them by, what it made of each — and each read film handed to the alerts package, whose rules say whether anybody is told.
Two surfaces in one process: the REST contract the terminal's **YouTube** tab (Films, Channels, Topics, Candidates, Prompts) reads, and eight tools at
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
| `channels`, `topics` | the watch list, each row with `added_by` (`operator` / `agent`); a channel also holds the prompt its new films are read by and, optionally, a filter; a topic holds neither | REST and tools add; **only REST removes** |
| `candidates` | what a topic's search found and a model screened by its metadata: a verdict and a sentence on why, and — once the operator has decided — which decision | the loop; **only REST decides** |
| `topic_runs` | one row per attempt to search a topic: how it ended and the report — what the source returned, what was already known, what became candidates and how they were screened, or why it failed; swept past 30 days | the loop; **nobody edits it** |
| `ignored_channels` | channels whose films never become candidates | **only REST** |
| `videos` | one row per film however many doors it came through (`origins`), its state and retry schedule; a film a channel's filter turned away is kept as `filtered_out` with the reason | the loop; `POST /videos` and `analyse_video` enqueue one, and release a `filtered_out` one |
| `transcripts` | the words, apart from `videos` so a list never reads TOAST | the loop |
| `prompts`, `prompt_versions` | what a model is told to look for in a film; new words are a new version, never an overwrite; a deleted prompt keeps its row | **only REST** writes; the seeded one is edited, never deleted |
| `readings` | one per film and prompt — a summary, one Markdown text laid out by the prompt, a 1-10 score — stamped with model, moment, prompt and its version, overwritten on a re-read by the same prompt | the loop; `POST /videos/{id}/readings` orders another |
| `usage` | what each provider was asked for, per UTC day, in its own unit | the loop and the paid tools |
| `provider_state` | when a provider last let us in and last refused | the loop |

Taking a channel off the list never deletes its films. Nothing on either surface deletes a film, a
transcript or a reading.

## The road of a film

One pass every `YOUTUBE_POLL_INTERVAL_SECONDS` — until the operator saves another interval in the terminal's Settings (see
*Settings* below) — four steps, each with a batch limit:

1. **discover** — the latest films of each active channel, and a search for each topic that is due. **A topic's results are
   not films of the archive**: those that pass the length floor and ceiling and are not already known (in `videos`, from a
   followed or an ignored channel, or already a candidate) are screened by one model call on their title, description,
   channel and length, and stored as **candidates** — nothing is transcribed or read for them. Without a model, or a day
   with tokens left, they are stored `unscreened` and offered all the same.
   **A channel with a filter** puts the films it has not seen to the same model first (see *Channel filter*).
   Shorts (under `MIN_VIDEO_SECONDS`, 180) and films over `MAX_VIDEO_SECONDS` are **not kept at all** —
   never stored when the source lists them, deleted if their length arrives after they were stored, refused with the
   reason when named by hand. A stream still live waits until it has ended.
2. **transcribe** — `discovered` → `transcribed`. **Gemini listens to every film**; YouTube's own captions are
   not read, because from Azure YouTube refuses every request for them. A film is priced before it is asked (its
   seconds) and asked only when the day has that much left; a film the day cannot pay for waits for tomorrow. No
   text (nothing said, an answer cut off, a private film) is `no_transcript`, asked again after
   `RETRY_DELAYS_MINUTES` (60, 360, 1440) and then `gave_up`. **Blocked is not a miss**: a crowded model, a rate
   limit, a timeout or a bad key spends no attempt; the pass stops asking and Gemini rests
   `TRANSCRIBER_COOLDOWN_MINUTES` (15).
3. **read** — one model call per film by the prompt the film was noticed with, no tools, no history, a strict JSON schema, the
   transcript marked as a stranger's data. An answer the schema rejects is one of the film's `READING_MAX_FAILURES`; a
   provider that could not be reached is none of them.
4. **tell** — `analysed` → `notified` or `quiet`. Every read film is handed to the alerts package as a `youtube.film.read`
   event (channel, topic, score, instruments, link and the message to send); what it does with it — tell nobody, tell one
   person, tell another about this channel only — is a rule the operator sets in the Alerts tab, not something this
   archive decides. The marker is written **after** the alerts package accepts the film; a film not handed over within
   `ALERT_WINDOW_HOURS` is let go as quiet. Without an alerts package every read film ends quiet.

A film named by hand (`POST /videos`, `analyse_video`) does not wait for a pass: it is transcribed and read at once, and ends quiet (whoever asked is already looking), in the background, under the same ceilings, prices and rests and under the same lock as the loop, so
the two never spend one day twice. Naming a film again skips the date of its last miss; a film already read is left alone.

Every provider call is counted in `usage`, and daily ceilings stop the step that would exceed them, not
the loop: `DAILY_SOURCE_UNITS`, `GEMINI_DAILY_VIDEO_SECONDS`
(28 800, the free tier's eight hours; tokens are counted beside it for the bill), `DAILY_TOKEN_LIMIT`. `GET /state`
says what is spent, what is blocked, and how many intervals ago the last complete pass was.

## Prompts

A prompt is the operator's words about what to look for in a film and how to lay the text out. The seeded one (`Rynkowy`,
from migration `0003`) is a row like any other with one lock: it cannot be deleted, so there is always a prompt to read by.
A channel holds one prompt (a topic holds none: it reads nothing), and a film takes it when it is noticed — changing it is for films noticed after. Another
prompt reads a film already transcribed on request (`POST /videos/{id}/readings`): no words are asked for, the day's tokens
are spent, the film does not move, and nobody is told.

What no prompt can change is in `analysis.system_message`: the transcript is data, there are no tools, and the answer is
`{summary_pl, text, impact_score}`. An answer outside that is not stored. The agent chooses a prompt by name and cannot write,
edit or delete one.

## Settings

Three numbers live in one row of `loop_settings` and are the operator's from the terminal (`GET`/`PATCH /settings`): the minutes
between passes, and the interval and film count a topic added without limits of its own gets. With no row the environment
stands (`YOUTUBE_POLL_INTERVAL_SECONDS`, `YOUTUBE_TOPIC_DEFAULT_*`), which is why nothing is seeded. The loop reads the interval
after each pass; a save cuts or stretches a wait in progress and the heartbeat's `expected_seconds` follows. Topics already on
the list keep their own limits. The agent cannot change any of it.

## Channel filter

A channel may carry a **filter**: the operator's words (1 to 1000 characters) about which of its films to process. Without one — the
default, and every channel that was on the list before — every new film goes on as always. With one, the films of the channel's latest
listing that the archive has not stored yet are put to the model in one call, on their title, description, channel and length, and
each is stored by the answer: *proposed* goes on the road like any film, *rejected* is stored `filtered_out` with the model's
sentence and is never transcribed, read or announced, and never put to the model again. **A film nobody could judge — no model, a
day without tokens, an answer the schema rejects, no verdict for that one film — is not stored at all** and comes back with the next
listing: passing it unjudged would pay for the very transcript the filter is there to save. Answers that were paid for and said
nothing about a film (a refusal, a broken schema, no verdict) are counted, and after `JUDGE_MAX_FAILURES` (3) the film is stored
`filtered_out` saying it could not be judged; a model that is absent, spent or unreachable counts none. A stream still running, a
premiere and a film of unknown length wait without being put to the model. The price is that a channel which
publishes more than the fifteen films the listing holds between two judgements loses the oldest; `GET /state` says how many active
channels have a filter (`channels_filtered`), next to `model_configured` and the analyser's spent day.

A new filter, a changed one and none at all apply to films found afterwards; a `filtered_out` film stays so. `filtered_out` is left out
of `GET /videos` unless asked for (`state=filtered_out`), and `POST /videos` or `analyse_video` on it — "analyse anyway" — puts it on the
road, by its channel's prompt unless one is named. The operator sets a filter when following (`POST /channels`) or later
(`PATCH /channels/{id}`, where `null` takes it off and leaving it out keeps it); the agent may give one only to a channel it follows
for the first time.

## Providers

Three protocols in `providers/base.py`; which implementation runs is a setting — the real one or the simulation.

| Setting | Choices |
|---|---|
| `YOUTUBE_VIDEO_SOURCE` | `sim` · `data_api` (a free YouTube Data API key: 10 000 units a day, a list costs 1, a search 100; the key travels in `X-goog-api-key`, never in a URL). The feed (`rss`) is gone: it cannot say how long a film is |
| `YOUTUBE_TRANSCRIBER` | `sim` · `gemini` (listens to the film from its address; `YOUTUBE_GEMINI_API_KEY`, needs `data_api`) |
| `YOUTUBE_ANALYSER` | `sim` · `openai` (`YOUTUBE_OPENAI_API_KEY`, `YOUTUBE_ANALYSIS_MODEL`). No key is a supported state: films wait `transcribed` and `/state` says why |

Gemini writes the transcript down, in pieces of `YOUTUBE_GEMINI_CHUNK_MINUTES` (15; `gemini-3.1-flash-lite` by default — measured: a 29-minute film in 79 s, ~170k tokens), verbatim and in the
film's language, with `[MM:SS]` per paragraph; the model's name is stored on the transcript and shown on the
card. The reading stays with the analyser.

## The simulation

All three default to `sim`. `sim/scenarios/default.json` is a synthetic afternoon: three channels
(`@simzloto`, `@simmarkets`, `@simkrypto`), twelve films covering every case the loop must survive (a channel's filter turns away
`simfilm0008`, the one the scenario marks `rejected`) —
Polish and English speech; a film with nothing said; a Short, a five-hour
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

## Candidates

A topic is for finding what the operator did not know to look for, so what it finds is **offered, never read**. The tab's
*Candidates* section lists them newest find first (or newest film first), each with a link to the film on YouTube, its channel
and the model's sentence. Four decisions, each made once and none of them the agent's: *follow the channel* (under the
watch list's ceiling, with a prompt), *analyse the film* (the path of a film named by hand), *dismiss* (the same film is not
offered again) and *ignore the channel* (its films stop becoming candidates until it is let back). The two channel decisions
settle the channel's other open candidates with it. A candidate the model rejected is stored and shown on request, so the
screening can be checked and the same film is never paid for twice.

Screening shares the analyser's key, model and day (`DAILY_TOKEN_LIMIT`); `GET /state` names the missing model or the spent day.

## Topic runs

Every search of a topic is written down, whatever came of it: *found* (new candidates), *nothing new* (the source answered and there
was nothing to offer), *failed* (the source refused or never answered — its message, and Google's own reason and sentence, are kept) and
*skipped* (the source's day could not pay for a search). A failure or a skip that repeats the topic's previous run — same outcome, same
error — within the UTC day is **not written again**: it recurs for as long as its cause lasts, and would bury the runs that mean something.

**A refused search holds its topic back for the topic's own interval** (`topics.retry_at`, shown on `GET /topics`): the source counts a
refusal against the day like any search — 101 units — so retrying on every pass made a failing topic the most expensive thing in the
archive (on 22–24 October eight of them spent the whole 8 000-unit day by morning, and starved the channels' discovery). A search the
source never answered cost nothing and is tried again on the next pass. The hold does not move `last_run_at`, which is where the next
search's window starts; a search that goes through lifts it. The report counts what the source returned, how many of them were already known or belonged to a settled channel, how many
were outside the length bounds, and how the rest were screened — with, for those offered without a verdict, why (`no_model`,
`day_spent`, `unusable`, `failed`, `no_verdict` for a model that answered and left some out). A run keeps the phrase it searched and
outlives the topic; runs older than 30 days are swept when the next is written. `GET /topic-runs` reads them (newest first, optionally
one topic), and `GET /topics` carries each topic's latest. Cost in units and tokens stays in `usage`, per day.

## Surfaces

REST (`contract.py`, generated into the terminal as `contract.youtube.generated.ts`):
`GET /videos` (window, channel, topic, score, state — `filtered_out` only when asked for; a reading without its text) · `GET /videos/{id}` (every reading, with its text) · `POST /videos/{id}/readings` · `GET|POST /prompts` · `PATCH|DELETE /prompts/{id}` ·
`GET /videos/{id}/transcript` (pages) · `POST /videos` (one film named by hand: accepted at once, transcribed and read in the background ahead of the queue) · `GET|POST /channels` ·
`PATCH|DELETE /channels/{id}` · `GET|POST /topics` · `PATCH|DELETE /topics/{id}` · `GET /topic-runs` (`topic_id`, `since` included and `until` excluded as for `/videos`, `limit`) · `GET /candidates` (`view` open · rejected · decided, `sort` found · published, `topic_id`) ·
`POST /candidates/{id}/follow-channel|analyse|dismiss|ignore-channel` · `GET /ignored-channels` · `DELETE /ignored-channels/{id}` · `GET /state` ·
`GET /health`.

Tools: `youtube_archive_status` (with the prompts on offer), `recent_videos`, `read_video`, `read_transcript` read;
`search_youtube`, `follow_channel`, `add_topic`, `analyse_video` write or spend — `follow_channel` and `analyse_video` take an optional prompt name (and `follow_channel` an optional filter), `add_topic` none. None removes anything and none decides about a candidate: a topic proposes, the operator decides. Lists carry an excerpt; `read_video` carries the
readings (each text cut at 8 000 characters) and no transcript; `read_transcript` pages the words (8 000 characters at most) with a notice that
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
