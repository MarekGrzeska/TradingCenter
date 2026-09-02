# One Linux App Service Plan and every app in `local.web_app_names`, all running non-stop, so one shared plan beats as
# many Container Apps. **B3, and each step up was a measurement**: read `plan_memory` (alert at 92%) before changing it.
resource "azurerm_service_plan" "main" {
  name                = "asp-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "B3"

  # Exactly one worker, on purpose: capital.com counts its 10 req/s per *account*, so a second worker spends one
  # allowance twice and the overflow reaches a caller as missing data. Capacity comes from the rate-limiting design.
  worker_count = 1
}

locals {
  # Every App Service app, once. Everything that carried a hand-typed numeral counts this instead: on 18 August
  # 2026 the memory alert the SKU decision stands on still said "all four apps" at seven.
  web_app_names = {
    "capital-gateway"  = local.capital_gateway_app_name
    "market-data"      = local.market_data_app_name
    "workbench"        = local.workbench_app_name
    "trading-mcp"      = local.trading_mcp_app_name
    "polymarket-data"  = local.polymarket_data_app_name
    "social-data"      = local.social_data_app_name
    "strategy"         = local.strategy_app_name
    "telegram-gateway" = local.telegram_gateway_app_name
  }

  capital_gateway_app_name = "app-tradingcenter-gateway"
  market_data_app_name     = "app-tradingcenter-market-data"
  # **Still `-agent`, and that is a decision.** The name of an App Service is an identity here: the system-assigned
  # identity takes it, `DATABASE_USER` *is* that identity, and its application id sits on three lists elsewhere.
  workbench_app_name   = "app-tradingcenter-agent"
  trading_mcp_app_name = "app-tradingcenter-trading-mcp"
  # Named after the module from the first day, which is the one thing `workbench_app_name` above cannot be — a
  # rename later is a new identity, a new Postgres role and an edit in every module that names the old one.
  polymarket_data_app_name  = "app-tradingcenter-polymarket-data"
  social_data_app_name      = "app-tradingcenter-social-data"
  strategy_app_name         = "app-tradingcenter-strategy"
  telegram_gateway_app_name = "app-tradingcenter-telegram-gateway"

  # Deterministic App Service hostnames, used ahead of `terraform apply` instead of waiting on the computed
  # `default_hostname`: Azure names of this form are `<name>.azurewebsites.net` with no surprises.
  capital_gateway_hostname  = "${local.capital_gateway_app_name}.azurewebsites.net"
  market_data_hostname      = "${local.market_data_app_name}.azurewebsites.net"
  workbench_hostname        = "${local.workbench_app_name}.azurewebsites.net"
  trading_mcp_hostname      = "${local.trading_mcp_app_name}.azurewebsites.net"
  polymarket_data_hostname  = "${local.polymarket_data_app_name}.azurewebsites.net"
  social_data_hostname      = "${local.social_data_app_name}.azurewebsites.net"
  strategy_hostname         = "${local.strategy_app_name}.azurewebsites.net"
  telegram_gateway_hostname = "${local.telegram_gateway_app_name}.azurewebsites.net"

  # What `market-data` is called when it is the *resource* a token is asked for: the terminal asks Entra for
  # `<uri>/<scope>`, and Easy Auth accepts a token whose audience is this.
  market_data_api_uri   = "api://tradingcenter-market-data"
  market_data_api_scope = "access_as_user"

  capital_gateway_api_uri   = "api://tradingcenter-capital-gateway"
  capital_gateway_api_scope = "access_as_user"

  # The same, one level out, for the tool server that writes. Unlike market-data's this pairs with no delegated
  # scope: its only caller presents a client-credentials token, and there is nobody to consent on whose behalf.
  trading_mcp_api_uri = "api://tradingcenter-trading-mcp"

  # The same shape for the prediction-market archive, and with a delegated scope too: the workbench reaches it
  # with a managed identity and the terminal as a person, so its door is asked to recognise both.
  polymarket_data_api_uri   = "api://tradingcenter-polymarket-data"
  polymarket_data_api_scope = "access_as_user"

  # The post archive's own audience, with a delegated scope for polymarket-data's reason: the workbench reaches it
  # with a managed identity and both screens reach it as the operator, so its door recognises both.
  social_data_api_uri   = "api://tradingcenter-social-data"
  social_data_api_scope = "access_as_user"

  # The strategy platform's own audience, without a delegated scope for the reason trading-mcp has none: its
  # callers are backend services presenting client credentials.
  strategy_api_uri   = "api://tradingcenter-strategy"
  strategy_api_scope = "access_as_user"

  # The gateway's own audience. It has no screen — the notification is the screen — so the delegated scope below is
  # not a browser's: it is the operator's `az`, bootstrapping the first bot and the first destination by hand.
  telegram_gateway_api_uri   = "api://tradingcenter-telegram-gateway"
  telegram_gateway_api_scope = "access_as_user"

  # Microsoft's own well-known registration for the Azure CLI, and the only client the operator has for a
  # module with no screen. Bootstrapping the gateway is `curl` with a token from `az`, so this is what the
  # scope below is pre-authorized for.
  azure_cli_client_id = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

  # There used to be a third of this shape, for the tool server the agent built teams through. Those tools are a
  # layer in the workbench now — no address, no audience, nothing for a caller to present.

  # The workbench's own registration (entra.tf), whose scope is granted to the terminal but is not yet the one
  # its token carries. The `-agent` spelling is the resource name's, for the reason `workbench_app_name` gives.
  workbench_api_uri   = "api://tradingcenter-agent"
  workbench_api_scope = "access_as_user"

  # One string used in three places that MUST agree: the SPA registration's redirect URI, the origin market-data
  # allows a browser to call from, and what the deploy builds against. Read rather than typed — SWA invents it.
  terminal_origin = "https://${azurerm_static_web_app.terminal.default_host_name}"

  # The same three-way agreement for the phone screen, and it reaches exactly one back end: only
  # polymarket-data's CORS names it, because only polymarket-data is asked for anything.
  pocket_origin = "https://${azurerm_static_web_app.pocket.default_host_name}"

  kv_secret_uri = {
    for k, name in local.key_vault_secret_names :
    k => "${azurerm_key_vault.main.vault_uri}secrets/${name}/"
  }

  # GHCR is private because the repository is, so without these the container never starts. They belong in
  # `application_stack`: the provider writes the DOCKER_REGISTRY_SERVER_* settings itself and refuses them elsewhere.
  ghcr_registry_url      = "https://ghcr.io"
  ghcr_registry_username = "MarekGrzeska"
  ghcr_registry_password = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.ghcr_pull_token})"
}

