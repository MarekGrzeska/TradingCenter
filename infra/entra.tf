# A non-admin Entra identity for the local `market-data` process.
#
# The Postgres server's Active Directory Administrator (database.tf,
# `postgres_admin_object_id` — the human operator) bypasses every GRANT on every
# database on the server; that is what "administrator" means in Flexible Server. So the
# admin account cannot also be the "dev" identity the local process authenticates with —
# doing that would make the dev/prod database split cosmetic, since the admin's token
# reaches `market_data` regardless of what `market_data_dev`'s role is granted.
#
# This app registration is that separate identity. It is not a person: the developer
# still uses their own Entra account for the portal, Terraform and DBeaver — see
# docs/dbeaver-azure-connection.html — and reserves it for exactly that, never for what
# the automated process reads from `.env`.
resource "azuread_application" "market_data_dev" {
  display_name = "sp-tradingcenter-market-data-dev"
}

resource "azuread_service_principal" "market_data_dev" {
  client_id = azuread_application.market_data_dev.client_id
}

resource "azuread_application_password" "market_data_dev" {
  application_id = azuread_application.market_data_dev.id
  display_name   = "local-market-data-dev"
  # A year, not "never" — a secret with no expiry is a secret nobody ever rotates.
  end_date = timeadd(timestamp(), "8760h")

  lifecycle {
    # Otherwise every plan wants to rotate it, because timestamp() is never the same
    # value twice.
    ignore_changes = [end_date]
  }
}

output "market_data_dev_client_id" {
  value = azuread_application.market_data_dev.client_id
}

output "market_data_dev_object_id" {
  description = "The service principal's object id — what Postgres role creation needs, not the application's own object id."
  value       = azuread_service_principal.market_data_dev.object_id
}

output "market_data_dev_client_secret" {
  sensitive = true
  value     = azuread_application_password.market_data_dev.value
}
