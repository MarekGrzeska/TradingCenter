output "resource_group_name" {
  value = azurerm_resource_group.tfstate.name
}

output "storage_account_name" {
  value = azurerm_storage_account.tfstate.name
}

output "container_name" {
  value = azurerm_storage_container.tfstate.name
}

# Not committed as an .auto.tfvars because it is generated, not decided — a value the
# main infra root's backend config reads from this output, not from a human choosing it.
output "backend_config" {
  description = "Paste into infra/main.tf's backend block, or feed to `terraform init -backend-config`."
  value = {
    resource_group_name  = azurerm_resource_group.tfstate.name
    storage_account_name = azurerm_storage_account.tfstate.name
    container_name       = azurerm_storage_container.tfstate.name
    key                  = "tradingcenter.tfstate"
  }
}