# capital-gateway: reachable, guarded by the module's own key check — which the browser the Accounts screen needs left
# as **the only thing between this app and the internet**. Acceptable because it refuses to start off the demo host.
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

    # **The preflight is answered by the platform, never by the app**: an `OPTIONS` carries no token, Easy Auth answered
    # it 401, and that reaches `fetch` as a thrown error. `capital_gateway` MUST NOT add CORS — two layers double it.
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

    # Who may reach this module past the door, read by the module itself: Easy Auth authorizes an application and not a
    # route, and this app serves the account next to the routes that place orders. Since `the-key-opens-only-the-stream`
    # the application decides on every HTTP route and the shared key opens none of them — the two service callers are
    # named here as well as on `allowed_applications` below, and neither list substitutes for the other.
    MODULE_CALLER_APPLICATION_IDS = jsonencode([
      data.azuread_service_principal.market_data_managed_identity.client_id,
      data.azuread_service_principal.trading_mcp_managed_identity.client_id,
    ])
    BROWSER_CALLER_APPLICATION_IDS = jsonencode([azuread_application.terminal.client_id])

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.capital_gateway_easy_auth.password

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    # **This app authenticates now, and the sentence that stood here was false**: under `AllowAnonymous` nothing is
    # validated and no principal injected. Possible only in this order — both service callers are listed below first.
    unauthenticated_action = "Return401"

    # **The stream must not pass through Easy Auth at all**: it intercepts the upgrade and never completes it, which
    # killed every candle feed on 20 August 2026. The key is checked inside the handler — the one door held by it alone.
    excluded_paths = ["/ws/stream", "/"]

    active_directory_v2 {
      client_id                  = module.capital_gateway_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Two spellings of **this** API and nothing else. It carried market-data's until 22 August 2026, and while that
      # stood a token leaked from anywhere that could obtain one also opened the broker connection.
      allowed_audiences = [
        local.capital_gateway_api_uri,
        module.capital_gateway_easy_auth.client_id,
      ]

      # The browser and the two service callers, listed *before* this app requires authentication — that ordering is the
      # point. A managed identity publishes `principal_id`; the client id lives on the service principal it names.
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
    # The deploy workflow sets the real image tag with `az webapp config container set`; Terraform reverting it to
    # the placeholder on every apply would fight the thing that is supposed to own this value.
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# The API half of the pair whose client half is `azuread_application.terminal`. Its own registration rather than
# reusing market-data's: a token is issued *for* an API, and the two are two doors with two lists of who may knock.
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

# market-data: public, Easy Auth-gated, and the **API** half of a pair whose client half is `terminal` — which is client
# and which resource is the whole content. The scope id is kept in state: regenerating revokes and re-grants every apply.
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

    # CORS belongs **here and not in the application**: a preflight carries no credential, and Easy Auth would answer it
    # 401 before the container saw it. So `market_data` MUST NOT add a middleware — two layers double the header.
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

  # Return401, not RedirectToLoginPage: the terminal reaches this app through `fetch()`, and a redirect handed to
  # `fetch` resolves to an HTML login page masquerading as a JSON body. It holds and renews an Entra token itself.
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # The candle stream and nothing else, since a browser cannot put a header on a handshake. **Exempt from Easy Auth is
    # not exempt from authentication**: the module guards it with a one-time ticket, and learned to before this existed.
    excluded_paths = ["/ws/candles", "/ping"]

    active_directory_v2 {
      client_id                  = module.market_data_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Two audiences for one API: a token asked for by scope name arrives with the `api://` uri, one asked for as
      # `<client-id>/.default` with the client id. Accepting both means neither spelling is a silent 401 later.
      allowed_audiences = [
        local.market_data_api_uri,
        module.market_data_easy_auth.client_id,
      ]

      # Which clients may present a token at all — one backend caller, since the conversation and the teams runner are one
      # process. What keeps it to `/mcp` is TOOL_CALLER_APPLICATION_IDS below; neither substitutes for the other.
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
    # What this module presents to the gateway besides the key. Set here rather than left to the module, because the
    # absence of this setting is what selects local work. The stream is outside the gateway's authenticator anyway.
    GATEWAY_SCOPE   = "${local.capital_gateway_api_uri}/.default"
    GATEWAY_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.gateway_api_key})"

    # No credential in the URL and no AZURE_* triple: config.py refuses one, and the identity is ambient here unlike a
    # developer machine's. `DATABASE_USER` is the Postgres role for it, named after this app so the two cannot drift.
    DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.prod.name}?sslmode=require"
    DATABASE_USER = local.market_data_app_name

    # This module's share of the server's 35 connections — the largest share: the only module writing a row per closed candle per pair while serving two surfaces.
    # The whole budget is one number, checked by `scripts/tests/test_pool_budget.py`.
    DATABASE_POOL_SIZE = "8"

    # The module migrates inside the lifespan, so the warm-up window must outlast the longest migration. 1800 is the
    # platform's ceiling, so `migration_lock_wait_seconds` sits at 1500: the module has to give up first and say why.
    WEBSITES_CONTAINER_START_TIME_LIMIT = "1800"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.market_data_easy_auth.password

    # The module refuses to hand out stream tickets to a request Easy Auth did not identify, rather than trusting the
    # block above: switch it off and this turns an open ticket factory — which is an open stream — into a refusal.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    # Which caller reaches which surface past the door: the workbench `/mcp`, the terminal the REST contract. Client ids
    # only, from the `azp` claim — `X-MS-CLIENT-PRINCIPAL-ID` names the signed-in person, which refused every request.
    TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id

    # Two REST callers since the strategy platform arrived, the second a program. It reads the REST contract and
    # deliberately not `/mcp`, which is narrowed for a model and too tight for a loop reading three hundred bars.
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

