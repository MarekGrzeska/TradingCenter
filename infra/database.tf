# PostgreSQL Flexible Server — one instance, several logical databases, roles with disjoint access (design.md, "Jeden
# serwer, dwie bazy logiczne, trzy tożsamości"). Password auth is off: every caller presents an Entra token instead.

data "azurerm_client_config" "current" {}

resource "azurerm_postgresql_flexible_server" "main" {
  name                = "psql-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  version             = var.postgres_version

  # Covered by the free-tier grant for the first 12 months, and that grant is 750 hours of *one* B1ms — which is
  # exactly why there is one server for every database rather than one each.
  sku_name   = "B_Standard_B1ms"
  storage_mb = 32768

  backup_retention_days = 7
  # Pinned to what Azure assigned on creation: left unset, the provider reads it back as drift and wants to null it
  # out, which is not worth risking on a live database for a value nobody chose.
  zone = "2"

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  lifecycle {
    # The provider wants an administrator_login/password pair even though this server has password auth off —
    # ignoring the drift beats fighting the provider every plan.
    ignore_changes = [administrator_login, administrator_password]
  }
}

# The one exception a Flexible Server allows for TLS is per-connection opt-out, and setting this ON removes it: the
# module must not be able to weaken this from its own side (specs/market-data-database-connection).
resource "azurerm_postgresql_flexible_server_configuration" "require_tls" {
  name      = "require_secure_transport"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "ON"
}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "human" {
  server_name         = azurerm_postgresql_flexible_server.main.name
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = var.postgres_admin_object_id
  principal_name      = var.postgres_admin_upn
  principal_type      = "User"
}

resource "azurerm_postgresql_flexible_server_database" "prod" {
  name      = "market_data"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# A second logical database on the same server, not a second server — the free grant is 750 hours of *one* B1ms. Its
# Entra role is not created here: like every other, it is a one-off `psql` step against the AD Administrator.
resource "azurerm_postgresql_flexible_server_database" "agent" {
  name      = "agent"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# A third, same server and same reason: a module owning its own *schema* is the rule, not its own server. **The identity
# is the same one `agent` takes** since the two became one process, so this database needs that role created in it too.
resource "azurerm_postgresql_flexible_server_database" "teams" {
  name      = "teams"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# A fourth, same reason once more. Its role is the one-off `scripts/grant-schema-ownership.sql` step; without it the
# module starts, tries to migrate and stops, which is the intended failure rather than a quiet one.
resource "azurerm_postgresql_flexible_server_database" "polymarket" {
  name      = "polymarket"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# A fifth, and the reasoning has still not changed. It needs the same one-off grant run in it before the first deploy
# migrates, or the module starts and refuses on a table it cannot alter.
resource "azurerm_postgresql_flexible_server_database" "strategy" {
  name      = "strategy"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# `market_data_dev` used to sit beside it, for the one morning that arrangement lasted. Applying its removal DROPS it:
# dev data is disposable, but the operator should know that is what the plan's `destroy` means.

# The App Service plan's own outbound addresses join this rule once the plan exists — read off the resource rather than
# typed, because they change with the SKU. Only the developer's address is known up front.
resource "azurerm_postgresql_flexible_server_firewall_rule" "developer" {
  name             = "AllowDeveloper"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = var.developer_ip_address
  end_ip_address   = var.developer_ip_address
}

# One rule per address, read straight off the app's own resource, so a plan-tier change is never a manual firewall edit.
# First convergence needs two applies: a resource-level `for_each` refuses to plan against "known after apply".
resource "azurerm_postgresql_flexible_server_firewall_rule" "market_data_outbound" {
  for_each = toset(azurerm_linux_web_app.market_data.possible_outbound_ip_address_list)

  name             = "AllowMarketDataOutbound-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}

# Same two-apply shape as the rule above. One rule set where there were two: the workbench reaches both databases from
# one app's addresses, and the second set only ever duplicated the first under another name.
resource "azurerm_postgresql_flexible_server_firewall_rule" "workbench_outbound" {
  for_each = toset(azurerm_linux_web_app.workbench.possible_outbound_ip_address_list)

  name             = "AllowAgentOutbound-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}

# The third of the same shape and the same two-apply first convergence. The addresses are the plan's, so this overlaps
# the two above entirely — written out anyway, because a rule named after its app survives that app being removed.
resource "azurerm_postgresql_flexible_server_firewall_rule" "polymarket_data_outbound" {
  for_each = toset(azurerm_linux_web_app.polymarket_data.possible_outbound_ip_address_list)

  name             = "AllowPolymarketDataOutbound-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}

# The fourth, and the last thing to say about the shape is that it repeats: `terraform apply
# -target=azurerm_linux_web_app.strategy` once, then the normal unrestricted apply.
resource "azurerm_postgresql_flexible_server_firewall_rule" "strategy_outbound" {
  for_each = toset(azurerm_linux_web_app.strategy.possible_outbound_ip_address_list)

  name             = "AllowStrategyOutbound-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}
