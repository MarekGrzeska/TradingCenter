# There used to be a `sp-tradingcenter-market-data-dev` registration here, for the local process. Local work moved to a
# container the same day, retiring the identity and its yearly rotation — and config.py holds local runs to loopback.

# --- the terminal, as a caller of the workbench ---------------------------------------

# The browser half of the pair whose other half is `module.workbench_easy_auth`. It holds no secret and cannot: a
# single-page application authenticates the *operator*, and what it gets back travels in an `Authorization` header.
resource "azuread_application" "terminal" {
  display_name = "app-tradingcenter-terminal"

  single_page_application {
    # The trailing slash is not optional — the provider refuses a redirect URI without one when there is no path
    # segment — and MSAL's default `window.location.origin` has none, so the terminal sets `redirectUri` explicitly.
    redirect_uris = [for origin in var.vps_terminal_origins : "${origin}/"]
  }

  # One process, one registration, one scope to ask for — the archive's own went with its process in stage 3 of
  # `one-process-per-security-boundary`, and teams' before it.
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

  # Microsoft Graph, for the Users tab: delegated, so the call is the signed-in admin's own and a person without a
  # directory role is refused by Graph even holding this token. Consent is granted below, once, for everyone.
  required_resource_access {
    resource_app_id = data.azuread_service_principal.msgraph.client_id

    dynamic "resource_access" {
      for_each = local.terminal_graph_scopes

      content {
        id   = data.azuread_service_principal.msgraph.oauth2_permission_scope_ids[resource_access.value]
        type = "Scope"
      }
    }
  }

  # **No block for any package of the workbench, and that is the pattern rather than an omission**: a `resource_access.id`
  # must be concrete at plan time, and a scope this same apply creates is not.
}

resource "azuread_service_principal" "terminal" {
  client_id = azuread_application.terminal.client_id
}

# `data.azuread_service_principal.msgraph` is declared in github-oidc.tf.
locals {
  terminal_graph_scopes = ["User.Invite.All", "User.Read.All", "Application.Read.All", "AppRoleAssignment.ReadWrite.All"]
}

# Admin consent for everyone, so no prompt reaches the operator. What a person can actually do is the intersection of
# this and their own directory roles.
resource "azuread_service_principal_delegated_permission_grant" "terminal_graph" {
  service_principal_object_id          = azuread_service_principal.terminal.object_id
  resource_service_principal_object_id = data.azuread_service_principal.msgraph.object_id
  claim_values                         = local.terminal_graph_scopes
}

locals {
  admin_user_object_ids = toset(concat([var.operator_object_id], var.admin_user_object_ids))
}

# The existing operators keep what they have: without this the gate (fail-closed) would refuse them on the day it ships.
# Apply this *before* the code that reads `roles` is merged — an old process ignores the claim.
resource "azuread_app_role_assignment" "admin_workbench" {
  for_each            = local.admin_user_object_ids
  app_role_id         = module.workbench_easy_auth.role_ids["admin"]
  principal_object_id = each.value
  resource_object_id  = module.workbench_easy_auth.service_principal_object_id
}

resource "azuread_app_role_assignment" "admin_gateway" {
  for_each            = local.admin_user_object_ids
  app_role_id         = module.capital_gateway_easy_auth.role_ids["admin"]
  principal_object_id = each.value
  resource_object_id  = module.capital_gateway_easy_auth.service_principal_object_id
}

output "workbench_service_principal_object_id" {
  description = "Resource id of the workbench's app roles, for the terminal's Users tab."
  value       = module.workbench_easy_auth.service_principal_object_id
}

output "gateway_service_principal_object_id" {
  description = "Resource id of the gateway's app roles, for the terminal's Users tab."
  value       = module.capital_gateway_easy_auth.service_principal_object_id
}