# workbench: public, Easy Auth-gated, same shape as market-data — SWA cannot proxy its stream. **Two surfaces in one
# app** with one identity, which is what made keeping the resource name worth more than fixing it.
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
    # No `websockets_enabled`: the turn streams over plain HTTP (`fetch` + `ReadableStream`), never an upgrade
    # (design.md, "Odpowiedź strumieniem: fetch + ReadableStream, nie EventSource").

    # Same reasoning as market-data's own CORS block: the preflight carries no credential and Easy Auth would refuse
    # it before the container saw it. The workbench MUST NOT add one of its own — two layers double the header.
    cors {
      allowed_origins     = [local.terminal_origin, local.pocket_origin]
      support_credentials = false
    }

    application_stack {
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"

      docker_registry_url      = local.ghcr_registry_url
      docker_registry_username = local.ghcr_registry_username
      docker_registry_password = local.ghcr_registry_password
    }
  }

  # Return401, not RedirectToLoginPage, for market-data's reason: the terminal reaches this app through `fetch()`,
  # and a redirect resolves to an HTML login page masquerading as a JSON body.
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    # The health probe and nothing else: every other path answers 401 before the container is reached, dead or alive
    # alike. The lifespan does not finish until both migrations do, so answering here proves both databases.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = module.workbench_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both audiences, deliberately — see the comment on `module.workbench_easy_auth` in entra.tf. A terminal asking
      # by market-data's scope carries that audience; one asking for this app's own carries this. Either is accepted.
      allowed_audiences = [
        local.workbench_api_uri,
        module.workbench_easy_auth.client_id,
        local.market_data_api_uri,
        module.market_data_easy_auth.client_id,
      ]

      # One caller: the terminal, holding the operator's own delegated token. The second — teams-mcp forwarding that
      # token between processes — went away with the process, and the identity now travels inside this one.
      # Two browsers, and the phone screen is here for one reason: the conversation is how it reaches
      # polymarket-data's tools. It never speaks MCP itself — the workbench holds the model key and the
      # tool servers' addresses, and those servers admit this app's managed identity, not a browser.
      allowed_applications = [
        azuread_application.terminal.client_id,
        azuread_application.pocket.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # **Two databases, one identity.** No credential in either URL and no AZURE_CLIENT_* triple. One DATABASE_USER for
    # both, so that role has to exist in *both* databases — the single operator step this merge carries.
    AGENT_DATABASE_URL = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.agent.name}?sslmode=require"
    TEAMS_DATABASE_URL = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.teams.name}?sslmode=require"
    DATABASE_USER      = local.workbench_app_name

    # This module's share of the server's 35 connections — four for **each** of this process's two pools, so eight of the server's 35 — a turn holds one connection while the model answers.
    # The whole budget is one number, checked by `scripts/tests/test_pool_budget.py`.
    DATABASE_POOL_SIZE = "4"

    # The one credential no identity can replace: OpenAI is not in Entra. Key Vault references rather than literals, so
    # neither value enters state or a log — and **two keys still**, so the teams experiments bill on their own line.
    AGENT_OPENAI_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.openai_api_key})"
    TEAMS_OPENAI_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.teams_openai_api_key})"

    # Two catalogues from two variables. Nothing in this root creates these models; the variables exist so a fourth
    # entry is one line here. No TEAMS_DEFAULT_MODEL_ID, because every agent in a saved revision names its own model.
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

    # The read tool server, which is **market-data itself** since `market-mcp-into-market-data`; the setting keeps its
    # name because the address moved, not the relationship. Removing it is the rollback for the whole tool loop.
    MARKET_MCP_URL   = "https://${local.market_data_hostname}"
    MARKET_MCP_SCOPE = "${local.market_data_api_uri}/.default"

    # There is no TEAMS_MCP_URL any more. The tools that build and run teams are a layer in
    # this process — no address, no scope, no second hop, and nothing to set last.

    # The second tool server — the demo account — under the same both-or-neither rule, and the one with the larger
    # consequence, since four of its tools write. It works only alongside trading-mcp's own `allowed_applications`.
    TRADING_MCP_URL   = "https://${local.trading_mcp_hostname}"
    TRADING_MCP_SCOPE = "${local.trading_mcp_api_uri}/.default"

    # The third tool server, same rule and same rollback. **This pair MUST reach the app before the image that uses
    # it**: an apply landing after the deploy is an outage in between, and neither half substitutes for the other.
    POLYMARKET_MCP_URL   = "https://${local.polymarket_data_hostname}"
    POLYMARKET_MCP_SCOPE = "${local.polymarket_data_api_uri}/.default"

    # The fourth, same rule and same rollback — clear this pair and restart, and the conversation runs without
    # post tools, which is a state its own tests walk.
    SOCIAL_MCP_URL   = "https://${local.social_data_hostname}"
    SOCIAL_MCP_SCOPE = "${local.social_data_api_uri}/.default"

    # The fifth, and the one whose tool acts outside this system: it sends a Telegram message. Same both-or-neither
    # rule and the same rollback — clear the pair and restart, and the conversation notifies nobody.
    TELEGRAM_MCP_URL   = "https://${local.telegram_gateway_hostname}"
    TELEGRAM_MCP_SCOPE = "${local.telegram_gateway_api_uri}/.default"

    # The sixth, and the one the teams' clock reads: `pending_setups` is the number a trigger wakes a team on. The
    # other half of this pairing — the workbench in strategy's `allowed_applications` and TOOL_CALLER_APPLICATION_IDS —
    # has stood since `the-screen-is-mostly-refusals`; this pair is what was missing. Same rollback: clear and restart.
    STRATEGY_MCP_URL   = "https://${local.strategy_hostname}"
    STRATEGY_MCP_SCOPE = "${local.strategy_api_uri}/.default"

    # The teams surface's own clock, in this app's `lifespan` rather than a timer calling in, which would need its own
    # registration. **The one setting here whose value is a decision**: config.py defaults it on, this states it.
    SCHEDULER_ENABLED = "true"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.workbench_easy_auth.password

    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

