# Created here, with 3-day retention, and the roles get no logs:CreateLogGroup, so a group can
# never appear without its retention (ADR 0025, decision 7). verity-probe has no group: it runs on
# support-assistant-role, which may only write to that function's own group.
resource "aws_cloudwatch_log_group" "function" {
  for_each          = local.role_names
  name              = "/aws/lambda/${each.key}"
  retention_in_days = 3
}