output "app_role_ids" {
  description = "Role GUIDs the Users tab assigns: workbench admin and viewer, gateway admin."
  value = {
    workbench_admin  = module.workbench_easy_auth.role_ids["admin"]
    workbench_viewer = module.workbench_easy_auth.role_ids["viewer"]
    gateway_admin    = module.capital_gateway_easy_auth.role_ids["admin"]
  }
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
  app_roles      = local.app_roles

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

# No pre-authorization for the archives: all three are served by the workbench, whose
# scope the one above covers.


# The three values the terminal's build needs. All three are public by nature — a client id and a scope name travel in
# every authorization request the browser makes — so they go through `vars`, never `secrets`.
output "terminal_entra_client_id" {
  value = azuread_application.terminal.client_id
}

output "terminal_entra_tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "terminal_entra_scope" {
  description = "The scope the terminal asks for when it wants a token for the workbench — the archive's, since the archive is a package of it."
  value       = "${local.workbench_api_uri}/${local.workbench_api_scope}"
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
    redirect_uris = [for origin in var.vps_pocket_origins : "${origin}/"]
  }


  # One API: the workbench, which serves the conversation and — since `one-process-per-security-boundary` — both
  # archives, under `/polymarket` and `/social`, so one token reaches all three.
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

output "pocket_origins" {
  description = "Where the phone screen is served — its redirect URIs, and the origin the edge's CORS allows."
  value       = var.vps_pocket_origins
}


# --- the operator, as the one caller of the door to Telegram that is a person ------------

# The only pre-authorization whose client is not something in this repository. The door to Telegram has no screen — the
# notification is its screen — so the operator's client is `az`, and the routes this exists for are the two a managed
# identity must never reach: adopting a bot and binding a destination. On the workbench's registration since stage 4 of
# `one-process-per-security-boundary`, when `/telegram` became a package of that process.
#
# Without it `az account get-access-token --resource api://tradingcenter-agent` meets a consent prompt that a command
# line cannot answer.
resource "azuread_application_pre_authorized" "workbench_cli" {
  application_id       = module.workbench_easy_auth.application_id
  authorized_client_id = local.azure_cli_client_id
  permission_ids       = [module.workbench_easy_auth.scope_id]
}


# --- the operator's own MCP client, as a caller of every tool surface (`operator-mcp-access`) ----------------------------

# Claude Code on the operator's machine (`scripts/mcp_token.py`), a public client. Its own registration rather than `az`'s,
# so the tool lists name one application that is nothing else, and removing it takes nothing else with it.
resource "azuread_application" "claude_code" {
  display_name = "app-tradingcenter-claude-code"

  # A native client: Entra accepts any port on loopback for this platform, which is what MSAL's local listener picks.
  public_client {
    redirect_uris = ["http://localhost"]
  }

  required_resource_access {
    resource_app_id = module.workbench_easy_auth.client_id

    resource_access {
      id   = module.workbench_easy_auth.scope_id
      type = "Scope"
    }
  }

  # The gateway's API is the one trading-mcp accepts from outside: moving the account is the gateway's `admin`.
  required_resource_access {
    resource_app_id = module.capital_gateway_easy_auth.client_id

    resource_access {
      id   = module.capital_gateway_easy_auth.scope_id
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "claude_code" {
  client_id = azuread_application.claude_code.client_id
}

# Both, so neither the first sign-in nor the silent token for the second API meets a consent prompt a helper with ten
# seconds and no screen could not answer. No role assignment: the role is the person's, and the operator holds `admin`.
resource "azuread_application_pre_authorized" "workbench_claude_code" {
  application_id       = module.workbench_easy_auth.application_id
  authorized_client_id = azuread_application.claude_code.client_id
  permission_ids       = [module.workbench_easy_auth.scope_id]
}

resource "azuread_application_pre_authorized" "gateway_claude_code" {
  application_id       = module.capital_gateway_easy_auth.application_id
  authorized_client_id = azuread_application.claude_code.client_id
  permission_ids       = [module.capital_gateway_easy_auth.scope_id]
}

# Public by nature, like the terminal's: a client id travels in every authorization request. `CLAUDE_CODE_APPLICATION_ID`
# in the environment `vps`, and an argument of `scripts/claude-mcp.sh install`.
output "claude_code_entra_client_id" {
  value = azuread_application.claude_code.client_id
}
