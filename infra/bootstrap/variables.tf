variable "location" {
  description = "Azure region. Poland Central — see docs/azure-infrastructure-proposal.html for why."
  type        = string
  default     = "polandcentral"
}

variable "storage_account_name" {
  description = "Globally unique. Lowercase letters and numbers only, 3-24 characters."
  type        = string
  default     = "sttradingcenterstate"
}
