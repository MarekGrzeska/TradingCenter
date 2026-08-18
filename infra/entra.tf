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

  # Ready for whenever the terminal is changed to ask for a token scoped to the agent
  # by name, rather than reusing its market-data token against it (see the comment on
  # `module.agent_easy_auth` below) — `required_resource_access` takes one block per resource,
  # so this sits alongside the one above rather than replacing it.
  required_resource_access {
    resource_app_id = module.agent_easy_auth.client_id

    resource_access {
      id   = module.agent_easy_auth.scope_id
      type = "Scope"
    }
  }

  # And the same again for teams, standing ready for the same reason — the terminal's
  # teams tab (tasks.md group 9) reaches that module with the token it already holds, and
  # this block is what a later change needs to have been here for the terminal to ask for
  # a token scoped to teams by name instead.
  required_resource_access {
    resource_app_id = module.teams_easy_auth.client_id

    resource_access {
      id   = module.teams_easy_auth.scope_id
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

# --- agent, as a caller of the terminal (its own API registration) ------------------
#
# Its own registration rather than reuse of `module.market_data_easy_auth` — each backend
# module is its own API here the same way each is its own deployable (design.md,
# "Osobny moduł `modules/agent`"), and tasks.md 10.6 asks for exactly this: a
# registration and a scope of the agent's own.
#
# The terminal's identity layer (`src/auth/`) acquires one token today, scoped to
# market-data — `add-agent-chat`'s Migration Plan lists only `VITE_AGENT_HTTP` as the
# terminal-side step to go live, no second scope. So `allowed_audiences` on the
# agent's App Service (app-service.tf) accepts *both* this new audience and
# market-data's: the terminal's existing token works against agent unmodified today,
# and the scope below stands ready, pre-authorized, for whenever the terminal is
# changed to ask for it by name instead.
module "agent_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-agent-easyauth"
  identifier_uri = local.agent_api_uri
  redirect_uri   = "https://${local.agent_hostname}/.auth/login/aad/callback"

  id_token_issuance_enabled = true

  scope = {
    value                      = local.agent_api_scope
    admin_consent_display_name = "Talk to the agent"
    admin_consent_description  = "Allows the app to reach the agent as the signed-in operator."
    user_consent_display_name  = "Talk to the agent on your behalf"
    user_consent_description   = "Allows the app to reach the agent as you."
  }
}

resource "azuread_application_pre_authorized" "agent_terminal" {
  application_id       = module.agent_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.agent_easy_auth.scope_id]
}

# --- teams, as an API of its own -----------------------------------------------------
#
# The fifth backend module and the fourth registration of this shape. Its own, for the
# reason the agent's comment above gives: each backend module is its own API here the
# same way each is its own deployable, and a module that borrowed another's registration
# could never be removed without touching the one it borrowed from (design.md, "Moduł ma
# dać się usunąć przez skasowanie katalogu i zasobów").
#
# The scope below is granted to the terminal and pre-authorized, but is not yet what the
# terminal's token carries — `src/auth/` asks Entra for market-data's scope and reuses
# that token everywhere. So `allowed_audiences` on the teams App Service (app-service.tf)
# accepts market-data's audience as well, exactly as agent's does, and for exactly as
# long: until the terminal is taught to ask for each module's scope by name.
module "teams_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-teams-easyauth"
  identifier_uri = local.teams_api_uri
  redirect_uri   = "https://${local.teams_hostname}/.auth/login/aad/callback"

  id_token_issuance_enabled = true

  scope = {
    value                      = local.teams_api_scope
    admin_consent_display_name = "Compose and run agent teams"
    admin_consent_description  = "Allows the app to reach the teams module as the signed-in operator."
    user_consent_display_name  = "Compose and run your agent teams"
    user_consent_description   = "Allows the app to reach the teams module as you."
  }
}

resource "azuread_application_pre_authorized" "teams_terminal" {
  application_id       = module.teams_easy_auth.application_id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [module.teams_easy_auth.scope_id]
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