# Secret-read access only — Set/Delete/Purge stays with the operator (key-vault.tf). Keyed the same as
# `local.web_app_names`, so a new module appears in the grant and in every count below, or in neither.
locals {
  web_app_principal_ids = {
    "capital-gateway"  = azurerm_linux_web_app.capital_gateway.identity[0].principal_id
    "market-data"      = azurerm_linux_web_app.market_data.identity[0].principal_id
    "workbench"        = azurerm_linux_web_app.workbench.identity[0].principal_id
    "trading-mcp"      = azurerm_linux_web_app.trading_mcp.identity[0].principal_id
    "polymarket-data"  = azurerm_linux_web_app.polymarket_data.identity[0].principal_id
    "social-data"      = azurerm_linux_web_app.social_data.identity[0].principal_id
    "strategy"         = azurerm_linux_web_app.strategy.identity[0].principal_id
    "telegram-gateway" = azurerm_linux_web_app.telegram_gateway.identity[0].principal_id
  }
}

# One grant, every app by `for_each` rather than a copy each: market-mcp reached production without one, and an
# unresolved Key Vault reference does not fail loudly — the pull reports `unauthorized`, which reads as GHCR's fault.
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

# The workbench's own client id, which market-data's `allowed_applications` and TOOL_CALLER_APPLICATION_IDS both name:
# an App Service identity publishes `principal_id` only, and the `client_id` lives on the service principal it names.
data "azuread_service_principal" "workbench_managed_identity" {
  object_id = azurerm_linux_web_app.workbench.identity[0].principal_id
}

# The two service callers of capital-gateway, for its own `allowed_applications`, looked up for the reason the
# workbench's is: an App Service identity publishes an object id, and the door needs a client id.
data "azuread_service_principal" "market_data_managed_identity" {
  object_id = azurerm_linux_web_app.market_data.identity[0].principal_id
}

data "azuread_service_principal" "trading_mcp_managed_identity" {
  object_id = azurerm_linux_web_app.trading_mcp.identity[0].principal_id
}

# trading-mcp: a tool server whose only caller is a backend service, so no delegated scope and no consent screen. What
# sits behind it places orders rather than reading an archive, so every gate below is as narrow as it can be written.
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

  # Not for reaching capital-gateway, which is a static key in a header: this identity exists so the app can read its
  # own Key Vault references — the GHCR pull token and that very key.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true
    # No `cors`: no browser ever calls this app, so there is no preflight to answer. No `ip_restriction` either, and
    # neither has any other app here — worth saying because three files claimed otherwise until 20 August 2026.

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

    # The health probe and nothing else, as market-data and the workbench have it: the platform restarts the container
    # off this response and speaks no Easy Auth. It answers with the module's own state, naming no account and no tool.
    excluded_paths = ["/health"]

    active_directory_v2 {
      client_id                  = module.trading_mcp_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      allowed_audiences = [
        local.trading_mcp_api_uri,
        module.trading_mcp_easy_auth.client_id,
      ]

      # **Two callers, and a list of two on purpose** — enumerated, never "anyone authenticated in the directory". The
      # terminal is not one: a browser talks to the workbench. Adding a name here is a decision, not a side effect.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # The gateway by its own hostname, over TLS. Its `X-Gateway-Key` check admits the credential below on every
    # caller, loopback included, so there is no address here that would make the key optional.
    CAPITAL_GATEWAY_URL = "https://${local.capital_gateway_hostname}"

    # The same secret capital-gateway reads and market-data presents — one value, three readers, as a Key Vault
    # reference so it never enters state or a log. Unresolved, the module refuses to start, which is the intended failure.
    CAPITAL_GATEWAY_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.gateway_api_key})"
    # The same second credential market-data presents, for the same reason: the gateway's door validates a token
    # rather than trusting a key two modules share. Unset — local work — leaves the key as the whole credential.
    CAPITAL_GATEWAY_SCOPE = "${local.capital_gateway_api_uri}/.default"

    # App Service's default expectation for a Linux custom container, matching the Dockerfile's own ENV. Said in both
    # places so a reader of either sees the number the other uses.
    TRADING_MCP_PORT = "80"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.trading_mcp_easy_auth.password

    # The module checks the caller's identity itself rather than trusting that the block above is switched on — the
    # same refusal to take the platform on faith the others make, and here it guards a module that writes to an account.
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

