# AM-085 — Remove copy-only entity memory from active paths

## Objective

Remove `entity_memory` as an active projection, retrieval, context, profile,
and FTS layer. It copies accepted observation text without consolidation,
authority, or a distinct lifecycle.

## Current and target state

`process_ai_batch` writes `ai_items.title + ': ' + ai_items.details` into
`entity_memory`; ContextBuilder, retrieval, generic profiles, and
`entity_memory_fts` read/index it. Direct accepted `ai_items` and `memory_fts`
already provide source-backed observation content and provenance.

Target: all active consumers use accepted observations directly. Existing
`entity_memory` rows and its old FTS table remain inert legacy state; no
automatic deletion or historical rebuild runs. Physical cleanup is deferred to
the separately controlled repair workflow.

## Constraints

- Do not rewrite source, claim, canonical, or manual rows during normal use.
- Do not add a replacement summary table or compatibility layer.
- Preserve bounded queries, source item provenance, and exact retrieval paths.

## Sequence and validation

1. Remove projection writes and entity merge handling for the copy-only table.
2. Replace context/retrieval/profile reads with bounded accepted `ai_items`.
3. Remove `entity_memory` FTS creation, rebuild, triggers, and health checks.
4. Prove no copied row is recreated, legacy rows are ignored, direct
   observations retain provenance, and FTS/retrieval/context/profile paths
   remain bounded. No schema migration or live operation is included.

## Outcome

Completed 2026-08-28. Removed all active writes, reads, entity-merge handling,
and FTS registration for `entity_memory`. Direct accepted observations now
serve the affected bounded consumers. Existing rows are deliberately inert;
physical cleanup remains separate controlled repair work. Temporary SQLite
projection, context, retrieval, profile, migration, and full-suite checks pass.
