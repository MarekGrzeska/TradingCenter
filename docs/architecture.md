# Architecture

## The shape

One repository, many modules, no shared runtime. A module is a directory under `modules/`
that runs on its own and publishes a contract. Nothing imports across that boundary.

```
                    ┌──────────────────────────────┐
   capital.com ────▶│  capital-gateway             │
   (REST + WS)      │  trade · history · stream    │
                    └──────────────┬───────────────┘
                                   │ HTTP + WebSocket
                    ┌──────────────┴───────────────┐
                    │                              │
              terminal (later)             agents / backtests
```

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
provider, not an archive. When an archive is wanted it belongs to a module whose job that
is — giving one candle two origins, with only one of them reachable, is worse than not
storing it at all.

## Relationship to TradingHub

TradingHub is the previous ecosystem and still runs. Its modules move here one at a time;
`capital-gateway` supersedes its `broker-gateway`, which stays where it is until retiring
it is a separate, deliberate decision.

Prior art there is worth reading before rebuilding something. It is not worth importing.
