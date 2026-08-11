# Azure OpenAI — the agent's only model provider (design.md, "Osobny moduł
# `modules/agent`, port 8030"). `azurerm_cognitive_account` (kind "OpenAI") is the
# resource a deployment attaches to; one `azurerm_cognitive_deployment` per entry in
# `var.agent_models`, which is also what `agent`'s own MODELS app setting is built
# from (app-service.tf) — one variable, not a list kept in sync by hand in two files.
#
# Before the first `apply`: check the subscription type and its Azure OpenAI quota
# (tasks.md 10.0). A Free Trial subscription carries zero quota for every model in this
# service regardless of remaining credit, so `azurerm_cognitive_deployment` below has
# nothing to provision against and fails opaquely on quota rather than explaining the
# subscription type (design.md's Risk, "Subskrypcja Free Trial ma zerową quotę").
# Pay-As-You-Go is the prerequisite; Terraform cannot check it for itself.
resource "azurerm_cognitive_account" "openai" {
  name                = "oai-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  kind                = "OpenAI"
  sku_name            = "S0"

  # Required for an OpenAI-kind account — without a custom subdomain the account has
  # no per-resource endpoint to hand `agent`'s AZURE_OPENAI_ENDPOINT below.
  custom_subdomain_name = "oai-tradingcenter"

  identity {
    type = "SystemAssigned"
  }
}

# Global Standard, not Standard: pay-as-you-go per token with no reserved capacity
# provisioned ahead of traffic, matching a module whose whole point is not knowing yet
# how many turns an operator will run (design.md's Risks, "Rachunek rośnie bez
# hamulca" — the cost tab is visibility, not a limit).
resource "azurerm_cognitive_deployment" "agent_models" {
  for_each = var.agent_models

  name                 = each.key
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = each.value.model_name
    version = each.value.model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = each.value.capacity
  }
}

# design.md, "Wobec Azure OpenAI: tożsamość zarządzana, lokalnie klucz" — no key to
# rotate, leak or hold in Key Vault in production. `Cognitive Services OpenAI User` is
# the read/invoke role, deliberately not `Contributor`: the app calls deployments, it
# does not manage the account.
resource "azurerm_role_assignment" "agent_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_linux_web_app.agent.identity[0].principal_id
}

output "openai_account_name" {
  value = azurerm_cognitive_account.openai.name
}

output "openai_endpoint" {
  value = azurerm_cognitive_account.openai.endpoint
}
