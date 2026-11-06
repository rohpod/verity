variable "account_id" {
  description = "The account these roles and ARNs belong to. Never written out: it comes from terraform.tfvars."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be 12 digits."
  }
}

variable "table_name" {
  description = "The graph table the roles may reach."
  type        = string
}

variable "build_dir" {
  description = "Where scripts/build_lambdas.py wrote the zips."
  type        = string
}

variable "manifests_dir" {
  description = "content/manifests, published to SSM."
  type        = string
}

variable "schedule_state" {
  description = "ENABLED only after a manual crawl and a second one have passed (ADR 0025, decision 8)."
  type        = string
  default     = "DISABLED"

  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.schedule_state)
    error_message = "schedule_state must be ENABLED or DISABLED."
  }
}

variable "enable_probe" {
  description = "Creates verity-probe, which exists only to prove the LeadingKeys limit (ADR 0025, decision 5)."
  type        = bool
  default     = false
}
