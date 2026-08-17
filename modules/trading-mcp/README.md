# trading-mcp

MCP tools over `capital-gateway`'s demo account — account reads and order writes,
so a `teams` zespół can act on what it decides rather than only recommend it. See
`openspec/changes/add-trading-tools/` for the proposal this module was built from.

**Every write tool is demo-only, checked against the gateway, not against this
module's own configuration.** `market-mcp` stays read-only to the letter — this is a
sixth module, not a switch flipped on the fifth one (specs/market-mcp-tools).

**One transport: streamable HTTP.** No `stdio` — a locally spawned process carries no
caller identity, and a module that moves money needs its `allowed_applications` list
to mean something (specs/trading-mcp-transport).

## What

- `config.py` — settings, and the one credential this module cannot start without:
  `capital-gateway`'s caller key, required at every address including loopback (the
  gateway's own `RequireGatewayKey` checks every caller the same way, unlike
  `market-data`'s Easy Auth, which only gates a remote instance).
- `client.py` — the one seam every call to the gateway passes through. Reads retry
  once on a `5xx`; writes never retry, because the gateway takes no idempotency key.
  Also the demo-only guard: `ensure_demo_environment()` reads `GET /capabilities` and
  refuses to proceed unless it names `"demo"`, re-checked after any failed call.
- `errors.py` — `GatewayUnavailable`, `GatewayRefused` and `NotDemoEnvironment`, the
  three ways a call to the gateway can fail, kept apart because only one of them is
  worth retrying and only one of them is this module's own guard rather than the
  gateway's answer.
- `network_identity.py` — a deliberate twin of `market_mcp`'s file of the same name:
  who may reach this module over the network, and the one exempt path (`/health`).
- `server.py` / `__main__.py` — the FastMCP instance and its one transport.
- `tools/account.py` — `get_positions`, `get_working_orders`, `get_balance`: reads,
  annotated `readOnlyHint=True`.
- `tools/instruments.py` — `get_instrument_terms` and `size_for_margin`: reads, and the
  only arithmetic in the module. The terms are the provider's own — the deposit it
  requires, the smallest and largest order it takes, the step sizes move in — none of
  which a model can derive from anything else it sees. `size_for_margin` turns a deposit
  into a size, rounded **down** to that step, and takes the price as an argument rather
  than reading one: the size then rests on the same number from the archive that the
  decision did, and the trace shows which. Measured reason for both: an agent sizing 2%
  of an account into US100 sent the deposit divided by the price, which at a 5% margin
  requirement committed a twentieth of what it meant to.
- `tools/orders.py` — `place_order`, `close_position`, `amend_stops`,
  `cancel_working_order`: writes, annotated as changing state, never retried by this
  module on its own failure. What each one decides for itself is only what its own
  arguments cannot mean together — a LIMIT with no `level`, a MARKET carrying one
  (capital-gateway drops it without a word), a stop both set and cleared.
- `tools/_shared.py` — the two seams every tool goes through: `_read` and `_write`,
  which turn a `GatewayClient` outcome into a refusal, an access failure, or a
  settled/unsettled `OrderResultOut`. A provider `REJECTED` is a refusal naming the
  reason; a `PENDING` settlement is `outcome="unsettled"`, carried through rather
  than resolved. `_write` also owns the demo check, so its failures carry the same
  wording as every other one here and say the thing that matters at that point:
  nothing was sent. Which gateway status is a refusal and which is "I could not ask"
  is `GatewayRefused.is_access_failure` — one list, in `errors.py`, because a 401
  read as a refusal sends an agent re-editing an order nobody looked at.

## Running

```bash
uv run python -m trading_mcp
```

Needs `capital-gateway` running and reachable, and `CAPITAL_GATEWAY_API_KEY` set to
its `GATEWAY_API_KEY`. Copy `.env.example` to `.env` first.

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## Deploy

This module's infrastructure is in `infra/app-service.tf`: an Entra registration of its
own, the App Service, a Key Vault read policy, a rule in `capital-gateway`'s firewall, and
the `TRADING_MCP_*` pair on `teams`. Applying it is the operator's job and never CI's —
CI plans only, and `terraform-apply.yml` refuses any plan touching `azuread_*` outright,
because the CI principal holds `Application.Read.All` and not write.

**There is no new secret to set.** This module reads `gateway-api-key`, the same value
capital-gateway checks and market-data presents. If the platform is running at all, it is
already in the vault.

The order is forced by the gateway's firewall, which reads the outbound addresses off an
App Service that has to exist first:

1. **`terraform apply -target=azurerm_linux_web_app.trading_mcp`.** The app must stand
   before anything can read its addresses — a resource-level `for_each` refuses to plan
   against a value known only after apply, which is the same two-phase start market-data,
   agent and teams each needed. The Entra registration and its secret come along as
   dependencies of this target rather than as a second `-target`.

2. **`terraform apply`,** unrestricted. This is what converges the rest: the rule in
   `capital-gateway`'s firewall, the Key Vault access policy, this module's
   `allowed_applications` (one entry — `teams`'s managed identity, and nothing else ever),
   and `TRADING_MCP_URL` / `TRADING_MCP_SCOPE` on `teams`. The settings change restarts
   `teams` on its own; until it has restarted, its write tools are simply not there.

3. **`deploy-trading-mcp.yml`** builds the image and deploys it, ending in a smoke check on
   `/health` — the one path outside Easy Auth, answering with the module's own state and
   naming neither the account nor the tools. Until that runs, the App Service serves the
   placeholder image Terraform created it with, `teams` finds no tools at the address it
   was given, and a team carrying a write tool is refused at start-up rather than left to
   guess (specs/teams-tool-access).

**What to check after the first deploy, and it is not the same as "the site answers".**
This module refuses to start against anything but the demo account, checked against the
gateway's own `GET /capabilities` rather than against its own configuration
(specs/trading-mcp-upstream-access). A `/health` that answers is therefore already proof
of two things: the gateway is reachable with the shared key, and it is a demo session.

**Rollback.** Clear `TRADING_MCP_URL` and `TRADING_MCP_SCOPE` on `teams` and restart it.
The read tools stay exactly where they were, teams without write tools is the state it ran
in for the whole of phase 1, and every order already placed keeps its row in that module's
trade trace. Nothing here is undone by removing this module: an order that reached the
account is the broker's, not this platform's, and the demo positions are closed in the
terminal the way they always were.
