# Federated identity for GitHub Actions (design.md, "Wdrożenia przez OIDC"): no Azure secret lives in the repository or
# in GitHub Secrets at all — GitHub's OIDC token exchanges for an Azure AD one at run time, so there is nothing to leak.
resource "azuread_application" "github_actions" {
  display_name = "app-tradingcenter-github-actions"
}

resource "azuread_service_principal" "github_actions" {
  client_id = azuread_application.github_actions.client_id
}

locals {
  github_repo = "MarekGrzeska/TradingCenter"

  # The same repository, spelled the way GitHub's OIDC token now spells it — owner and repository as immutable numeric
  # ids, refused by Entra as AADSTS700213 against a name-based credential. Read from the live setting, never typed.
  github_repo_immutable = "MarekGrzeska@48219464/TradingCenter@1326647472"
}

# One credential per subject GitHub actually presents rather than a wildcard. The trap is the middle one: a job
# declaring `environment: production` is issued that subject *instead of* the ref, so `main_branch` matched no deploy.
resource "azuread_application_federated_identity_credential" "main_branch" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-main-branch"
  description    = "Pushes to main from a job with no environment — currently none"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo}:ref:refs/heads/main"
}

resource "azuread_application_federated_identity_credential" "production_environment" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-production-environment"
  description    = "Every App Service deploy — one reusable workflow, running in the production environment"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo}:environment:production"
}

resource "azuread_application_federated_identity_credential" "pull_request" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-pull-request"
  description    = "Pull requests — terraform plan only, never apply or deploy"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo}:pull_request"
}

# The same three subjects in the immutable-id form. Both forms are registered deliberately: a credential only ever
# *matches*, so an extra one costs nothing, and CI is not at the mercy of when GitHub's migration lands here.
resource "azuread_application_federated_identity_credential" "main_branch_immutable" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-main-branch-immutable"
  description    = "Pushes to main from a job with no environment, immutable-id subject"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo_immutable}:ref:refs/heads/main"
}

resource "azuread_application_federated_identity_credential" "production_environment_immutable" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-production-environment-immutable"
  description    = "Every App Service deploy, immutable-id subject — this is the one they present"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo_immutable}:environment:production"
}

resource "azuread_application_federated_identity_credential" "pull_request_immutable" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-pull-request-immutable"
  description    = "Pull requests, immutable-id subject — terraform plan only"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo_immutable}:pull_request"
}

# Contributor on the resource group this root manages — everything CI ever needs to
# create, update or (via `terraform plan`) merely read.
resource "azurerm_role_assignment" "github_actions_contributor" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.github_actions.object_id
}

# The state backend lives in another resource group and is only referred to here. Composed as a string rather than read
# with a data source: that is a management-plane GET, and CI's grant is data-plane only, so the lookup 403'd every plan.
locals {
  tfstate_resource_group_id = join("", [
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}",
    "/resourceGroups/rg-tradingcenter-tfstate",
  ])
  tfstate_storage_account_id = join("", [
    local.tfstate_resource_group_id,
    "/providers/Microsoft.Storage/storageAccounts/sttradingcenterstate",
  ])
}

# `Reader` on the state resource group, so CI's plan can refresh the two role assignments below — its own grant there is
# data-plane only. Moving them into `bootstrap/` does not work: that root runs before this one exists.
resource "azurerm_role_assignment" "github_actions_tfstate_reader" {
  scope                = local.tfstate_resource_group_id
  role_definition_name = "Reader"
  principal_id         = azuread_service_principal.github_actions.object_id
}

resource "azurerm_role_assignment" "github_actions_tfstate" {
  scope                = local.tfstate_storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.github_actions.object_id
}

# `Owner` at the subscription does not imply Storage's data-plane RBAC. Applied while the backend still used the access
# key, so switching to `use_azuread_auth` cannot lock the operator out — and from `var.operator_object_id`, or CI would.
resource "azurerm_role_assignment" "operator_tfstate" {
  scope                = local.tfstate_storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.operator_object_id
}

# Read-only directory access, and only because `terraform plan` needs it: every plan in CI failed with
# `Authorization_RequestDenied` before this grant. `Application.Read.All` deliberately, since CI plans and never applies.
data "azuread_service_principal" "msgraph" {
  client_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph, the same everywhere
}

resource "azuread_app_role_assignment" "github_actions_directory_read" {
  app_role_id         = data.azuread_service_principal.msgraph.app_role_ids["Application.Read.All"]
  principal_object_id = azuread_service_principal.github_actions.object_id
  resource_object_id  = data.azuread_service_principal.msgraph.object_id
}

output "github_actions_client_id" {
  value = azuread_application.github_actions.client_id
}
