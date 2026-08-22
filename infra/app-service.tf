# One Linux App Service Plan and every app in `local.web_app_names` — the list itself, with
# no count repeated here, for the reason that local's own comment gives three lines down:
# this line said "seven of them today" at four (design.md, "App Service, nie Container
# Apps"). All of them run non-stop, so one shared plan is
# cheaper than as many Container Apps billed by CPU-second. The list is that local rather
# than a sentence here, because a sentence here is what said "six apps" at seven.
#
# The fifth and sixth apps arrive after the measurement below was taken against four, and
# the shape of that measurement says what to expect: most of the plan's memory is platform
# overhead that grows per *app*, not per unit of work. So `plan_memory` (monitoring.tf,
# alert at 92%) is the thing to watch after each of them is deployed, and the answer if it
# fires is the same one B1 got — a bigger SKU, never a second worker.
#
# B2 rather than the B1 this started on, and the measurement is the reason (openspec:
# scale-app-service-plan-to-b2). The two changes that added the third and fourth app both
# said the pressure was a thing to measure once they were deployed rather than predict;
# measured on 15 August 2026, the nightly floor of the plan's MemoryPercentage had walked
# from 73.5% (10 Aug, two apps) to 83.1% (13 Aug, four), with a 89.2% peak against an alert
# at 92.
#
# What that is NOT is a leak: the two original apps came down over the same window
# (gateway's peak working set 262 -> 193 MB, market-data's 327 -> 311 MB). The four apps'
# peaks together are ~882 MB of the 1.75 GB B1 had, so roughly half of what the plan
# reported. The rest is the platform — four containers, four Kestrels, Easy Auth, the OS —
# and that overhead grows with the number of apps rather than with their work. Which is
# why the answer is memory, not a rewrite.
# **B3 since `add-teams-mcp`, and the arithmetic is the same as the last two times.**
# Measured 16 August 2026, right after phases 1-3 deployed: six apps, 84% of B2's 3.5 GB,
# against an alert threshold of 92%. One more tenant costs 4-9 points at the 150-310 MB
# this plan's own history says a module weighs — so the seventh app either fits with two
# points to spare or trips the alert on its first night. That is not a coin worth
# flipping, and "deploy and watch" is exactly what the two previous changes here already
# warned against.
#
# **Left at B3 while two tenants went away** (`agent-and-teams-one-workbench`: teams and
# teams-mcp became one process with agent). The arithmetic says the room is there; the
# reason not to act on it is the same one that put the SKU up twice — a measurement
# beats a subtraction. Read the memory alert over a week of the merged process before
# stepping down, since one process holding two schemas and a clock is not the sum of the
# three that answered before it.
resource "azurerm_service_plan" "main" {
  name                = "asp-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "B3"

  # Exactly one worker, on purpose — design.md, "Gateway ma dokładnie jedną instancję".
  # capital.com counts its 10 req/s limit per *account*, not per process; a second
  # worker means a second RateGate and a second budget spent from the same allowance,
  # and the overflow reaches a caller looking exactly like missing data, not like a
  # traffic problem. DO NOT add autoscaling or raise this number — if more capacity is
  # ever needed, it has to come from a change to the rate-limiting design first, not
  # from turning a knob here. The move to B2 above deliberately left this alone: a bigger
  # SKU buys memory and a second core for the one worker, never a second worker.
  worker_count = 1
}

locals {
  # Every App Service app, once. Everything that used to carry a hand-typed numeral —
  # the memory alert's own text, the headings below — counts this instead, because a
  # numeral in a message is a fact that goes stale silently: on 18 August 2026 the alert
  # the SKU decision stands on still said "all four apps" at seven.
  web_app_names = {
    "capital-gateway" = local.capital_gateway_app_name
    "market-data"     = local.market_data_app_name
    "workbench"       = local.workbench_app_name
    "trading-mcp"     = local.trading_mcp_app_name
    "polymarket-data" = local.polymarket_data_app_name
    "strategy"        = local.strategy_app_name
  }

  capital_gateway_app_name = "app-tradingcenter-gateway"
  market_data_app_name     = "app-tradingcenter-market-data"
  # **Still `-agent`, and that is a decision rather than an oversight.** The name of an
  # App Service is an identity here, not a label: the system-assigned identity takes it,
  # `DATABASE_USER` below *is* that identity, and the identity's application id sits on
  # three lists in two other modules. Renaming buys a nicer hostname and costs a new
  # identity, new roles in both databases and three edits in modules this change does not
  # touch (`agent-and-teams-one-workbench/design.md`, D2). The module is called
  # `workbench`; the resource is called what it was.
  workbench_app_name   = "app-tradingcenter-agent"
  trading_mcp_app_name = "app-tradingcenter-trading-mcp"
  # Named after the module from the first day, which is the one thing `workbench_app_name`
  # above cannot be. The cost of getting this wrong is written three lines up: a resource
  # name here is an identity, so a rename later is a new identity, a new Postgres role and
  # an edit in every module that names the old one.
  polymarket_data_app_name = "app-tradingcenter-polymarket-data"
  strategy_app_name        = "app-tradingcenter-strategy"

  # Deterministic App Service hostnames — used ahead of `terraform apply` (e.g. in the
  # Easy Auth redirect URI below) instead of waiting on the computed `default_hostname`,
  # since Azure names of this form are `<name>.azurewebsites.net` with no surprises.
  capital_gateway_hostname = "${local.capital_gateway_app_name}.azurewebsites.net"
  market_data_hostname     = "${local.market_data_app_name}.azurewebsites.net"
  workbench_hostname       = "${local.workbench_app_name}.azurewebsites.net"
  trading_mcp_hostname     = "${local.trading_mcp_app_name}.azurewebsites.net"
  polymarket_data_hostname = "${local.polymarket_data_app_name}.azurewebsites.net"
  strategy_hostname        = "${local.strategy_app_name}.azurewebsites.net"

  # What `market-data` is called when it is the *resource* a token is asked for, rather
  # than the app serving a request. The terminal asks Entra for `<uri>/<scope>`; Easy
  # Auth accepts a token whose audience is this.
  market_data_api_uri   = "api://tradingcenter-market-data"
  market_data_api_scope = "access_as_user"

  capital_gateway_api_uri   = "api://tradingcenter-capital-gateway"
  capital_gateway_api_scope = "access_as_user"

  # Same idea, one level out, for the tool server that writes. Unlike market-data's, this
  # pairs with no delegated scope: the only caller is
  # `teams`, presenting a client-credentials token from its managed identity. A browser
  # never asks for this one, and there is nobody to consent on whose behalf.
  trading_mcp_api_uri = "api://tradingcenter-trading-mcp"

  # The same shape again for the prediction-market archive. Like trading-mcp's and unlike
  # market-data's, it pairs with no delegated scope: the only caller today is the workbench
  # presenting a client-credentials token. The terminal will need one when it grows a
  # subpage — that change adds it, along with the delegated scope and the REST caller.
  polymarket_data_api_uri = "api://tradingcenter-polymarket-data"
  # The strategy platform's own audience. It has one for the same reason trading-mcp does:
  # its callers are backend services presenting a managed identity, so there is no consent
  # screen and no delegated scope — only client credentials.
  strategy_api_uri = "api://tradingcenter-strategy"

  # There used to be a third of this shape, for the tool server the agent built teams
  # through. Those tools are a layer in the workbench now — no address, no audience, and
  # nothing for a caller to present.

  # The same shape for the workbench's own registration (entra.tf) — see the comment there
  # for why its scope is granted to the terminal today but not yet the one the terminal's
  # token actually carries. The `-agent` spelling is the resource name's, kept for the
  # reason `workbench_app_name` gives.
  workbench_api_uri   = "api://tradingcenter-agent"
  workbench_api_scope = "access_as_user"

  # Where the terminal is served from. One string, used in three places that MUST agree:
  # the SPA registration's redirect URI, the origin market-data allows a browser to call
  # it from, and the address the deploy workflow builds against. Read from the resource
  # rather than typed, because Static Web Apps invents the name.
  terminal_origin = "https://${azurerm_static_web_app.terminal.default_host_name}"

  kv_secret_uri = {
    for k, name in local.key_vault_secret_names :
    k => "${azurerm_key_vault.main.vault_uri}secrets/${name}/"
  }

  # GHCR is private, because the repository is, so App Service needs a credential to pull
  # at all — without these the container never starts and the site answers 503 with
  # `ImagePullUnauthorizedFailure` in the docker log. Identical for every app, so said
  # once here rather than seven times below.
  #
  # These belong in `application_stack`, not `app_settings`: the provider owns the three
  # DOCKER_REGISTRY_SERVER_* settings and refuses them by name in app_settings ("cannot
  # set a value for DOCKER_REGISTRY_SERVER_PASSWORD in app_settings"), because it writes
  # them itself from the fields below.
  #
  # The alternative that needs no stored credential is Azure Container Registry, which
  # App Service pulls from with its managed identity — rejected on cost: it is a paid
  # resource and every other piece of this platform fits the free-tier grant.
  ghcr_registry_url      = "https://ghcr.io"
  ghcr_registry_username = "MarekGrzeska"
  ghcr_registry_password = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.ghcr_pull_token})"
}

