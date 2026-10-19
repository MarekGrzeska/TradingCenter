variable "display_name" {
  description = "The registration's name in Entra — `app-tradingcenter-<module>-easyauth` for all six."
  type        = string
}

variable "identifier_uri" {
  description = <<-EOT
    The static `api://…` audience. Static rather than `api://<client-id>` because the client
    id is computed by the application resource itself, and a resource cannot refer to itself.
  EOT
  type        = string
}

variable "scope" {
  description = <<-EOT
    The one delegated scope this API exposes, or null for the three registrations that expose
    none. Those three are reached by a backend service with a managed identity and
    client-credentials, so there is no consent screen and nothing to consent to.

    `type = "User"` in every case that has one: the operator reaching their own data through
    their own terminal is exactly what user consent is for, and it needs no administrator.
  EOT
  type = object({
    value                      = string
    admin_consent_display_name = string
    admin_consent_description  = string
    user_consent_display_name  = string
    user_consent_description   = string
  })
  default = null
}


variable "app_roles" {
  description = <<-EOT
    Roles a signed-in person can be given on this API, keyed by the value that appears in the token's `roles` claim.
    Assigned to users (`azuread_app_role_assignment`, or Microsoft Graph from the terminal's Users tab), never to applications.
  EOT
  type = map(object({
    display_name = string
    description  = string
  }))
  default = {}
}
