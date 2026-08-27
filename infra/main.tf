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

  # Created once by infra/bootstrap/ — see that root for why this cannot bootstrap itself. `use_azuread_auth` reads the
  # state blob with an Entra token instead of the account key, so no storage key is ever handled by either caller.
  backend "azurerm" {
    resource_group_name  = "rg-tradingcenter-tfstate"
    storage_account_name = "sttradingcenterstate"
    container_name       = "tfstate"
    key                  = "tradingcenter.tfstate"
    use_azuread_auth     = true
  }
}

# `use_oidc` and the client/tenant/subscription ids are deliberately absent: the provider reads them from `ARM_*`, which
# the workflow sets and a local run does not. Hardcoding `use_oidc = true` would break every local `terraform`.
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
