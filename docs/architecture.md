# Architecture

## The shape

One repository, many modules, no shared runtime. A module is a directory under `modules/`
that runs on its own and publishes a contract. Nothing imports across that boundary at
runtime; source may be shared at build time through `packages/`, under the conditions in
"What may be shared, and what may not".

```
                  capital.com
                  (REST + WS)
                       │
                       ▼
        ┌──────────────────────────────┐
        │  capital-gateway             │──────────────────┐
        │  trade · history · stream    │                  │
        └──────────────┬───────────────┘                  │ instruments
                       │ HTTP + WebSocket                 │
                       ▼                                  │
        ┌──────────────────────────────┐                  │
        │  market-data                 │                  │
        │  archive · coverage · rollups│                  │
        │  REST  ·  MCP tools at /mcp  │                  │
        └──────┬───────────────┬───────┘                  │
     candles,  │               │  the same archive,       │
     the live  │               │  reduced for a model     │
     stream    │               │  (MCP, streamable HTTP)  │
               │  ┌────────────┘                          │
               │  │                                       │
               │  │  ┌──────────────────────────────┐     │
               │  ├─▶│  agent                       │◀─── OpenAI
               │  │  │  conversation · tools · cost │     │
               │  │  └──────────────┬───────────────┘     │
               │  │                 │ HTTP, streamed      │
               │  └────┐            │                     │
               │       ▼            │                     │
               │     ┌──────────────────────────────┐     │
               │     │  teams                       │◀─── OpenAI
               │     │  agents as data · runs · cost│     │
               │     └──────────────┬───────────────┘     │
               │                    │ HTTP, streamed      │
               ▼                    ▼                     ▼
                            terminal ◀────────────────────┘
    charts · grid · search · archive panel · agent panel · teams canvas
```

`terminal` is a consumer, not a peer: it publishes no contract of its own and nothing
depends on it. It reads market data through one interface, and that interface now has two
implementations behind it — candles and the live stream from `market-data`, the instrument
catalogue from `capital-gateway`, composed into a single instance the views never see
through. The charts were not rewritten when the archive arrived, which is the whole point
of having had the interface first. `agent` is a third, unrelated source behind its own
interface — a conversation and its cost, nothing that shares a shape with a candle. `teams`
is a fourth, and unlike the agent's it publishes a shape the terminal *edits*: a graph the
operator composes on a canvas and saves as a new revision.

`market-data` sits between the two on purpose. capital.com counts its rate limit against the
account rather than the process, so a second client anywhere spends the same allowance twice:
the gateway owns the only door to the provider, and the archive refuses to start if its
upstream URLs point anywhere else.

**The archive serves two surfaces, not one.** `market-data` publishes the REST contract the
terminal reads and, at `/mcp`, eleven read-only MCP tools handing the same archive on in a
different shape — a chart wants every candle, a model wants a summary, so the read comes
out reduced rather than proxied. Both are the same process reading the same functions: a
tool and a route are two consumers of one layer (`market_data/reads.py`), which is what
stops a decision like "collected beats computed" from being made twice.

Those tools stood in a module of their own until 19 August 2026, and what that module was
made of turned out to be mostly the separation itself: an HTTP client to market-data, a
committed copy of market-data's schema, a script policing the copy, and an identity to
present at the door. All of it is gone, and not one tool, ceiling or sentence about
uncertainty went with it. What did go is the desktop client's stdio door — the tools are
reachable over the network only now, which is where their two real callers already were.

The merge moved a question rather than answering it. A gate in front of an application
authorizes the **application**, so admitting `agent` and `teams` for eleven read-only tools
would admit them to `POST /pairs` and `DELETE /pairs/{symbol}` as well. What keeps them to
`/mcp` is the module's own record of caller against surface
(`market_data/caller_access.py`), with a refusal test for every pair that has no business
together — and a path the record does not name is refused rather than passed.

`agent` reaches OpenAI and the archive's tool surface, and nothing else in this diagram.
The edge is deliberately narrow: no route to the REST contract, no entitlement to one, and
no code that would know what to do with a candle. What it has is a tool list it did not
write, fetched at the start of a session and used as given.

