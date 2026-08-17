# teams-mcp

MCP tools over the `teams` catalogue, so a team can be built and corrected by talking to
the agent in the terminal instead of by dragging boxes on a canvas.

Port **8070**. One caller: `agent`. One upstream: `teams`.

```
terminal ──> agent ──MCP──> teams-mcp ──HTTP──> teams
```

## What it is for

Composing a team on the canvas is good when you know what you want to build and expensive
when you are still looking — and looking is the normal state of this work. The harder half
is correcting one: a run leaves a trace, the conclusion from that trace is "this agent
gets too little context", and moving that conclusion into the definition by hand means
retyping a form in another tab. A model that has just read the trace can write the
revision instead.

## The thing to understand before reading the code

**Every tool here acts in a person's name, and there are two credentials in play.**

| Header | Carries | Answers |
|---|---|---|
| `Authorization` | this module's caller (`agent`, a managed identity) | who is calling teams-mcp |
| `X-Operator-Authorization` | the operator's own token, forwarded | in whose name they are calling |

The second is presented to `teams` as its `Authorization`, so the authenticator in front
of `teams` puts the operator's principal on the request — exactly what happens when the
terminal calls it directly. That is the whole mechanism by which a team created from the
chat is **the operator's**: it shows up in their Teams tab, it can be edited by hand, and
it spends against their limits.

Without that token every tool refuses and says so. It is never read from a tool argument —
a model writes whatever it finds plausible, and an identity that can be written is an
identity that can be borrowed.

## Commands

```
uv run python -m teams_mcp          # port 8070, one transport, no stdio to choose
uv run pytest                       # 61 tests
uv run ruff check .
uv run pyright
uv run python scripts/contract.py check     # the committed snapshot of teams' wire
uv run python scripts/contract.py generate  # rewrite it after teams' contract moves
```

## Settings

Copy `.env.example`. Locally nothing is required: the defaults reach `teams` on loopback.

| Setting | |
|---|---|
| `TEAMS_URL` | where `teams` is. Loopback locally |
| `TEAMS_SCOPE` | set **only** when the URL is remote; a scope against loopback is refused at startup, and so is a remote URL without one |
| `TEAMS_REQUEST_TIMEOUT_SECONDS` | 30 — past the slowest thing one tool asks for |
| `TEAMS_MCP_PORT` / `TEAMS_MCP_HOST` | 8070, loopback. The container overrides the host |
| `REQUIRE_AUTHENTICATED_PRINCIPAL` | false locally, true in Azure |

There is no setting for the operator's credential, and there will not be one: it arrives
per call or the call is refused.

## The tools

Twelve, grouped by what somebody is trying to do rather than by `teams`' thirty-six
routes.

| | |
|---|---|
| `list_teams`, `read_team` | what exists, and what one looks like |
| `create_team` | a team and its first revision, in one call |
| `revise_team` | name only what changes; the rest of the revision is carried over |
| `list_models`, `list_tools` | what may go in a definition |
| `run_team`, `read_run`, `list_runs` | start one, read what it did and what it cost |
| `schedule_team`, `trigger_team` | on a clock, or on a market condition |
| `list_schedules` | what is set, what fired, and what was skipped and why |

`read_run` answers for a run that is still working and says that it is — a partial trace
presented as a result is the mistake worth avoiding here.

**`unattended_ack` is not a parameter and must not become one.** `teams` refuses a
schedule over a revision carrying a tool it cannot confirm is a read, unless that
acknowledgement is present. Offered as a field, a model would set it the moment a refusal
was in its way, and a safeguard would disappear without a line of code changing. The
operator ticks that box in the terminal, where they can see what they are agreeing to.

## What this module does not do

- **No limits of its own.** Daily cost, order ceilings, unattended-work refusals — all of
  them are `teams`', checked on the same path a click in the terminal takes. A new door
  into a module is not a new policy for it.
- **No market data.** That is `market-mcp`, which the agent reaches separately.
- **No retry on a write.** A repeated `create_team` is a second team and a repeated
  `run_team` a second bill. Reads retry once.
- **No copy of `teams`' catalogue.** Models and tool names come from `teams` at call time.
  The committed OpenAPI snapshot is a check, not a source: `scripts/contract.py check`
  fails when `teams`' document moves, which is how a drift becomes a red build rather than
  a 404 in a tool call.

## One thing it cannot see

Whether `teams`' clock is switched on. That setting is `teams`' and is not published on
its wire, so `schedule_team` and `trigger_team` warn on **every** save that nothing may
fire. Over-warning is wrong about precision; silence would be wrong about fact. Closing it
properly is one field on `teams`' side.
