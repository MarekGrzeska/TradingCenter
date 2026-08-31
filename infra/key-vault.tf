# capital.com credentials and the shared gateway key live here, never in Terraform state (design.md, "Wartość nie
# przechodzi przez kod Terraforma"): this file creates the vault, and values are set out-of-band after apply.

# Key Vault names are globally unique and a soft-deleted vault holds its name, so a plain "kv-tradingcenter" would fail
# to recreate after a destroy. The random suffix, not purge protection, is what design.md accepts as the fix.
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

# The human operator needs full secret access to run `az keyvault secret set` after apply. `var.operator_object_id` and
# not the current client: an apply from CI would hand this policy to the CI principal and take it from the operator.
resource "azurerm_key_vault_access_policy" "operator" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = var.operator_object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
}

# Secret names the app identities are granted Get/List on and that app settings reference by URI. Values are set by hand
# with `az keyvault secret set --vault-name <output.key_vault_name> --name <below> --value ...` after apply.
locals {
  key_vault_secret_names = {
    capital_api_key    = "capital-api-key"
    capital_identifier = "capital-identifier"
    capital_password   = "capital-password"
    gateway_api_key    = "gateway-api-key"

    # The conversation's OpenAI key. Unlike the database, which the app reaches with its managed identity, OpenAI has
    # no Entra to present one to — an API key is the only credential it accepts.
    openai_api_key = "openai-api-key"

    # The teams surface's key — a second secret rather than a second reader, and the reason is the bill: on one key the
    # experiments and the operator's chat arrive as one number. **One process since the merge, and still two keys.**
    teams_openai_api_key = "teams-openai-api-key"

    # The operator's own Telegram account, which is the only identity allowed to talk to the bot that creates bots.
    # Three secrets rather than one blob so each is rotated on its own, and the session string is the one that is a
    # standing credential to a personal account — `telegram-gateway`'s own README says what it can and cannot do.
    telegram_api_id   = "telegram-api-id"
    telegram_api_hash = "telegram-api-hash"
    telegram_session  = "telegram-session"

    # A GitHub token with `read:packages`, the only way App Service can pull from GHCR. The one credential here that
    # expires on a calendar rather than on demand; docs/rotacja-poswiadczen.html is where the renewal is written down.
    ghcr_pull_token = "ghcr-pull-token"
  }
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}