# capital-gateway: reachable, and guarded by what the module itself checks.
#
# It used to be reachable only from two addresses — market-data's and trading-mcp's own
# outbound ones — with the in-code X-Gateway-Key check as the first layer and those rules
# as the second. That arrangement had no room for a browser, and the terminal's Accounts
# screen is a browser: it cannot hold the shared key (a secret in downloaded code is a
# published secret) and it does not call from a fixed address.
#
# So the address rules are gone and Easy Auth stands here instead, and the price is written
# down rather than discovered: **the in-code check is now the only thing between this app
# and the internet**. A leaked key used to be useless off the plan; now it is enough. What
# limits the damage is unchanged and is the reason this was acceptable — the module refuses
# to start against anything but the capital.com demo host, so there is no real money behind
# this door (openspec/changes/accounts-screen-opens-the-gateway/design.md, D2).
resource "azurerm_linux_web_app" "capital_gateway" {
  name                = local.capital_gateway_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on          = true
    websockets_enabled = true

    # **The browser's preflight is answered here, by the platform, and never by the app.**
    # The third half-copied pattern in two days, and the one that made the Accounts screen
    # say "capital-gateway is not reachable" on 20 August 2026 with nothing in the
    # gateway's log: the terminal was asking the right host by then, but a cross-origin
    # `GET /accounts` carrying a bearer token is preflighted, and an `OPTIONS` carries no
    # token at all. Easy Auth answered it `401`, the browser refused the real request, and
    # a network-level refusal reaches `fetch` as a thrown error rather than a status —
    # which is why the screen reported an unreachable module instead of a rejected one.
    # Measured against production from outside: this app answered the preflight `401`
    # where `market-data` answered `200` with `Access-Control-Allow-Origin`.
    #
    # Same two lines market-data and the workbench already carry, and the note there
    # applies here word for word: **`capital_gateway` MUST NOT add a CORS middleware of
    # its own**, because two layers each appending the header produce a doubled one and a
    # browser rejects that response. `support_credentials` stays off — the terminal sends
    # a bearer token, never a cookie.
    #
    # This opens no route: what a browser may reach past the door is `caller_access.py`'s
    # list, and it is unchanged.
    cors {
      allowed_origins     = [local.terminal_origin]
      support_credentials = false
    }

    application_stack {
      # Placeholder — group 7's deploy workflow pushes the real GHCR image after the
      # first build. Terraform must not fight that: see the lifecycle block below.
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }

  }

  app_settings = {
    GATEWAY_ENV        = "production"
    CAPITAL_BASE_URL   = "https://demo-api-capital.backend-capital.com"
    CAPITAL_STREAM_URL = "wss://api-streaming-capital.backend-capital.com/connect"

    CAPITAL_API_KEY    = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.capital_api_key})"
    CAPITAL_IDENTIFIER = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.capital_identifier})"
    CAPITAL_PASSWORD   = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.capital_password})"
    GATEWAY_API_KEY    = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.gateway_api_key})"

    # Who may reach this module without the shared key, on a token the block below has
    # already validated. The terminal, and nothing else — and the module reads this list
    # itself (`capital_gateway/caller_access.py`) rather than trusting that anyone past
    # Easy Auth belongs everywhere: Easy Auth authorizes an application, not a route, and
    # this app serves the account next to the routes that place orders.
    BROWSER_CALLER_APPLICATION_IDS = jsonencode([azuread_application.terminal.client_id])

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.capital_gateway_easy_auth.password

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    # **This app authenticates now, and the sentence that used to stand here was false.**
    # It said anonymous was deliberate and bought a narrower thing — "a request that *does*
    # carry a token has it validated before the app sees it". It does not. Measured on
    # 20 August 2026: a request carrying `Authorization: Bearer notatoken` reached this
    # module's own middleware and was refused by it, where the same request to market-data
    # was refused by the platform with `WWW-Authenticate` and never arrived. Under
    # `AllowAnonymous` the auth module validates nothing and injects no
    # `x-ms-client-principal` — which left `caller_access.py` reading claims from a header
    # nobody filled in, and the terminal's Accounts screen refused as an unidentified
    # caller for as long as it existed.
    #
    # What made the flip possible is the ordering, not a change of mind: market-data and
    # trading-mcp present tokens of their own identities as of `the-gateway-door-
    # authenticates`, and both are in `allowed_applications` below. Doing this first would
    # have cut both off at the moment of apply, which is what the old comment correctly
    # feared.
    unauthenticated_action = "Return401"

    # **The stream must not pass through Easy Auth at all.** Measured the hard way on
    # 20 August 2026, minutes after this block was first applied: market-data's feeds died
    # with "timed out during opening handshake" and did not come back, because the auth
    # module intercepts the WebSocket upgrade and never completes it — `AllowAnonymous`
    # governs whether a request is refused, not whether the upgrade survives the
    # interception. The gateway kept answering HTTP the whole time, so nothing looked
    # broken from the outside while candles stopped arriving and the archive fell back to
    # REST until capital.com started answering `error.too-many.requests`.
    #
    # `market-data` carries the same exclusion for its own `/ws/candles`, for the same
    # reason. Nothing is lost by it: the gateway checks the caller key inside the
    # WebSocket handler itself (`app.py`, `stream`), which is where that check has always
    # been — Easy Auth was never what guarded this path.
    #
    # `/` is the health route, excluded for the reason market-data excludes `/ping`.
    #
    # Both exclusions matter more now than they did when they were written. With
    # `require_authentication = true` above, an excluded path is the only kind that
    # reaches this app without a token — so `/ws/stream` is, from this apply onward, the
    # one route in this system whose door is the shared key alone, checked inside the
    # gateway's own WebSocket handler. That is not a gap left open by accident: an
    # authenticator in front of a WebSocket upgrade intercepts it and never completes it,
    # which killed every candle feed for an hour on 20 August 2026.
    excluded_paths = ["/ws/stream", "/"]

    active_directory_v2 {
      client_id                  = module.capital_gateway_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Four, and the fourth is not decoration — it is the one this list was missing, and
      # the terminal's Accounts screen stayed refused for it. Two spellings of *this* API,
      # for the reason market-data's own block gives, and two of **market-data's**, because
      # the terminal's identity layer acquires one token scoped to market-data and reuses
      # it here. A token asked for by scope name carries the `api://` uri as its audience;
      # the same request as `<client-id>/.default` carries the client id — and the operator's
      # token carries the client id, which is why listing only the uri looked like a working
      # configuration and refused every browser request.
      #
      # `module.workbench_easy_auth` has carried all four since it was written. This block
      # copied three of them, and the missing one only became visible when
      # `require_authentication` was turned on and the platform started actually checking:
      # before that nothing validated the audience at all, so nothing could notice.
      allowed_audiences = [
        local.capital_gateway_api_uri,
        module.capital_gateway_easy_auth.client_id,
        local.market_data_api_uri,
        module.market_data_easy_auth.client_id,
      ]

      # The browser, and — since `the-gateway-door-authenticates` — the two service callers
      # as well. They are listed *before* this app requires authentication, which is the
      # whole point of the ordering: an entry here costs nothing while
      # `unauthenticated_action` is still `AllowAnonymous`, and doing it the other way
      # round would cut both modules off at the moment of apply.
      #
      # A managed identity publishes `principal_id`, and `allowed_applications` wants the
      # client id, which lives on the service principal that object id names — the same
      # lookup market-data already does for the workbench.
      allowed_applications = [
        azuread_application.terminal.client_id,
        data.azuread_service_principal.market_data_managed_identity.client_id,
        data.azuread_service_principal.trading_mcp_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  lifecycle {
    # The deploy workflow (group 7) sets the real image tag with `az webapp config
    # container set` / webapps-deploy — Terraform reverting that to the placeholder on
    # every apply would fight the thing that is supposed to own this value.
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# The API half of the pair whose client half is `azuread_application.terminal` — the same
# shape market-data has had since the terminal first needed a token for it. Its own
# registration rather than reusing market-data's: a token is issued *for* an API, and the
# two APIs are two doors with two lists of who may knock.
module "capital_gateway_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-gateway-easyauth"
  identifier_uri = local.capital_gateway_api_uri
  redirect_uri   = "https://${local.capital_gateway_hostname}/.auth/login/aad/callback"

  id_token_issuance_enabled = true

  scope = {
    value                      = local.capital_gateway_api_scope
    admin_consent_display_name = "Read the demo account"
    admin_consent_description  = "Allows the app to read and fund the capital.com demo account as the signed-in operator."
    user_consent_display_name  = "Read your demo account"
    user_consent_description   = "Allows the app to read and fund your capital.com demo account."
  }
}

# market-data: public, but Easy Auth-gated — design.md, "Easy Auth zostaje tam, gdzie po
# drugiej stronie jest przeglądarka — przed market-data". `terminal` is the browser-side
# caller (via Static Web Apps, group 7); the gateway never sees a browser at all.
#
# This registration is also the **API** half of the pair: `terminal` (entra.tf) is a
# separate client registration that asks Entra for a token *for this one* and sends it in
# an `Authorization` header. Two registrations rather than one that plays both parts,
# because which is the client and which is the resource is the whole content of the
# arrangement — market-data is an API for however many consumers arrive, and the terminal
# is the first of them.
# Generated once and kept in state. A scope id must be a stable GUID: regenerating it
# would revoke the terminal's permission and re-grant a different one on every apply.
module "market_data_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-market-data-easyauth"
  identifier_uri = local.market_data_api_uri
  redirect_uri   = "https://${local.market_data_hostname}/.auth/login/aad/callback"

  id_token_issuance_enabled = true

  scope = {
    value                      = local.market_data_api_scope
    admin_consent_display_name = "Read and manage the candle archive"
    admin_consent_description  = "Allows the app to reach market-data as the signed-in operator."
    user_consent_display_name  = "Read and manage your candle archive"
    user_consent_description   = "Allows the app to reach market-data as you."
  }
}

resource "azurerm_linux_web_app" "market_data" {
  name                = local.market_data_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on          = true
    websockets_enabled = true

    # CORS belongs **here and not in the application**, and the reason is the preflight.
    # A cross-origin request carrying an `Authorization` header is preceded by an
    # `OPTIONS` that by definition carries no credential at all; Easy Auth, set to
    # `Return401` below, would answer it with a 401 before the container saw it, and no
    # browser request would ever get through however good its token. App Service's own
    # CORS stands in front of Easy Auth, which is exactly where the answer has to come
    # from.
    #
    # Consequence to carry forward: **`market_data` MUST NOT add a CORS middleware of its
    # own.** Two layers each appending `Access-Control-Allow-Origin` produce a doubled
    # header, and a browser rejects a response carrying two — the same note sits in
    # `market_data/app.py`.
    #
    # `support_credentials` stays off: the terminal sends a bearer token, never a cookie,
    # and turning it on would forbid the wildcard-free origin list from ever being
    # widened without thought.
    cors {
      allowed_origins     = [local.terminal_origin]
      support_credentials = false
    }

    application_stack {
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }
  }

  # Return401, not RedirectToLoginPage: `terminal` reaches this app through `fetch()`,
  # not top-level browser navigation, and a redirect response handed to `fetch` resolves
  # to an HTML login page masquerading as a JSON body instead of a request `terminal`
  # can react to. The terminal handles that 401 itself — it holds an Entra token and
  # renews it (`src/auth/`), which is what makes the cookie Easy Auth would rather use
  # unnecessary.
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # The candle stream, and nothing else. A browser cannot put a header on a WebSocket
    # handshake — the API has no room for one — so Easy Auth would be checking for a
    # cookie the browser will not send across two hostnames, and would refuse every
    # subscription forever.
    #
    # **Exempt from Easy Auth is not exempt from authentication.** The module guards this
    # path itself, with a one-time ticket it issues over HTTP where headers do work
    # (`market_data/tickets.py`). Deploy order follows from that and is not
    # interchangeable: the module learned to check tickets before this line existed,
    # because the reverse leaves an open WebSocket on the internet in between.
    #
    # `/ping` is the other exemption, and it needs no guard of its own: Easy Auth returns
    # 401 for every non-excluded path whether the container behind it is alive or dead, so
    # an external availability probe (`azurerm_application_insights_standard_web_test`
    # below, monitoring.tf) can never tell the two apart without a path that answers before
    # Easy Auth would. `/ping` (market_data/routers/meta.py) reads nothing and returns a
    # fixed body for exactly that reason — nothing here needs protecting.
    excluded_paths = ["/ws/candles", "/ping"]

    active_directory_v2 {
      client_id                  = module.market_data_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Two audiences for one API: a token asked for by scope name arrives with the
      # `api://` uri as its audience, one asked for as `<client-id>/.default` arrives
      # with the client id. Accepting both means neither spelling of the request is a
      # silent 401 later.
      allowed_audiences = [
        local.market_data_api_uri,
        module.market_data_easy_auth.client_id,
      ]

      # Which clients may present a token at all. The terminal (a user's own delegated
      # token) and the workbench (its managed identity, client-credentials) since the tool
      # surface moved into this module — a future service reaching this API adds itself
      # here, deliberately, rather than inheriting access by having a token from the same
      # tenant.
      #
      # One backend caller rather than two since `agent-and-teams-one-workbench`: the
      # conversation and the teams runner are one process and present one identity.
      #
      # This list is where the door is, and it is no longer the whole of the answer:
      # Easy Auth authorizes an application, not a route, so the workbench on this list is
      # past every path in the module. What keeps it to `/mcp` is
      # TOOL_CALLER_APPLICATION_IDS below, read by the module's own layer
      # (`market_data/caller_access.py`). Both are required; neither substitutes for the
      # other.
      allowed_applications = [
        azuread_application.terminal.client_id,
        data.azuread_service_principal.workbench_managed_identity.client_id,
        data.azuread_service_principal.strategy_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    GATEWAY_BASE_URL   = "https://${local.capital_gateway_hostname}"
    GATEWAY_STREAM_URL = "wss://${local.capital_gateway_hostname}/ws/stream"
    # What this module presents to the gateway besides the key: a token of its own
    # identity, for the gateway's audience. Set here rather than left to the module,
    # because the absence of this setting is what selects local work, where there is no
    # directory to ask (the-gateway-door-authenticates). The stream is not covered by it —
    # `/ws/stream` is outside the gateway's authenticator, so the key is what opens it.
    GATEWAY_SCOPE   = "${local.capital_gateway_api_uri}/.default"
    GATEWAY_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.gateway_api_key})"

    # No credential in the URL and no AZURE_* triple here — config.py refuses a
    # DATABASE_URL that carries one, and the App Service's own system-assigned identity
    # is ambient (db.py's DefaultAzureCredential finds it with no configuration), unlike
    # the developer machine's service principal in .env. DATABASE_USER is the role
    # 5.7 created in Postgres for this identity — named after this app on purpose, so the
    # two never drift apart.
    DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.prod.name}?sslmode=require"
    DATABASE_USER = local.market_data_app_name

    # The module migrates its own database inside the lifespan, so App Service's warm-up
    # window has to outlast the longest migration this module can run — the candle table
    # is the largest thing in the system. 1800 is the platform's own ceiling here, which
    # is why `migration_lock_wait_seconds` (market_data/config.py) sits below it at 1500
    # rather than the other way round: the module has to be the one that gives up first
    # and says why. The platform giving up first restarts the container, which starts the
    # same migration again and explains nothing.
    WEBSITES_CONTAINER_START_TIME_LIMIT = "1800"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.market_data_easy_auth.password

    # Something *is* in front of this app, so the module refuses to hand out stream
    # tickets to a request Easy Auth did not identify. It does not take that on trust:
    # were `auth_settings_v2` above switched off by a careless edit, this setting is what
    # turns an open ticket factory — which is an open stream — into a refusal.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    # Which caller reaches which surface, once Easy Auth has let it through the door.
    # The workbench is here for the eleven read-only tools at `/mcp`; without this list it
    # would also reach `POST /pairs` and `DELETE /pairs/{symbol}`, because the gate in
    # front authorizes an application and not a route. The terminal is the caller of the
    # REST contract and has no business on `/mcp`.
    #
    # Client ids, and only client ids — the same identifiers `allowed_applications` above
    # is written in, because the module reads the same fact from the token: the `azp`
    # (or `appid`) claim naming the application the token was issued to.
    #
    # This list carried object ids too for one afternoon, on the theory that Easy Auth
    # might put either in `X-MS-CLIENT-PRINCIPAL-ID`. Measured in production on
    # 19 August 2026 instead: for the terminal's delegated token that header carries the
    # signed-in **person's** object id, so no list of application identifiers could ever
    # have matched it, and every REST request was refused until the image was rolled back.
    # The module reads the claims blob now (`market_data/caller_access.py`), which is the
    # only place the calling application appears for both kinds of token.
    TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id

    # Two REST callers since the strategy platform arrived, and the second one is a
    # program rather than a person. It reads `/candles` and `POST /indicators` — the REST
    # contract, deliberately not `/mcp`: that surface is narrowed for a model (ten
    # indicators a call, two hundred points a series), which is right for an agent and too
    # tight for a loop reading three hundred bars of three facts at once.
    REST_CALLER_APPLICATION_IDS = join(",", [
      azuread_application.terminal.client_id,
      data.azuread_service_principal.strategy_managed_identity.client_id,
    ])

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# workbench: public, Easy Auth-gated, same shape as market-data — Static Web Apps cannot
# proxy its stream any more than it can market-data's WebSocket, so the terminal calls this
# app's own hostname directly, same as it does market-data's.
#
# **Two surfaces in one app since `agent-and-teams-one-workbench`:** the operator's
# conversation and the teams they compose and run. Two databases, two OpenAI keys and two
# model catalogues, one process — and one identity, which is what made keeping the resource
# name worth more than fixing it (`workbench_app_name` above).
#
# One request to the teams half starts a whole team of model calls, which is why
# `REQUIRE_AUTHENTICATED_PRINCIPAL` below matters more here than anywhere else in this
# file: the process refuses to trust that the Easy Auth block above it was left switched on
# (specs/teams-browser-access, "Moduł nie bierze na wiarę warstwy przed sobą").
resource "azurerm_linux_web_app" "workbench" {
  name                = local.workbench_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `websockets_enabled`: the turn streams over plain HTTP (`fetch` +
    # `ReadableStream`), never a WebSocket upgrade — design.md, "Odpowiedź
    # strumieniem: fetch + ReadableStream, nie EventSource".

    # Same reasoning as market-data's own CORS block above: the preflight for a
    # cross-origin request carrying `Authorization` has no credential on it at all,
    # and Easy Auth would refuse it before the container ever saw it. The workbench MUST
    # NOT add a CORS middleware of its own for the same reason market-data's own comment
    # gives — two layers would double the header and a browser rejects that.
    cors {
      allowed_origins     = [local.terminal_origin]
      support_credentials = false
    }

    application_stack {
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }
  }

  # Return401, not RedirectToLoginPage — same reasoning as market-data's own block:
  # the terminal reaches this app through `fetch()`, and a redirect resolves to an
  # HTML login page masquerading as a JSON body.
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # The health probe, and nothing else — the same exemption market-data's `/ping`
    # carries, for the same reason: every other path answers Easy
    # Auth's 401 before the container is reached, dead or alive alike, so the deploy
    # workflow had no way to tell a serving process from a crash loop. It read the
    # control plane instead and reported green over a container exiting with code 3
    # (16 August 2026).
    #
    # This route reads nothing and returns a fixed body (`workbench/app.py`), so there is
    # nothing here to protect. What makes it enough is the lifespan: it does not finish
    # until **both** migrations do, so a process that answers this at all has two databases
    # at the revisions its image was built for.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = module.workbench_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both audiences, deliberately — see the long comment on `module.workbench_easy_auth`
      # in entra.tf. The terminal's existing token (asked for by market-data's scope)
      # carries market-data's audience; a terminal asking for this app's own scope by name
      # carries this application's instead. Either is accepted.
      allowed_audiences = [
        local.workbench_api_uri,
        module.workbench_easy_auth.client_id,
        local.market_data_api_uri,
        module.market_data_easy_auth.client_id,
      ]

      # One caller: the terminal, holding the operator's own delegated token. There used to
      # be a second — teams-mcp, forwarding that same token from one process to another —
      # and it went away with the process. The identity now travels inside this one
      # (`teams_tools/operator.py`).
      allowed_applications = [azuread_application.terminal.client_id]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # **Two databases, one identity.** No credential in either URL and no AZURE_CLIENT_*
    # triple — `workbench/config.py` refuses a URL carrying one when DATABASE_USER is set,
    # and the system-assigned identity is ambient. One DATABASE_USER for both, because one
    # App Service presents one identity: that role has to exist in *both* databases, which
    # is the single operator step this merge carries
    # (`agent-and-teams-one-workbench/design.md`, Migration Plan).
    AGENT_DATABASE_URL = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.agent.name}?sslmode=require"
    TEAMS_DATABASE_URL = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.teams.name}?sslmode=require"
    DATABASE_USER      = local.workbench_app_name

    # The one credential this process cannot replace with an identity: OpenAI is not in
    # Entra, so there is nothing to present a managed-identity token to. Key Vault
    # references rather than literals — neither value enters Terraform state or a deploy
    # log (key-vault.tf).
    #
    # **Two keys, still.** The teams experiments bill against their own so their cost has
    # its own line; that was always about the invoice and never about the process boundary,
    # and one process with two clients buys the same thing.
    AGENT_OPENAI_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.openai_api_key})"
    TEAMS_OPENAI_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.teams_openai_api_key})"

    # Two catalogues, from two variables, for the reason their descriptions give. Nothing
    # in this root creates these models; the variables exist so a fourth entry is one line
    # here rather than a hand-edited app setting. No TEAMS_DEFAULT_MODEL_ID to pair with
    # the conversation's: every agent in a saved revision names its own model
    # (specs/teams-models).
    AGENT_MODELS = jsonencode([
      for id, m in var.agent_models : {
        id                 = id
        model              = m.model
        display_name       = m.display_name
        cost_rank          = m.cost_rank
        input_rate_per_1m  = m.input_rate_per_1m
        output_rate_per_1m = m.output_rate_per_1m
      }
    ])
    TEAMS_MODELS = jsonencode([
      for id, m in var.teams_models : {
        id                 = id
        model              = m.model
        display_name       = m.display_name
        cost_rank          = m.cost_rank
        input_rate_per_1m  = m.input_rate_per_1m
        output_rate_per_1m = m.output_rate_per_1m
      }
    ])
    # The cheapest entry — same choice `.env.example` documents: "Domyślny model to
    # najtańszy (Luna); najdroższy wybiera się świadomie."
    AGENT_DEFAULT_MODEL_ID = "gpt-5.6-luna"

    # The read tool server, read by both surfaces, and the scope this app's managed
    # identity asks Entra for a token to reach it with. It is **market-data itself** since
    # `market-mcp-into-market-data` — the tools are a route of the archive, so this is the
    # archive's hostname and the archive's scope; the setting keeps its name because what
    # moved is the address, not the relationship. Both or neither: `workbench/config.py`
    # refuses a remote URL with no scope at startup. Removing MARKET_MCP_URL is also the
    # rollback for the whole tool loop — the conversation falls back to answering without
    # tools, which is a path its own tests walk, and a team assigning tools is refused at
    # run time rather than left to guess.
    MARKET_MCP_URL   = "https://${local.market_data_hostname}"
    MARKET_MCP_SCOPE = "${local.market_data_api_uri}/.default"

    # There is no TEAMS_MCP_URL any more. The tools that build and run teams are a layer in
    # this process — no address, no scope, no second hop, and nothing to set last.

    # The second tool server — the demo account, through trading-mcp. Same both-or-neither
    # rule, checked per server, and the same rollback shape: clearing TRADING_MCP_URL takes
    # the account tools away and leaves the archive's exactly where they are, with the rows
    # in `tool_calls` still recording what happened while it had them.
    #
    # This is the setting with the larger consequence of the two, because four of the tools
    # behind it change the account rather than read it. It only works alongside the entry in
    # trading-mcp's own `allowed_applications` below: without that, the process starts,
    # asks, and is refused at the door.
    TRADING_MCP_URL   = "https://${local.trading_mcp_hostname}"
    TRADING_MCP_SCOPE = "${local.trading_mcp_api_uri}/.default"

    # The third tool server — the prediction-market archive. Same both-or-neither rule,
    # checked per server, and the same rollback: clearing POLYMARKET_MCP_URL takes those
    # nine tools away and leaves the other two servers' exactly where they are.
    #
    # **This pair MUST reach the app before the image that uses it**, which is the trap
    # every module here has had: the setting and the entry in polymarket-data's
    # `allowed_applications` above are one apply, and an apply landing after the workbench
    # deploy is an outage in between. Neither substitutes for the other — without the
    # entry, this process starts, asks, and is refused at the door.
    POLYMARKET_MCP_URL   = "https://${local.polymarket_data_hostname}"
    POLYMARKET_MCP_SCOPE = "${local.polymarket_data_api_uri}/.default"

    # The teams surface's own clock — schedules and triggers fire from a task in this app's
    # `lifespan`, not from anything in Azure. A timer calling in from outside would need its
    # own Entra registration to get past Easy Auth, and would put the schedule in Terraform,
    # which is to say back in the operator's hands rather than in the catalogue where they
    # set it.
    #
    # **On, and this is the one setting in this file whose value is a decision rather than a
    # fact.** `teams/config.py` defaults it to `true`, so this line does not turn the clock
    # on so much as state that it is meant to be on: deleting it would leave the clock
    # running and say nothing about whether anyone chose that. Back to `"false"` is one line
    # and an `apply`, and it leaves the catalogue untouched — a run started by hand works
    # either way (specs/teams-schedules, "Budzenie wyłączone ustawieniem").
    SCHEDULER_ENABLED = "true"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.workbench_easy_auth.password

    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# Secret-read access only — Set/Delete/Purge stays with the operator (key-vault.tf).
