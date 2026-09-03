# AM-120 — Semantic Graph Projection

## Control-plane status

This ExecPlan is a synchronized repository mirror. Notion controls this task's
scope, status, dependencies, gates, authorization, and completion; this plan
cannot authorize a further reader cutover, live action, or any scope change.

## Objective

Make validated semantic claims usable as a temporal SQLite graph without
upgrading AI output into canonical truth. The graph has one writer,
`SemanticGraphProjector`; deterministic canonical reducers remain the only
automatic authority path.

## Current and target state

Migration 14 created immutable claims and empty graph tables. Migration 15
adds claim-to-observation lineage and per-claim projection state. Accepted
batch projection now resolves claim entity references, creates observed claim
nodes and links, materializes accepted canonical entity nodes, and permits only
an already accepted task-to-project link to become an accepted graph edge.

The existing `relationships` table remains a compatibility table with active
legacy writers/readers. It is neither converted nor declared graph-authoritative
by this increment. Its source-backed conversion and read-only cutover must wait
until callers move to graph queries; no startup conversion or live replay is
allowed.

## Authority and rebuild contract

| Layer | Authoritative input | Writer | Rebuild/rollback |
| --- | --- | --- | --- |
| `semantic_claims` | validated submitted-message evidence | AI repository | immutable; no rewrite |
| `graph_nodes`, `graph_edges`, `graph_edge_claims` | claims plus resolved canonical IDs | `SemanticGraphProjector` | replay accepted batches on a copied fixture only |
| canonical tasks | validated compatibility observation plus deterministic reconciler | `TaskReconciler` | ordinary idempotent projection; manual locks dominate |
| legacy `relationships` | pre-existing context flows | legacy context code | compatibility-only; out of scope for this increment |

Claims and claim nodes are `observed`. Canonical entity nodes are `accepted` as
representations of already accepted records, not as approval of the AI claim.
Only `task --belongs_to--> project` is automatically accepted after the task
reducer resolved it unambiguously. Any other relationship claim remains
observed or enters Review through its existing resolver path. Superseded
accepted task-project edges receive a closing validity boundary rather than a
history rewrite.

## Implementation sequence

1. Add forward migration 15 for `ai_items.source_claim_id` and semantic-claim
   projection state; leave migrations 1–14 unchanged.
2. Persist each claim before its compatibility observation and link duplicate
   observations to their original claim without duplicate side effects.
3. Thread source-claim lineage through canonical task, event, and fact writes.
4. Add the sole graph writer and invoke it in the transactional accepted-batch
   projection after entity/task resolution.
5. Cover exact evidence lineage, accepted-edge authority, low-confidence
   non-acceptance, migration shape, and repeat projection with synthetic
   temporary SQLite fixtures.
6. Before a relationship-table conversion, inventory every old writer and
   reader, define graph-query replacement behavior, snapshot any approved live
   database, and run dry-run/replay proof. That cutover is not part of this
   initial implementation.

## Risks and limits

- Entity resolver ambiguity remains Review; the projector records unresolved
  claim references as `review` and never invents a graph link.
- Graph rows are a derived projection, not evidence. Every graph edge links to
  one or more immutable claims, which link to exact submitted messages.
- No live migration, corpus replay, relationship conversion, graph repair, or
  backfill is authorized by this plan.
- AM-121 must expose only bounded read-only graph queries and must exclude
  observed/rejected/superseded relationships from current operational views by
  default.

## Validation

- Fresh migration and legacy upgrade retain the forward migration ledger.
- Malformed/foreign evidence claims cannot reach the graph writer.
- Accepted task-project edges include exact claim evidence and source lineage.
- Replaying an item leaves node, edge, and edge-claim counts unchanged.
- A non-accepted task claim can create only observed graph material, never an
  accepted relation.
- An active manual task-project edge blocks automatic replay and changes the
  claim projection outcome to `review` without removing history.

## Progress

- 2026-08-24: implemented migration 15, compatibility observation lineage,
  deterministic graph projection, and focused temporary-SQLite coverage. The
  legacy relationship-table cutover remains deliberately pending on caller
  migration and an approved bounded compatibility plan.
