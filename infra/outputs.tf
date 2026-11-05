# No ARNs here: they contain the account ID.
output "table_name" {
  value = module.table.name
}

output "budget_name" {
  value = module.guardrails.budget_name
}
