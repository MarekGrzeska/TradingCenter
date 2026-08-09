output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "postgres_server_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_server_name" {
  value = azurerm_postgresql_flexible_server.main.name
}
