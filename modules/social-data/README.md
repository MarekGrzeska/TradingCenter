# social-data

The post archive. One door to each social source, one database, two surfaces in one process: the
REST contract the terminal and pocket read, and four tools at `/mcp` the workbench reads.

A post is a market input the way a candle is: it happened at a moment, it is worth keeping after
everybody has scrolled past it, and the question asked of it later is not the question asked at the
time. This module keeps them. It decides nothing and alerts on nothing.

```bash
uv run alembic upgrade head
uv run uvicorn social_data.app:app --reload --port 8090
uv run pytest        # unit; anything needing a database skips without Docker
uv run pytest -m db  # against a throwaway PostgreSQL (testcontainers)
uv run ruff check .
uv run pyright
```

Port **8090**. Not 8040 or 8050, which stay nobody's on purpose: a `.env` left pointing at either
has to keep reading as a server that is off, rather than reaching a working module that is not the
one it meant.

## What it collects

The unit is a **post**: its source, the identifier that source gave it, its author, its text, when
it was published and when this module first saw it. Identity is the pair *(source, external\_id)* —
two sources are free to number their posts the same way, and one day they will.

**Collection is the module's own loop, never a side effect of a read.** In the application this came
from, asking for a day's posts fetched the feed and wrote what it found, so what the archive held
depended on who had looked and when. Here a read reads.

**There is no backfill.** The feed answers questions about the past, so reaching backwards would be
possible; the archive starts on the day it was deployed instead, and says so. An archive that begins
at a known moment is worth more than one that begins wherever the first pass happened to reach.

## What a model made of it

Each post carries at most one **reading**: a Polish translation, a list of topics and a market-impact
score from 1 to 10 — each stamped with the model that produced it and the moment it did. The module
holds somebody else's judgement, and never presents it as its own.

Re-reading **overwrites**. The history here is the post; the score is not history, and nobody
reconstructs what a model thought last week about a post from last month. What survives an overwrite
is the bill: token usage is written per post and per operation, because the money was spent on the
reading that no longer stands too.

The score is computed at collection rather than when somebody asks, and that is what makes it
useful to a tool: `min_score` has to filter on something that already exists. Asking a model at
question time would give a different answer in two conversations about the same sentence and would
pay per question rather than once per post.

**Without an API key the module collects and does not enrich.** That is a supported state, walked by
its own tests: readings stay empty and `/state` says why, rather than the screen showing posts with
no explanation.

## Four tools, none of which write

Read the recent posts, read an explicit window, open one post in full, ask what the archive is
doing. That last one exists so a model can say "the archive has not collected for three hours"
instead of "there are no posts" — the two are indistinguishable from the data alone.

The set departs from `polymarket-data`, whose tools write, and the difference is the reason rather
than a preference: there the writing tools change the **list of observations**, which is a list an
operator curates. Here the source is collected whole and there is no list to add to, so a writing
tool would have nothing to write that the loop is not already writing.

Lists return an excerpt; the full text is a separate call. A day of posts at full length is a
context window spent before the model has done anything with them.

Which caller reaches which surface is this module's own record, route by route
(`social_data/caller_access.py`), not the platform's: Easy Auth authorizes an application, so a
caller admitted to the tools would otherwise be past every REST route as well.

## Where the shape came from

The functionality was read out of `MarekGrzeska/MarketTools` (C#), where it is 1 134 lines across a
module that also holds prediction markets, news and Telegram. Three of its choices are reversed here
and the reasons are in `openspec/changes/archive/…-social-data-collects-the-posts`: a read that
wrote, a translation-and-score layer with no stamp on it, and a name tied to the one source it had.

Telegram is not here. Neither is the news aggregator. Both are somebody's next decision, not this
module's missing half.
