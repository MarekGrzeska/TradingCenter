# Federated identity for GitHub Actions — design.md, "Wdrożenia przez OIDC, obrazy w
# GHCR": no Azure secret lives in the repository or in GitHub Secrets at all. GitHub's
# OIDC token exchanges for an Azure AD token at workflow run time; there is nothing
# stored to leak.
resource "azuread_application" "github_actions" {
  display_name = "app-tradingcenter-github-actions"
}

resource "azuread_service_principal" "github_actions" {
  client_id = azuread_application.github_actions.client_id
}

locals {
  github_repo = "MarekGrzeska/TradingCenter"

  # The same repository, spelled the way GitHub's OIDC token now spells it: owner and
  # repository carry their immutable numeric ids. GitHub is migrating every subject claim
  # to this form, and this repository is already on it — a token minted here presents
  # `repo:MarekGrzeska@48219464/TradingCenter@1326647472:...`, which matches none of the
  # name-based credentials below and is refused by Entra with AADSTS700213.
  #
  # Read from the live setting, never typed from memory:
  #   gh api repos/MarekGrzeska/TradingCenter/actions/oidc/customization/sub
  # The ids are stable — they survive a rename of either the account or the repository,
  # which is the whole point of the change.
  github_repo_immutable = "MarekGrzeska@48219464/TradingCenter@1326647472"
}

# One credential per subject GitHub actually presents: pushes to `main` run the deploy
# and `terraform apply` workflows, pull requests run `terraform plan`. Scoping to these
# two subjects (rather than a wildcard `repo:owner/repo:*`) means a token minted for any
# other ref — a random branch, a fork's PR — is simply refused by Entra before it ever
# reaches Azure.
resource "azuread_application_federated_identity_credential" "main_branch" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-main-branch"
  description    = "Pushes to main — deploy workflows and terraform apply"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo}:ref:refs/heads/main"
}

resource "azuread_application_federated_identity_credential" "pull_request" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-pull-request"
  description    = "Pull requests — terraform plan only, never apply or deploy"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo}:pull_request"
}

# The same two subjects again, in the immutable-id form GitHub actually presents today.
# Both forms are registered deliberately: a federated credential only ever *matches* the
# subject in the token, so an extra one that matches nothing costs nothing and refuses
# nothing (Entra allows 20 per application). Keeping the name-based pair means CI is not
# at the mercy of exactly when GitHub's migration lands on this repository, in either
# direction.
#
# Once the rollout has settled and every run presents the id form, the two name-based
# credentials above are dead weight and can be deleted — the scoping argument for them
# carries over unchanged to these two.
resource "azuread_application_federated_identity_credential" "main_branch_immutable" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-main-branch-immutable"
  description    = "Pushes to main, immutable-id subject — deploy workflows and terraform apply"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_repo_immutable}:ref:refs/heads/main"
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

# The state backend lives in a different resource group (infra/bootstrap/, group 3) and
# is not managed by this root — looked up, not created, so `terraform plan` in CI can
# read/write state without an access key (backend `use_azuread_auth`, main.tf).
data "azurerm_storage_account" "tfstate" {
  name                = "sttradingcenterstate"
  resource_group_name = "rg-tradingcenter-tfstate"
}

resource "azurerm_role_assignment" "github_actions_tfstate" {
  scope                = data.azurerm_storage_account.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.github_actions.object_id
}

# `Owner` at the subscription (what the operator has) does not imply Storage's own
# data-plane RBAC — blob read/write needs this explicit grant regardless. Applied here,
# with the backend still on the storage account's access key (main.tf), specifically so
# that switching the backend to `use_azuread_auth = true` afterward doesn't lock the
# operator's own `terraform` out of the state it just wrote this role assignment into.
resource "azurerm_role_assignment" "operator_tfstate" {
  scope                = data.azurerm_storage_account.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

output "github_actions_client_id" {
  value = azuread_application.github_actions.client_id
}
