# AM-078 — Database integrity

## Objective

Enforce SQLite's existing foreign keys for every application connection and
report bounded logical-reference gaps that cannot safely become physical keys.

## Authority and constraints

Raw messages and source-evidence versions are immutable. Canonical tasks,
relationships, and context references remain their existing authority; this
work only rejects new broken physical references and reports logical gaps.
There is no table rebuild, migration, repair, backfill, or live-data action.

## Delivery and validation

1. Enable `PRAGMA foreign_keys=ON` as the first connection setting.
2. Define fixed, query-only checks for task, AI-item, relationship, open-loop,
   conversation-context, and evidence-version references.
3. Surface only table/key/count diagnostics from `make db-check`.
4. Prove foreign-key rejection, injected logical-reference gaps, and audit
   non-mutation with temporary-SQLite fixtures.

## Final outcome

No migration was required. Connection-level foreign-key enforcement and the
read-only orphan inventory are covered with temporary-SQLite fixtures; the
implementation does not modify source, canonical, or materialized rows.
