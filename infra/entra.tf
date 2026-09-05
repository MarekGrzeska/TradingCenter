# There used to be a `sp-tradingcenter-market-data-dev` registration here, for the local process. Local work moved to a
# container the same day, retiring the identity and its yearly rotation — and config.py holds local runs to loopback.

# --- the terminal, as a caller of market-data ---------------------------------------

# The browser half of the pair whose other half is `module.market_data_easy_auth`. It holds no secret and cannot: a
# single-page application authenticates the *operator*, and what it gets back travels in an `Authorization` header.
resource "azuread_application" "terminal" {
  display_name = "app-tradingcenter-terminal"

  single_page_application {
    # The trailing slash is not optional — the provider refuses a redirect URI without one when there is no path
    # segment — and MSAL's default `window.location.origin` has none, so the terminal sets `redirectUri` explicitly.
    redirect_uris = ["${local.terminal_origin}/"]
  }

  required_resource_access {
    resource_app_id = module.market_data_easy_auth.client_id

    resource_access {
      id   = module.market_data_easy_auth.scope_id
      type = "Scope"
    }
  }

  # Ready for whenever the terminal asks for a token scoped to the workbench by name rather than reusing market-data's.
  # There used to be a third block, for teams: one process, one registration, one scope to ask for.
  required_resource_access {
    resource_app_id = module.workbench_easy_auth.client_id

    resource_access {
      id   = module.workbench_easy_auth.scope_id
      type = "Scope"
    }
  }

  # The gateway, since the Accounts screen: the shared key the modules use cannot travel to a browser, so a token for
  # this API is what the screen presents instead.
  required_resource_access {
    resource_app_id = module.capital_gateway_easy_auth.client_id

    resource_access {
      id   = module.capital_gateway_easy_auth.scope_id
      type = "Scope"
    }
  }

  # **No block for the strategy platform, and that is the pattern rather than an omission** — `polymarket-data` has none
  # either. A `resource_access.id` must be concrete at plan time, and a scope this same apply creates is not.
}

resource "azuread_service_principal" "terminal" {
  client_id = azuread_application.terminal.client_id
}

# Consent, decided here instead of on a screen: without this the operator is asked whether they agree to give their own
# terminal access to their own archive — a question with one sensible answer, asked of the person who configured both.
resource "azuread_application_pre_authorized" "terminal" {
  application_id       = module.market_data_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.market_data_easy_auth.scope_id]
}

# The same for the gateway's own API, standing ready rather than in use: it is what makes asking for the gateway by name
# a change to the terminal alone, with no second consent prompt on the day it happens.
resource "azuread_application_pre_authorized" "terminal_gateway" {
  application_id       = module.capital_gateway_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.capital_gateway_easy_auth.scope_id]
}

# --- the workbench, as an API of its own ---------------------------------------------
#
# Its own registration rather than reuse of market-data's: a module that borrowed another's could never be removed
# without touching it. **There used to be two of these** — one process, one registration, and the `-agent` spelling
# stays because a rename means a new client id, which the terminal's build and three allow-lists hold.
module "workbench_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-agent-easyauth"
  identifier_uri = local.workbench_api_uri
  redirect_uri   = "https://${local.workbench_hostname}/.auth/login/aad/callback"

  id_token_issuance_enabled = true

  scope = {
    value                      = local.workbench_api_scope
    admin_consent_display_name = "Talk to the agent and run teams"
    admin_consent_description  = "Allows the app to reach the workbench as the signed-in operator."
    user_consent_display_name  = "Talk to the agent and run teams on your behalf"
    user_consent_description   = "Allows the app to reach the workbench as you."
  }
}

resource "azuread_application_pre_authorized" "workbench_terminal" {
  application_id       = module.workbench_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.workbench_easy_auth.scope_id]
}


# It stands ready rather than in use for the reason the first three did: a `resource_access.id` must
# be concrete at plan time, so the terminal's registration cannot name a scope this same apply creates.
resource "azuread_application_pre_authorized" "social_data_terminal" {
  application_id       = module.social_data_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.social_data_easy_auth.scope_id]
}

