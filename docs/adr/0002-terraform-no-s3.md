# 0002 — Terraform/OpenTofu with direct Lambda uploads; no S3
- **Status:** Accepted (2026-11-05)

## Context
New Free-plan accounts get **no Always Free S3 storage**; S3 is funded from credits only ([S3 pricing](https://aws.amazon.com/s3/pricing/)). Both AWS SAM and CDK need an S3 bucket for deployment artefacts (CDK's comes from bootstrapping). Lambda accepts direct zip uploads up to 50 MB.

## Decision
- Use **Terraform** (OpenTofu works as a drop-in alternative) with local state that is git-ignored.
- Upload Lambda code as direct zips.
- Use **no S3 anywhere**: evidence lives in DynamoDB or is git-versioned in the repo.

## Alternatives
- SAM: AWS-native and simpler for Lambda, but needs an S3 bucket.
- CDK: needs bootstrap resources, including S3.

## Consequences
- Lambda packages must stay small (well under 50 MB zipped), so no scikit-learn or numpy at runtime. ML inference is pure Python.
- Local state means one operator, which is fine for this project.
- Terraform is a transferable industry skill.
