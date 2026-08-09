terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Created once by infra/bootstrap/ — see that root for why this cannot bootstrap
  # itself. Values match its `backend_config` output exactly.
  #
  # `use_azuread_auth` reads/writes the state blob with an Azure AD token instead of the
  # storage account's access key — the local developer's own `az login` token locally,
  # the GitHub Actions OIDC token in CI (github-oidc.tf grants that identity, and the
  # operator, Storage Blob Data Contributor on this account). No storage key is ever
  # handled by either. Flipped on only after that role assignment exists — see
  # github-oidc.tf's comment on `operator_tfstate` for the bootstrapping order.
  backend "azurerm" {
    resource_group_name  = "rg-tradingcenter-tfstate"
    storage_account_name = "sttradingcenterstate"
    container_name       = "tfstate"
    key                  = "tradingcenter.tfstate"
    use_azuread_auth     = true
  }
}

# `use_oidc` and the client/tenant/subscription ids are deliberately absent here: they
# come from the `ARM_USE_OIDC`/`ARM_CLIENT_ID`/`ARM_TENANT_ID`/`ARM_SUBSCRIPTION_ID`
# environment variables, which the provider reads on its own. Locally none of those are
# set, so the provider falls back to the ambient `az login` session; the Terraform
# workflow (group 7) sets them from repository *vars* (never secrets — design.md) so the
# same code authenticates through the federated credential in github-oidc.tf instead.
# Hardcoding `use_oidc = true` here would break every local `terraform` run.
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

provider "azuread" {}

resource "azurerm_resource_group" "main" {
  name     = "rg-tradingcenter"
  location = var.location

  tags = {
    project = "tradingcenter"
  }
}
