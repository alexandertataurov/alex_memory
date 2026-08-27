# AM-120 — Semantic Graph Projection

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

### Progress

- 2026-08-27: added `current_authoritative_edges`, a bounded read-only graph
  query contract. It returns current canonical-node edges only: automatic
  results are restricted to the existing task-to-project reducer allowlist and
  require immutable claim evidence, while manual results retain no fabricated
  AI provenance. Temporary-SQLite fixtures prove acceptance, temporal expiry,
  observed/source-less exclusion, manual authority, and the current
  person/company relationship parity gap. No runtime reader, relationship
  conversion, migration, replay, repair, or live action changed.
