terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Local state on purpose — this is the chicken-and-egg exception. It creates the
  # storage account that every other Terraform root's state lives in, so it cannot
  # itself depend on that storage account being there yet.
  #
  # openspec/changes/provision-azure-platform, design.md, "Bootstrap osobnym
  # katalogiem ze stanem lokalnym".
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

  # Off, on purpose: azurerm_storage_account always pulls the account's primary/secondary
  # keys into Terraform state, and this root's state is committed (see .gitignore). Every
  # caller already authenticates with Entra (`use_azuread_auth = true`, infra/main.tf), so
  # the keys have no legitimate use — disabling shared key auth makes them permanently
  # inert instead of live secrets sitting in a checked-in file.
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
