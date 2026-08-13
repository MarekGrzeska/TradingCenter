# One Linux App Service Plan, four apps (capital-gateway, market-data, market-mcp, agent —
# design.md, "App Service, nie Container Apps"): all of them run non-stop, so a shared B1
# plan is cheaper than as many Container Apps billed by CPU-second, and B1 fits the
# free-tier grant this subscription is on. `add-agent-chat`'s own design.md prices its app
# onto this same plan explicitly rather than a second one — see its Risk, "Czwarta
# aplikacja na B1 z jednym workerem"; `add-market-data-mcp` does the same for the fifth,
# and the real pressure is a thing to measure after both are deployed, not to predict.
resource "azurerm_service_plan" "main" {
  name                = "asp-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "B1"

  # Exactly one worker, on purpose — design.md, "Gateway ma dokładnie jedną instancję".
  # capital.com counts its 10 req/s limit per *account*, not per process; a second
  # worker means a second RateGate and a second budget spent from the same allowance,
  # and the overflow reaches a caller looking exactly like missing data, not like a
  # traffic problem. DO NOT add autoscaling or raise this number — if more capacity is
  # ever needed, it has to come from a change to the rate-limiting design first, not
  # from turning a knob here.
  worker_count = 1
}

locals {
  capital_gateway_app_name = "app-tradingcenter-gateway"
  market_data_app_name     = "app-tradingcenter-market-data"
  market_mcp_app_name      = "app-tradingcenter-market-mcp"
  agent_app_name           = "app-tradingcenter-agent"

  # Deterministic App Service hostnames — used ahead of `terraform apply` (e.g. in the
  # Easy Auth redirect URI below) instead of waiting on the computed `default_hostname`,
  # since Azure names of this form are `<name>.azurewebsites.net` with no surprises.
  capital_gateway_hostname = "${local.capital_gateway_app_name}.azurewebsites.net"
  market_data_hostname     = "${local.market_data_app_name}.azurewebsites.net"
  market_mcp_hostname      = "${local.market_mcp_app_name}.azurewebsites.net"
  agent_hostname           = "${local.agent_app_name}.azurewebsites.net"

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

  # The same shape for the agent's own registration (entra.tf) — see the comment there
  # for why its scope is granted to the terminal today but not yet the one the
  # terminal's token actually carries.
  agent_api_uri   = "api://tradingcenter-agent"
  agent_api_scope = "access_as_user"

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
# ip_restriction is the second. Its only intended caller is market-data, on the same
# plan, so the exception is the plan's own outbound addresses rather than "the
# internet." Read from market-data's resource (5.6 does the same for the database
# firewall) — never typed by hand, because they change with the plan's SKU.
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

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.agent_easy_auth.value

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
      # There is deliberately no second entry. The terminal never reaches this app; a
      # browser talks to the agent, and the agent talks here.
      allowed_applications = [data.azuread_service_principal.agent_managed_identity.client_id]
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