# Keyed the same as `local.web_app_names`, so the grant above and every count below read
# the same list of apps. A new module appears in both or in neither.
locals {
  web_app_principal_ids = {
    "capital-gateway" = azurerm_linux_web_app.capital_gateway.identity[0].principal_id
    "market-data"     = azurerm_linux_web_app.market_data.identity[0].principal_id
    "workbench"       = azurerm_linux_web_app.workbench.identity[0].principal_id
    "trading-mcp"     = azurerm_linux_web_app.trading_mcp.identity[0].principal_id
    "polymarket-data" = azurerm_linux_web_app.polymarket_data.identity[0].principal_id
    "strategy"        = azurerm_linux_web_app.strategy.identity[0].principal_id
  }
}

# One grant, seven apps. Every one of them is the same three lines with a different managed
# identity, and writing them out seven times is how market-mcp reached production on
# 13 August 2026 without one at all: it holds no application secret of its own, so the
# resource looked unnecessary and was simply never written. It was not unnecessary.
# `docker_registry_password` is a `@Microsoft.KeyVault(...)` reference like everybody
# else's, and a reference the app cannot resolve does not fail loudly — it resolves to
# nothing, and the image pull that follows reports the only thing it can see:
#
#   DockerApiException: Head "https://ghcr.io/v2/.../market-mcp/manifests/<sha>":
#   unauthorized
#
# which reads as a broken registry credential and sent the first hour of diagnosis to GHCR.
# The same token, read out of this vault by hand, pulls that exact manifest. A `for_each`
# over the app list cannot leave one out.
#
# Two of the seven have more than the registry token to resolve, and neither reference is
# optional: `teams` reads `teams-openai-api-key`, and `trading-mcp` reads
# `CAPITAL_GATEWAY_API_KEY` and refuses to start with a blank one.
#
# Read-only in every case. Writing the values stays with the operator (key-vault.tf).
resource "azurerm_key_vault_access_policy" "apps" {
  for_each = local.web_app_principal_ids

  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = each.value

  secret_permissions = ["Get", "List"]
}

