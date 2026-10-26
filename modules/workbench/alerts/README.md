# alerts

Who is told what, and when. The rules the operator sets in the terminal's **Alerts** tab, the clock that looks at them,
and the delivery through the door to Telegram. A package of the workbench, served under **`/alerts`** — **mounted only when
`ALERTS_DATABASE_URL` is set**; absent, the process runs without it and the archives collect and read as before and tell
nobody. Its own database `alerts`, its own migration chain (`alembic-alerts.ini`, lock key 8120), two read-only tools at
`/mcp`. Specified by `openspec/changes/alerts-package` (and, once archived, the `alerts-*` specs).

```bash
# from modules/workbench
uv run alembic -c alembic-alerts.ini upgrade head    # the process runs it itself too
uv run pytest tests/alerts                            # anything needing a database skips without Docker
```

## A rule

`source` + `destination` (+ `bot`) + `template` + a rhythm. The `bot` is the @name to tell through; empty means the recipient's only bot, and a recipient with several bots makes a rule that did not choose one a defect, never a guess. The source is one of two kinds, and they are not two flavours of one thing:

- **a value** — a read-only tool of this process (`get_last_price`, an indicator, a prediction market's price) is asked
  again and again, and the rule goes off on the step from *no* to *yes*, not on every look that finds yes. The first look
  only sets a baseline, a look that could not learn the value is a third thing (never a *no*), a crossing inside the
  cool-down is a line of history and not a message, and nothing here calls a model;
- **an event** — a package announced a type of event with the schema of its attributes (`youtube.film.read`,
  `social.post.read`, `teams.run.finished`) and publishes one when it happens; the rule's filter is a list of terms on
  those attributes, all of which must hold.

A rule is **checked when it is saved** against what exists — the tool, its arguments, the field of its answer, the event
type, the attribute and the comparison its type allows, the recipient, the slots of the template — and refused with every
reason at once, each with the field it belongs to. The same function checks a draft.

## What reaches a phone

A rule going off is written as a **fire** before the door is asked, leased while it is sent, and then: delivered; tried
again after the wait the door named (or a doubling one) for `ALERTS_RETRY_WINDOW_HOURS` and let go unsent after that;
refused for good (unknown or blocked recipient — not asked twice); throttled (a rule tells at most `ALERTS_MAX_PER_HOUR`
times an hour, and the operator hears *once* that it was cut). Delivery is at least once: a crash between Telegram taking a
message and the fire being marked tells twice, never zero times. A one-time rule switches itself off when its message is
delivered, and takes its "already told" back if the message never arrives. A message longer than one Telegram takes
(16 000 characters at most) goes as several of 3 500, cut at a paragraph, a line or a word; the fire counts the parts
that arrived (`parts_sent`), so a retry sends only the rest, and it is delivered after the last.

## Who calls it

| | |
|---|---|
| the terminal (`ALERTS_REST_CALLER_APPLICATION_IDS`) | `GET /catalog` (everything a rule can be made of), `GET/POST /rules`, `PUT/PATCH/DELETE /rules/{id}`, `GET /rules/{id}/history`, `POST /drafts`, `GET /state` |
| the packages of this process, as this process | `PUT /event-types/{name}` and `POST /events`. **Only these two refuse the operator's application** — an event accepted from the internet is a message on the phone written by a stranger |
| the conversation and the teams, as functions | `alert_rules` and `alert_fires` (read-only) and `propose_alert_change` (what a described change would make of a rule; costs tokens, so not read-only) — no tool makes, changes or removes a rule |

The producers keep their own *already told* marker and write it only after this package accepts an event; the same
occurrence published twice (`type` + `source_key`) is one event and one alert.

## A rule from a sentence

`POST /drafts {sentence}` shows a model what exists (read-only tools with their numeric fields, event types, recipients, the
pairs the archive follows) and asks for one structured answer. The answer goes through the same validation as a saved
rule and comes back as a **proposal** — a rule to fill the form with, and every reason it is wrong; nothing is stored but
the tokens, which have a daily ceiling. It has its own key (`ALERTS_OPENAI_API_KEY`); without one everything else works.
With `rule_id` the sentence is a change to that rule: the model also sees it, and the proposal is the whole rule as it
would then stand (bot, hourly ceiling and switch carried over); the operator still saves it with `PUT`.

## Configuration

`ALERTS_DATABASE_URL` (all-or-nothing, like the other packages) and everything else under `ALERTS_`: the clock's tick, the
shortest interval a rule may look at (`MIN_INTERVAL_SECONDS`), the retry window, the hourly cap, the events' retention, the
draft's model and daily ceiling, and the REST caller list — its own, because these routes decide who is told what. The
workbench's `.env.example` is the list. The package needs from the host a tool surface (`alerts.catalog.ToolSource`) and a
client over the door to Telegram; it imports neither, which is what `tests/test_layering.py` holds.

## What it does not do

It does not decide whether a price is *right*, and it does not look at a value faster than `MIN_INTERVAL_SECONDS`: a rule
sees the price at each look, so a spike that returns between two looks is not caught (`get_last_price` carries no high/low
of a forming period, on purpose). It does not tell anyone through anything but the door to Telegram, and a rule cannot run a
team — both are the next change this package is the right place for.
