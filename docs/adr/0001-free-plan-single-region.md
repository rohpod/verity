# 0001 — AWS Free plan, single region eu-west-1
- **Status:** Accepted (2026-11-05)

## Context
The project must cost $0. The AWS account was created after 15 Jul 2025 on the **Free plan**. That plan never bills; usage beyond the Always Free allowances draws down credits. It ends after 6 months or when the credits run out, whichever comes first. The Free plan does not support multi-region features or AWS Organizations. ([AWS Billing: Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html), [Free plan supported services](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html))

## Decision
- Stay on the Free plan and never upgrade.
- Design to Always Free allowances only, and track credit burn as a secondary safeguard.
- Use the single region **eu-west-1 (Ireland)**. This matches the EU-exposed customer story and gives us a data-residency attribute.

## Alternatives
- Paid plan: allows real billing, so it is rejected.
- us-east-1: the default for most tutorials, but it weakens the EU narrative.

## Consequences
- The live environment is **temporary** (about 6 months), so everything must be rebuildable from Terraform.
- The static snapshot is the permanent portfolio artefact.
- No multi-region designs.
