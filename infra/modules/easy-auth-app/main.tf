terraform {
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

resource "azuread_application" "this" {
  display_name    = var.display_name
  identifier_uris = [var.identifier_uri]

  # The `api` block is here even with no scope inside it, and that is not tidiness: without it the provider defaults to
  # v1 tokens, and Entra refuses such a registration under the tenant's URI policy — which cost an interrupted apply.
  api {
    requested_access_token_version = 2

    dynamic "oauth2_permission_scope" {
      for_each = var.scope == null ? [] : [var.scope]

      content {
        id                         = random_uuid.scope[0].result
        value                      = oauth2_permission_scope.value.value
        type                       = "User"
        enabled                    = true
        admin_consent_display_name = oauth2_permission_scope.value.admin_consent_display_name
        admin_consent_description  = oauth2_permission_scope.value.admin_consent_description
        user_consent_display_name  = oauth2_permission_scope.value.user_consent_display_name
        user_consent_description   = oauth2_permission_scope.value.user_consent_description
      }
    }
  }

  # Roles a person can hold on this API. They travel in the token's `roles` claim, which is what the process's door reads
  # (`access-roles`); a role id is a stable GUID for the reason the scope's is.
  dynamic "app_role" {
    for_each = var.app_roles

    content {
      id                   = random_uuid.role[app_role.key].result
      value                = app_role.key
      display_name         = app_role.value.display_name
      description          = app_role.value.description
      allowed_member_types = ["User"]
      enabled              = true
    }
  }

  # No web redirect and no implicit grant since the platform authenticator went with Azure: nothing signs in *to* this
  # registration any more, and a redirect URI on a hostname nobody holds is one somebody else could register.
}

# Generated once and kept in state. A scope id must be a stable GUID: regenerating it would
# revoke the terminal's permission and grant a different one on every apply.
resource "random_uuid" "scope" {
  count = var.scope == null ? 0 : 1
}

resource "random_uuid" "role" {
  for_each = var.app_roles
}

resource "azuread_service_principal" "this" {
  client_id = azuread_application.this.client_id
}
