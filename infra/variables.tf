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
