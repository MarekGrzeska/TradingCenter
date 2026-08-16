# One Linux App Service Plan, six apps (capital-gateway, market-data, market-mcp, agent,
# teams, trading-mcp — design.md, "App Service, nie Container Apps"): all of them run
# non-stop, so one shared plan is cheaper than as many Container Apps billed by CPU-second.
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
  capital_gateway_app_name = "app-tradingcenter-gateway"
  market_data_app_name     = "app-tradingcenter-market-data"
  market_mcp_app_name      = "app-tradingcenter-market-mcp"
  agent_app_name           = "app-tradingcenter-agent"
  teams_app_name           = "app-tradingcenter-teams"
  trading_mcp_app_name     = "app-tradingcenter-trading-mcp"
  teams_mcp_app_name       = "app-tradingcenter-teams-mcp"

  # Deterministic App Service hostnames — used ahead of `terraform apply` (e.g. in the
  # Easy Auth redirect URI below) instead of waiting on the computed `default_hostname`,
  # since Azure names of this form are `<name>.azurewebsites.net` with no surprises.
  capital_gateway_hostname = "${local.capital_gateway_app_name}.azurewebsites.net"
  market_data_hostname     = "${local.market_data_app_name}.azurewebsites.net"
  market_mcp_hostname      = "${local.market_mcp_app_name}.azurewebsites.net"
  agent_hostname           = "${local.agent_app_name}.azurewebsites.net"
  teams_hostname           = "${local.teams_app_name}.azurewebsites.net"
  trading_mcp_hostname     = "${local.trading_mcp_app_name}.azurewebsites.net"
  teams_mcp_hostname       = "${local.teams_mcp_app_name}.azurewebsites.net"

  # What `market-data` is called when it is the *resource* a token is asked for, rather
  # than the app serving a request. The terminal asks Entra for `<uri>/<scope>`; Easy
  # Auth accepts a token whose audience is this.
  market_data_api_uri   = "api://tradingcenter-market-data"
  market_data_api_scope = "access_as_user"

  # Same idea, one level down: what market-mcp is called when *it* is the resource a
  # token is asked for — this time by a service's managed identity (client-credentials),
  # never a signed-in user, so there is no delegated scope to pair it with (contrast
  # `market_data_api_scope` above).
  market_mcp_api_uri = "api://tradingcenter-market-mcp"

  # And the same one level further out, for the tool server that writes. Like market-mcp's
  # and unlike market-data's, this pairs with no delegated scope: the only caller is
  # `teams`, presenting a client-credentials token from its managed identity. A browser
  # never asks for this one, and there is nobody to consent on whose behalf.
  trading_mcp_api_uri = "api://tradingcenter-trading-mcp"

  # And once more for the tool server the agent builds teams through. Its only caller is
  # `agent`'s managed identity, so it pairs with no delegated scope either — but note
  # what travels *inside* a call to it: the operator's own token, in a header of its own,
  # which is a different credential answering a different question and is not what this
  # audience is about (add-teams-mcp design.md, D2).
  teams_mcp_api_uri = "api://tradingcenter-teams-mcp"

  # The same shape for the agent's own registration (entra.tf) — see the comment there
  # for why its scope is granted to the terminal today but not yet the one the
  # terminal's token actually carries.
  agent_api_uri   = "api://tradingcenter-agent"
  agent_api_scope = "access_as_user"

  # And the same for teams (entra.tf). It is both a resource — the terminal asks for a
  # token naming it — and a caller: its managed identity presents one to market-mcp, the
  # way the agent's does.
  teams_api_uri   = "api://tradingcenter-teams"
  teams_api_scope = "access_as_user"

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
  # `ImagePullUnauthorizedFailure` in the docker log. Identical for both apps, so said
  # once here rather than twice below.
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
resource "azuread_application" "market_data_easy_auth" {
  display_name = "app-tradingcenter-market-data-easyauth"

  # A static name, not `api://<client-id>`: the client id is computed by this very
  # resource, and a resource cannot refer to itself.
  identifier_uris = [local.market_data_api_uri]

  api {
    # v2 tokens, matching the `/v2.0` tenant endpoint Easy Auth is configured with below.
    # A v1 token against a v2 endpoint is rejected for its `iss` claim, and the error
    # says nothing about versions.
    requested_access_token_version = 2

    # The one scope this API exposes. `User` — consented by the signing-in operator, not
    # requiring an admin — because that is exactly what it is: the operator reaching
    # their own archive through their own terminal.
    oauth2_permission_scope {
      id                         = random_uuid.market_data_scope.result
      value                      = local.market_data_api_scope
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Read and manage the candle archive"
      admin_consent_description  = "Allows the app to reach market-data as the signed-in operator."
      user_consent_display_name  = "Read and manage your candle archive"
      user_consent_description   = "Allows the app to reach market-data as you."
    }
  }

  web {
    redirect_uris = ["https://${local.market_data_hostname}/.auth/login/aad/callback"]

    implicit_grant {
      id_token_issuance_enabled = true
    }
  }
}