- 2026-08-26: completed the required caller inventory before any compatibility
  conversion. Legacy writes enter `relationships` through `ContextService`,
  `ContextGraphImprover`, and Review acceptance (`ensure_relationship`);
  readers include `ContextBuilder` traversal, task project resolution, Person
  Profile/evidence chat discovery, profile scan chat selection, People
  discovery, and graph diagnostics. The graph projector currently has only one
  automatic accepted-edge contract: `task -> belongs_to -> project`. A direct
  reader cutover would therefore drop or wrongly upgrade the legacy
  person/company-to-project relationships. The next increment must first define
  a bounded graph query contract and deterministic/manual projection authority
  for every required relationship kind, with parity fixtures, before moving a
  reader. No relationship conversion, replay, repair, or live action ran.

## Compatibility-cutover contract — 2026-08-26

The graph may become a runtime relationship source only for an explicitly
bounded reader once all of the following are true:

- the edge joins two canonical nodes and is current at the reader's `as_of`;
- its authority is `accepted` from an allowlisted deterministic reducer or
  `manual`; observed, rejected, and superseded graph material is never
  operational context;
- automatic edges retain one or more exact immutable claim references, while
  a manual edge remains manually authoritative without pretending to have AI
  evidence;
- the reader receives stable endpoint types/IDs, relationship type, validity,
  authority, confidence, and claim provenance under an explicit SQL limit.

This contract currently has parity only for the deterministic
`task -> belongs_to -> project` edge. It does not authorize conversion of
legacy person/company/project relationships: `ContextService` and
`ContextGraphImprover` can currently create those compatibility rows from
validated observations or confidence thresholds, but neither path is an
allowlisted graph-acceptance reducer. Context traversal, People discovery, and
Person Profile must therefore continue to read `relationships` until each
relationship kind has a deterministic/manual authority mapping and parity
fixtures. This is a derived-projection/read-contract decision only; it changes
no raw evidence, observation, canonical state, schema, or live data.

Explicit Review acceptance is the authority mapping for non-task relationship
kinds. A reviewed `graph_link` now writes a manual person/company-to-project
graph edge alongside its compatibility row. The graph also exposes a bounded
manual-edge API for person-company and company-project decisions. These edges
have no invented claim lineage. Compatibility rows inferred from model
confidence remain outside accepted-graph reads until they are independently
reviewed; they are not backfilled or upgraded.

`context_builder_relationship_parity_gaps` is the bounded, read-only
readiness diagnostic for the first future reader cutover. It follows the
current ContextBuilder relationship expansion depth, then reports only grouped
compatibility relationship kinds that lack a current accepted/manual graph
counterpart at the requested `as_of`. It does not expose relationship content,
write either layer, or treat a zero-gap synthetic fixture as authorization for
a live reader change.

### Progress

- 2026-08-27: added `current_authoritative_edges`, a bounded read-only graph
  query contract. It returns current canonical-node edges only: automatic
  results are restricted to the existing task-to-project reducer allowlist and
  require immutable claim evidence, while manual results retain no fabricated
  AI provenance. Temporary-SQLite fixtures prove acceptance, temporal expiry,
  observed/source-less exclusion, manual authority, and the current
  person/company relationship parity gap. No runtime reader, relationship
  conversion, migration, replay, repair, or live action changed.
- 2026-08-27: explicit manual authority now has parity for person-company,
  person-project, and company-project relationship kinds. Accepted graph-link
  review writes the manual person/company-project edge, while direct manual
  graph projection supports the remaining kinds without fabricated AI
  provenance. Unreviewed compatibility inference remains excluded, so no
  reader cutover, conversion, migration, replay, or live action is authorized.
- 2026-08-27: added the bounded ContextBuilder parity-gap diagnostic. Fixtures
  prove manual parity, observed-graph exclusion, and temporal expiry without
  changing a runtime reader. A reader moves only after its own accepted/manual
  fixture coverage reports no gaps.
- 2026-08-29: tightened the diagnostic to rank the same capped relationship
  set that ContextBuilder returns rather than inspecting an unrelated first
  page of rows. Seed/depth clipping is now explicit and therefore
  inconclusive, never a green cutover signal. A temporary-SQLite fixture proves
  a newest compatibility-only edge is reported even when older manual graph
  edges fill the reader cap. The reader and authority rules are unchanged.
- 2026-08-30: exposed the existing diagnostic through `make graph-parity`
  (`SEEDS="person:123 project:456"`, optional `AS_OF`, and `GRAPH_DEPTH`). It
  opens SQLite read-only and returns only grouped relationship gaps plus an
  explicit `ready` flag; it does not print relationship content or mutate
  state. This enables owner-run real-reader proof without authorizing a
  reader cutover.