# polymarket-data: shaped like trading-mcp, one backend caller with a managed identity. Behind it is a watch list, never
# money — the narrow gate is that **the tool caller must not reach the route that deletes collected history**.
module "polymarket_data_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-polymarket-data-easyauth"
  identifier_uri = local.polymarket_data_api_uri
  redirect_uri   = "https://${local.polymarket_data_hostname}/.auth/login/aad/callback"

  # A delegated scope since `polymarket-screen-opens-the-archive`. It had none while the workbench was the only
  # caller: a managed identity presenting client credentials has no consent screen and nothing to consent to.
  scope = {
    value                      = local.polymarket_data_api_scope
    admin_consent_display_name = "Read and manage the prediction-market archive"
    admin_consent_description  = "Allows the app to reach polymarket-data as the signed-in operator, including removing collected history."
    user_consent_display_name  = "Read and manage your prediction-market archive"
    user_consent_description   = "Allows the app to read what you track on Polymarket, change that list, and remove collected history."
  }
}

resource "azurerm_linux_web_app" "polymarket_data" {
  name                = local.polymarket_data_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # Two things need it, and Polymarket is neither — that upstream is public. It is the database, through an Entra
  # token fetched at connection time, and the GHCR pull token in Key Vault.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true

    # **The preflight is answered by the platform, never by the app** — the fourth time this trap has been walked into,
    # measured again on 22 August 2026. `polymarket_data` MUST NOT add a middleware: two layers double the header.
    cors {
      allowed_origins     = [local.terminal_origin, local.pocket_origin]
      support_credentials = false
    }

    # No `ip_restriction`, like the other apps. Nothing in this root has ever set one;
    # what differs between these apps is only which credential their door asks for.

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

    # The health route and nothing else — the platform restarts the container off this response and speaks no Easy
    # Auth, and `deploy_probe.py` reads the same path. It answers with the module's own state, naming no tracked event.
    excluded_paths = ["/"]

    active_directory_v2 {
      client_id                  = module.polymarket_data_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both spellings of the same request, for market-data's reason: by scope name the audience is the `api://` uri,
      # as `<client-id>/.default` it is the client id.
      allowed_audiences = [
        local.polymarket_data_api_uri,
        module.polymarket_data_easy_auth.client_id,
      ]

      # Three callers, named, each reaching exactly one of this module's two surfaces — the workbench the nine tools
      # at `/mcp`, the terminal and pocket the REST contract. Being on this list is not what separates them; the
      # settings below are. Easy Auth authorizes an application, not a route.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
        azuread_application.terminal.client_id,
        azuread_application.pocket.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = {
    # No credential in the URL and no AZURE_* triple — config.py refuses one when DATABASE_USER is set, and the
    # identity is ambient. That user is the role `scripts/grant-schema-ownership.sql` creates, named after this app.
    DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.polymarket.name}?sslmode=require"
    DATABASE_USER = local.polymarket_data_app_name

    # This module's share of the server's 35 connections — the sampling loop is one query per pass, and both surfaces read.
    # The whole budget is one number, checked by `scripts/tests/test_pool_budget.py`.
    DATABASE_POOL_SIZE = "3"

    # Polymarket's two public surfaces, set here rather than left to the module's defaults for the reason every other
    # upstream address is: a default that changed under a dependency bump would move it with nothing here to say so.
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    CLOB_BASE_URL  = "https://clob.polymarket.com"

    # Measured, not decorative: the provider's edge refuses `Python-urllib/*` with 403 "error code: 1010" on both
    # surfaces (22 August 2026), and a library default changing on a bump would read as an access refusal.
    PROVIDER_USER_AGENT = "tradingcenter-polymarket-data/0.1 (+https://github.com/MarekGrzeska)"

    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.polymarket_data_easy_auth.password

    # The module checks the caller's identity itself rather than trusting the block above is switched on — the same
    # refusal to take the platform on faith market-data, trading-mcp and the workbench all make.
    REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

    # Which caller reaches which surface, by the `azp` claim and never by `X-MS-CLIENT-PRINCIPAL-ID`. What separates the
    # two is not reading from writing but that **removing collected history is a REST route**.
    TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id
    # Comma-separated, which `config.py` splits: two browsers reach the REST contract now and the module's own record
    # has to name both, or the second is refused by the module after the platform has already let it through.
    REST_CALLER_APPLICATION_IDS = join(",", [
      azuread_application.terminal.client_id,
      azuread_application.pocket.client_id,
    ])

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

output "polymarket_data_hostname" {
  value = azurerm_linux_web_app.polymarket_data.default_hostname
}
# social-data: the same door as polymarket-data, and one difference behind it — **nothing on either surface writes**.
# What the record separates is which caller reaches which surface, not what either may change.
module "social_data_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-social-data-easyauth"
  identifier_uri = local.social_data_api_uri
  redirect_uri   = "https://${local.social_data_hostname}/.auth/login/aad/callback"

  scope = {
    value                      = local.social_data_api_scope
    admin_consent_display_name = "Read the post archive"
    admin_consent_description  = "Allows the app to read collected posts and what a model made of them."
    user_consent_display_name  = "Read your post archive"
    user_consent_description   = "Allows the app to read the posts this system has collected for you."
  }
}

resource "azurerm_linux_web_app" "social_data" {
  name                = local.social_data_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # The database through an Entra token fetched at connection time, and the GHCR pull token in Key Vault. The
  # feed needs no credential, and the model key is a setting rather than an identity.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true

    # **The preflight is answered by the platform, never by the app** — the fifth time this trap has been walked
    # into. This module MUST NOT add a middleware of its own: two layers double the header.
    cors {
      allowed_origins     = [local.terminal_origin, local.pocket_origin]
      support_credentials = false
    }

    application_stack {
      # Placeholder — `deploy-social-data.yml` pushes the real GHCR image; the
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

    # The health route and nothing else — the platform restarts the container off this response and speaks no
    # Easy Auth, and `deploy_probe.py` reads the same path. It names the module and nothing it has collected.
    excluded_paths = ["/"]

    active_directory_v2 {
      client_id                  = module.social_data_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      allowed_audiences = [
        local.social_data_api_uri,
        module.social_data_easy_auth.client_id,
      ]

      # Three callers, each reaching exactly one surface — the workbench the four tools at `/mcp`, the terminal
      # and pocket the REST contract. Being on this list is not what separates them; the settings below are.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
        azuread_application.terminal.client_id,
        azuread_application.pocket.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  # Merged, because the gateway is the setting whose *absence* is a working configuration: without it this
  # module collects and reads exactly as before and tells nobody, which `/state` reports.
  app_settings = merge(
    {
      # No credential in the URL and no AZURE_* triple — config.py refuses one when DATABASE_USER is set, and the
      # identity is ambient. That user is the role `scripts/grant-schema-ownership.sql` creates, named after this app.
      DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.social.name}?sslmode=require"
      DATABASE_USER = local.social_data_app_name

      # This module's share of the server's 35 connections — collecting is one pass, and nothing here writes on a request.
      # The whole budget is one number, checked by `scripts/tests/test_pool_budget.py`.
      DATABASE_POOL_SIZE = "3"

      # The feed, set here rather than left to the module's default for the reason every other upstream address is:
      # it is somebody's side project, and the day it moves is a deployment.
      TRUTH_SOCIAL_FEED_URL = "https://www.trumpstruth.org/feed"
      PROVIDER_USER_AGENT   = "tradingcenter-social-data/0.1 (+https://github.com/MarekGrzeska)"

      # The conversation's key, read from Key Vault like the workbench reads its two — a reference, never a value in
      # this file. **Shared rather than a third secret**, so the readings arrive on the same line of the bill as the
      # chat; splitting them is one more `key_vault_secret_names` entry and one edit here, the day that matters.
      OPENAI_API_KEY = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.openai_api_key})"

      # Left to config.py's defaults on purpose: which model reads a post is a decision to change by restarting,
      # not one to redeploy for. Clearing OPENAI_API_KEY is the rollback — the module then collects and reads
      # nothing, a state its own tests walk.

      MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.social_data_easy_auth.password

      # The module checks the caller's identity itself rather than trusting the block above is switched on.
      REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

      # Which caller reaches which surface, by the `azp` claim and never by `X-MS-CLIENT-PRINCIPAL-ID`.
      TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id
      REST_CALLER_APPLICATION_IDS = join(",", [
        azuread_application.terminal.client_id,
        azuread_application.pocket.client_id,
      ])

      APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
    },
    # All three or none — config.py refuses every partial form, because each of them is silence that reads
    # like a working configuration. The threshold is left to config.py's own default.
    var.telegram_alert_destination == "" ? {} : {
      TELEGRAM_GATEWAY_URL   = "https://${local.telegram_gateway_hostname}"
      TELEGRAM_GATEWAY_SCOPE = "${local.telegram_gateway_api_uri}/.default"
      ALERT_DESTINATION      = var.telegram_alert_destination
    }
  )

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

output "social_data_hostname" {
  value = azurerm_linux_web_app.social_data.default_hostname
}

output "terminal_entra_scope_social" {
  description = "The scope the terminal and pocket ask for when they want a token for social-data. Carried as a literal by both deploy workflows, like every other scope here."
  value       = "${local.social_data_api_uri}/${local.social_data_api_scope}"
}

output "social_data_managed_identity_principal_id" {
  description = "The operator's one-off Postgres role creation in the `social` database needs this object id (scripts/grant-schema-ownership.sql)."
  value       = azurerm_linux_web_app.social_data.identity[0].principal_id
}


output "terminal_entra_scope_polymarket" {
  description = "The scope the terminal asks for when it wants a token for polymarket-data. `deploy-terminal.yml` carries this as a literal beside the four hostnames, like the workbench's and the gateway's — a repository variable per scope would be four chances to leave one unset, and the failure surfaces at sign-in as a message about an unknown resource."
  value       = "${local.polymarket_data_api_uri}/${local.polymarket_data_api_scope}"
}

output "polymarket_data_managed_identity_principal_id" {
  description = "The operator's one-off Postgres role creation in the `polymarket` database needs this object id (scripts/grant-schema-ownership.sql)."
  value       = azurerm_linux_web_app.polymarket_data.identity[0].principal_id
}

# There is no teams-mcp block below this line any more: those tools became a layer inside the workbench, and what went
# with it is a whole App Service, its Easy Auth registration and secret, an identity, a policy — and a network hop.

# --- the strategy platform ------------------------------------------------------------
#
# The fifth app, and the second whose callers are all programs. **A fifth tenant on the plan is the thing to watch**:
# read `plan_memory` over a week before concluding anything, since a module here weighs 150-310 MB.
data "azuread_service_principal" "strategy_managed_identity" {
  object_id = azurerm_linux_web_app.strategy.identity[0].principal_id
}

module "strategy_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-strategy-easyauth"
  identifier_uri = local.strategy_api_uri
  redirect_uri   = "https://${local.strategy_hostname}/.auth/login/aad/callback"

  # A delegated scope since `the-screen-is-mostly-refusals`, whose absence was the whole reason this module answered
  # 401 to a browser: a caller list says who may enter, a scope is what lets somebody ask for the key.
  scope = {
    value                      = local.strategy_api_scope
    admin_consent_display_name = "Read the strategy platform and manage what it watches"
    admin_consent_description  = "Allows the app to reach the strategy platform as the signed-in operator: read the catalogue and every decision, and start or stop watching a pair."
    user_consent_display_name  = "Read your strategies and manage what they watch"
    user_consent_description   = "Allows the app to read what your strategies decided and why, and to start or stop watching an instrument. It cannot place an order."
  }
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

    # CORS belongs here rather than in the application, for the reason the three blocks above give: a preflight
    # carries no credential of any kind, so Easy Auth would refuse it before the app ever saw it.
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

    # One path, and it has to be the one `strategy/caller_access.py` also opens: two gates stand in front of every
    # request, and exempting a path from one is not exempting it — which is how the deploy of d2e2290 failed.
    excluded_paths = ["/ping"]

    active_directory_v2 {
      client_id                  = module.strategy_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both spellings of this app's audience, for the reason market-data's taught on 21 August 2026: a list holding
      # only the scope-name form looks like a working configuration until something asks the other way.
      allowed_audiences = [
        local.strategy_api_uri,
        module.strategy_easy_auth.client_id,
      ]

      # Two callers, each here for one of this module's two surfaces — the workbench `/mcp`, the terminal the REST
      # contract. Which reaches which is not something this list can say; the two settings below are.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
        azuread_application.terminal.client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  # Merged, because the gateway is the setting whose *absence* is a working configuration: without it this
  # platform evaluates and records exactly as before and says nothing.
  app_settings = merge(
    {
      # The archive by its own hostname, and its REST contract rather than `/mcp`: that surface is narrowed for a model
      # and too tight for a loop reading three hundred bars of three facts at once.
      MARKET_DATA_URL = "https://${local.market_data_hostname}"
      # What this module presents to the archive: a token of its own identity for the archive's audience. Set here
      # because the absence of this setting is what selects local work, where there is no directory to ask.
      MARKET_DATA_SCOPE = "${local.market_data_api_uri}/.default"

      # No credential in the URL and no AZURE_* triple: config.py refuses one, and the system-assigned identity is
      # ambient. `DATABASE_USER` is the role the operator creates once for that identity, named after this app.
      DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.strategy.name}?sslmode=require"
      DATABASE_USER = local.strategy_app_name

      # This module's share of the server's 35 connections — the runner evaluates one watch at a time, and a backtest reads market-data over HTTP.
      # The whole budget is one number, checked by `scripts/tests/test_pool_budget.py`.
      DATABASE_POOL_SIZE = "3"

      MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.strategy_easy_auth.password

      # The module does not take the block above on trust: were `auth_settings_v2` switched off by a careless edit,
      # this setting is what keeps both surfaces from answering an unidentified caller.
      REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

      # Which caller reaches which surface once Easy Auth has let it through, by the `azp`/`appid` claim naming the
      # application — never the principal-id header, which for a delegated token names the signed-in person.
      TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id
      # Comma-separated, which `config.py` splits: two browsers reach the REST contract now and the module's own record
      # has to name both, or the second is refused by the module after the platform has already let it through.
      REST_CALLER_APPLICATION_IDS = join(",", [
        azuread_application.terminal.client_id,
        azuread_application.pocket.client_id,
      ])

      APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
    },
    # All three or none — config.py refuses every partial form. Only a decision naming a trade is announced,
    # and only where it changes, so this channel speaks on the scale of setups rather than of bars.
    var.telegram_alert_destination == "" ? {} : {
      TELEGRAM_GATEWAY_URL   = "https://${local.telegram_gateway_hostname}"
      TELEGRAM_GATEWAY_SCOPE = "${local.telegram_gateway_api_uri}/.default"
      ALERT_DESTINATION      = var.telegram_alert_destination
    }
  )

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

# --- the door to Telegram --------------------------------------------------------------
#
# The eighth app, and the third whose callers are all programs — but the first with no browser among them at all: this
# module has no screen, because the notification is the screen. **The eighth tenant on one B3 plan** is the thing to
# watch; `plan_memory` alerts at 92%, and a module here weighs 150-310 MB.
data "azuread_service_principal" "social_data_managed_identity" {
  object_id = azurerm_linux_web_app.social_data.identity[0].principal_id
}

module "telegram_gateway_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-telegram-gateway-easyauth"
  identifier_uri = local.telegram_gateway_api_uri
  redirect_uri   = "https://${local.telegram_gateway_hostname}/.auth/login/aad/callback"

  # Three callers present client credentials and need no scope. This one exists for a fourth that is not a module:
  # the operator, bootstrapping the first bot and the first destination. Those two routes are REST-only and reachable
  # by nobody else — a gateway whose destinations only the gateway can create is a gateway that never sends.
  scope = {
    value                      = local.telegram_gateway_api_scope
    admin_consent_display_name = "Manage the door to Telegram"
    admin_consent_description  = "Allows the app to reach telegram-gateway as the signed-in operator, including adding bots and binding destinations."
    user_consent_display_name  = "Manage your door to Telegram"
    user_consent_description   = "Allows the app to add bots, bind who receives notifications, and send one."
  }
}

