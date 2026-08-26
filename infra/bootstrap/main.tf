terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Local state on purpose — this is the chicken-and-egg exception: it creates the storage account every other root's
  # state lives in, so it cannot itself depend on that account being there (provision-azure-platform, design.md).
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

resource "azurerm_resource_group" "tfstate" {
  name     = "rg-tradingcenter-tfstate"
  location = var.location

  tags = {
    project = "tradingcenter"
    purpose = "terraform-state"
  }
}

resource "azurerm_storage_account" "tfstate" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.tfstate.name
  location                 = azurerm_resource_group.tfstate.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  # Off, on purpose: `azurerm_storage_account` always pulls the account's keys into state, and this root's state is
  # committed. Every caller authenticates with Entra, so disabling shared key auth makes those keys permanently inert.
  shared_access_key_enabled = false

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 30
    }
  }

  tags = {
    project = "tradingcenter"
    purpose = "terraform-state"
  }
}

resource "azurerm_storage_container" "tfstate" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"
}
