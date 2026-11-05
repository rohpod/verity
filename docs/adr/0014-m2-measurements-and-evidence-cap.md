# 0014 — M2 measurements, throttling retries and the inline evidence cap
- **Status:** Accepted (2026-11-05). Refines [0013](0013-dynamodb-write-model.md), which stays in force except for its throttling line.

## Context
ADR 0013 and D14 left three things for M2 to settle: how throttling is handled, what `load_graph` costs, and the inline evidence cap. Those results were first written into ADR 0013 after it was accepted, which breaks the rule that accepted ADRs are not edited. The end-of-M2 review restored ADR 0013 and moved them here.

The review also corrected two claims from those edits. A plain `load_graph` ignores 48% of what it reads, not 29%, because `H#` items are ignored too. And `content_ref` is no way out for oversized evidence in a live crawl, because it points to a git-versioned file that a Lambda cannot write.

## Decision
**Throttling** (replaces ADR 0013's "Throttling uses boto3's built-in retries with backoff")
- **Single calls use boto3's `standard` retry mode.**
- **The repository retries cancelled transactions itself.** boto3 does not retry a `TransactionCanceledException`, and a transaction that runs out of capacity can be reported as a cancellation with reason `ProvisionedThroughputExceeded`. It tries up to 8 times, with pauses doubling from 0.2 s to a 10 s cap, about 22 s in all.
- **It never retries a conflict.** If a conflict is among the reasons, the data changed and repeating the write would not fix that. A cancelled transaction wrote nothing and the version checks run again on each attempt, so repeating is safe.

**Inline evidence cap**
- **The cap is 16 KB of canonical JSON** (D14), down from the 50 KB placeholder.
- **The main reason is that only raising it is safe.** Stored evidence is validated again on every read. Raising the cap later changes nothing that is stored. Lowering it could make stored items unreadable, and one such item would break `load_graph`. So start low.
- **The cap limits the worst case only.** A 16 KB document is an item of about 17 KB: 17 write units and 5 read units, against 51 and 13 at 50 KB. It saves nothing on evidence of a normal size.
- **The value is provisional.** The largest fixture evidence item is 703 bytes, but fixtures are not crawl output, and the crawler also collects role policies, which can be much larger. M6 measures real sizes and decides what happens to evidence over the cap.

## Alternatives
| Option | Why not chosen |
|---|---|
| Keep the cap at 50 KB | Lowering it later is the unsafe direction, and nothing yet needs that much |
| Cap near DynamoDB's 400 KB item limit | One item could cost about 400 write units, over 26 s of the table's capacity |
| Keep the results in ADR 0013 and relax the no-edit rule | The record of what was decided, and when, is the point of an ADR |

## Consequences
All sizes come from AWS's published size and capacity rules, because moto reports no capacity for transactions.

- **Measured on the fixture estate:** 276 items, 117 KB, averaging 425 bytes and all under 1 KB. `load_graph` costs about 29 read units strongly consistent, in 3 pages of 100 items, about 2 s of the table's 15 units. A node write and an edge write each cost 4 write units.
- **A plain `load_graph` ignores 48% of what it reads:** the `R#` mirrors and `H#` versions, plus usage records, which the fixture estate does not have. The bytes are 29% `R#` and 19% `H#`.
- **At the design target** (300 nodes, 1,000 edges, about 1 MB) a scan is about 264 read units, roughly 18 s at 15 per second. The first seed is about 5,200 write units, roughly 6 minutes.
- **A scan is not a snapshot.** A node written while it runs can appear in an older version. Run it when no writer is active, as the daily crawl and the export are.
- **Daily crawls outgrow the design target.** This is an estimate from real record sizes, assuming a daily crawl for 150 days with 15 to 30 resources, starting from the design target. It stays free, but "full loads take seconds" (ADR 0003) stops being true:

  | Each crawl adds, per resource | Items | Size | Full scan at 15 units |
  |---|---|---|---|
  | An `OBSERVED` edge | 7,500 to 12,000 | 3 to 5 MB | 50 to 80 s |
  | That, plus an Evidence record with `ABOUT` and `COLLECTED_FROM` edges | 19,000 to 35,000 | 9 to 17 MB | 2.5 to 4.5 min |

  Evidence is the larger part. M6 decides how to limit it.
- **Edge writes do not re-check the nodes they connect.** A transaction checks the edge's own version, not its endpoints, so a node ended at the same moment can be left with an open edge, and a `max_out` limit can be exceeded. This comes from reading the code and is not covered by a test. It is safe with one writer at a time, so M8 must not run a seed and a crawl together.
- **A test fails if boto3 or botocore is imported outside `graph/dynamodb/`** (`tests/graph/test_boto3_boundary.py`). It reads every tracked source file outside `tests/`, so new packages are covered.