# Generated once and kept in state. A scope id must be a stable GUID: regenerating it
# would revoke the terminal's permission and re-grant a different one on every apply.
resource "random_uuid" "market_data_scope" {}

resource "azuread_service_principal" "market_data_easy_auth" {
  client_id = azuread_application.market_data_easy_auth.client_id
}

resource "azuread_application_password" "market_data_easy_auth" {
  application_id = azuread_application.market_data_easy_auth.id
  display_name   = "easy-auth"
  end_date       = timeadd(timestamp(), "8760h")

  lifecycle {
    ignore_changes = [end_date]
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
      client_id                  = azuread_application.market_data_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Two audiences for one API: a token asked for by scope name arrives with the
      # `api://` uri as its audience, one asked for as `<client-id>/.default` arrives
      # with the client id. Accepting both means neither spelling of the request is a
      # silent 401 later.
      allowed_audiences = [
        local.market_data_api_uri,
        azuread_application.market_data_easy_auth.client_id,
      ]

      # Which clients may present a token at all. The terminal (a user's own delegated
      # token) and market-mcp (its managed identity, client-credentials) — a future
      # service reaching this API adds itself here, deliberately, rather than
      # inheriting access by having a token from the same tenant.
      allowed_applications = [
        azuread_application.terminal.client_id,
        data.azuread_service_principal.market_mcp_managed_identity.client_id,
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

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.market_data_easy_auth.value

    # Something *is* in front of this app, so the module refuses to hand out stream
    # tickets to a request Easy Auth did not identify. It does not take that on trust:
    # were `auth_settings_v2` above switched off by a careless edit, this setting is what
    # turns an open ticket factory — which is an open stream — into a refusal.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# agent: public, Easy Auth-gated, same shape as market-data — design.md, "agent
# dostanie własny adres, a nie ścieżkę pod adresem terminala": Static Web Apps cannot
# proxy its stream any more than it can market-data's WebSocket, so the terminal calls
# this app's own hostname directly, same as it does market-data's.
resource "azurerm_linux_web_app" "agent" {
  name                = local.agent_app_name
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
    # and Easy Auth would refuse it before the container ever saw it. agent MUST NOT
    # add a CORS middleware of its own for the same reason market-data's own comment
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

    # The health probe, and nothing else — the same exemption market-data's `/ping` and
    # market-mcp's `/health` carry, for the same reason: every other path answers Easy
    # Auth's 401 before the container is reached, dead or alive alike, so the deploy
    # workflow had no way to tell a serving process from a crash loop. It read the
    # control plane instead and reported green over a container exiting with code 3
    # (16 August 2026).
    #
    # This route reads nothing and returns a fixed body (`agent/app.py`), so there is
    # nothing here to protect. What makes it enough is the lifespan: it does not finish
    # until the migration does, so a process that answers this at all has a database at
    # the revision its image was built for.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = azuread_application.agent_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both audiences, deliberately — see the long comment on `agent_easy_auth` in
      # entra.tf. The terminal's existing token (asked for by market-data's scope)
      # carries market-data's audience; a future terminal asking for the agent's own
      # scope by name carries this application's instead. Either is accepted.
      allowed_audiences = [
        local.agent_api_uri,
        azuread_application.agent_easy_auth.client_id,
        local.market_data_api_uri,
        azuread_application.market_data_easy_auth.client_id,
      ]

      allowed_applications = [azuread_application.terminal.client_id]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # No credential in the URL and no AZURE_CLIENT_* triple — same as market-data:
    # config.py refuses a DATABASE_URL carrying one, and the system-assigned identity
    # is ambient. DATABASE_USER is the role the operator creates by hand in the
    # `agent` database (tasks.md's Migration Plan step 3, design.md's Risk "Baza
    # `agent` w produkcji zakładana ręcznie") — named after this app so the two never
    # drift apart.
    DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.agent.name}?sslmode=require"
    DATABASE_USER = local.agent_app_name

    # The one credential this module cannot replace with an identity: OpenAI is not in
    # Entra, so there is nothing to present a managed-identity token to. Key Vault
    # reference rather than a literal — the value never enters Terraform state or a
    # deploy log (key-vault.tf, design.md "Wobec OpenAI: klucz, i tylko klucz").
    OPENAI_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.openai_api_key})"

    # The module's own catalogue — see `var.agent_models`'s own description. Nothing in
    # this root creates these models; the variable exists so a fourth entry is one line
    # here rather than a hand-edited app setting.
    MODELS = jsonencode([
      for id, m in var.agent_models : {
        id                 = id
        model              = m.model
        display_name       = m.display_name
        cost_rank          = m.cost_rank
        input_rate_per_1m  = m.input_rate_per_1m
        output_rate_per_1m = m.output_rate_per_1m
      }
    ])
    # The cheapest entry — same choice `.env.example` documents, and design.md's own
    # Risk: "Domyślny model to najtańszy (Luna); najdroższy wybiera się świadomie."
    DEFAULT_MODEL_ID = "gpt-5.6-luna"

    # The tool server, and the scope this app's managed identity asks Entra for a token
    # to reach it with. Both or neither: `agent/config.py` refuses a remote URL with no
    # scope at startup. Removing MARKET_MCP_URL is also the rollback for the whole tool
    # loop — the module falls back to answering without tools, which is a path its own
    # tests walk.
    MARKET_MCP_URL   = "https://${local.market_mcp_hostname}"
    MARKET_MCP_SCOPE = "${local.market_mcp_api_uri}/.default"

    # The second tool server — teams, through teams-mcp. Same both-or-neither rule,
    # checked per server since `add-teams-mcp`, and the same rollback: clearing
    # TEAMS_MCP_URL takes the team tools away and leaves the archive ones exactly where
    # they are. **Set last**, after teams-mcp is deployed and answering, because this is
    # the setting that makes the tools appear — the same ordering the agent's own
    # MARKET_MCP_URL had (Migration Plan, step 5).
    TEAMS_MCP_URL   = "https://${local.teams_mcp_hostname}"
    TEAMS_MCP_SCOPE = "${local.teams_mcp_api_uri}/.default"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.agent_easy_auth.value

    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# teams: the same shape as agent, and for the same reasons — a browser reaches it
# directly under its own hostname (Static Web Apps proxies nothing here), Easy Auth gates
# it, and its own managed identity is what it presents to the database and to market-mcp.
#
# What it is not: a second agent. One request here starts a whole team of model calls,
# which is why `REQUIRE_AUTHENTICATED_PRINCIPAL` below matters more than anywhere else in
# this file — the module refuses to trust that the Easy Auth block above it was left
# switched on (specs/teams-browser-access, "Moduł nie bierze na wiarę warstwy przed sobą").
resource "azurerm_linux_web_app" "teams" {
  name                = local.teams_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `websockets_enabled`, same as agent: run progress is delivered over plain HTTP,
    # because a browser cannot put an `Authorization` header on a WebSocket handshake and
    # the credential must not travel in the address instead (specs/teams-browser-access,
    # "Poświadczenie nie wędruje w adresie").

    # Same reasoning as market-data's and agent's own CORS blocks: the preflight for a
    # cross-origin request carrying `Authorization` has no credential on it, and Easy Auth
    # would refuse it before the container saw it. teams MUST NOT add a CORS middleware of
    # its own — two layers double the header and a browser rejects that.
    cors {
      allowed_origins     = [local.terminal_origin]
      support_credentials = false
    }

    application_stack {
      # Placeholder — `deploy-teams.yml` pushes the real GHCR image after the first build.
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

    # The health probe, and nothing else — the exemption every module here carries, and
    # the one that makes a deploy check worth running: with it, `deploy-teams.yml` reaches
    # the *process*, not the control plane, which reported green over a crash-looping
    # container on 16 August 2026. The lifespan does not finish until the migration does,
    # so a process answering this at all has a database at its image's revision.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = azuread_application.teams_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both spellings of this module's own audience, plus market-data's — see the comment
      # on `teams_easy_auth` (entra.tf). The terminal holds one token today, asked for by
      # market-data's scope; the scope of this module's own stands pre-authorized for
      # whenever the terminal asks for it by name.
      allowed_audiences = [
        local.teams_api_uri,
        azuread_application.teams_easy_auth.client_id,
        local.market_data_api_uri,
        azuread_application.market_data_easy_auth.client_id,
      ]

      # Two callers now, and they arrive holding different things. The terminal presents
      # the operator's own delegated token. `teams-mcp` presents **the same operator's
      # token**, forwarded — it is on this list because Easy Auth checks the calling
      # application as well as the audience, and the forwarded token's `appid` is the
      # terminal's while the connection is teams-mcp's. Neither entry lets a service act
      # as itself here: every request to this module still carries a person
      # (add-teams-mcp specs/teams-mcp-authorship).
      allowed_applications = [
        azuread_application.terminal.client_id,
        data.azuread_service_principal.teams_mcp_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # No credential in the URL and no AZURE_CLIENT_* triple — `teams/config.py` refuses a
    # DATABASE_URL carrying one when DATABASE_USER is set, and the system-assigned identity
    # is ambient. DATABASE_USER is the role the operator creates in the `teams` database
    # (README's Deploy section), named after this app so the two never drift apart.
    DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.teams.name}?sslmode=require"
    DATABASE_USER = local.teams_app_name

    # This module's own OpenAI key, not the one agent reads — a separate secret so the
    # cost of these experiments shows up on its own line (key-vault.tf). Key Vault
    # reference rather than a literal: the value never enters Terraform state or a log.
    OPENAI_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.teams_openai_api_key})"

    # The module's own catalogue — `var.teams_models`, separate from `var.agent_models`
    # for the reason that variable's description gives. No DEFAULT_MODEL_ID to pair with
    # it: every agent in a saved revision names its own model (specs/teams-models).
    MODELS = jsonencode([
      for id, m in var.teams_models : {
        id                 = id
        model              = m.model
        display_name       = m.display_name
        cost_rank          = m.cost_rank
        input_rate_per_1m  = m.input_rate_per_1m
        output_rate_per_1m = m.output_rate_per_1m
      }
    ])

    # The tool server, and the scope this app's managed identity asks Entra for a token to
    # reach it with. Both or neither: `teams/config.py` refuses a remote URL with no scope
    # at startup. Clearing MARKET_MCP_URL is also the rollback for the whole tool loop —
    # teams without a tool server is a supported state, not a broken one, as long as no
    # team assigns tools to its agents (specs/teams-tool-access).
    MARKET_MCP_URL   = "https://${local.market_mcp_hostname}"
    MARKET_MCP_SCOPE = "${local.market_mcp_api_uri}/.default"

    # The second tool server, and the one that writes. Independently optional from the
    # pair above: clearing these two and restarting takes the *write* tools away and leaves
    # the read ones exactly where they were — which is both the rollback for phase 2 and
    # the state this module ran in for the whole of phase 1 (specs/teams-tool-access,
    # "Nieosiągalny jest tylko serwer, z którego nikt nic nie ma").
    #
    # Both or neither, again: `teams/config.py` refuses a remote URL with no scope and a
    # scope with no URL, checked separately per server so the error names which of the two
    # is half-configured.
    TRADING_MCP_URL   = "https://${local.trading_mcp_hostname}"
    TRADING_MCP_SCOPE = "${local.trading_mcp_api_uri}/.default"

    # The module's own clock — schedules and triggers fire from a task in this app's
    # `lifespan`, not from anything in Azure (design.md, "Zegar w procesie modułu, nie w
    # Azure"). A timer calling in from outside would need its own Entra registration to
    # get past Easy Auth, and would put the schedule in Terraform, which is to say back
    # in the operator's hands rather than in the catalogue where they set it.
    #
    # **Off, deliberately, and this is the one setting in this file whose value is a
    # decision rather than a fact.** `teams/config.py` defaults it to `true`, so leaving
    # it out of this map would *enable* the clock — the opposite of leaving it alone.
    #
    # The reason it is off has changed, and the new one is weaker. It *was* a broken
    # guard: `teams/validation.py` consulted a hand-kept `STATE_CHANGING_TOOLS =
    # frozenset()`, so the check refusing an unattended schedule over a revision carrying
    # write tools (specs/teams-schedules) asked an empty set and refused nothing, while
    # this app already had `TRADING_MCP_URL`. That is closed — the check now reads each
    # server's own `readOnlyHint` at save time and refuses anything it cannot confirm is
    # a read.
    #
    # What is left is that no schedule has ever fired on a running stack (task 8.2 of
    # `add-teams-schedules-and-triggers`). Turning the clock on here is the operator's
    # call after that pass, not something to slip in with a code change.
    #
    # Flipping it is one line here plus an `apply`; every schedule and trigger already
    # in the catalogue stays exactly where it is either way, and a run started by hand
    # works with the clock off (specs/teams-schedules, "Budzenie wyłączone ustawieniem").
    SCHEDULER_ENABLED = "false"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.teams_easy_auth.value

    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# Secret-read access only — Set/Delete/Purge stays with the operator (key-vault.tf).
resource "azurerm_key_vault_access_policy" "capital_gateway" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.capital_gateway.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

resource "azurerm_key_vault_access_policy" "market_data" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.market_data.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

# Secret-read only, same as the other two: this app resolves the
# `@Microsoft.KeyVault(...)` references on its `docker_registry_password` and its
# `OPENAI_API_KEY`. Writing those values stays with the operator (key-vault.tf).
resource "azurerm_key_vault_access_policy" "agent" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.agent.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

# Two references to resolve here, not one: `docker_registry_password` and this module's
# own `teams-openai-api-key`. Without this policy neither resolves, and the failure is the
# quiet kind market-mcp's comment below documents — a reference the app cannot read
# resolves to nothing rather than to an error.
resource "azurerm_key_vault_access_policy" "teams" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.teams.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

# The same read-only grant, and market-mcp went to production without it on 13 August
# 2026. It holds no application secret of its own — market-data is reached with a managed
# identity and there is no OpenAI key here — so the resource looked unnecessary and was
# never written. It is not: `docker_registry_password` is a `@Microsoft.KeyVault(...)`
# reference like everybody else's, and a reference the app cannot resolve does not fail
# loudly. It resolves to nothing, and the pull that follows reports the only thing it can
# see:
#
#   DockerApiException: Head "https://ghcr.io/v2/.../market-mcp/manifests/<sha>":
#   unauthorized
#
# — which reads as a broken registry credential, and sent the first hour of diagnosis at
# GHCR. The same token, read out of this vault by hand, pulls that exact manifest.
resource "azurerm_key_vault_access_policy" "market_mcp" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.market_mcp.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

output "capital_gateway_hostname" {
  value = azurerm_linux_web_app.capital_gateway.default_hostname
}

output "market_data_hostname" {
  value = azurerm_linux_web_app.market_data.default_hostname
}

output "agent_hostname" {
  value = azurerm_linux_web_app.agent.default_hostname
}

output "market_data_managed_identity_principal_id" {
  description = "Postgres role creation (5.7 / old 4.7) needs this object id."
  value       = azurerm_linux_web_app.market_data.identity[0].principal_id
}

output "teams_hostname" {
  value = azurerm_linux_web_app.teams.default_hostname
}

output "teams_managed_identity_principal_id" {
  description = "The operator's one-off Postgres role creation for the `teams` database needs this object id (modules/teams/README.md, Deploy)."
  value       = azurerm_linux_web_app.teams.identity[0].principal_id
}

output "agent_managed_identity_principal_id" {
  description = "The operator's manual Postgres role creation for `agent` needs this object id (design.md's Risk, \"Baza `agent` w produkcji zakładana ręcznie\")."
  value       = azurerm_linux_web_app.agent.identity[0].principal_id
}

# The agent's own client id — what market-mcp's `allowed_applications` (below) has to
# name. Same reason market-mcp needs one of these to appear in market-data's list:
# `azurerm_linux_web_app.identity` publishes `principal_id` and `tenant_id` only, and
# the identity's `client_id` lives on the service principal found by that object id.
data "azuread_service_principal" "agent_managed_identity" {
  object_id = azurerm_linux_web_app.agent.identity[0].principal_id
}

# The same lookup for teams — it is market-mcp's second caller, and `allowed_applications`
# there names client ids, which `identity[0]` does not export.
data "azuread_service_principal" "teams_managed_identity" {
  object_id = azurerm_linux_web_app.teams.identity[0].principal_id
}

# market-mcp: not public in the sense the terminal ever reaches it — its only intended
# caller is a backend service (the agent module, whose own change is still to come, not
# this one), authenticating with a managed identity rather than a signed-in user. That is why
# this registration carries no `api { oauth2_permission_scope {...} }` block the way
# market-data's does: there is no delegated consent flow here, only client-credentials.
resource "azuread_application" "market_mcp_easy_auth" {
  display_name    = "app-tradingcenter-market-mcp-easyauth"
  identifier_uris = [local.market_mcp_api_uri]

  # No `oauth2_permission_scope` (see above) but the `api` block still has to be here, and
  # leaving it out cost an interrupted `apply` on 13 August 2026. Two failures, one cause:
  #
  #   1. Entra refused the registration outright — "InvalidUniqueTenantIdentifierAsPerAppPolicy:
  #      all newly added URIs must contain a tenant verified domain, tenant ID, or app ID".
  #      The tenant policy exempts applications asking for v2 tokens, which is why
  #      `api://tradingcenter-market-data` was accepted when it was created and
  #      `api://tradingcenter-market-mcp` was not.
  #   2. Had it been accepted, the agent's token would have been rejected on arrival: this
  #      app's own Easy Auth is configured against the `/v2.0` tenant endpoint below, and a
  #      v1 token there fails on its `iss` claim with an error naming no versions at all.
  #
  # The default is 1. Every other registration here sets 2 inside a block it needed for a
  # scope; this one needs the block for nothing else, which is exactly how it went missing.
  api {
    requested_access_token_version = 2
  }

  web {
    redirect_uris = ["https://${local.market_mcp_hostname}/.auth/login/aad/callback"]
  }
}

resource "azuread_service_principal" "market_mcp_easy_auth" {
  client_id = azuread_application.market_mcp_easy_auth.client_id
}

resource "azuread_application_password" "market_mcp_easy_auth" {
  application_id = azuread_application.market_mcp_easy_auth.id
  display_name   = "easy-auth"
  end_date       = timeadd(timestamp(), "8760h")

  lifecycle {
    ignore_changes = [end_date]
  }
}

resource "azurerm_linux_web_app" "market_mcp" {
  name                = local.market_mcp_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # This is the outbound half of task 5.1 — the identity market-mcp presents *to*
  # market-data. `MARKET_DATA_SCOPE` below asks Entra for a token naming this identity;
  # `allowed_applications` on market-data's own auth_settings_v2 (above) is what has to
  # name it back for that token to be worth anything.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `cors` block and no `ip_restriction`: this app is never called from a browser
    # (contrast market-data), so there is no preflight to answer and no plan-mate
    # address list to allow — Easy Auth below is the one gate, the same choice
    # market-data itself makes.

    application_stack {
      # Placeholder — the deploy workflow pushes the real GHCR image after the first
      # build. Terraform must not fight that: see the lifecycle block below.
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }
  }

  # The inbound half of task 5.2 — who may call *this* app. Return401, matching
  # market-data: nothing here is a browser navigation to redirect.
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # The health probe, same exemption as market-data's `/ping` — the platform restarts
    # the container off this response and does not speak Easy Auth's protocol
    # (specs/market-mcp-transport, "Zdrowie modułu da się sprawdzić bez sesji MCP").
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = azuread_application.market_mcp_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      allowed_audiences = [
        local.market_mcp_api_uri,
        azuread_application.market_mcp_easy_auth.client_id,
      ]

      # The real caller, replacing the placeholder this app was created with: the
      # agent's managed identity, presenting a client-credentials token for
      # `market_mcp_api_uri`. Same lookup pattern market-mcp itself needs to appear in
      # market-data's list — `identity[0]` exports the Entra object id, and the client
      # id lives on the service principal behind it.
      #
      # Two backend callers now, and still no browser: teams reads the archive through
      # the same tools the agent does, with its own managed identity rather than a
      # borrowed one (proposal.md — "`market-mcp` zyskuje drugiego wołającego, co jest
      # wpisem w `allowed_applications`, a nie zmianą jego zachowania"). market-mcp itself
      # changes not one line for this.
      #
      # The terminal is still absent from this list on purpose: a browser talks to agent
      # or to teams, and they talk here.
      allowed_applications = [
        data.azuread_service_principal.agent_managed_identity.client_id,
        data.azuread_service_principal.teams_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    MARKET_DATA_URL   = "https://${local.market_data_hostname}"
    MARKET_DATA_SCOPE = "${local.market_data_api_uri}/.default"

    # Matches the port `Dockerfile`'s CMD binds to via `FastMCP(port=...)` reading this
    # setting through `config.py`'s `mcp_http_port` — App Service's own default
    # expectation for a Linux custom container (no WEBSITES_PORT override, same as the
    # other two apps).
    MCP_HTTP_PORT = "80"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.market_mcp_easy_auth.value

    # Same reasoning as market-data's own setting of the same name: the module does not
    # take on trust that Easy Auth above is actually configured correctly, and checks
    # for the principal header itself (specs/market-mcp-transport, "Żądanie z sieci
    # niesie tożsamość wołającego").
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# The managed identity's own client id — what market-data's `allowed_applications`
# (above) actually has to name, and what `identity[0]` on the web app resource itself
# does NOT export. `azurerm_linux_web_app.identity` publishes `principal_id` (the
# Entra object id) and `tenant_id` only; the identity's own service principal, looked
# up by that object id, is where its `client_id` lives.
data "azuread_service_principal" "market_mcp_managed_identity" {
  object_id = azurerm_linux_web_app.market_mcp.identity[0].principal_id
}

output "market_mcp_hostname" {
  value = azurerm_linux_web_app.market_mcp.default_hostname
}

# trading-mcp: the sixth app, and the second tool server. Shaped after market-mcp and not
# after market-data, for the same reason market-mcp is: its only caller is a backend
# service presenting a managed identity, so there is no delegated scope and no consent
# screen — only client credentials.
#
# Where it differs from market-mcp is what sits behind it. market-mcp reads an archive;
# this one places orders on a live broker connection, which is why every gate below is
# written as narrow as it can be: one caller in `allowed_applications`, one exempt path,
# and a credential the app resolves from Key Vault rather than one this root ever holds.
resource "azuread_application" "trading_mcp_easy_auth" {
  display_name    = "app-tradingcenter-trading-mcp-easyauth"
  identifier_uris = [local.trading_mcp_api_uri]

  # Required even with no scope inside it — see market-mcp's own comment above, and the
  # interrupted apply of 13 August 2026 that wrote it: the tenant policy on identifier
  # URIs exempts applications asking for v2 tokens, and Easy Auth below is configured
  # against the `/v2.0` endpoint. The default is 1, and both failures it causes name
  # something other than the version.
  api {
    requested_access_token_version = 2
  }

  web {
    redirect_uris = ["https://${local.trading_mcp_hostname}/.auth/login/aad/callback"]
  }
}

resource "azuread_service_principal" "trading_mcp_easy_auth" {
  client_id = azuread_application.trading_mcp_easy_auth.client_id
}

resource "azuread_application_password" "trading_mcp_easy_auth" {
  application_id = azuread_application.trading_mcp_easy_auth.id
  display_name   = "easy-auth"
  end_date       = timeadd(timestamp(), "8760h")

  lifecycle {
    ignore_changes = [end_date]
  }
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
  # grant `azurerm_key_vault_access_policy.trading_mcp` below makes.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `cors` and no `ip_restriction`, the same two omissions market-mcp makes: no
    # browser ever calls this app, so there is no preflight to answer, and the gate on who
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

    # The health probe and nothing else, exactly as market-mcp and teams have it: the
    # platform restarts the container off this response and speaks no Easy Auth
    # (specs/trading-mcp-transport, "Zdrowie modułu da się sprawdzić bez sesji MCP"). It
    # answers with the module's own state and names neither the account nor the tools.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = azuread_application.trading_mcp_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      allowed_audiences = [
        local.trading_mcp_api_uri,
        azuread_application.trading_mcp_easy_auth.client_id,
      ]

      # **One caller, and it is a list of one on purpose** (specs/trading-mcp-transport,
      # "Wołający jest wskazany imiennie" — an enumerated list, never "anyone authenticated
      # in the directory"). market-mcp's list has two entries
      # because two modules read the archive; nothing but `teams` has any business placing
      # an order, and the terminal least of all — a browser talks to `teams`, and `teams`
      # talks here. Adding an entry to this list is the single largest change anyone can
      # make to what this platform can do to the account.
      allowed_applications = [
        data.azuread_service_principal.teams_managed_identity.client_id,
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

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.trading_mcp_easy_auth.value

    # The module checks the caller's identity itself rather than trusting that the block
    # above is switched on — the same refusal to take the platform on faith that
    # market-mcp and teams both make (specs/trading-mcp-transport, "Wołający jest wskazany
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

# Two references to resolve, and neither is optional: `docker_registry_password` and
# `CAPITAL_GATEWAY_API_KEY`. Without this policy the first fails the way market-mcp's
# comment above describes — an unauthorized GHCR pull that reads like a broken registry
# credential — and the second would leave the module refusing to start with a blank key.
resource "azurerm_key_vault_access_policy" "trading_mcp" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.trading_mcp.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

output "trading_mcp_hostname" {
  value = azurerm_linux_web_app.trading_mcp.default_hostname
}

# --- teams-mcp ------------------------------------------------------------------------
#
# The seventh module, and the second one whose tools change something. Where trading-mcp
# acts on an account, this one acts on the *catalogue* — and, unlike every other app here,
# it acts **in a person's name**: the operator's own token travels inside the call, in a
# header of its own, and is what teams sees when it decides whose team this is
# (add-teams-mcp design.md, D2). The registration below is only about the other question,
# which is who may reach this module at all.
resource "azuread_application" "teams_mcp_easy_auth" {
  display_name    = "app-tradingcenter-teams-mcp-easyauth"
  identifier_uris = [local.teams_mcp_api_uri]

  # Required even with no scope inside it — see market-mcp's own comment above, and the
  # interrupted apply of 13 August 2026 that wrote it.
  api {
    requested_access_token_version = 2
  }

  web {
    redirect_uris = ["https://${local.teams_mcp_hostname}/.auth/login/aad/callback"]
  }
}

resource "azuread_service_principal" "teams_mcp_easy_auth" {
  client_id = azuread_application.teams_mcp_easy_auth.client_id
}

resource "azuread_application_password" "teams_mcp_easy_auth" {
  application_id = azuread_application.teams_mcp_easy_auth.id
  display_name   = "easy-auth"
  end_date       = timeadd(timestamp(), "8760h")

  lifecycle {
    ignore_changes = [end_date]
  }
}

resource "azurerm_linux_web_app" "teams_mcp" {
  name                = local.teams_mcp_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # For reading its own Key Vault reference (the GHCR pull token), and for nothing else
  # today. It is **not** how this module reaches `teams`: that call carries the
  # operator's token, not this identity's, which is the whole of why a team created from
  # the chat belongs to the operator and not to a service.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `cors` and no `ip_restriction`, the same omissions market-mcp and trading-mcp
    # make: no browser calls this app, and the gate on who may reach it is Easy Auth.

    application_stack {
      # Placeholder — `deploy-teams-mcp.yml` pushes the real GHCR image after the first
      # build; the lifecycle block below stops Terraform reverting it.
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

    # The health probe and nothing else — the platform restarts the container off this
    # response and speaks no Easy Auth (specs/teams-mcp-transport, "Jedno wejście
    # odpowiada bez poświadczenia"). It answers with the module's own state and names
    # nothing about the catalogue or its owners.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = azuread_application.teams_mcp_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      allowed_audiences = [
        local.teams_mcp_api_uri,
        azuread_application.teams_mcp_easy_auth.client_id,
      ]

      # One caller, enumerated (specs/teams-mcp-transport, "Wołający jest jeden i jest
      # nazwany"). The terminal is not on it and must not be: a browser talks to `agent`,
      # and `agent` talks here. Adding an entry is adding a second thing that can create
      # teams and start runs in somebody's name.
      allowed_applications = [
        data.azuread_service_principal.agent_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # teams by its own hostname, over TLS. The scope below is what this module presents
    # to *reach* it; whose request it then is arrives separately, per call.
    TEAMS_URL   = "https://${local.teams_hostname}"
    TEAMS_SCOPE = "${local.teams_api_uri}/.default"

    # App Service's default expectation for a Linux custom container, matching the
    # Dockerfile's own ENV.
    TEAMS_MCP_PORT = "80"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.teams_mcp_easy_auth.value

    # The module checks the caller's identity itself rather than trusting that the block
    # above is switched on — the same refusal to take the platform on faith the other two
    # MCP modules make.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# One reference to resolve — `docker_registry_password`. Without this policy the pull
# fails in the way market-mcp's comment describes: an unauthorized GHCR pull that reads
# like a broken registry credential.
resource "azurerm_key_vault_access_policy" "teams_mcp" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.teams_mcp.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

# teams-mcp's own client id, for the list on teams' side — the same lookup the others
# need, and for the same reason: `identity[0]` publishes an object id, not a client id.
data "azuread_service_principal" "teams_mcp_managed_identity" {
  object_id = azurerm_linux_web_app.teams_mcp.identity[0].principal_id
}

output "teams_mcp_hostname" {
  value = azurerm_linux_web_app.teams_mcp.default_hostname
}
