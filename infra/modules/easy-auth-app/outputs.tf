output "client_id" {
  description = "The audience and the Easy Auth client id."
  value       = azuread_application.this.client_id
}

output "application_id" {
  description = "The resource id (`/applications/<uuid>`), which pre-authorization and the password both take."
  value       = azuread_application.this.id
}

output "password" {
  description = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET for this app."
  value       = azuread_application_password.this.value
  sensitive   = true
}

output "scope_id" {
  description = "The delegated scope's stable GUID, or null where there is no scope."
  value       = var.scope == null ? null : random_uuid.scope[0].result
}