output "capital_gateway_hostname" {
  value = azurerm_linux_web_app.capital_gateway.default_hostname
}

output "market_data_hostname" {
  value = azurerm_linux_web_app.market_data.default_hostname
}

output "workbench_hostname" {
  value = azurerm_linux_web_app.workbench.default_hostname
}

output "market_data_managed_identity_principal_id" {
  description = "Postgres role creation (5.7 / old 4.7) needs this object id."
  value       = azurerm_linux_web_app.market_data.identity[0].principal_id
}

output "workbench_managed_identity_principal_id" {
  description = "The operator's one-off Postgres role creation needs this object id — and needs it in **both** databases now, `agent` and `teams`, because one App Service presents one identity (agent-and-teams-one-workbench/design.md, Migration Plan)."
  value       = azurerm_linux_web_app.workbench.identity[0].principal_id
}

# The workbench's own client id — what market-data's `allowed_applications` and its
# TOOL_CALLER_APPLICATION_IDS both have to name: `azurerm_linux_web_app.identity` publishes
# `principal_id` and `tenant_id` only, and the identity's `client_id` lives on the service
# principal found by that object id. One lookup where there were two: the conversation and
# the teams runner present the same identity now.
data "azuread_service_principal" "workbench_managed_identity" {
  object_id = azurerm_linux_web_app.workbench.identity[0].principal_id
}

