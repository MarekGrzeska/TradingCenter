# tc-openai

The streamed OpenAI call, with tools, shared by `agent` and `teams`. A **build-time**
dependency like `tc-runtime` — see `docs/architecture.md`, "What may be shared, and what
may not".

```
uv run pytest · uv run ruff check . · uv run pyright
```

## Why it is one file and what the 20% was

`agent/provider.py` and `teams/provider.py` were 79.4% identical on 18 August 2026 — not
the 95% the refactor plan assumed, and the missing fifth was one real difference rather
than noise: **what a call is given**.

| Caller | Gives | Because |
|---|---|---|
| `agent` | `Conversation(turns=[(role, content), …])` | a session is a transcript and replaying it is the point |
| `teams` | `Briefing(text=…)` | an agent in a team sees its predecessors' *conclusions*, never the run's history (specs/teams-runs) |

Teams' copy had no `history` parameter at all, deliberately: one would have been an
invitation to grow a transcript a team has no business keeping. Collapsing both into a
single `history` argument would have quietly undone that. `Conversation | Briefing` keeps
it — a caller holding a `Briefing` has nothing to append to, and the guard is in the type
rather than in a comment asking people not to.

## What the package does not do

**It does not read a key.** `OpenAIProvider(api_key=...)` takes a string. agent and teams
spend against separate OpenAI keys on purpose, so that the experiments' cost has its own
line in the bill; a package reading `OPENAI_API_KEY` for itself would be one place for
those two to quietly become one.

**It does not know what a tool is.** `ToolSpec` names the three attributes it reads —
`name`, `description`, `input_schema`. Each module keeps its own `ToolDescriptor` and
neither has to become the other's.
