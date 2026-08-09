variable "location" {
  description = "Azure region. Poland Central — see docs/azure-infrastructure-proposal.html for why."
  type        = string
  default     = "polandcentral"
}

variable "postgres_version" {
  description = "17, not 18 — TimescaleDB and tooling lag a new major by a release or two."
  type        = string
  default     = "17"
}

variable "developer_ip_address" {
  description = <<-EOT
    The developer's own outbound IP, admitted to the database firewall so local
    development can reach Azure directly instead of a container (design.md,
    "Praca lokalna korzysta z market_data_dev na serwerze w Azure"). Changes when the
    operator's ISP reassigns an address — see docs/dbeaver-azure-connection.html for
    how to notice and fix that.
  EOT
  type        = string
}

variable "postgres_admin_object_id" {
  description = "Entra object id of the human administrator for the Postgres server."
  type        = string
}

variable "postgres_admin_upn" {
  description = "Entra user principal name of the human administrator for the Postgres server."
  type        = string
}

variable "operator_email" {
  description = "Where the monitoring alerts (infra/monitoring.tf) go — a single-operator project, so a person, not a distribution list."
  type        = string
}

variable "operator_object_id" {
  description = <<-EOT
    Entra object id of the human operator — the one who writes Key Vault secret values
    by hand and owns the state container's data-plane access.

    Named explicitly rather than read from `data.azurerm_client_config.current`, which
    resolves to whoever is running Terraform: the operator locally, but the CI service
    principal in GitHub Actions. That difference silently rewrote the operator's own
    Key Vault access policy to point at CI — `terraform plan` in CI planned to destroy
    and recreate it with CI's object id, which would have locked the operator out of the
    vault they are the only one who writes to.

    Today this is the same person as `postgres_admin_object_id`; they are kept apart
    because "administers the database server" and "writes secrets into the vault" are
    different jobs that a second person could one day hold.
  EOT
  type        = string
}
