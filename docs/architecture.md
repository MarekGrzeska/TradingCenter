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
               │  └─▶│  workbench                   │◀─── OpenAI ×2
               │     │  ┌────────────┬─────────────┐│     │
               │     │  │conversation│teams        ││     │
               │     │  │tools · cost│as data · runs││    │
               │     │  └────────────┴─────────────┘│     │
               │     │  two schemas · one process   │     │
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
of having had the interface first. The `workbench` is a third source behind its own
interfaces — a conversation and its cost, nothing that shares a shape with a candle; and,
unlike the conversation's, its teams surface publishes a shape the terminal *edits*: a graph
the operator composes on a canvas and saves as a new revision. One base URL for both, since
they are one process.

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
authorizes the **application**, so admitting a caller for eleven read-only tools would admit
it to `POST /pairs` and `DELETE /pairs/{symbol}` as well. What keeps it to
`/mcp` is the module's own record of caller against surface
(`market_data/caller_access.py`), with a refusal test for every pair that has no business
together — and a path the record does not name is refused rather than passed.

The `workbench` reaches OpenAI and the archive's tool surface, and nothing else in this
diagram. The edge is deliberately narrow: no route to the REST contract, no entitlement to
one, and no code that would know what to do with a candle. What it has is a tool list it did
not write, fetched at the start of a session and used as given.

**The terminal's token stopped being one token on 22 August 2026.** It had asked Entra for
`market-data`'s scope and presented that to the workbench and the gateway too — the gateway
accepting that audience as a third one was infrastructure bent to fit the client rather than
the client taught to ask. The pre-authorizations for asking each back end by name had stood
in `infra/entra.tf` since August, unused, with a comment saying so. `polymarket-screen-opens-the-archive`
spent them: one `Identity` per audience off one MSAL session, so a leaked token opens one
module rather than four, and an audience says which resource it is for again.

That edge is the one thing in this diagram with no committed copy of its contract
anywhere. Every other arrow has one — the terminal's generated types, trading-mcp's
snapshot of the gateway's document, the terminal's hand-written agent DTOs — because HTTP
does not describe itself at call time. MCP does: the tool names, descriptions and argument
schemas arrive in the same session that uses them, so there is no second copy to drift and
nothing to regenerate. The trade is that a tool added on the archive's side reaches the
model with no review on the caller's side, which is safe exactly as long as the archive's
own specification keeps forbidding a tool that writes — and, since the merge, as long as
the caller record keeps the writing routes out of that caller's reach.

**The two surfaces of the workbench sit beside each other, not one under the other.** Same
edges out to OpenAI and the archive, a database each, a key each — and no import between
them. What differs is what they store. One keeps a conversation; the other keeps the
*definition* of a team — agents, their roles and the dependencies between them — as data in
a revision that never changes once written, so a run months apart from another can be
compared against the same definition rather than against a memory of it.

They were two modules until 20 August 2026, and what separated them turned out to be mostly
the separation: twin tool clients, twin registries, twin providers, twin catalogues, twelve
settings that existed twice, and a whole third module — `teams-mcp` — whose only reason to
exist was that the conversation built teams at a neighbour's address. What is left of that
module is its tools, unchanged in name, description, ceiling and refusal, reaching the teams
routes through an ASGI transport in the same process. Two network hops became none.

The rule that was "no module imports another module" needs a second form inside the process
that resulted, and it has one: `agent/` and `teams/` import neither each other nor
`teams_tools/`, `teams_tools/` imports neither of them, and `workbench/` — the assembly — is
the only place that may import all three. It is a test that reads the imports
(`tests/test_layering.py`), not an understanding: the first convenient dependency is written
in a hurry, and a rule with no failing case is a preference.

## The prediction-market archive

`polymarket-data` arrived on 22 August 2026 and is `market-data`'s shape rather than the
gateway's: one module, its own database, the REST contract the terminal reads and nine MCP
tools at `/mcp`, in one process. It is drawn apart from the diagram above because it touches
none of it — a different provider, a different kind of price, and no arrow to `capital-gateway`
at all.

```
                  polymarket.com
              gamma (metadata) + clob (prices)
                        │  public, no credential to present
                        ▼
        ┌──────────────────────────────┐
        │  polymarket-data             │
        │  archive · sampling · backfill│
        │  REST  ·  MCP tools at /mcp  │
        └──────┬───────────────┬───────┘
      events,  │               │  the same archive,
      history, │               │  reduced for a model
      changes  │               │  — and a watch list it may change
               │  ┌────────────┘
               ▼  ▼
          terminal   workbench
        (the tab,    (the third tool server)
         REST)
```

