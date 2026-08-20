# There used to be a `sp-tradingcenter-market-data-dev` registration here — the identity
# the local market-data process authenticated to `market_data_dev` with, separate from
# the human operator because the server's AD Administrator bypasses every GRANT. Local
# work moved to a container the same day (openspec/changes/local-dev-database-in-docker),
# which retired both the identity and its yearly secret rotation. Local processes now
# carry no cloud identity at all — and config.py holds them to loopback because of it.

# --- the terminal, as a caller of market-data ---------------------------------------

# The browser half of the pair whose other half is `module.market_data_easy_auth`
# (app-service.tf). This registration holds no secret and cannot: a single-page
# application runs where every byte it carries is readable, so it authenticates the
# *operator* and never itself. What it gets back is a token for market-data, which it
# sends in an `Authorization` header — the thing an Easy Auth cookie cannot do across two
# hostnames (openspec/changes/authenticate-terminal-to-market-data, design.md).
resource "azuread_application" "terminal" {
  display_name = "app-tradingcenter-terminal"

  single_page_application {
    # The trailing slash is not optional — the provider refuses a redirect URI without
    # one when there is no path segment ("URI must have a trailing slash when there is no
    # path segment"). Azure then matches it exactly, and MSAL's own default is
    # `window.location.origin`, which has **no** trailing slash. So the terminal sets its
    # `redirectUri` explicitly rather than taking the default; the two spellings must
    # agree, and this is the one that can be registered.
    redirect_uris = ["${local.terminal_origin}/"]
  }

  required_resource_access {
    resource_app_id = module.market_data_easy_auth.client_id

    resource_access {
      id   = module.market_data_easy_auth.scope_id
      type = "Scope"
    }
  }

  # Ready for whenever the terminal is changed to ask for a token scoped to the workbench
  # by name, rather than reusing its market-data token against it (see the comment on
  # `module.workbench_easy_auth` below) — `required_resource_access` takes one block per
  # resource, so this sits alongside the one above rather than replacing it.
  #
  # There used to be a third block here, for teams. Its module and the workbench's are one
  # process, so there is one registration to stand ready and one scope to ask for.
  required_resource_access {
    resource_app_id = module.workbench_easy_auth.client_id

    resource_access {
      id   = module.workbench_easy_auth.scope_id
      type = "Scope"
    }
  }

  # The gateway, since the Accounts screen. The terminal reads the demo account from it
  # directly — the shared key the modules use cannot travel to a browser, so a token for
  # this API is what the screen presents instead
  # (openspec/changes/accounts-screen-opens-the-gateway).
  required_resource_access {
    resource_app_id = module.capital_gateway_easy_auth.client_id

    resource_access {
      id   = module.capital_gateway_easy_auth.scope_id
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "terminal" {
  client_id = azuread_application.terminal.client_id
}

# Consent, decided here instead of on a screen. Without this the operator is asked, at
# first sign-in and again after any scope change, whether they agree to give their own
# terminal access to their own archive — a question with one sensible answer, asked of
# the only person who could have configured either side.
resource "azuread_application_pre_authorized" "terminal" {
  application_id       = module.market_data_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.market_data_easy_auth.scope_id]
}

# The same, for the gateway's own API. Standing ready rather than in use today: the
# terminal still presents its market-data token, which that app accepts as a third
# audience (app-service.tf). This is what makes asking for the gateway by name a change to
# the terminal alone, with no second consent prompt on the day it happens.
resource "azuread_application_pre_authorized" "terminal_gateway" {
  application_id       = module.capital_gateway_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.capital_gateway_easy_auth.scope_id]
}

# --- the workbench, as an API of its own ---------------------------------------------
#
# Its own registration rather than reuse of `module.market_data_easy_auth` — each backend
# module is its own API here the same way each is its own deployable, and a module that
# borrowed another's registration could never be removed without touching the one it
# borrowed from ("Moduł ma dać się usunąć przez skasowanie katalogu i zasobów").
#
# The terminal's identity layer (`src/auth/`) acquires one token today, scoped to
# market-data, and reuses it everywhere. So `allowed_audiences` on this app's App Service
# (app-service.tf) accepts *both* this audience and market-data's: the terminal's existing
# token works against it unmodified, and the scope below stands ready, pre-authorized, for
# whenever the terminal is changed to ask for it by name instead.
#
# **There used to be two of these**, one for the chat and one for teams. One process, one
# registration — and the display name keeps the `-agent` spelling for the same reason the
# App Service does (`local.workbench_app_name`): renaming an Entra application means a new
# client id, and the client id is what the terminal's build and three allow-lists hold.
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

# The three values the terminal's build needs (deploy-terminal.yml). All three are public
# by nature — a client id and a scope name travel in every authorization request the
# browser makes, and are visible to anyone with the developer tools open. They go through
# `vars`, never `secrets`; nothing here adds a stored secret.
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
