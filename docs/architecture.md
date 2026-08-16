# Architecture

## The shape

One repository, many modules, no shared runtime. A module is a directory under `modules/`
that runs on its own and publishes a contract. Nothing imports across that boundary.

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
        └──────┬───────────────┬───────┘                  │
     candles,  │               │  the same archive,       │
     the live  │               │  reduced for a model     │
     stream    │               ▼                          │
               │      ┌──────────────────────┐            │
               │      │  market-mcp          │            │
               │      │  MCP tools,          │            │
               │      │  read-only           │            │
               │      └───┬──────────────┬───┘            │
               │          │              │ MCP (stdio)    │
               │   MCP    │              ▼                │
               │  (streamable HTTP)  the operator's       │
               │  ┌───────┤           desktop client      │
               │  │       ▼                               │
               │  │  ┌──────────────────────────────┐     │
               │  │  │  agent                       │◀─── OpenAI
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

`market-mcp` is a consumer of `market-data`, the same shape as `terminal`: it reads the
published contract and imports nothing. Where it differs is the shape of what it hands
onward — a chart wants every candle, a model wants a summary, so the same archive read
comes out reduced rather than proxied. It has three callers and they arrive by two doors:
`agent` and `teams`, over streamable HTTP from their own containers, and whatever MCP
client the operator runs on the desktop, over stdio. One tool set, registered once; the
transport decides only how a request gets in, and a second HTTP caller is an entry in
`allowed_applications` rather than a change to this module.

`agent` reaches OpenAI and `market-mcp`, and nothing else in this diagram. That it is not
drawn under `market-data` is the point: the archive is two hops away, and the module has
no address for it, no credential for it and no code that would know what to do with a
candle. What it has is a tool list it did not write, fetched from `market-mcp` at the
start of a session and used as given.

That edge is the one thing in this diagram with no committed copy of its contract
anywhere. Every other arrow has one — the terminal's generated types, market-mcp's OpenAPI
snapshot, the terminal's hand-written agent DTOs — because HTTP does not describe itself
at call time. MCP does: the tool names, descriptions and argument schemas arrive in the
same session that uses them, so there is no second copy to drift and nothing to
regenerate. The trade is that a tool added on the `market-mcp` side reaches the model with
no review on the `agent` side, which is safe exactly as long as that module's own
specification keeps forbidding a tool that writes.

`teams` sits beside `agent`, not under it: the same edges out to OpenAI and `market-mcp`,
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

A sixth module rather than a switch on the fifth. `market-mcp` stays read-only to the
letter, and the two tool servers are separate deployables with separate identities, so
"which module may move the account" is answered by a list of callers rather than by a flag
inside one that reads.

The demo-only guarantee lives here and nowhere else that can be turned off: `trading-mcp`
asks `capital-gateway` what environment it is bound to and refuses to open a port unless
the answer is the demo one. It is not a setting of its own — a module that decided this
from its own configuration would be a module an environment variable could aim at real
money. Everything the operator *can* change — how large an order may be, how many a run or
a day may place — lives one module up, in a `teams` revision, where every one of them is
optional and an absent one means no limit at all. That split is the rule worth carrying to
the next ceiling anyone adds: **a number the operator must not be able to change belongs in
`trading-mcp`; a budget that is theirs belongs in the revision.**

## Why no shared library

Shared code is coupling that no contract records. Two modules importing the same helper
cannot be deployed, tested or deleted independently, and the day one needs the helper to
change is the day both do.

The cost is real and accepted: DTOs will be spelled out twice when a second module needs
the same shape. That duplication is visible in a diff. A shared base class that quietly
constrains four modules is not.

## Module anatomy

```
modules/<name>/
  <package>/        the code
  tests/            its own suite, runnable with no other module present
  pyproject.toml    its own dependencies
  README.md         what / run / test / contract, on one screen
  .env.example      what it needs configured
```

A module is deleted by deleting its directory. If that breaks something else, the
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