That edge is the one thing in this diagram with no committed copy of its contract
anywhere. Every other arrow has one — the terminal's generated types, trading-mcp's
snapshot of the gateway's document, the terminal's hand-written agent DTOs — because HTTP
does not describe itself at call time. MCP does: the tool names, descriptions and argument
schemas arrive in the same session that uses them, so there is no second copy to drift and
nothing to regenerate. The trade is that a tool added on the archive's side reaches the
model with no review on the `agent` side, which is safe exactly as long as the archive's
own specification keeps forbidding a tool that writes — and, since the merge, as long as
the caller record keeps the writing routes out of that caller's reach.

`teams` sits beside `agent`, not under it: the same edges out to OpenAI and the archive,
its own database, its own key, and no edge between the two modules at all. What differs is
what it stores. `agent` keeps a conversation; `teams` keeps the *definition* of a team —
agents, their roles and the dependencies between them — as data in a revision that never
changes once written, so a run months apart from another can be compared against the same
definition rather than against a memory of it.

## The order path

`teams` has one more edge than the diagram above draws, and it is drawn apart because the
picture is a straight line while the read path is a fan — folding it in would cross three
arrows to say something simpler than any of them:

```
        ┌──────────────────────────────┐
        │  capital-gateway             │  the only door to the provider,
        │  trade · history · stream    │  for orders as much as for candles
        └──────────────▲───────────────┘
                       │ HTTP · caller key on every request, loopback included
                       │ demo confirmed by asking, not by configuration
        ┌──────────────┴───────────────┐
        │  trading-mcp                 │
        │  MCP tools · account · orders│
        └──────────────▲───────────────┘
                       │ MCP (streamable HTTP) · exactly one named caller
        ┌──────────────┴───────────────┐
        │  teams                       │
        └──────────────────────────────┘
```

A module of its own rather than a switch on something that reads. The archive's tools stay
read-only to the letter, and the tool server that writes is a separate deployable with a
separate identity, so "which module may move the account" is answered by a list of callers
rather than by a flag inside a process that also serves candles.

**One more, and it points the other way.** `teams-mcp` puts the *catalogue* behind
MCP tools so that `agent` can build and correct a team from the chat — the same shape one
level up, one named caller, its own identity:

```
        ┌──────────────────────────────┐
        │  teams                       │  the catalogue, the runs, the money
        └──────────────▲───────────────┘
                       │ HTTP · Authorization = **the operator's own token**, forwarded
        ┌──────────────┴───────────────┐
        │  teams-mcp                   │
        │  MCP tools · build · run     │
        └──────────────▲───────────────┘
                       │ MCP · exactly one named caller
                       │ X-Operator-Authorization carries the person
        ┌──────────────┴───────────────┐
        │  agent                       │
        └──────────────────────────────┘
```

The arrow into `teams` is the one worth reading twice. Every other edge in this system is a
module proving *itself* to the next one; this one carries the credential of the person who
asked, taken off the request `agent` is serving and passed no further. That is not a
detail of the transport: `teams` filters every statement by owner, so a module acting on
its own identity would create teams nobody can see — existing, costing money, impossible to
open in the terminal. The two credentials never merge, and they travel in two headers for
exactly that reason.

The demo-only guarantee lives here and nowhere else that can be turned off: `trading-mcp`
asks `capital-gateway` what environment it is bound to and refuses to open a port unless
the answer is the demo one. It is not a setting of its own — a module that decided this
from its own configuration would be a module an environment variable could aim at real
money. Everything the operator *can* change — how large an order may be, how many a run or
a day may place — lives one module up, in a `teams` revision, where every one of them is
optional and an absent one means no limit at all. That split is the rule worth carrying to
the next ceiling anyone adds: **a number the operator must not be able to change belongs in
`trading-mcp`; a budget that is theirs belongs in the revision.**

## What may be shared, and what may not

**Nothing is shared at runtime.** A module reaches another only through a published
contract — HTTP described by OpenAPI, MCP, or typed events. No module imports another
module's package, reads another module's database, or runs on another module's identity.
That boundary is the architecture and it does not move.

