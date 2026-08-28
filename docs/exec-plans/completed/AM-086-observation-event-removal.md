# AM-086 — Remove duplicate observation context events

## Objective

Stop projecting ordinary accepted observations as `observation_recorded`
context events. An event must add an actual dated occurrence or state meaning;
an ordinary observation remains the source-backed `ai_items` record.

## Current and target state

`ContextService.process_ai_item()` previously mapped every otherwise-unhandled
kind to `observation_recorded`, copying title, details, date, entity links, and
provenance into `context_events`. Context packages, related retrieval, person
profiles, and contact timelines then exposed the duplicate wrapper.

Target: explicit lifecycle/payment/project mappings continue to create semantic
events. Ordinary observations create no event; the readers use the original,
bounded linked `ai_items` observation and ignore legacy duplicate wrappers.

## Constraints

- No raw evidence, claim, canonical, manual, or existing derived rows change.
- No historical deletion, rebuild, migration, replay, or live repair.
- Preserve temporal `as_of`, entity scoping, bounded limits, and source-message
  provenance.

## Sequence and validation

1. Make the fallback event mapping absent rather than generic.
2. Exclude legacy wrappers from event consumers and retain direct observations
   in related retrieval and contact timelines.
3. Prove ordinary projection creates no event, semantic projection still does,
   and legacy wrappers do not displace their source observation.
4. Run focused context/retrieval/conversation tests and the standard local
   quality checks. Existing duplicate rows remain inert pending separately
   authorized repair work.

## Outcome

Completed 2026-08-28. Ordinary observations no longer create context events.
Context packages and person profiles ignore retained legacy wrappers; related
retrieval and contact timelines use the source-backed observation itself.
Semantic event mappings remain intact. Temporary-SQLite focused, broader
partitioned, UI, lint, type, documentation, and diff checks pass. No migration,
replay, deletion, or live operation ran.
