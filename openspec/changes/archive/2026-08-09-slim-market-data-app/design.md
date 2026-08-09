## Context

Proposal.md has the why. Here: only what shapes the move.

What `app.py` holds today, counted:

| | |
|---|---|
| lines | 773 |
| routes | 15, across 5 unrelated areas |
| domain helpers | 4 (`_market_status`, `_decide_late_pairs`, `_fill_out`, `_tracked_pair_out`), ~100 lines |
| module-level mutable state | 1 (`_market_status_cache`) |
| `app.state` reads | 20 |

The `app.state` count matters: the module already has a working pattern for "a thing built once at
startup and reached from a route". `pool`, `hub`, `ingest`, `job_runner`, `settings`, `history` and
`client` all use it. The market-status cache is the single dependency that does not, and the single
one that leaks between tests.

## Goals / Non-Goals

**Goals:**

- No route changes path, method, status code, response model, or OpenAPI shape.
- The market-status cache becomes an ordinary dependency: constructed in `lifespan`, reachable from
  a route, constructible by a test.
- Deciding a late pair's state is testable without an HTTP client.

**Non-Goals:**

- Changing the market-status TTL, what is cached, or when the gateway is asked. The one-minute TTL
  and the "only ask about late pairs" rule are load-bearing and measured — `app.py`'s own comment
  records 74 requests over a quarter-hour of a weekend without them. This change moves that code;
  it does not tune it.
- Touching `contract.py`. The wire shapes are the one thing that must not move.
- Splitting `tracking.py` (389 lines) or `jobs/store.py` (337). They are cohesive; being long is not
  the same as being mixed. `app.py` is being split because it holds *unrelated* things, not because
  of its size.
- Introducing a service or repository layer. The module's shape — routes over functions over
  `asyncpg` — works and is not what this change is about.

## Decisions

### The cache becomes an object on `app.state`, following the pattern already there

```python
class MarketStatus:
    """Whether an instrument's market is open, remembered for a minute."""
    def __init__(self, instruments: GatewayInstruments, ttl: timedelta = _TTL) -> None: ...
    async def of(self, symbol: str) -> bool | None: ...
```

Built in `lifespan`, stored as `app.state.market_status`, read through a `Depends` like `pool` and
`hub` already are. A test constructs one with a fake `GatewayInstruments` and asserts the TTL
directly, which today needs a `TestClient` and a reach into a private module global.

Considered and rejected: an `lru_cache` with a time bucket, or `functools.cache` on a helper. Both
keep the state module-global — the actual defect — while making it harder to see.

### `_decide_late_pairs` moves to `tracking.py`; `_market_status` becomes the new module

The split follows what each one talks to. `_decide_late_pairs` reads `CollectionState` and calls
`collection_state`, both of which live in `tracking.py` — it is tracking logic that happens to be
called from a route. `_market_status` talks to the gateway and owns a cache, which is neither
tracking nor HTTP, so it gets its own small module next to the other gateway-facing code.

`_fill_out` and `_tracked_pair_out` are contract shaping — one line per field, no logic — and belong
with the models they build, as `classmethod`s on `FillOut` and `TrackedPairOut` in `contract.py`.
`PairEstimateOut.of()` is already exactly this, so the pattern is the module's own, not an import.

### Five routers, split by area, not by verb

`meta`, `candles`, `pairs`, `jobs`, `stream`. Each is an `APIRouter` in its own module under
`market_data/routers/`; `app.py` includes them. The shared `pool` and `hub` dependencies move to a
`deps.py` so a router does not import from `app.py` and create a cycle.

Split by area rather than by HTTP verb because that is how the module's specs are organised
(`market-data-api`, `market-data-jobs`, `market-data-tracking`) and how changes actually arrive: a
change to jobs touches four routes that are all in one file, and none of the others.

Tags stay exactly as they are (`meta`, `tracking`, `jobs`, …) rather than being derived from the
router name, because the tag is part of the published OpenAPI document and this change must not
move it.

### `test_app.py` is the acceptance criterion, and it must barely change

68 tests, 1342 lines, covering every route. If this refactor is behaviour-preserving, the only edit
they need is **deleting** the fixture that clears the module global — replaced by constructing a
`MarketStatus` for the app under test.

Any other required edit to `test_app.py` means a route moved, a status code changed, or a dependency
resolved differently. So the rule for this change: a needed test edit is not a chore, it is a
finding, and it goes in review.md as one.

The second, independent check is the OpenAPI document. If `generate-terminal-contract-from-openapi`
has landed, `contract:check` fails on any drift in the published schema; if it has not, the schema
is dumped before and after and diffed by hand.

## Risks / Trade-offs

- **Router splits routinely move `operationId` and component ordering.** FastAPI derives
  `operationId` from the function name and the route, not the router, so it should hold — but
  "should" is why the OpenAPI diff is a task and not an assumption.
- **More files to open to follow one request.** Real cost, paid deliberately: fifteen routes in five
  areas in one file is worse, and the areas do not call each other.
- **`deps.py` is a new place for a cycle to appear** if it ever grows imports back toward the
  routers. Keep it to dependency providers only.
- **The move is large and touches everything at once.** Mitigated by ordering: helpers move first
  under the existing tests, routers second. Each step keeps the suite green on its own, so a
  bisect lands on a small commit.

## Migration Plan

No schema change, no data migration, no contract change. Deployment is a code swap; nothing about a
running archive, its jobs or its tracked pairs is affected.
