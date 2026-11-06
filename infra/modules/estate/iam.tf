# Lambda roles are managed here. ADR 0015's rule that IAM identities stay outside OpenTofu
# applies to people, not to function roles (ADR 0025, decision 6).

# Caps what any function role can ever do, whatever a later edit to its policy grants
# (ADR 0025, decision 7). It allows everything and denies model invocation.
resource "aws_iam_policy" "boundary" {
  name        = "verity-function-boundary"
  description = "Permissions boundary for Verity function roles: no model invocation"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "AllowWithinTheRole", Effect = "Allow", Action = "*", Resource = "*" },
      { Sid = "NeverInvokeAModel", Effect = "Deny", Action = local.boundary_deny, Resource = "*" },
    ]
  })
}

resource "aws_iam_role" "function" {
  for_each             = local.role_names
  name                 = "${each.key}-role"
  permissions_boundary = aws_iam_policy.boundary.arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "inline" {
  for_each = local.inline_policies
  name     = element(split("/", each.key), 1)
  role     = aws_iam_role.function[each.value.function].name

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = each.value.statements
  })
}
