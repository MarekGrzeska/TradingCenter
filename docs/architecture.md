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
               │          │           desktop client      │
               │          ▼                               │
               │  ┌──────────────────────────────┐        │
               │  │  agent                       │◀────── OpenAI
               │  │  conversation · tools · cost │        │
               │  └──────────────┬───────────────┘        │
               │                 │ HTTP, streamed         │
               ▼                 ▼                        ▼
                            terminal ◀────────────────────┘
        charts · grid · search · archive panel · agent panel
```

`terminal` is a consumer, not a peer: it publishes no contract of its own and nothing
depends on it. It reads market data through one interface, and that interface now has two
implementations behind it — candles and the live stream from `market-data`, the instrument
catalogue from `capital-gateway`, composed into a single instance the views never see
through. The charts were not rewritten when the archive arrived, which is the whole point
of having had the interface first. `agent` is a third, unrelated source behind its own
interface — a conversation and its cost, nothing that shares a shape with a candle.

`market-data` sits between the two on purpose. capital.com counts its rate limit against the
account rather than the process, so a second client anywhere spends the same allowance twice:
the gateway owns the only door to the provider, and the archive refuses to start if its
upstream URLs point anywhere else.

`market-mcp` is a consumer of `market-data`, the same shape as `terminal`: it reads the
published contract and imports nothing. Where it differs is the shape of what it hands
onward — a chart wants every candle, a model wants a summary, so the same archive read
comes out reduced rather than proxied. It has two callers and they arrive by different
doors: `agent`, over streamable HTTP from its own container, and whatever MCP client the
operator runs on the desktop, over stdio. One tool set, registered once; the transport
decides only how a request gets in.

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