**Why there is no gateway in front of it**, when capital.com has one: that boundary is not
about being an upstream, it is about where reading stops and money starts. `trading-mcp`
exists so a write to the account has its own process, its own identity and its own demo
check — and `capital-gateway` exists because capital.com counts a rate budget against the
*account*, so a second client anywhere spends the same allowance twice. Neither holds here.
Polymarket's two surfaces are public, need no credential, and this system buys and sells
nothing on them. A second application would cost an App Service, an identity and a deploy
with no argument for it. If that ever changes — if anything here starts trading there — the
gateway/tools boundary is drawn then, and drawn for the reason it exists.

**The two surfaces have two callers, and that is enforced twice.** The workbench presents a
managed identity and reaches `/mcp`; the terminal presents the operator's own token and
reaches the REST contract. Neither reaches the other's, and the platform's gate cannot draw
that line — it authorizes an application, not a route — so the module keeps the record
itself (`polymarket_data/caller_access.py`). The line does not fall between reading and
writing, because the tool caller writes the watch list by design. It falls at **removing
collected history**, which is REST-only and is the one act here nobody can undo.

**Why it is not a widening of `market-data`.** A prediction market is not an instrument, its
price is not a candle, and its provider is not capital.com. `market-data`'s only door to the
outside is the gateway, and that is the property that keeps the candle archive's integrity
answerable; hanging a second provider off it would cost exactly that.

