# 0003 — Knowledge graph on DynamoDB single-table + NetworkX, behind a repository interface
- **Status:** Accepted (2026-11-05)

## Context
The product's intelligence is graph-shaped: impact analysis, crosswalks and audit trails. The candidate managed graph databases are ruled out: Neptune is paid and is a Paid-plan-only service. The candidate embedded graph database, Kùzu, was archived in Oct 2025. DynamoDB is Always Free only in **provisioned mode with the Standard table class**, with 25 GB storage and 25 RCU/WCU ([DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/)).

## Decision
- Store the graph in an **adjacency-list single table** called `verity-graph`:
  - nodes are `META` items
  - edges are `E#` items, with mirrored `R#` items for reverse lookups
  - node history is append-only `H#` items
  - one GSI indexes nodes by type
- Capacity is table 15/15 plus GSI 10/10, with auto-scaling **off**.
- Load the graph into **NetworkX** to traverse it.
- All access goes through a `GraphRepository` protocol. Implementations: `InMemoryRepository` and `DynamoDBRepository`.

## Alternatives
| Option | Why not chosen |
|---|---|
| Neptune | Paid; Paid plan only |
| Neo4j AuraDB | Not AWS |
| Kùzu | Archived |
| SQLite in S3 | Needs S3 |
| Relational tables (RDS) | Not free |

## Consequences
- Fine at hundreds to low thousands of nodes. Full loads at 15 RCU take seconds, which is acceptable for a daily crawl.
- Migrating to a dedicated graph database later means writing a new repository implementation, not rebuilding the application.
