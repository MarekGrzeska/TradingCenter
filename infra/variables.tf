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
    The operator's own outbound IP, admitted to the database firewall for the
    operator-run tools that reach production directly: alembic migrations against
    market_data and DBeaver (docs/dbeaver-azure-connection.html). Local development
    does not use it — that runs on the compose.yaml container
    (openspec/changes/local-dev-database-in-docker). Changes when the ISP reassigns
    an address.
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

variable "agent_models" {
  description = <<-EOT
    The agent's model catalogue, one entry per model — the Terraform half of design.md's
    "Katalog modeli jest konfiguracją, nie kodem". This root does not *create* anything
    from it: the models belong to OpenAI's own account, reached with an API key
    (design.md, "Wobec OpenAI: klucz, i tylko klucz"), so there is no deployment
    resource to declare and no capacity to reserve. All this variable does is build the
    agent's MODELS app setting (app-service.tf) — a fourth model is one more entry here
    and a restart, exactly as `modules/agent/.env.example` describes for local runs.

    Map key is this module's own stable id (`agent/models_catalogue.py`), carried in
    every session and usage row. `model` is what OpenAI is actually asked for, kept
    separate because the two need not match — an id outlives a model renamed upstream.

    `model` MUST name something OpenAI serves to this key — nothing here verifies it,
    and a name from memory fails at the first turn, not at `apply`. Operator confirms
    against `GET https://api.openai.com/v1/models` before deploying.

    Rates move faster than this module does (design.md, "Cennik jest konfiguracją") —
    the defaults below are illustrative, read from public pricing in August 2026; check
    OpenAI's own pricing page before trusting them at deploy time, the same caution
    `modules/agent/.env.example` carries.
  EOT
  type = map(object({
    model              = string
    display_name       = string
    cost_rank          = number
    input_rate_per_1k  = string
    output_rate_per_1k = string
  }))
  default = {
    "gpt-5.6-luna" = {
      model              = "gpt-5.6-luna"
      display_name       = "Luna"
      cost_rank          = 1
      input_rate_per_1k  = "0.0002"
      output_rate_per_1k = "0.0012"
    }
    "gpt-5.6-terra" = {
      model              = "gpt-5.6-terra"
      display_name       = "Terra"
      cost_rank          = 2
      input_rate_per_1k  = "0.002"
      output_rate_per_1k = "0.012"
    }
    "gpt-5.6-sol" = {
      model              = "gpt-5.6-sol"
      display_name       = "Sol"
      cost_rank          = 3
      input_rate_per_1k  = "0.005"
      output_rate_per_1k = "0.03"
    }
  }
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
