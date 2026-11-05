# Verity's AWS baseline (ADR 0015). State is local and git-ignored (ADR 0002).
# IAM identities are not managed here: see docs/runbooks/m3-account-baseline.md.

provider "aws" {
  region              = "eu-north-1" # the only region Verity uses (ADR 0011)
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = {
      project    = "verity"
      managed_by = "opentofu"
    }
  }
}

module "table" {
  source = "./modules/table"
}

module "guardrails" {
  source       = "./modules/guardrails"
  budget_email = var.budget_email
}
