# There used to be a `sp-tradingcenter-market-data-dev` registration here — the identity
# the local market-data process authenticated to `market_data_dev` with, separate from
# the human operator because the server's AD Administrator bypasses every GRANT. Local
# work moved to a container the same day (openspec/changes/local-dev-database-in-docker),
# which retired both the identity and its yearly secret rotation. Local processes now
# carry no cloud identity at all — and config.py holds them to loopback because of it.

# --- the terminal, as a caller of market-data ---------------------------------------

# The browser half of the pair whose other half is `market_data_easy_auth`
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
    resource_app_id = azuread_application.market_data_easy_auth.client_id

    resource_access {
      id   = random_uuid.market_data_scope.result
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
  application_id       = azuread_application.market_data_easy_auth.id
  authorized_client_id = azuread_application.terminal.client_id
  permission_ids       = [random_uuid.market_data_scope.result]
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
