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

  web {
    redirect_uris = [var.redirect_uri]

    dynamic "implicit_grant" {
      for_each = var.id_token_issuance_enabled ? [true] : []

      content {
        id_token_issuance_enabled = true
      }
    }
  }
}

# Generated once and kept in state. A scope id must be a stable GUID: regenerating it would
# revoke the terminal's permission and grant a different one on every apply.
resource "random_uuid" "scope" {
  count = var.scope == null ? 0 : 1
}

resource "azuread_service_principal" "this" {
  client_id = azuread_application.this.client_id
}

# What Easy Auth reads as MICROSOFT_PROVIDER_AUTHENTICATION_SECRET. `end_date` is ignored after creation: `timestamp()`
# moves on every plan, and a rotation the app has not restarted for is an app rejecting every token.
resource "azuread_application_password" "this" {
  application_id = azuread_application.this.id
  display_name   = "easy-auth"
  end_date       = timeadd(timestamp(), "8760h")

  lifecycle {
    ignore_changes = [end_date]
  }
}