resource "azurerm_linux_web_app" "telegram_gateway" {
  name                = local.telegram_gateway_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # The database through an Entra token fetched at connection time, and the Key Vault references below. Telegram
  # itself takes neither: a bot token is a row in this module's own database, and the account session is a secret.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true

    # No `cors` block, unlike the four modules above: no browser calls this app. Adding one later would mean a
    # screen exists, and there is none.

    application_stack {
      # Placeholder — `deploy-telegram-gateway.yml` pushes the real GHCR image; the
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

    # One path, and it is one `telegram_gateway/caller_access.py` also opens — two gates stand in front of every
    # request, and exempting a path from one is not exempting it. It names the module and nothing it holds.
    excluded_paths = ["/"]

    active_directory_v2 {
      client_id                  = module.telegram_gateway_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"

      # Both spellings of this app's audience, for the reason market-data's taught on 21 August 2026: a list holding
      # only the scope-name form looks like a working configuration until something asks the other way.
      allowed_audiences = [
        local.telegram_gateway_api_uri,
        module.telegram_gateway_easy_auth.client_id,
      ]

      # Three callers, and the split between them is not reading from writing — all three send. It is that creating
      # a bot and binding a destination are REST alone, which the two settings below are what actually say.
      allowed_applications = [
        data.azuread_service_principal.workbench_managed_identity.client_id,
        data.azuread_service_principal.social_data_managed_identity.client_id,
        data.azuread_service_principal.strategy_managed_identity.client_id,
        # The operator, through `az`. Not a module, and the only one of the four that is a person — the two routes
        # it exists for are the ones a managed identity must never reach: adopting a bot and binding a destination.
        local.azure_cli_client_id,
      ]
    }

    login {
      token_store_enabled = true
    }
  }

  # Merged rather than written once, because the account session is the setting whose *absence* is a working
  # configuration: without it this module sends normally and refuses to create bots, naming what is missing.
  app_settings = merge(
    {
      # No credential in the URL and no AZURE_* triple — config.py refuses one when DATABASE_USER is set, and the
      # identity is ambient. That user is the role `scripts/grant-schema-ownership.sql` creates for this app.
      DATABASE_URL  = "postgresql://${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.telegram.name}?sslmode=require"
      DATABASE_USER = local.telegram_gateway_app_name

      # This module's share of the server's 35 connections — one HTTP call per message, not a query per row.
      # The whole budget is one number, checked by `scripts/tests/test_pool_budget.py`.
      DATABASE_POOL_SIZE = "4"

      # Telegram's bot surface, set here rather than left to the module's default for the reason every other
      # upstream address is: a default that moved under a dependency bump would move with nothing to say so.
      BOT_API_BASE_URL = "https://api.telegram.org"

      MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = module.telegram_gateway_easy_auth.password

      # The module checks the caller's identity itself rather than trusting the block above is switched on.
      REQUIRE_AUTHENTICATED_PRINCIPAL = "true"

      # Which caller reaches which surface, by the `azp`/`appid` claim naming the application — never the
      # principal-id header, which for a delegated token names the signed-in person.
      TOOL_CALLER_APPLICATION_IDS = data.azuread_service_principal.workbench_managed_identity.client_id
      REST_CALLER_APPLICATION_IDS = join(",", [
        data.azuread_service_principal.social_data_managed_identity.client_id,
        data.azuread_service_principal.strategy_managed_identity.client_id,
        # Easy Auth admits an application; this is what lets that application reach these routes. Both are needed
        # and neither substitutes for the other — `caller_access.py` refuses on this list alone.
        local.azure_cli_client_id,
      ])

      APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
    },
    # All three or none, and never a reference to a secret with no value: an unresolved Key Vault reference is left
    # in place as its own literal text, which `TELEGRAM_API_ID` would refuse to parse — a module that will not start
    # over a capability it is supposed to work without.
    var.telegram_account_session_configured ? {
      TELEGRAM_API_ID   = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.telegram_api_id})"
      TELEGRAM_API_HASH = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.telegram_api_hash})"
      TELEGRAM_SESSION  = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.telegram_session})"
    } : {}
  )

  lifecycle {
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

output "telegram_gateway_hostname" {
  value = azurerm_linux_web_app.telegram_gateway.default_hostname
}

output "telegram_gateway_scope" {
  description = "What a caller asks Entra for when it wants a token for the gateway. Carried as a literal by social-data's and strategy's settings, like every other scope here."
  value       = "${local.telegram_gateway_api_uri}/.default"
}

output "telegram_gateway_managed_identity_principal_id" {
  description = "The operator's one-off Postgres role creation in the `telegram` database needs this object id — and `scripts/grant-schema-ownership.sql` has to be run there too, before the first deploy tries to migrate."
  value       = azurerm_linux_web_app.telegram_gateway.identity[0].principal_id
}
