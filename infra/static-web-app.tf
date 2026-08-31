# `terminal` — Free tier, with Static Web Apps' own built-in Entra ID login rather than a custom registration like
# market-data's: "built-in" is the platform's own multi-tenant app, so there is nothing here to register or rotate.
resource "azurerm_static_web_app" "terminal" {
  name                = "swa-tradingcenter-terminal"
  resource_group_name = azurerm_resource_group.main.name
  # Static Web Apps ships in five regions, Poland Central is not one, and this subscription's West Europe is closed to
  # new customers. Only static content and a login redirect are served here — nothing latency-sensitive.
  location = "eastus2"

  sku_tier = "Free"
  sku_size = "Free"

  lifecycle {
    # The deploy action records which repository and branch it deployed from, so these appear after the first deploy
    # although nothing here sets them. Left to fight it out, Terraform and the deploy would trade them every apply.
    ignore_changes = [repository_url, repository_branch]
  }
}

output "terminal_default_host_name" {
  value = azurerm_static_web_app.terminal.default_host_name
}

output "terminal_api_key" {
  description = "Consumed by the deploy workflow (deploy-terminal.yml) as a GitHub secret — SWA has no OIDC deployment path yet, unlike the two App Service apps."
  sensitive   = true
  value       = azurerm_static_web_app.terminal.api_key
}

# `pocket` — the same Free tier, the same region and the same reason as the terminal above. A second app rather than a
# route inside that one: they are separate builds with separate identities, and a Free SWA costs nothing to hold.
resource "azurerm_static_web_app" "pocket" {
  name                = "swa-tradingcenter-pocket"
  resource_group_name = azurerm_resource_group.main.name
  # eastus2 for the terminal's reason, not a preference: Static Web Apps ships in five regions, Poland Central is not
  # one of them, and this subscription's West Europe is closed to new customers.
  location = "eastus2"

  sku_tier = "Free"
  sku_size = "Free"

  lifecycle {
    # The deploy action writes these after the first deploy although nothing here sets them; left to fight it out,
    # Terraform and the deploy would trade them every apply.
    ignore_changes = [repository_url, repository_branch]
  }
}

output "pocket_default_host_name" {
  value = azurerm_static_web_app.pocket.default_host_name
}

output "pocket_api_key" {
  description = "Consumed by deploy-pocket.yml as the AZURE_STATIC_WEB_APPS_API_TOKEN_POCKET secret — SWA still has no OIDC deployment path, so this is the same narrow exception the terminal's token is."
  sensitive   = true
  value       = azurerm_static_web_app.pocket.api_key
}
