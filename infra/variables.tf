# Since move-from-azure-to-vps this root holds the Entra registrations and CI's access to its own state, nothing else.

variable "operator_object_id" {
  description = <<-EOT
    Entra object id of the human operator, who owns the state container's data-plane access.

    Named explicitly rather than read from `data.azurerm_client_config.current`, which resolves to whoever is running
    Terraform: the operator locally, but the CI service principal in GitHub Actions — and a plan in CI would then move the
    operator's grant onto CI.
  EOT
  type        = string
}

# Where the terminal and the pocket are served (openspec/changes/move-from-azure-to-vps). Each is an origin, no trailing
# slash: the registrations add it. Defaults are the names the server answers on today — sslip.io resolves them to its
# address, which Let's Encrypt accepts — and the day a domain exists they change here and the registrations follow. Entra
# needs HTTPS on a name, so an address would not do.
variable "vps_terminal_origins" {
  description = "Origins the terminal is served from; its redirect URIs."
  type        = list(string)
  default     = ["https://terminal.57-129-181-251.sslip.io"]
}

variable "vps_pocket_origins" {
  description = "Origins the pocket is served from; its redirect URIs."
  type        = list(string)
  default     = ["https://pocket.57-129-181-251.sslip.io"]
}