The two surfaces divide the same way the archive's do, and the division is sharper here
because **three of the nine tools write**. What they write is the list of observations — the
same thing an operator clicks — so the rule `market-data-tools` states outright ("the set
only reads") is deliberately not inherited, and is named in the specification rather than
left to be discovered in the code. The line that *is* hard sits elsewhere and is the one the
caller record enforces: **no tool deletes collected history.** That is a REST route, and the
one act in the module nobody can undo.

## The order path

The workbench's teams surface has one more edge than the diagram above draws, and it is
drawn apart because the picture is a straight line while the read path is a fan — folding it
in would cross three arrows to say something simpler than any of them:

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
        │  workbench (teams surface)   │
        └──────────────────────────────┘
```

A module of its own rather than a switch on something that reads. The archive's tools stay
read-only to the letter, and the tool server that writes is a separate deployable with a
separate identity, so "which module may move the account" is answered by a list of callers
rather than by a flag inside a process that also serves candles.

### Why it stays that way — decided 20 August 2026, by measurement

Two tool servers stopped being modules a day apart: `market-mcp` mounted as `/mcp` inside
`market-data` on 19 August 2026, and `teams-mcp` dissolved into the workbench as a function
call on the 20th. Both paid. `trading-mcp` was put to the same question and the answer came
out the other way, so the reason is written here rather than left as "proxy by principle" —
the arithmetic is in `docs/rachunek-po-refactorze.html`, card C.

The line count is close to a wash: the fold deletes ~790 hand-written lines of scaffolding
and writes back ~570, because Easy Auth authorizes an application and not a path, so the
gateway would need the route-by-route record `market-data` had to write for exactly this
reason (`caller_access.py`, 221 lines and 348 of tests on the day it landed). The fold
that justified this direction ran 1 260 out against 569 back. This one is near one to one.

What decides it is three things no line count shows.

**~~The probe dies and nothing replaces it.~~ — withdrawn on 20 August 2026, the same day it
was written.** The argument had two halves. The first stands: `trading-mcp` refuses to open a
port until the gateway has told it the account is a demo one, so its `/health` 200 proves it
reached the gateway, with the shared key, and was believed — the most a probe proves anywhere
here. The second was false. The gateway was said to be unprobeable, its `ip_restriction`
admitting only the service plan's own outbound addresses; **there is no such restriction, on this
app or on any other in the resource group.** `az webapp config access-restriction show` answers
`Allow` / "Allow all" for all four, `ip_restriction` appears nowhere in `infra/`, and the
gateway's `/` answered a laptop on the first try. `deploy-gateway.yml` probes it now, so the fold
would not have taken a probe away from anything. Read this argument as one point about
`trading-mcp`'s own probe, not as two.

**The demo guard stops being two answers.** The gateway derives its environment from the
host it is bound to and refuses to start elsewhere; `trading-mcp` refuses to listen until
it has read that answer over the wire. In one process the second collapses into the first.

**A fault in a tool would take the archive's feed with it.** `market-data` fills every
candle through the gateway. Today a crash in an order tool kills a process nothing else
depends on. The two folds that worked had the opposite shape — the tools moved into the
module they already could not survive without.

One premise of the question was wrong, and it argues the other way, so it is recorded too —
and it was wrong by more than the day's correction assumed. The gateway was described as sitting
behind "a list of two addresses"; the correction written here first said it sits behind one list
of the *plan's* addresses. It sits behind no list at all. Every caller that knows the hostname
reaches it, and the one thing holding the workbench out — or anybody else — is that they do not
hold `GATEWAY_API_KEY`. So the fold would not open a closed network boundary — it would
change which credential closes it, from a static key two apps share to an enumerated list
of named applications. That is the better mechanism, and it is available to the gateway
**without** the fold. Whether to give it one is a separate question, and an infrastructure
change, so it goes through a proposal on its own merits.

The rule that comes out of the measurement is narrower than the one it replaces, and it is
mechanical enough to apply to the next tool server without measuring again: **a tool server
standing in front of the owner of its own data folds into it; a tool server standing in
front of a different security boundary does not.** `market-mcp` and `teams-mcp` were the
first kind. `trading-mcp` is the second — the gateway is not the owner of the account, it
is the only door to a provider that owns it, and the whole point of a second module here is
that the door and the list of who may knock are not the same artifact.

**One more, and it points the other way — and it is no longer a network edge at all.** The
tools that build and correct a team from the chat put the *catalogue* behind MCP, and they
live inside the workbench:

```
        ┌───────────────────────────────────────────────┐
        │  workbench                                    │
        │                                               │
        │   conversation ──▶ team tools ──▶ teams routes│
        │                    (MCP names,    (owner filter,
        │                     ceilings,      limits,     │
        │                     refusals)      validation) │
        │                        │                      │
        │                        └─ ASGI, no socket ─────┤
        │      the operator's principal travels with it, │
        │      taken off the chat request being served   │
        └───────────────────────────────────────────────┘
```

The arrow into the teams routes is the one worth reading twice, for two reasons.

**It goes through the routes rather than around them.** The owner filter, the revision
validation, the daily cost limit and the tool-catalogue check live there, and a tool
reaching past them into the store would be the access policy written a second time — which
is exactly what the requirement "a tool set does not extend what the operator can already
do" forbids.

**It carries a person, not a service.** Every other edge in this system is a module proving
*itself* to the next one; this one carries the identity of the operator who asked. The
catalogue filters every statement by owner, so a call acting on the process's own identity
would create teams nobody can see — existing, costing money, impossible to open in the
terminal. What travels changed with the merge and is worth stating: not the operator's
bearer token, which needed an authenticator in the middle to mean anything, but the
principal Easy Auth already put on the incoming request. One credential fewer in flight,
the same answer at the other end.

The demo-only guarantee lives here and nowhere else that can be turned off: `trading-mcp`
asks `capital-gateway` what environment it is bound to and refuses to open a port unless
the answer is the demo one. It is not a setting of its own — a module that decided this
from its own configuration would be a module an environment variable could aim at real
money. Everything the operator *can* change — how large an order may be, how many a run or
a day may place — lives one module up, in a team revision, where every one of them is
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

**A package does not get a capability spec, and that is measured rather than assumed.**
The question was opened on 20 August 2026, because `openspec/specs/` holds nothing for
`packages/` while three specs each state that a module presents an identity rather than a
password, migrates itself under an advisory lock and owns what its migrations create — all
of it code that now lives once, in `tc-runtime`. The titles do repeat: 22 of them, over 33
of 389 requirement statements.

The requirements do not. Comparing bodies rather than titles across every repeated one:
**one paragraph is shared by all the homes of a title, against 103 that are not**, and ten
scenario names are shared against 86, of which only three have identical bodies. Even
`agent` and `teams`, two surfaces of one process, share four paragraphs against sixty.

The reason is visible in any one of them. `market-data`'s "Migruje dokładnie jeden proces
naraz" is the workbench's plus a paragraph and a scenario: the wait must exceed the longest
migration *because the candle table is the largest thing here*, which is why it is 1500
seconds against 300. A package-level requirement either drops that reason or is a third
body written from scratch. So the rule is: **a package earns a spec when the requirement it
satisfies is the same for every consumer — and here it is the same rule with a different
reason each time, which is a different requirement.** What repeats is the naming, and that
is a naming collision rather than duplication: OpenSpec addresses a requirement by its
title, and three of these titles mean three different things.

### Why the rule changed

It used to read: no shared library at all, because shared code is coupling no contract
records, and duplication is at least visible in a diff. The reasoning was sound and the
price turned out to be higher than the argument assumed. Measured on 18 August 2026:
**959 lines** of production Python existed only as hand-maintained copies of each other,
and four separate bugs had been fixed in one copy and not the other — one of them the
retry on the order path, fixed in one of them and missing from the other for a day. Those
two are one module since `agent-and-teams-one-workbench`, and their remaining twins went the
way a package could not take them: by ceasing to have a second copy.

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

`polymarket-data`'s archive is the same kind of thing and unrecreatable for a harder reason:
the provider's price history reaches back only so far, and a market that resolved stops being
queryable at all. What was not collected while it mattered cannot be collected afterwards at
any price in provider calls — which is why deleting it is a REST route no tool can reach, and
why the module records the oldest moment it could actually get rather than the edge of the
window it asked for.

## Relationship to TradingHub

TradingHub is the previous ecosystem and still runs. Its modules move here one at a time;
`capital-gateway` supersedes its `broker-gateway`, which stays where it is until retiring
it is a separate, deliberate decision.

Prior art there is worth reading before rebuilding something. It is not worth importing.
