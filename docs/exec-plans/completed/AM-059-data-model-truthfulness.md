# AM-059 — Data-model truthfulness

## Objective

Make authority and representation boundaries explicit without rebuilding live
derived state.

## Current and target state

`global_state_snapshots.state_json` previously held rendered text. The target
keeps existing rows intact while new snapshots record structured JSON separately
from their rendered presentation.

## Constraints and decisions

- Accepted canonical rows are never rewritten by this work.
- No live migration, replay, backfill, repair, or conversion runs.
- Migration 23 is additive: `state_payload_json` is the structured payload and
  `rendered_state` is presentation; `state_json` text remains intact.

## Affected modules and sequence

1. Add the additive SQLite migration.
2. Write new global snapshots as structured JSON plus rendered text.
3. Document authority/rebuild contracts and the compatibility boundary.
4. Prove a new snapshot is parseable and an existing text row is unchanged.

## Risks and validation

The principal risk is treating a materialized display cache as source truth or
silently converting existing rows. Focused temporary-SQLite tests verify both
the new payload and migration preservation. The full local test split, lint,
type, documentation, and diff checks verify integration.

## Final outcome

Migration 23 and the documentation contract landed without operating on live
data. Existing rows retain their stored text, while all newly written global
snapshots have an unambiguous structured payload and rendering.
