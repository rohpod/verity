variable "account_id" {
  description = "The only AWS account this may touch. Kept out of the repo: set it in terraform.tfvars."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be 12 digits."
  }
}

variable "budget_email" {
  description = "Where budget alerts go. Kept out of the repo: set it in terraform.tfvars."
  type        = string
  sensitive   = true
}

variable "schedule_state" {
  description = "ENABLED only after a manual crawl and a second one have passed (ADR 0025)."
  type        = string
  default     = "DISABLED"
}

variable "enable_probe" {
  description = "Creates verity-probe while the LeadingKeys limit is proved, then false again."
  type        = bool
  default     = false
}
