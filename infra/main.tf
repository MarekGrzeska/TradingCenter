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
  }

  # Created once by infra/bootstrap/ — see that root for why this cannot bootstrap
  # itself. Values match its `backend_config` output exactly.
  backend "azurerm" {
    resource_group_name  = "rg-tradingcenter-tfstate"
    storage_account_name = "sttradingcenterstate"
    container_name       = "tfstate"
    key                  = "tradingcenter.tfstate"
  }
}

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
