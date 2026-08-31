# pocket

The prediction-market screen on a phone, and the agent that reads it. React+TS, two screens, two
upstreams: `polymarket-data`'s REST contract and the workbench's conversation. Like the terminal it
is a **consumer, not a peer** — it publishes nothing, owns no database, and reaches no other module.

```bash
pnpm install
pnpm dev                 # 5174
pnpm dev --host          # same, reachable from a phone on the same Wi-Fi
pnpm test                # vitest
pnpm lint · pnpm typecheck
pnpm contract:generate   # after polymarket_data/contract.py moves; CI's contract:check fails on a stale file
```

Port **5174**. The terminal holds 5173 and both read the same archive; nothing here waits on the
other, so either may run alone — and `scripts/dev.py` starts both, dropping both under
`--no-terminal`, because neither is a back end.

## Why a second front end rather than a tab in the terminal

The terminal is a trading screen: a chart with drawings, a grid of instruments, a conversation, a
team canvas. It assumes a mouse, a keyboard and a window wide enough for two panes, and its
Polymarket tab is written on that assumption. This one assumes a thumb. That is the whole of the
difference, and it is why the two share a **contract** rather than components: `src/data/
contract.polymarket.generated.ts` is printed from the same Python models the terminal reads, by the
same generator, so the archive moving breaks both at compile time and neither at runtime.

Nothing here imports from `modules/terminal`, and nothing there imports from here.

## What it shows

One list, grouped by observation group, a card per event:

- **Collapsed**: the title, whether prices are actually arriving (`collecting` / `stalled` /
  `resolved`), the group, and the leading market as a bar and a percentage. A stalled observation
  carries the archive's own reason rather than a red dot.
- **Open**: every market in display order — open above resolved, likeliest first, uncollected last —
  each with its outcomes, and the four windows (`1h`, `4h`, `24h`, `7d`) for the leading one.

A market is read by the outcome the provider lists **first**, never by the highest-priced one: the
row would change identity as prices moved, and a list that reorders under the thumb cannot be
scanned. The prices across a `neg_risk` set are never added up, for the reason the contract gives.

**A window with no value is a dash carrying its reason, never a zero** — a zero would be a claim
about the market rather than about the archive. Same for a price: `—`, not `0%`.

Two acts change what is observed, and both are the archive's: tracking an event (which creates its
group if the name is new) and removing one. **Removing takes every price ever collected with it** —
there is no pause, and the sheet says so rather than asking "are you sure".

## What makes it a phone app rather than a narrow desktop one

- Every control is at least `--tap` (2.75rem) in both directions, and the card's whole header is the
  toggle rather than a chevron beside it.
- Dialogs come up from the bottom edge, where the thumb is, and stay above the keyboard.
- Inputs are 16px, because iOS Safari zooms the page in on focus for anything smaller and never
  zooms back out.
- `viewport-fit=cover` plus `env(safe-area-inset-*)`, so the sticky header clears the notch.
- The list re-reads on `visibilitychange`, and **that is the read that matters**: every mobile
  browser throttles a background tab and Safari suspends one outright, so the 60s poll is not a
  guarantee. The header says when the archive last answered rather than implying it is current, and
  the freshness line is itself the refresh control — a button that only refreshed would duplicate
  both the poll and the pull.
- Pull down from the top of the list to re-read. A refresh button in a corner is the desktop idiom;
  this screen has no corner a thumb reaches.
- A collapsed card renders **no** market rows. One measured event holds 128 markets.
- Installable: `manifest.webmanifest` and an apple-touch-icon, so it can live on a home screen.

## The agent, and why the browser never speaks MCP

The second tab is a chat with the workbench. It is the only way this app reaches a tool, and that is
not a shortcut avoided but the shape of the system: the workbench holds the model key and the tool
servers' addresses, and `polymarket-data`'s tool surface admits **its managed identity** and no
browser at all (`polymarket_data/caller_access.py`). A phone that called `/mcp` itself would be
refused, and a phone that held an OpenAI key would be a leaked key.

The turn arrives over SSE — `fetch` and a `ReadableStream`, not `EventSource`, which can neither
`POST` nor carry an `Authorization` header. Fragments append as they land; **the transcript is
re-read when the turn ends**, because the module's copy carries the ids, the tool calls as recorded
and whether the turn finished. Stopping is the module's own route, never an aborted request: an
abort leaves the turn running with nobody reading it, and the reply is finished and billed anyway.

Every tool call is on screen — name, outcome, duration, and open, its arguments and the text the
model itself was handed. That is the difference between a tool that answered nothing and one that
was never asked, and it is the reason to have this tab on a phone at all.

The history is one sheet: the conversations newest first, the current one marked, and the model for
this conversation at the top of it. **A new conversation is not created by the tap** — it exists once
something has been said in it, which is what keeps the list free of rows nobody wrote in. Opening the
tab resumes the newest rather than starting another.

The conversation has **its own audience**: a token minted for the archive is never sent to the
workbench. With no `VITE_ENTRA_SCOPE_WORKBENCH` the agent goes without a credential rather than
borrowing one — locally that is correct, and against a deployed workbench it is a 401 the screen can
name.

## Reading the archive

Two tabs, kept mounted: switching must not throw away a half-typed question or restart the poll.

`GET /events` and `GET /groups` on a 60s poll — the archive samples once a minute, so asking more
often costs battery to redraw the same numbers. `GET /events/{id}/changes` only for cards that are
open: each window is a query per outcome.

A failed poll keeps the last answer on screen and adds a line saying it is the last answer. Only the
first read has nothing to fall back on, and that one renders the failure instead of an empty list —
"nothing is tracked" and "the archive is down" must not look alike.

## Configuration

`.env` is per-module and gitignored; copy `.env.example`. `VITE_POLYMARKET_HTTP` is where the
archive answers (a relative path goes through the dev proxy), `POLYMARKET_PROXY_TARGET` is what that
proxy forwards to and never reaches the browser.

**Sign-in is all three Entra values or none.** `VITE_ENTRA_CLIENT_ID`, `VITE_ENTRA_TENANT_ID` and
`VITE_ENTRA_SCOPE_POLYMARKET` are set by the deploy and unset locally, where `polymarket-data`
requires no principal and every request goes out bare. Two of the three is refused by
`data/config.ts` rather than half-configured: it would send the operator to a sign-in that cannot
finish, and Entra reports that as an unknown resource rather than as the missing setting it is.

## Deployment

A Static Web App of its own — `swa-tradingcenter-pocket`, Free tier, `infra/static-web-app.tf` —
deployed by `.github/workflows/deploy-pocket.yml` on any push to `main` under `modules/pocket/`. A
pull request gets a preview environment, and closing it takes that environment down: the Free SKU
allows three.

It carries **its own Entra registration**, `app-tradingcenter-pocket`, rather than a second redirect
URI on the terminal's: one registration for two origins means consent granted for one is granted for
the other, and the two screens are meant to be revocable apart. It asks for one API — the archive's
`access_as_user` — and `polymarket-data` names it twice, in Easy Auth's `allowed_applications` and
in its own `REST_CALLER_APPLICATION_IDS`, because the platform authorizes an application and the
module authorizes a surface.

**The infrastructure has to land before the image that needs it**, the way it does for every module
here: the registration, the CORS origin and the caller lists are one `terraform apply`, and the
operator runs it — this root manages Entra objects, which CI may read and not write.