# The two service callers of capital-gateway, for its own `allowed_applications`. They
# reach that module with a shared key today and with a token of their own from
# `the-gateway-door-authenticates` onward; the lookup is here for the same reason the
# workbench's is — an App Service identity publishes an object id, and the door needs a
# client id.
data "azuread_service_principal" "market_data_managed_identity" {
  object_id = azurerm_linux_web_app.market_data.identity[0].principal_id
}

data "azuread_service_principal" "trading_mcp_managed_identity" {
  object_id = azurerm_linux_web_app.trading_mcp.identity[0].principal_id
}

# trading-mcp: a tool server, and shaped unlike market-data: its only caller is a backend
# service presenting a managed identity, so there is no delegated scope and no consent
# screen — only client credentials.
#
# Where it differs from every other tool surface here is what sits behind it. The archive's
# tools read an archive; this one places orders on a live broker connection, and every
# gate below is
# written as narrow as it can be: one caller in `allowed_applications`, one exempt path,
# and a credential the app resolves from Key Vault rather than one this root ever holds.
module "trading_mcp_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-trading-mcp-easyauth"
  identifier_uri = local.trading_mcp_api_uri
  redirect_uri   = "https://${local.trading_mcp_hostname}/.auth/login/aad/callback"

  # No scope: client credentials only, so there is no consent screen to name one for.
}

