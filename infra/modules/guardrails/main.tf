variable "budget_email" {
  type      = string
  sensitive = true
}

# A cost alarm with no actions, which keeps it free. Budgets include credits by default, which
# could hide usage the credits pay for, so they are excluded (ADR 0015).
resource "aws_budgets_budget" "zero_spend" {
  name         = "verity-zero-spend"
  budget_type  = "COST"
  limit_amount = "0.01"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_types {
    include_credit = false
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }
}

output "budget_name" {
  value = aws_budgets_budget.zero_spend.name
}
