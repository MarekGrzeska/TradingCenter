# PostgreSQL Flexible Server — one instance, two logical databases, three roles with
# disjoint access. See openspec/changes/provision-azure-platform/design.md, "Jeden
# serwer, dwie bazy logiczne, trzy tożsamości", for why it is shaped this way rather
# than two servers or one shared role.
#
# Password authentication is off. Every caller — the app's managed identity, the
# developer's own Entra account, an operator's tool — presents an Entra token instead,
# so there is no password anywhere to leak, rotate or find in a file.

data "azurerm_client_config" "current" {}

resource "azurerm_postgresql_flexible_server" "main" {
  name                = "psql-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  version             = var.postgres_version

  # Covered by the free-tier grant for the first 12 months (docs/azure-infrastructure-
  # proposal.html, section 8) — the free limit is 750 hours of *one* B1ms, which is
  # exactly why there is one server for both databases rather than one each.
  sku_name   = "B_Standard_B1ms"
  storage_mb = 32768

  backup_retention_days = 7
  # Pinned to what Azure actually assigned on creation — left unset, the provider
  # reads it back as drift and wants to null it out, which is not a change worth
  # risking on a live database for a value that was never a deliberate choice.
  zone = "2"

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  lifecycle {
    # The provider wants an administrator_login/password pair for password auth even
    # though this server has password auth turned off — ignore drift on that pair
    # rather than fight the provider every plan.
    ignore_changes = [administrator_login, administrator_password]
  }
}

# The one exception a Flexible Server allows for TLS is per-connection opt-out. Setting
# this to ON at the server level removes that opt-out, matching
# specs/market-data-database-connection/spec.md, "Połączenie z bazą jest szyfrowane" —
# the module must not be able to weaken this from its own side.
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

# A second logical database on the same server, not a second server — design.md,
# "Baza: druga baza logiczna, jeden serwer": the free grant is 750 hours of *one*
# B1ms. The Entra role this database's data actually needs is not created here —
# same as `market_data`'s own role, it is a manual `psql` step against the server's AD
# Administrator (`workbench_managed_identity_principal_id` in app-service.tf is the object
# id that step grants).
resource "azurerm_postgresql_flexible_server_database" "agent" {
  name      = "agent"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# A third, same server again and for the same reason — the free grant is 750 hours of one
# B1ms, and a module owning its own *schema* is the rule, not owning its own server
# (specs/teams-database-connection, "Moduł nie dzieli bazy z innym modułem"). The role
# this database's data belongs to is not created here: like `market_data`'s and `agent`'s,
# it is a one-off `psql` step against the server's AD Administrator. **The identity is the
# same one `agent` takes** since the two modules became one process, so this database needs
# that role created in it too — the one operator step
# `agent-and-teams-one-workbench` carries.
resource "azurerm_postgresql_flexible_server_database" "teams" {
  name      = "teams"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# A fourth, same server and the same reason once more. Its role is the one-off `psql` step
# every database here has needed: `scripts/grant-schema-ownership.sql` against the server's
# AD Administrator, with the object id `polymarket_data_managed_identity_principal_id`
# (app-service.tf) names. Without it the module starts, tries to migrate and stops — which
# is the intended failure rather than a quiet one (specs/polymarket-data-store).
resource "azurerm_postgresql_flexible_server_database" "polymarket" {
  name      = "polymarket"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# A fifth, and the reasoning has still not changed: one server, one logical database per
# module that owns data. Its role is the same one-off `psql` step, and this one needs
# `scripts/grant-schema-ownership.sql` run in it as well, before the first deploy tries to
# migrate — or the module starts and refuses on a table it cannot alter.
resource "azurerm_postgresql_flexible_server_database" "strategy" {
  name      = "strategy"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# `market_data_dev` used to sit beside it — the database local development wrote to for
# the one morning that arrangement lasted (openspec/changes/local-dev-database-in-docker).
# Applying its removal DROPS it, data and all; dev data is disposable by definition, but
# the operator should know that is what the plan's `destroy` means.

# The App Service plan's own outbound addresses join this rule once the plan exists —
# app-service.tf reads them off the resource rather than them being typed here, because
# they change with the plan's SKU (design.md, "Firewall na adresy IP, nie prywatny
# endpoint"). Only the developer's address is known up front.
resource "azurerm_postgresql_flexible_server_firewall_rule" "developer" {
  name             = "AllowDeveloper"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = var.developer_ip_address
  end_ip_address   = var.developer_ip_address
}

# market-data is the only app that talks to the database — capital-gateway never
# touches it. One rule per address, read straight off market-data's own resource so a
# future plan-tier change (which reassigns these) is never a manual firewall edit.
#
# First-time convergence needs two applies: `possible_outbound_ip_address_list` is not
# knowable until the web app exists, and a resource-level `for_each` (unlike a `dynamic`
# block's) refuses to plan against a value that is only "known after apply". Run
# `terraform apply -target=azurerm_linux_web_app.market_data` once, then the normal
# unrestricted `terraform apply` — every apply after that converges in one step, because
# the value is already in state.
resource "azurerm_postgresql_flexible_server_firewall_rule" "market_data_outbound" {
  for_each = toset(azurerm_linux_web_app.market_data.possible_outbound_ip_address_list)

  name             = "AllowMarketDataOutbound-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}

# Same two-apply shape as market-data's own rule above: `terraform apply
# -target=azurerm_linux_web_app.workbench` once, then the normal unrestricted apply.
#
# One rule set where there were two. The workbench reaches both the `agent` and the `teams`
# database, and it reaches them from one app's addresses — the second set only ever
# duplicated the first under another name, and it went away with the App Service it was
# read off.
resource "azurerm_postgresql_flexible_server_firewall_rule" "workbench_outbound" {
  for_each = toset(azurerm_linux_web_app.workbench.possible_outbound_ip_address_list)

  name             = "AllowAgentOutbound-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}

# The third of the same shape, and the same two-apply first convergence: `terraform apply
# -target=azurerm_linux_web_app.polymarket_data` once, then the normal unrestricted apply.
# The addresses are the plan's, so this rule set overlaps the two above entirely — written
# out anyway, because a rule named after the app it exists for is what survives an app
# being removed.
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