resource "azurerm_linux_web_app" "trading_mcp" {
  name                = local.trading_mcp_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # Not for reaching capital-gateway — that is a static key in a header, checked by the
  # gateway on every caller including this one. This identity exists so the app can read
  # its own Key Vault references (the GHCR pull token and that very key), which is the
  # grant `azurerm_key_vault_access_policy.apps["trading-mcp"]` makes.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `cors`: no browser ever calls this app, so there is no preflight to answer, and the
    # gate on who may reach it is Easy Auth below. No `ip_restriction` either — and neither has
    # any other app here, which is worth saying because three files claimed otherwise until
    # 20 August 2026. Nothing in this root has ever set one. What differs between these apps is
    # only which credential their door asks for.

    application_stack {
      # Placeholder — `deploy-trading-mcp.yml` (group 10) pushes the real GHCR image after
      # the first build; the lifecycle block below is what stops Terraform reverting it.
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }
  }

  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # The health probe and nothing else, exactly as market-data and teams have it: the
    # platform restarts the container off this response and speaks no Easy Auth
    # (specs/trading-mcp-transport, "Zdrowie modułu da się sprawdzić bez sesji MCP"). It
    # answers with the module's own state and names neither the account nor the tools.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = module.trading_mcp_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      allowed_audiences = [
        local.trading_mcp_api_uri,
        module.trading_mcp_easy_auth.client_id,
      ]

      # **Two callers, and it is a list of two on purpose** (specs/trading-mcp-transport,
      # "Wołający jest wskazany imiennie" — an enumerated list, never "anyone authenticated
      # in the directory"). The terminal is still not one of them and never will be: a
      # browser talks to the workbench, and the workbench talks here.
      #
      # `teams` was the only entry until `agent-gets-the-trading-tools`, when the operator
      # decided the chat should reach the account too — deliberately, and on the full set
      # including the four tools that write. The spec asks for exactly that: "dopisanie
      # kolejnego ma być decyzją, nie skutkiem ubocznym". Each name here is one more thing
      # that can move the account, and this list is still the largest lever in this file.
      #
      # Two entries became one when the chat and the teams runner became one process: the
      # same two callers, presenting the same identity. Nothing gained access it did not
      # have, and nothing lost any.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # The gateway by its own hostname, over TLS. Its firewall (top of this file) admits
    # this app's outbound addresses; its `X-Gateway-Key` check admits the credential
    # below. Both are needed — the gateway checks the header on every caller, loopback
    # included, so there is no address here that would make the key optional
    # (`trading_mcp/config.py`).
    CAPITAL_GATEWAY_URL = "https://${local.capital_gateway_hostname}"

    # The same secret capital-gateway itself reads and market-data presents — one value,
    # three readers, and a Key Vault reference rather than a literal so it never enters
    # Terraform state or a deploy log. With no value in the vault the reference resolves
    # to nothing and this module refuses to start, which is the intended failure and not
    # a quiet one (`config.py` requires the key).
    CAPITAL_GATEWAY_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.gateway_api_key})"
    # The same second credential market-data presents, for the same reason: the gateway's
    # door validates a token rather than trusting a key two modules share. Unset — local
    # work — leaves the key as the whole credential (the-gateway-door-authenticates).
    CAPITAL_GATEWAY_SCOPE = "${local.capital_gateway_api_uri}/.default"

    # App Service's default expectation for a Linux custom container, matching what the
    # Dockerfile's own ENV sets. Said here as well as there so a reader of either file
    # sees the number the other one uses (no WEBSITES_PORT override, like the other five).
    TRADING_MCP_PORT = "80"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.trading_mcp_easy_auth.password

    # The module checks the caller's identity itself rather than trusting that the block
    # above is switched on — the same refusal to take the platform on faith that
    # market-data and teams both make (specs/trading-mcp-transport, "Wołający jest wskazany
    # imiennie": a request with no established identity is refused before it reaches a
    # tool). For a module that writes to an account, the
    # failure this guards against is the one that would matter most.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

