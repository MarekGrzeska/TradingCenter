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
# Administrator (tasks.md's Migration Plan step 3; `agent_managed_identity_principal_id`
# in app-service.tf is the object id that step grants).
resource "azurerm_postgresql_flexible_server_database" "agent" {
  name      = "agent"
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
# -target=azurerm_linux_web_app.agent` once, then the normal unrestricted apply.
resource "azurerm_postgresql_flexible_server_firewall_rule" "agent_outbound" {
  for_each = toset(azurerm_linux_web_app.agent.possible_outbound_ip_address_list)

  name             = "AllowAgentOutbound-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}
