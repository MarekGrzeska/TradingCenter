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

variable "azure_openai_api_version" {
  description = <<-EOT
    Azure OpenAI's own REST API version, e.g. "2024-10-21" — not a model version.
    No default on purpose, same reasoning as `modules/agent/.env.example`: check the
    current value in Azure OpenAI's REST reference before setting this in
    terraform.tfvars. A guessed date answers 400 for a reason nothing here explains.
  EOT
  type        = string
}

variable "agent_models" {
  description = <<-EOT
    The agent's model catalogue and its Azure OpenAI deployments, one entry per model
    — the Terraform half of design.md's "Katalog modeli jest konfiguracją, nie kodem".
    Map key is this module's own stable id (`agent/models_catalogue.py`), reused
    verbatim as the Azure OpenAI deployment name and as MODELS' `id`/`deployment`
    (app-service.tf) — a fourth model is one more entry here, not a change in two
    places.

    `model_name`/`model_version` MUST name a real entry in the Cognitive Services
    model catalog — Terraform does not verify this. Operator checks
    `az cognitiveservices account list-models --location <var.location>` before
    `apply`; a version pinned from memory plans clean and the deployment then answers
    400 with nothing about why (design.md's Risk, "Wersja modelu w Terraformie nie
    jest potwierdzona").

    Rates move faster than this module does (design.md, "Cennik jest konfiguracją") —
    the defaults below are illustrative, read from public pricing in August 2026;
    check the Azure OpenAI resource's own pricing page before trusting them at deploy
    time, the same caution `modules/agent/.env.example` carries.
  EOT
  type = map(object({
    model_name         = string
    model_version      = string
    capacity           = number
    display_name       = string
    cost_rank          = number
    input_rate_per_1k  = string
    output_rate_per_1k = string
  }))
  default = {
    "gpt-5.6-luna" = {
      model_name         = "gpt-5.6-luna"
      model_version      = "1"
      capacity           = 10
      display_name       = "Luna"
      cost_rank          = 1
      input_rate_per_1k  = "0.0002"
      output_rate_per_1k = "0.0012"
    }
    "gpt-5.6-terra" = {
      model_name         = "gpt-5.6-terra"
      model_version      = "1"
      capacity           = 10
      display_name       = "Terra"
      cost_rank          = 2
      input_rate_per_1k  = "0.002"
      output_rate_per_1k = "0.012"
    }
    "gpt-5.6-sol" = {
      model_name         = "gpt-5.6-sol"
      model_version      = "1"
      capacity           = 10
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
