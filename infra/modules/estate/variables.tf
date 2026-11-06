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
