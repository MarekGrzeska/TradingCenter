# One Linux App Service Plan, two apps. design.md, "App Service, nie Container Apps":
# both modules run non-stop, so a shared B1 plan is cheaper than two Container Apps
# billed by CPU-second, and B1 fits the free-tier grant this subscription is on.
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

  # Deterministic App Service hostnames — used ahead of `terraform apply` (e.g. in the
  # Easy Auth redirect URI below) instead of waiting on the computed `default_hostname`,
  # since Azure names of this form are `<name>.azurewebsites.net` with no surprises.
  capital_gateway_hostname = "${local.capital_gateway_app_name}.azurewebsites.net"
  market_data_hostname     = "${local.market_data_app_name}.azurewebsites.net"

  kv_secret_uri = {
    for k, name in local.key_vault_secret_names :
    k => "${azurerm_key_vault.main.vault_uri}secrets/${name}/"
  }

  # GHCR is private, because the repository is, so App Service needs a credential to pull
  # at all — without these three the container never starts and the site answers 503 with
  # `ImagePullUnauthorizedFailure` in the docker log. Identical for both apps, so said
  # once here rather than twice below.
  #
  # The alternative that needs no stored credential is Azure Container Registry, which
  # App Service pulls from with its managed identity — rejected on cost: it is a paid
  # resource and every other piece of this platform fits the free-tier grant.
  ghcr_pull_settings = {
    DOCKER_REGISTRY_SERVER_URL      = "https://ghcr.io"
    DOCKER_REGISTRY_SERVER_USERNAME = "MarekGrzeska"
    DOCKER_REGISTRY_SERVER_PASSWORD = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.ghcr_pull_token})"
  }
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

  app_settings = merge(local.ghcr_pull_settings, {
    GATEWAY_ENV        = "production"
    CAPITAL_BASE_URL   = "https://demo-api-capital.backend-capital.com"
    CAPITAL_STREAM_URL = "wss://api-streaming-capital.backend-capital.com/connect"

    CAPITAL_API_KEY    = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.capital_api_key})"
    CAPITAL_IDENTIFIER = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.capital_identifier})"
    CAPITAL_PASSWORD   = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.capital_password})"
    GATEWAY_API_KEY    = "@Microsoft.KeyVault(SecretUri=${local.kv_secret_uri.gateway_api_key})"

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  })

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
resource "azuread_application" "market_data_easy_auth" {
  display_name = "app-tradingcenter-market-data-easyauth"

  web {
    redirect_uris = ["https://${local.market_data_hostname}/.auth/login/aad/callback"]

    implicit_grant {
      id_token_issuance_enabled = true
    }
  }
}

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

    application_stack {
      docker_image_name = "mcr.microsoft.com/appsvc/staticsite:latest"
    }
  }

  # Return401, not RedirectToLoginPage: `terminal` reaches this app through `fetch()`,
  # not top-level browser navigation, and a redirect response handed to `fetch` resolves
  # to an HTML login page masquerading as a JSON body instead of a request `terminal`
  # can react to. Client-side handling of the 401 (send the user through
  # /.auth/login/aad) is application work, not infrastructure — flagged here, not
  # solved here; it isn't one of this group's tasks.
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "azureactivedirectory"

    active_directory_v2 {
      client_id                  = azuread_application.market_data_easy_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"
    }

    login {
      token_store_enabled = true
    }
  }

  app_settings = merge(local.ghcr_pull_settings, {
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

    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  })

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

output "capital_gateway_hostname" {
  value = azurerm_linux_web_app.capital_gateway.default_hostname
}

output "market_data_hostname" {
  value = azurerm_linux_web_app.market_data.default_hostname
}

output "market_data_managed_identity_principal_id" {
  description = "Postgres role creation (5.7 / old 4.7) needs this object id."
  value       = azurerm_linux_web_app.market_data.identity[0].principal_id
}
