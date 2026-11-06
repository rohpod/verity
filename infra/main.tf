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

# The demo estate's resources use this provider, which has no default_tags: shadow-summariser and
# talent-screening are untagged in the fixture and must be untagged live (ADR 0025, decision 6).
provider "aws" {
  alias               = "estate"
  region              = "eu-north-1"
  allowed_account_ids = [var.account_id]
}

module "table" {
  source = "./modules/table"
}

module "guardrails" {
  source       = "./modules/guardrails"
  budget_email = var.budget_email
}

module "estate" {
  source     = "./modules/estate"
  account_id = var.account_id
  table_name = module.table.name

  # The zips come from scripts/build_lambdas.py and the manifests from content/manifests.
  build_dir      = "${path.root}/../.build"
  manifests_dir  = "${path.root}/../content/manifests"
  schedule_state = var.schedule_state
  enable_probe   = var.enable_probe

  providers = {
    aws = aws.estate
  }
}
