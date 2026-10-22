output "client_id" {
  description = "The audience and the Easy Auth client id."
  value       = azuread_application.this.client_id
}

output "application_id" {
  description = "The resource id (`/applications/<uuid>`), which pre-authorization and the password both take."
  value       = azuread_application.this.id
}

output "scope_id" {
  description = "The delegated scope's stable GUID, or null where there is no scope."
  value       = var.scope == null ? null : random_uuid.scope[0].result
}

output "role_ids" {
  description = "App role value -> its stable GUID, for assignments."
  value       = { for key, id in random_uuid.role : key => id.result }
}

output "service_principal_object_id" {
  description = "The service principal's object id: the `resource_object_id` of an app role assignment."
  value       = azuread_service_principal.this.object_id
}