- 2026-08-30: extended the deterministic accepted-task reducer to emit only
  the task's exact-claim-backed current person/company-to-project context:
  person `involved_in`, and company `involved_in` / `associated_with`.
  The bounded graph read admits these three kinds only when the edge records
  that reducer and immutable claim evidence. A parity fixture proves the
  matching legacy ContextService/ContextGraphImprover relationships have no
  gap; arbitrary confidence-only compatibility relationships remain excluded.
  No replay, repair, conversion, migration, runtime reader change, or live
  operation ran. A fresh owner read-only parity result remains required.
- 2026-08-30: task-derived person/company context edges now close when the
  canonical task moves to another project or a manual task-project decision
  takes precedence. The temporal regression proves all three derived edge kinds
  become superseded rather than surviving as current state.
- 2026-09-02: an owner-run, non-truncated parity check still found the three
  task-context compatibility kinds (`person involved_in project`, `company
  involved_in project`, and `company associated_with project`). Tracing showed
  they can predate persisted task-context graph rows because the legacy
  ContextService and ContextGraphImprover write compatibility rows directly.
  The bounded authoritative query now exposes only the same exact-claim-backed
  current task reducer at read time when its stored context edge is absent.
  The fallback is marked derived, has no stored edge ID, honours a manual
  task-project decision, and never reads or promotes `relationships`; a
  temporary-SQLite regression proves parity without replay/backfill. Fresh
  owner parity evidence is still required before reader cutover.
- 2026-09-02: the first fresh owner result remained negative after the
  read-only task-context fallback, proving its exact-claim predicate does not
  cover these real compatibility rows. `graph-parity` now adds a grouped,
  non-disclosing authority diagnostic for each gap: it distinguishes no matching
  canonical task, missing exact task-claim lineage, a manual task override, and
  an eligible reducer result omitted by the bounded query. It contains no
  task/item IDs, evidence text, or relationship content. The next owner result
  determines whether a query correction is justified or the rows must remain
  compatibility-only pending manual authority.
- 2026-09-02: fresh diagnostic evidence classified all three gaps as having no
  matching current task. Tracing the non-task path found that `ContextService`
  also creates canonical source-backed events before its compatibility rows.
  The graph projector and bounded reader now admit only an exact event reducer:
  canonical event, source item, immutable claim evidence, and person/company/
  project endpoints must agree. It supplies person `involved_in` and company
  `involved_in` / `associated_with`, excludes task-owned events to avoid
  duplicate authority, and can be derived read-only for historical missing
  materialization. A temporary-SQLite payment-event regression proves parity;
  confidence-only rows remain excluded. Fresh owner parity is required.
- 2026-09-02: corrected the parity authority diagnostic to inspect canonical
  event lineage before reporting that no task or event matches a compatibility
  edge. It now distinguishes an absent event from an event missing exact item,
  claim, evidence, endpoint, or temporal eligibility. The diagnostic remains
  read-only and never promotes either result into graph authority.
- 2026-09-02: added the historical canonical-event reducer for records created
  before claim lineage was populated on both the event and source item. It
  requires matching event/item endpoints and exact surviving source message,
  rejects task ownership and any partial/mismatched claim lineage, and returns
  the source-message locator without fabricating a claim ID. It is read-only,
  does not consult compatibility rows, and needs no replay or backfill.
- 2026-09-02: parity diagnostics now identify the rejected event boundary as an
  aggregate-safe reason (missing source item or claim, lineage mismatch,
  endpoint/source-message mismatch, temporal exclusion, task ownership, or
  missing claim evidence) instead of a generic lineage label.
- 2026-09-02: the owner reran the bounded, non-truncated parity gate after the
  historical-event representation change. It returned zero gaps and
  `ready: true`. This satisfies the first-reader readiness evidence only;
  ContextBuilder remains on its compatibility reader until a separately
  authorized cutover increment.
- 2026-09-03: owner authorized and completed that smallest reader increment:
  `ContextBuilder` now calls only `current_authoritative_edges()` while keeping
  its existing depth, 160-row per-frontier query bound, 80-row result cap,
  endpoint traversal, ranking path, and canonical UTC `as_of` behavior.
  Stored and derived automatic edges retain immutable-claim/source-message
  evidence for exact closure; manual authority stays manual. Compatibility-only,
  observed, confidence-only, expired, rejected, and source-less automatic rows
  are excluded. Focused temporary-SQLite coverage proves automatic provenance
  and compatibility exclusion. No writer, schema, conversion, replay, repair,
  backfill, or live-state action ran. No other reader cutover is authorized.