output "trading_mcp_hostname" {
  value = azurerm_linux_web_app.trading_mcp.default_hostname
}

# polymarket-data: the prediction-market archive, shaped like trading-mcp rather than like
# market-data — one backend caller presenting a managed identity, no delegated scope and no
# consent screen.
#
# What sits behind it is an archive and a watch list, never money: this system does not
# trade on Polymarket, and the three tools of nine that write write the watch list. So the
# narrow gate here is not about an account. It is that **the tool caller must not reach the
# route that deletes collected history** — the one act in this module nobody can undo — and
# Easy Auth cannot express that, because it authorizes an application and not a route. The
# two settings below are what does (`polymarket_data/caller_access.py`).
module "polymarket_data_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-polymarket-data-easyauth"
  identifier_uri = local.polymarket_data_api_uri
  redirect_uri   = "https://${local.polymarket_data_hostname}/.auth/login/aad/callback"

  # No scope: client credentials only, so there is no consent screen to name one for. The
  # terminal's subpage is the change that adds a delegated one.
}

resource "azurerm_linux_web_app" "polymarket_data" {
  name                = local.polymarket_data_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # Two things need it, and Polymarket is neither — that upstream is public and this module
  # presents nothing to it. It is the database (an Entra token fetched at connection time,
  # `DATABASE_USER` below being this identity) and the GHCR pull token in Key Vault.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `cors`: the terminal has no subpage here yet, so no browser calls this app and
    # there is no preflight to answer. The change that adds that subpage adds these two
    # lines with it — and, like every other app in this file, MUST NOT also add a CORS
    # middleware inside the module, because two layers each appending the header produce a
    # doubled one that a browser rejects.
    #
    # No `ip_restriction` either, like the other four. Nothing in this root has ever set
    # one; what differs between these apps is only which credential their door asks for.

    application_stack {
      # Placeholder — `deploy-polymarket-data.yml` pushes the real GHCR image; the
      # lifecycle block below is what stops Terraform reverting it.
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }
  }

  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # The health route and nothing else — the platform restarts the container off this
    # response and speaks no Easy Auth, and `scripts/deploy_probe.py` reads the same path
    # to ask whether the process inside came up. It answers with the module's own state and
    # names no tracked event.
    excluded_paths = ["/"]

    active_directory_v2 {
      client_id                  = module.polymarket_data_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both spellings of the same request, for market-data's reason: a token asked for by
      # scope name arrives with the `api://` uri as its audience, one asked for as
      # `<client-id>/.default` arrives with the client id.
      allowed_audiences = [
        local.polymarket_data_api_uri,
        module.polymarket_data_easy_auth.client_id,
      ]

      # One caller, named. The workbench's managed identity, for the nine tools at `/mcp`.
      # The terminal is deliberately not here: it has nothing to call yet, and adding it
      # ahead of the subpage would open the REST contract — deleting history included — to
      # a client that does not use it.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # No credential in the URL and no AZURE_* triple — `polymarket_data/config.py` refuses
    # a DATABASE_URL carrying one when DATABASE_USER is set, and the system-assigned
    # identity is ambient. DATABASE_USER is the role the operator's one-off
    # `scripts/grant-schema-ownership.sql` creates, named after this app so the two cannot
    # drift apart.
    DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.polymarket.name}?sslmode=require"
    DATABASE_USER = local.polymarket_data_app_name

    # Polymarket's two public surfaces. Set here rather than left to the module's defaults
    # for the reason every other upstream address in this file is set here: the address a
    # deployment talks to is a fact of the deployment, and a default that quietly changed
    # under a dependency bump would move it with nothing in this root to say so.
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    CLOB_BASE_URL  = "https://clob.polymarket.com"

    # Measured, not decorative: the provider's edge refuses `Python-urllib/*` with 403
    # "error code: 1010" on both surfaces (22 August 2026). A library default is a value
    # somebody else decides, and its changing on a dependency bump would read as an access
    # refusal with no change in this module.
    PROVIDER_USER_AGENT = "tradingcenter-polymarket-data/0.1 (+https://github.com/MarekGrzeska)"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.polymarket_data_easy_auth.password

    # The module checks the caller's identity itself rather than trusting the block above
    # is switched on — the same refusal to take the platform on faith market-data,
    # trading-mcp and the workbench all make.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    # Which caller reaches which surface once Easy Auth has let it through. Client ids and
    # only client ids: the module reads the `azp`/`appid` claim naming the application the
    # token was issued to, never `X-MS-CLIENT-PRINCIPAL-ID`, which for a delegated token
    # names the person at the keyboard (measured elsewhere in this repository on
    # 19 August 2026, by deploying the opposite assumption).
    #
    # `REST_CALLER_APPLICATION_IDS` is empty on purpose, and that is a refusal rather than
    # an omission: the REST contract has no consumer in production until the terminal grows
    # its subpage, and an empty list means nobody reaches it. Deleting collected history is
    # a REST route, so nobody in production can do that either — which is the intended
    # state for an act nobody can undo, until there is a screen to do it from.
    TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id
    REST_CALLER_APPLICATION_IDS = ""

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

