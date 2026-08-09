# `terminal` — Free tier (design.md, cost: one operator, no need for the paid tier's
# extra environments or bandwidth) with Static Web Apps' own built-in Entra ID login,
# not a custom app registration like market-data's Easy Auth (5.4). "Built-in" is the
# platform's own multi-tenant app — the operator hits `/.auth/login/aad` and there is
# nothing here to register or rotate.
resource "azurerm_static_web_app" "terminal" {
  name                = "swa-tradingcenter-terminal"
  resource_group_name = azurerm_resource_group.main.name
  # Static Web Apps only ships in five regions, Poland Central isn't one, and this
  # subscription's West Europe is closed to new customers (Azure error
  # RequestDisallowedByAzure at apply time — https://aka.ms/locationineligible). East US
  # 2 is the next closest of the remaining four (Central US, East US 2, West US 2, East
  # Asia). Static content and Easy Auth's login redirect are the only things served from
  # here — nothing latency-sensitive, unlike the database and the two App Service apps,
  # which do stay in Poland Central.
  location = "eastus2"

  sku_tier = "Free"
  sku_size = "Free"
}

output "terminal_default_host_name" {
  value = azurerm_static_web_app.terminal.default_host_name
}

output "terminal_api_key" {
  description = "Consumed by the deploy workflow (deploy-terminal.yml) as a GitHub secret — SWA has no OIDC deployment path yet, unlike the two App Service apps."
  sensitive   = true
  value       = azurerm_static_web_app.terminal.api_key
}
