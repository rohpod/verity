# 0013 — DynamoDB write model
- **Status:** Accepted (2026-11-05). Refines [0003](0003-dynamodb-graph-repository.md) and [0012](0012-graph-schema-refinements.md); both stay in force.

## Context
M2 implements `DynamoDBRepository` behind the contract M1 fixed. That contract needs several items to change together, while capacity is limited to 15 WCU on the table and 10 on GSI1. These facts were checked against AWS documentation on 2026-11-05:
- A transactional write uses 2 WCU per KB, against 1 for a standard write. Transactions have no other charge, but capacity is consumed even when one fails.
- One transaction holds up to 100 actions and 4 MB.
- GSI reads are eventually consistent only.
- A GSI write uses the index's capacity, and only when the index needs updating.

## Decision
**Writes**
- **Edges are transactional.** `E#` and `R#` are written in one `TransactWriteItems`, including on close and reopen, so forward and reverse lookups cannot disagree.
- **Node versions are transactional.** `META` and `H#` are written together.
- **Evidence is one conditional write.** It never changes, so it has no `H#` item and `history()` reads `META`.
- **Writes check the version they read.** A stale write fails with `ConcurrentWriteError` instead of overwriting.
- **Ending a node closes edges first.** Edges close in batches within the 100-action limit, then the node is written. A failed run can be retried, because closing a closed edge changes nothing.

**Storage**
- **Records are stored as JSON.** Each item holds its §H keys plus the whole record as a JSON string in `doc`. boto3 returns numbers as `Decimal`, which would break evidence hashes.
- **Write rules are shared.** The decisions in `InMemoryRepository` move into pure functions that both repositories call.
- **`table_definition()` is the table's single description.** The tests use it, and M3's OpenTofu follows it.

**Reads**
- **`load_graph` is one consistent Scan,** sorted client-side. `as_of` selects versions from the `H#` items with `version_at`.
- **`nodes_by_type` queries GSI1, then uses `BatchGetItem`,** because the index holds keys only (D14). A just-written node can be missing briefly. `check_integrity` also reports more than one Organisation, because the write-time check reads this index.

**Usage and dependencies**
- **`DynamoDBUsageSink` is one conditional `PutItem`,** so app roles need no read access (D8). `DynamoDBRepository` delegates to it.
- **boto3 is an optional `aws` extra on `verity-core`.** The Lambda runtime already provides it, so zips stay small. moto is a dev dependency.
- **Throttling uses boto3's built-in retries with backoff** (D14).

## Alternatives
| Option | Why not chosen |
|---|---|
| `BatchWriteItem` for edges | Half the capacity, but not atomic: a partial write leaves one direction of an edge missing |
| `R#` holding keys only | Smaller, but every reverse lookup would need a second read |
| Native DynamoDB attributes | Queryable fields are not needed, and numbers would return as `Decimal` |
| `H#` copy for Evidence | A 50 KB item would cost 200 WCU instead of 50, for a copy of something that never changes |
| No version check | A stale write would silently overwrite a newer one |
| A sentinel item for the one-Organisation rule | One more item type to guard a single-writer seed. `check_integrity` catches the case |

## Consequences
- An edge write costs 4 WCU, so a first seed of about 300 nodes and 1,000 edges takes roughly 6 minutes of write capacity. Re-seeding writes almost nothing.
- `load_graph` also reads `H#` and `U#` items. M2 measures that cost.
- Ending a node with more than about 50 edges is not atomic as a whole, but it is retryable.
- moto reports no capacity for transactions and shows no GSI delay. Capacity is calculated from item size, and M3's real round trip checks what moto cannot.
