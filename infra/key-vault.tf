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
#   az keyvault secret set --vault-name <output.key_vault_name> --name openai-api-key       --value ...
#   az keyvault secret set --vault-name <output.key_vault_name> --name teams-openai-api-key --value ...
# (the same gateway-api-key value three apps read — capital-gateway checks it, market-data
# and trading-mcp present it, exactly like GATEWAY_API_KEY in their .env.example files
# today. trading-mcp joined on `add-trading-mcp`, and this line said "both apps" until
# 18 August 2026)
locals {
  key_vault_secret_names = {
    capital_api_key    = "capital-api-key"
    capital_identifier = "capital-identifier"
    capital_password   = "capital-password"
    gateway_api_key    = "gateway-api-key"

    # The conversation's OpenAI key — the value `modules/workbench/.env` carries locally as
    # AGENT_OPENAI_API_KEY.
    # Unlike the database, which the app reaches with its managed identity, OpenAI has
    # no Entra to present one to: an API key is the only credential it accepts, so this
    # is the one place it can live without ending up in Terraform state or a deploy log
    # (design.md, "Wobec OpenAI: klucz, i tylko klucz").
    openai_api_key = "openai-api-key"

    # The teams surface's key — a second secret rather than a second reader of
    # `openai-api-key`, and the reason is the bill, not the security. A team spends across
    # several agents per run; on one key the experiments and the operator's chat arrive on
    # OpenAI's usage page as one number and neither can be judged. **They are one process
    # since `agent-and-teams-one-workbench` and still two keys**, because the split was
    # always about the invoice: two clients in one process buy the same thing
    # (`modules/workbench/.env.example`, TEAMS_OPENAI_API_KEY).
    teams_openai_api_key = "teams-openai-api-key"

    # A GitHub personal access token with `read:packages`, and nothing else — the only
    # way App Service can pull from GHCR, which is private because the repository is.
    # Both App Service apps reference it as DOCKER_REGISTRY_SERVER_PASSWORD.
    #
    # This is the one credential in the platform that expires on a calendar rather than
    # on demand: it is a GitHub token, so neither managed identity nor Key Vault rotation
    # applies. docs/rotacja-poswiadczen.html is where the renewal is written down.
    ghcr_pull_token = "ghcr-pull-token"
  }
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}
