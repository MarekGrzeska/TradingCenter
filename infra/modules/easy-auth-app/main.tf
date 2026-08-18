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

  # The `api` block is here even when there is no scope inside it, and that is not tidiness.
  # Leaving it out cost an interrupted apply on 13 August 2026 (market-mcp), with two
  # failures from one cause:
  #
  #   1. Entra refused the registration — "InvalidUniqueTenantIdentifierAsPerAppPolicy: all
  #      newly added URIs must contain a tenant verified domain, tenant ID, or app ID". The
  #      tenant policy exempts applications asking for v2 tokens, which is why
  #      `api://tradingcenter-market-data` was accepted and `api://tradingcenter-market-mcp`
  #      was not.
  #   2. Had it been accepted, the caller's token would have been rejected on arrival: Easy
  #      Auth is configured against the `/v2.0` tenant endpoint, and a v1 token there fails
  #      on its `iss` claim with an error naming no versions at all.
  #
  # The provider's default is 1. Every registration with a scope set 2 inside a block it
  # needed anyway; the three without one needed the block for nothing else, which is exactly
  # how it went missing. Unconditional here, so it cannot go missing again.
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

# What Easy Auth reads as MICROSOFT_PROVIDER_AUTHENTICATION_SECRET. `end_date` is ignored
# after creation: `timestamp()` moves on every plan, so without this the secret would be
# rotated on every apply — and a rotation the app has not restarted for is an app rejecting
# every token.
resource "azuread_application_password" "this" {
  application_id = azuread_application.this.id
  display_name   = "easy-auth"
  end_date       = timeadd(timestamp(), "8760h")

  lifecycle {
    ignore_changes = [end_date]
  }
}
