# capital.com credentials and the shared gateway key live here, never in Terraform
# state: design.md, "Do bazy — tożsamość, do capital.com — Key Vault" — "Wartość nie
# przechodzi przez kod Terraforma ani przez logi wdrożenia." This file creates the vault
# and the access grants; the secret *values* are set out-of-band with
# `az keyvault secret set` after apply, and app settings only ever hold a
# `@Microsoft.KeyVault(SecretUri=...)` reference (key-vault-secret names below).

# Key Vault names are globally unique and soft-deleted vaults hold their name for the
# retention window — a plain "kv-tradingcenter" would fail to recreate after a
# `terraform destroy`. The random suffix, not purge protection, is what design.md
# accepts as the fix (purge protection stays off on purpose).
resource "random_string" "key_vault_suffix" {
  length  = 4
  special = false
  upper   = false
  numeric = true
}

resource "azurerm_key_vault" "main" {
  name                = "kv-tradingctr-${random_string.key_vault_suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Soft delete cannot be turned off on a current-generation vault; purge protection is
  # left at its default (off) — see the comment above and design.md's Key Vault risk.
  soft_delete_retention_days = 90
}

# The human operator (mgrzeskait@outlook.com) needs full secret access to run
# `az keyvault secret set` after apply — nothing else in this root writes a secret value
# here.
#
# `var.operator_object_id`, not `data.azurerm_client_config.current.object_id`: the data
# source is whoever is running Terraform, so a `terraform apply` from CI would hand this
# policy to the CI service principal and take it away from the operator. See the
# variable's own description for how that surfaced.
resource "azurerm_key_vault_access_policy" "operator" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = var.operator_object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
}

# Secret names the two app identities are granted "Get"/"List" on (app-service.tf) and
# that app_settings reference by URI. Values, set manually after apply:
#   az keyvault secret set --vault-name <output.key_vault_name> --name capital-api-key      --value ...
#   az keyvault secret set --vault-name <output.key_vault_name> --name capital-identifier   --value ...
#   az keyvault secret set --vault-name <output.key_vault_name> --name capital-password     --value ...
#   az keyvault secret set --vault-name <output.key_vault_name> --name gateway-api-key      --value ...
# (the same gateway-api-key value both apps read — capital-gateway checks it, market-data
# presents it, exactly like GATEWAY_API_KEY in both .env.example files today)
locals {
  key_vault_secret_names = {
    capital_api_key    = "capital-api-key"
    capital_identifier = "capital-identifier"
    capital_password   = "capital-password"
    gateway_api_key    = "gateway-api-key"
  }
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}