output "polymarket_data_hostname" {
  value = azurerm_linux_web_app.polymarket_data.default_hostname
}

output "polymarket_data_managed_identity_principal_id" {
  description = "The operator's one-off Postgres role creation in the `polymarket` database needs this object id (scripts/grant-schema-ownership.sql)."
  value       = azurerm_linux_web_app.polymarket_data.identity[0].principal_id
}

# There is no teams-mcp block below this line any more. That module's tools became a
# layer inside the workbench (`agent-and-teams-one-workbench`), so what went with it is a
# whole App Service, an Easy Auth registration with its secret, a managed identity, a
# service-principal lookup, a Key Vault policy and a hostname output — and the second
# network hop every "run this team" used to make.

# --- the strategy platform ------------------------------------------------------------
#
# The fifth app, and the second one whose callers are all programs. It reads market-data's
# REST contract and is read by the workbench's triggers.
#
# **A fifth tenant on the plan is the thing to watch after this deploys.** The B3 decision
# above was taken at six apps and 84% of 3.5 GB, and this file's own history says a module
# weighs 150-310 MB. Read `plan_memory` (monitoring.tf, alert at 92%) over a week before
# concluding anything — the same instruction the last two SKU changes left, and for the
# same reason: a measurement beats an arithmetic.
data "azuread_service_principal" "strategy_managed_identity" {
  object_id = azurerm_linux_web_app.strategy.identity[0].principal_id
}

module "strategy_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-strategy-easyauth"
  identifier_uri = local.strategy_api_uri
  redirect_uri   = "https://${local.strategy_hostname}/.auth/login/aad/callback"

  # No scope. The terminal reads this module's decisions with a token for this app's own
  # registration, and the workbench presents a managed identity — neither path goes
  # through a consent screen, so there is nothing here for one to name.
}

resource "azurerm_linux_web_app" "strategy" {
  name                = local.strategy_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true

    # CORS belongs here rather than in the application, for the reason the three blocks
    # above it give: the terminal calls across origins, and a preflight carries no
    # credential of any kind, so Easy Auth would refuse it before the app ever saw it.
    cors {
      allowed_origins     = [local.terminal_origin]
      support_credentials = false
    }

    application_stack {
      # Placeholder — `deploy-strategy.yml` pushes the real GHCR image after the first
      # build; the lifecycle block below is what stops Terraform reverting it.
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }
  }

  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # One path, and it has to be the one this module's own caller record also treats as
    # open — `strategy/caller_access.py`, `OPEN_PATHS`. Two gates stand in front of every
    # request here, and exempting a path from only one of them is not exempting it: it
    # reads as open in this file and answers 401 from the module.
    #
    # That is exactly what happened to `/health`, which sat here until the deploy of
    # d2e2290 failed on it. `/ping` is the one this module opens, because it answers a
    # constant that never varies with anything the module holds — and it proves as much
    # about a deploy as `/health` would, since the lifespan serves nothing until its
    # migration is done.
    excluded_paths = ["/ping"]

    active_directory_v2 {
      client_id                  = module.strategy_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both spellings of this app's audience, for the reason `infra` learned on
      # market-data's on 21 August 2026: a token asked for by scope name carries the
      # `api://` uri, one asked for as `<client-id>/.default` carries the client id, and a
      # list holding only the first looks like a working configuration until something
      # asks the other way.
      allowed_audiences = [
        local.strategy_api_uri,
        module.strategy_easy_auth.client_id,
      ]

      # Two callers, each here for one of this module's two surfaces. The workbench
      # reaches `/mcp`, where its triggers read `pending_setups`; the terminal reaches the
      # REST contract. Which may reach which is not something this list can say — Easy
      # Auth authorizes an application, not a route — so the two settings below are what
      # actually keeps them apart (`strategy/caller_access.py`). Both are required;
      # neither substitutes for the other.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
        azuread_application.terminal.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # The archive by its own hostname, over TLS, and its REST contract rather than `/mcp`:
    # that surface is narrowed for a model and too tight for a loop reading three hundred
    # bars of three facts at once. market-data's `REST_CALLER_APPLICATION_IDS` admits this
    # identity; its `allowed_applications` admits it through the door.
    MARKET_DATA_URL = "https://${local.market_data_hostname}"
    # What this module presents to the archive: a token of its own identity for the
    # archive's audience. Set here rather than left to the module, because the absence of
    # this setting is what selects local work, where there is no directory to ask.
    MARKET_DATA_SCOPE = "${local.market_data_api_uri}/.default"

    # No credential in the URL and no AZURE_* triple: `config.py` refuses a DATABASE_URL
    # carrying one, and the App Service's own system-assigned identity is ambient.
    # DATABASE_USER is the role the operator creates once in Postgres for this identity —
    # named after this app on purpose, so the two never drift apart.
    DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.strategy.name}?sslmode=require"
    DATABASE_USER = local.strategy_app_name

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.strategy_easy_auth.password

    # The module does not take the block above on trust: were `auth_settings_v2` switched
    # off by a careless edit, this setting is what keeps both surfaces from answering an
    # unidentified caller.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    # Which caller reaches which surface, once Easy Auth has let it through the door.
    # Client ids, and only client ids — the same identifiers `allowed_applications` above
    # is written in, because the module reads the same fact from the token: the `azp` (or
    # `appid`) claim naming the application it was issued to, never the principal-id
    # header, which for a delegated token names the signed-in person.
    TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id
    REST_CALLER_APPLICATION_IDS = azuread_application.terminal.client_id

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

output "strategy_hostname" {
  value = azurerm_linux_web_app.strategy.default_hostname
}

output "strategy_managed_identity_principal_id" {
  description = "The operator's one-off Postgres role creation in the `strategy` database needs this object id — and `scripts/grant-schema-ownership.sql` has to be run there too, before the first deploy tries to migrate."
  value       = azurerm_linux_web_app.strategy.identity[0].principal_id
}