# The sixth. The strategy platform shipped for machine callers, so its registration announced no delegated scope at all
# — the terminal was on its caller list and still met a 401, because there was nothing for a browser to ask for.
resource "azuread_application_pre_authorized" "strategy_terminal" {
  application_id       = module.strategy_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.strategy_easy_auth.scope_id]
}

# The three values the terminal's build needs. All three are public by nature — a client id and a scope name travel in
# every authorization request the browser makes — so they go through `vars`, never `secrets`.
output "terminal_entra_client_id" {
  value = azuread_application.terminal.client_id
}

output "terminal_entra_tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "terminal_entra_scope" {
  description = "The scope the terminal asks for when it wants a token for market-data."
  value       = "${local.market_data_api_uri}/${local.market_data_api_scope}"
}

# --- pocket, as a caller of polymarket-data ------------------------------------------
#
# Its own registration rather than a second redirect URI on the terminal's: one registration for two origins means a
# consent granted for one is granted for the other, and the two screens are meant to be revocable apart. It asks for
# **one** API, which is the whole difference from the terminal's three blocks.
resource "azuread_application" "pocket" {
  display_name = "app-tradingcenter-pocket"

  single_page_application {
    # The trailing slash is not optional — the provider refuses a redirect URI without one when there is no path
    # segment — and MSAL's default `window.location.origin` has none, so `auth/entra.ts` sets `redirectUri` itself.
    redirect_uris = ["${local.pocket_origin}/"]
  }


  # One API: the workbench, which serves the conversation and — since `one-process-per-security-boundary` — the
  # prediction-market archive under `/polymarket`, so one token reaches both.
  required_resource_access {
    resource_app_id = module.workbench_easy_auth.client_id

    resource_access {
      id   = module.workbench_easy_auth.scope_id
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "pocket" {
  client_id = azuread_application.pocket.client_id
}


# The post archive's, for the same reason: a phone asked to consent mid-glance is a phone put back in a pocket.
resource "azuread_application_pre_authorized" "social_data_pocket" {
  application_id       = module.social_data_easy_auth.application_id
  authorized_client_id = azuread_application.pocket.client_id
  permission_ids       = [module.social_data_easy_auth.scope_id]
}

# The conversation's, for the same reason and on the same day: the agent tab acquires this one silently, which is
# exactly what a pre-authorization is for — without it the operator meets a consent prompt on a phone, mid-question.
resource "azuread_application_pre_authorized" "workbench_pocket" {
  application_id       = module.workbench_easy_auth.application_id
  authorized_client_id = azuread_application.pocket.client_id
  permission_ids       = [module.workbench_easy_auth.scope_id]
}

# The two values pocket's build needs that the terminal's does not already publish. Public by nature, like the
# terminal's three: a client id travels in every authorization request the browser makes. The scope it asks for is
# `terminal_entra_scope_polymarket`, which is the same string for both screens and stays output once.
output "pocket_entra_client_id" {
  value = azuread_application.pocket.client_id
}

output "pocket_origin" {
  description = "Where the phone screen is served — the redirect URI above, the origin the workbench's CORS allows, and what deploy-pocket.yml smoke-checks."
  value       = local.pocket_origin
}


# --- the operator, as the one caller of telegram-gateway that is a person ---------------

# The seventh pre-authorization and the only one whose client is not something in this repository. `telegram-gateway`
# has no screen — the notification is its screen — so the operator's client is `az`, and the two routes this exists
# for are the two a managed identity must never reach: adopting a bot and binding a destination.
#
# Without it `az account get-access-token --resource api://tradingcenter-telegram-gateway` meets a consent prompt
# that a command line cannot answer.
resource "azuread_application_pre_authorized" "telegram_gateway_cli" {
  application_id       = module.telegram_gateway_easy_auth.application_id
  authorized_client_id = local.azure_cli_client_id
  permission_ids       = [module.telegram_gateway_easy_auth.scope_id]
}