**Source may be shared at build time, under conditions.** Two modules may depend on a
package under `packages/`, which is resolved into each module's own lock and compiled
into each module's own image. Nothing is published to a registry and nothing is versioned:
there is one copy in the repository, and an image carries whichever copy was there when it
was built. A module still deploys, tests and rolls back alone.

Three conditions, and a candidate that fails any of them stays copied:

1. **Measured, not assumed.** The code is already a hand-maintained copy — at least 70%
   identical line for line between two modules. `scripts/measure-duplication.py` is what
   answers this, and a proposal to share something says what it printed.

   Code that does not exist yet cannot be measured, and the condition read literally said
   a new shared thing must first be written out three times and wait for someone to notice.
   So there is a second route to the same condition: the code is **new**, and it has more
   than one consumer and is identical for every one of them from the first day. A proposal
   taking that route names the consumers, and conditions 2 and 3 carry the whole weight —
   which is where they were carrying it anyway. `tc_mcp_kit.tool_schemas` (18 August 2026)
   is the first thing to arrive this way: one rule for slimming a published tool schema,
   for the three modules that publish one.
2. **Every difference is an argument.** What differs between the copies has to become a
   parameter, not a branch on which module is calling. A shared file with a switch per
   consumer is the base class this rule used to forbid, wearing a different hat.
3. **Every consumer is tested on every change.** A change under `packages/` runs the test
   job of each module that depends on it (`.github/workflows/checks.yml`). Sharing source
   converts a visible drift into an invisible regression unless this holds.

### Why the rule changed

It used to read: no shared library at all, because shared code is coupling no contract
records, and duplication is at least visible in a diff. The reasoning was sound and the
price turned out to be higher than the argument assumed. Measured on 18 August 2026:
**959 lines** of production Python existed only as hand-maintained copies of each other,
and four separate bugs had been fixed in one copy and not the other — one of them the
retry on the order path, fixed in `teams` and missing from `agent` for a day.

The old rule protected independent deploy, test and deletion. A build-time package
protects all three as well, because the coupling is resolved before an image exists. What
it does not protect on its own is the fourth thing the old rule gave for free — that a
change cannot break a module its author was not looking at — and that is what condition 3
buys back, in CI rather than in production.

**What this costs, stated plainly.** A module is no longer deleted by deleting its
directory alone: its entry comes out of the packages' consumer lists too, and a package
with no consumers left goes with it. And the build context of a containerised module is
the repository root rather than its own directory, because uv resolves the path
dependency while installing the lock.

## Module anatomy

```
modules/<name>/
  <package>/        the code
  tests/            its own suite, runnable with no other module present
  pyproject.toml    its own dependencies
  README.md         what / run / test / contract, on one screen
  .env.example      what it needs configured
```

A module is deleted by deleting its directory, plus its line in the dependency list of
any package under `packages/` — see the section above. If anything *else* breaks, the
something else was reaching past a contract.

## What a contract is

HTTP described by OpenAPI, a CLI, or typed events. Whatever it is, it is **published** —
a consumer depends on the contract, never on the implementation.

Where a contract cannot be described by the tool at hand, the gap is stated rather than
left for a reader to discover. `capital-gateway` publishes OpenAPI for its routes and
documents its WebSocket messages in its README, because OpenAPI has no vocabulary for
WebSocket payloads, and a test asserts the path is absent from the schema so the omission
stays deliberate.

## Ownership of data

A module owns its storage. `capital-gateway` deliberately owns none: it is a window onto a
provider, not an archive. The archive is `market-data`, a module whose job that is — giving
one candle two origins, with only one of them reachable, is worse than not storing it at all.

It is also the first module here with state that cannot be recreated by restarting it, and
that changes what a module directory contains: `migrations/` alongside the code, the schema
written as the statements a deployment runs. Rebuilding three years of minute candles for a
hundred instruments costs roughly 27 hours of provider calls, which is what turns backups
from a good habit into a requirement.

## Relationship to TradingHub

TradingHub is the previous ecosystem and still runs. Its modules move here one at a time;
`capital-gateway` supersedes its `broker-gateway`, which stays where it is until retiring
it is a separate, deliberate decision.

Prior art there is worth reading before rebuilding something. It is not worth importing.
