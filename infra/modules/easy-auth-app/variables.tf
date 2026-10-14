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

