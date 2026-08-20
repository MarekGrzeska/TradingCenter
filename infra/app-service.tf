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

  # Deterministic App Service hostnames — used ahead of `terraform apply` (e.g. in the
  # Easy Auth redirect URI below) instead of waiting on the computed `default_hostname`,
  # since Azure names of this form are `<name>.azurewebsites.net` with no surprises.
  capital_gateway_hostname = "${local.capital_gateway_app_name}.azurewebsites.net"
  market_data_hostname     = "${local.market_data_app_name}.azurewebsites.net"
  workbench_hostname       = "${local.workbench_app_name}.azurewebsites.net"
  trading_mcp_hostname     = "${local.trading_mcp_app_name}.azurewebsites.net"

  # What `market-data` is called when it is the *resource* a token is asked for, rather
  # than the app serving a request. The terminal asks Entra for `<uri>/<scope>`; Easy
  # Auth accepts a token whose audience is this.
  market_data_api_uri   = "api://tradingcenter-market-data"
  market_data_api_scope = "access_as_user"

  # Same idea, one level out, for the tool server that writes. Unlike market-data's, this
  # pairs with no delegated scope: the only caller is
  # `teams`, presenting a client-credentials token from its managed identity. A browser
  # never asks for this one, and there is nobody to consent on whose behalf.
  trading_mcp_api_uri = "api://tradingcenter-trading-mcp"

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

# capital-gateway: not public. design.md, "Uwierzytelnianie gatewaya w kodzie, nie w
# konfiguracji platformy" — the in-code X-Gateway-Key check is the first layer; this
# ip_restriction is the second. Its callers are market-data and, since phase 2 of the
# teams work, trading-mcp — both on the same plan, so the exception is those apps' own
# outbound addresses rather than "the internet." Read from their resources (5.6 does the
# same for the database firewall) — never typed by hand, because they change with the
# plan's SKU.
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
    always_on                     = true
    websockets_enabled            = true
    ip_restriction_default_action = "Deny"

    application_stack {
      # Placeholder — group 7's deploy workflow pushes the real GHCR image after the
      # first build. Terraform must not fight that: see the lifecycle block below.
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }

    dynamic "ip_restriction" {
      for_each = azurerm_linux_web_app.market_data.possible_outbound_ip_address_list
      content {
        name        = "AllowMarketData-${ip_restriction.key}"
        action      = "Allow"
        ip_address  = "${ip_restriction.value}/32"
        priority    = 100 + tonumber(ip_restriction.key)
        description = "market-data's own outbound address read from its resource"
      }
    }

    # The gateway's second caller, and the first one that writes: `trading-mcp` places
    # orders through this app (specs/trading-mcp-upstream-access). Its own block, read off
    # its own resource, rather than a widened market-data rule — the two apps share a plan
    # today and will very likely report the same addresses, but that is a fact about the
    # plan, not a promise, and a rule named after the module that needs it is the one that
    # can be removed with the module.
    #
    # What this does NOT buy is a second rate budget: capital.com counts its 10 req/s
    # against the *account*, so the tools called here spend the same allowance market-data
    # fills the archive from (design.md, "Drugi wołający `capital-gateway`").
    dynamic "ip_restriction" {
      for_each = azurerm_linux_web_app.trading_mcp.possible_outbound_ip_address_list
      content {
        name        = "AllowTradingMcp-${ip_restriction.key}"
        action      = "Allow"
        ip_address  = "${ip_restriction.value}/32"
        priority    = 200 + tonumber(ip_restriction.key)
        description = "trading-mcp's own outbound address read from its resource"
      }
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

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    # The deploy workflow (group 7) sets the real image tag with `az webapp config
    # container set` / webapps-deploy — Terraform reverting that to the placeholder on
    # every apply would fight the thing that is supposed to own this value.
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
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
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    GATEWAY_BASE_URL   = "https://${local.capital_gateway_hostname}"
    GATEWAY_STREAM_URL = "wss://${local.capital_gateway_hostname}/ws/stream"
    GATEWAY_API_KEY    = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.gateway_api_key})"

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
    REST_CALLER_APPLICATION_IDS = azuread_application.terminal.client_id

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
    # No `cors` and no `ip_restriction`, unlike market-data: no browser ever calls this
    # app, so there is no preflight to answer, and the gate on who
    # may reach it is Easy Auth below rather than an address list.

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

# There is no teams-mcp block below this line any more. That module's tools became a
# layer inside the workbench (`agent-and-teams-one-workbench`), so what went with it is a
# whole App Service, an Easy Auth registration with its secret, a managed identity, a
# service-principal lookup, a Key Vault policy and a hostname output — and the second
# network hop every "run this team" used to make.
