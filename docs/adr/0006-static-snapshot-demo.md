# 0006 — Public demo as a redacted static snapshot on GitHub Pages
- **Status:** Accepted (2026-11-05)

## Context
Visitors to the repository should be able to see a working demo. A public endpoint backed by live AWS would invite abuse and credit burn. The live AWS environment also expires with the Free plan (see ADR 0001).

## Decision
- `verity export` writes `snapshot.json`, which is a redacted copy of the real graph:
  - the AWS account ID is replaced with `000000000000`
  - function URLs are stripped
- The React dashboard reads only this file.
- GitHub Actions deploys the dashboard to **GitHub Pages**. CI holds no AWS credentials.

## Alternatives
- S3 + CloudFront: S3 is not free on this plan.
- Amplify: credits only.
- A public live API: abuse and cost risk.

## Consequences
- Pages hosting is a documented, hosting-only exception to the AWS-only rule.
- The demo is read-only, and shows the snapshot timestamp so visitors know how fresh it is.
- A screen recording of a live crawl can supplement it.
