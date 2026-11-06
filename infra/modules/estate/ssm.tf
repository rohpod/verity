# The manifests link a function to a system when it has no ai:system-id tag. Standard tier is free.
resource "aws_ssm_parameter" "manifest" {
  for_each = fileset(var.manifests_dir, "*.yaml")
  name     = "/verity/manifests/${each.key}"
  type     = "String"
  tier     = "Standard"
  value    = file("${var.manifests_dir}/${each.key}")
}
