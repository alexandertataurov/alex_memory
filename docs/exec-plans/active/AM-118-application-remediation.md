# AM-118 — Application Review and Remediation

## Objective

Turn the current source-backed review into an ordered remediation program. This
is not a rewrite or a live-state cleanup. It makes the evidence -> observation
-> canonical state -> bounded context path durable, truthful, and verifiable
before feature expansion or derived-state repair.

## Review baseline — 2026-08-24

- `make review` found 598 classes/functions in 66 maintained modules and 177
  temporary-SQLite tests. The largest modules are `operational.py` (1,340
  lines), `database.py` (1,271), `app.py` (1,109), `ai/repository.py` (1,052),
  `ui/screens.py` (974), `context/improver.py` (676), `context/builder.py`
  (668), and `intelligence.py` (560). Eighteen functions exceed roughly 100
  lines; the largest is the 527-line terminal `menu_loop`.
- One full `make check` run had 176 passing tests and one AI router/job failure.
  The exact test and an adjacent 39-test router selection passed afterward.
  Treat this as an order-dependent/intermittent baseline until reproduced or
  disproved; focused reruns do not make the full gate green.
- Existing tasks AM-052 through AM-112 already describe the implementation
  work. This plan orders their dependencies and records the shared acceptance
  boundary. No private archive, environment, session, log, media, snapshot, or
  live SQLite content was read.

## Material gaps

| Priority | Finding | Consequence | Work |
| --- | --- | --- | --- |
| P0 | AI jobs store only first/last message IDs; batch fetch re-queries that range. A successful provider result is marked analyzed before later projection. | Gapped/stale work can be changed or skipped and accepted results can be stranded after a projection failure. | AM-100–AM-102 |
| P0 | `process_ai_batch()` synchronously mixes canonical entities/tasks with summaries, graph repair, contact materialization, global snapshot, and operational refresh. | Retried/bad input can fan out into repeated derived effects without a separate canonical completion state. | AM-053, AM-067, AM-101 |
| P0 | `ContextService` and `ContactContextMaterializer` both write `person_context_state`. | Current content and its version history can represent different semantics. | AM-067 |
| P0 | `retrieve_related(..., as_of=...)` mostly delegates to general search; AI Q&A uses private provider helpers and can cite only a smaller separate evidence set. | Scoped/historical retrieval and citations can overclaim their evidence. | AM-093, AM-094, AM-108 |
| P0 | Task matching remains title-similarity-led after same-chat candidate selection. | Historical tasks can merge or remain open incorrectly; completion links can be absent. | AM-071 |
| P0 | Routing still has broad failure paths and incomplete workload/capability policy. | Failure scope, retry, quota accounting, model choice, and timeout ownership can disagree. | AM-052, AM-075, AM-099, AM-104–AM-106 |
| P1 | Bootstrap overlaps later migrations and old migrations use evolving compatibility behavior. | Fresh and legacy databases can reach a hybrid shape; semantic cleanup can happen at startup. | AM-096 |
| P1 | Shutdown and scheduled Brief reconciliation swallow broad exceptions. | A failed final commit or stale pre-brief state can be presented as clean/fresh. | AM-098 |
| P1 | `entity_memory` is copy-only AI text; generic events/open loops lack a proven lifecycle. | Duplicate derived text can acquire authority and pollute context. | AM-085, AM-086, AM-088 |
| P2 | Large modules are expensive to review but their ownership is unstable. | Early extraction would move risk rather than reduce it. | AM-068, last |

## Constraints

- Preserve raw evidence, version history, accepted observations, manual locks,
  feedback, and pins.
- Use temporary SQLite databases for tests; never authenticate Telegram or write
  the live database.
- Migrations are forward-only. A live maintenance action requires an SQLite
  snapshot, dry-run report, bounded/resumable apply, and idempotent replay.
- Do not substitute broad refactors, automatic graph mutation, or a backfill for
  a proven state contract. Retain the offline deterministic answer path.

## Delivery order

### 0. Reproducible quality baseline

1. Reproduce the router/job anomaly with ordered subsets, repeated isolated
   runs, and non-private failure details. Fix only with a root-cause regression.
2. Map authoritative writer, source, consumer, staleness, and rebuild contract
   for every table changed by later phases.
3. Ensure the quality command clearly reports a failed/incomplete command and
   critical-path negative coverage; do not impose an arbitrary global target.

Exit: `make check` is repeatably green or has one owned reproducible blocker.

### 1. Freeze durable evolution

1. Complete AM-096: select immutable sequential migrations or current bootstrap
   plus explicit legacy upgrades, without rewriting recorded history.
2. Add only forward changes needed for exact job membership, projection states,
   idempotency keys, and invalidation revisions.
3. Design AM-074 dry-run/resume behavior, but do not execute a repair.

Exit: fresh and representative legacy fixtures converge without hidden semantic
work during `connect()`.

### 2. One accountable AI request

1. Complete AM-052, then AM-099 so model eligibility is a stated policy.
2. Complete AM-106: one owner for physical-request retry, usage, and rate
   accounting. AM-104 binds execution to the selected model; AM-105 provides
   cancellable timeout handling and explicit provider-client cleanup.
3. Complete AM-075: typed/restart-safe failures before observation acceptance.
   AM-102 is complete: focused parity verification confirms strict
   provider-neutral semantic validation already precedes acceptance.

Exit: a physical request is counted once, failure scope is correct, and every
route is eligible for a testable reason.

### 3. Durable observation then canonical projection

1. Complete AM-100 exact membership and semantic versioning; stale work must
   requeue without widening to a numeric range.
2. Complete AM-101 durable result, validation, projection, and integration
   states. Replaying an accepted batch makes no second provider call and no
   duplicate event/conflict/task.
3. Complete AM-071 plus AM-079/AM-109 inside the idempotent canonical boundary.
   Manual status and correction authority remain dominant.

Exit: each canonical effect names its exact evidence/job/item and replay is
deterministic at every interruption point.

### 4. Revisioned derived-state ownership

1. Complete AM-053: projection marks scoped invalidations; workers coalesce and
   cannot clear a newer revision.
2. Complete AM-067 by removing the redundant person-state writer; version rows
   must record the final committed meaning. Completed 2026-08-28: the remaining
   profile-summary and canonical-person-merge SQL bypasses delegate to
   `ContactContextMaterializer`; no live rebuild ran.
3. Complete AM-057, AM-085–AM-088 with explicit source, supersession/removal,
   and rebuild rules.

Exit: no-op batches do not refresh global state, and freshness means evidence
coverage rather than refresh count.

### 5. Grounded reads and historical limits

1. Complete AM-093: true entity scope, exact message closure, stable provenance,
   bounded SQL fallback, and no implicit global leakage.
2. Complete AM-108 and AM-107: historical requests fail closed when unsupported,
   and Deep Dive rows prove task membership.
3. Complete AM-094 through the central router; every citable fact has an allowed
   identity and the deterministic answer remains available. Follow with AM-056
   and AM-110–AM-112 as candidate-only/reproducible extensions.

Exit: each factual claim is source-cited, labelled as inference, or explicitly
states that evidence is insufficient.

### 6. Repair then simplify

1. Exercise AM-074 on a copied fixture. A live snapshot and dry-run/count report
   need explicit approval.
2. Repair in order: FTS, exact job/projection recovery, lifecycle/project links,
   project health (AM-072), segments/context, and freshness coverage.
3. Align UX/docs/diagnostics with real states (AM-062, AM-098, AM-103). Only
   then perform AM-068 cohesive module extraction.

Exit: two repair runs cause no duplicate canonical effects and expose remaining
incompleteness honestly.

## Required validation

| Boundary | Proof |
| --- | --- |
| Jobs | gapped IDs, deletion/policy change, stale version, old done job, restart, exact replay |
| Provider | timeout, network/503/quota dimensions, sibling behavior, restart cooldown, one-call accounting |
| Projection | injected post-save failure, same-batch replay, dedupe, manual authority |
| Context | coalescing, revision race, failed refresh retry, one writer, no-op batch, source removal |
| Retrieval | unresolved scope, multilingual query, exact support, `as_of`, FTS/SQL parity |
| Repair | snapshot precondition, dry-run, resume, fixture twice, raw/manual row invariants |
| Runtime | degraded start, pre-brief failure, commit/disconnect failure, original-error preservation |

## Decisions and progress

- 2026-08-26: a current-source control-plane audit confirms the historical
  baseline remains a historical review, not a statement of present runtime.
  `make check` passes 223 temporary-SQLite tests with Ruff, formatting, and
  MyPy; `make docs-check` passes. The remaining implementation boundaries are
  AM-053 derived-materialization ownership, AM-071 task lifecycle, AM-075
  typed failure taxonomy, AM-104–AM-106 physical provider-request ownership,
  and AM-120 relationship compatibility cutover. The completed engineering
  harness record that duplicated AM-105 is now assigned `AM-123`; canonical
  AM-105 exclusively denotes provider request lifecycle. No product, schema,
  source-data, provider, replay, repair, or live maintenance action ran.
- 2026-08-26: reconciled the initial review against the current source and
  migration ledger. Exact job membership, strict local validation, durable
  projection states, transactional canonical projection, revisioned context
  invalidation, the single contact-materializer writer, direct quota-aware
  settings defaults, central routed Ask Memory, and AM-096's frozen migration
  ownership are implemented controls, not current gaps. Migration documentation
  now lists the complete 1–19 ledger. The remaining open work stays bounded by
  its existing task records: AM-053's remaining materialization ownership,
  AM-071 task lifecycle, AM-075 failure taxonomy, and AM-120's compatibility
  graph cutover. No runtime, schema, replay, repair, or live action ran.
- 2026-08-26: phase-0 quality baseline reproduced a restart-cooldown failure.
  `ai_model_usage` writes UTC `usage_date` values, while `QuotaTracker.cooldown`
  queried the host-local day. The reload now queries the UTC day, preserving an
  active persisted cooldown after fresh-router construction. The focused
  temporary-SQLite test passes; remaining AM-075 failure-taxonomy work is not
  claimed complete. The full gate also exposed the already-queued AM-122
  Textual profile mount regression, which was repaired in its own bounded
  presentation layer. No migration or maintenance action ran.
- 2026-08-24: AM-119 foundation started. Migration 14 adds immutable semantic
  claims, exact claim evidence, unresolved entity references, future graph
  tables, and canonical claim-lineage columns. Validated legacy observations
  dual-write an idempotent claim during the compatibility transition. No graph
  projector, historical conversion, or live maintenance action is included.
- 2026-08-24: AM-119 completed. Fresh-schema, direct-evidence rejection, and
  replay tests pass; the full `make check` gate passes 183 tests and
  `make docs-check` is current. AM-120 is the next required implementation
  unit and owns the first graph writer.
- 2026-08-24: AM-120 initial projection is in progress under its own ExecPlan.
  Migration 15 adds claim-to-observation lineage and claim projection state.
  The one deterministic graph writer records observed claim links and only the
  already resolved task-to-project relation as accepted. The legacy
  relationship-table conversion remains pending on a caller inventory and
  bounded compatibility cutover; no live migration, replay, or repair ran.
- Do contract and persistence work before reducing module size; responsibility
  boundaries must be stable first.
- Put newly found issues in the smallest applicable existing task rather than
  creating a parallel epic.
- Re-measure task-backlog evidence from a copied SQLite fixture immediately
  before repair. This review did not inspect private records.
- 2026-08-24: plan created from architecture/docs/source/caller review,
  `make review`, and temporary-SQLite tests. No schema, runtime, or record
  change occurred. Delivery phase 0 is next.
- 2026-08-24: implemented the bounded extraction-lifecycle slice: version-2
  provider-neutral validation, exact job membership, forward migration 13,
  durable item rejection/projection/invalidation states, idempotent canonical
  projection, and revision-safe context refresh. No live migration, repair,
  automatic corpus replay, or graph-maintenance change was run. Focused
  temporary-SQLite coverage includes malformed output, durable rejections,
  exact membership/deletion supersession, projection replay, context refresh,
  and migration compatibility.
- 2026-08-24: completed a bounded read/configuration slice without a schema
  migration: direct settings now use the runtime quota-aware default and
  reject invalid booleans; `retrieve_related` uses explicit canonical links
  with temporal fact bounds; Ask Memory uses the central router's typed answer
  path and retains deterministic fallback. The existing dirty worker and sole
  contact materializer writer were rechecked. Full bootstrap/migration-ledger
  normalization remains AM-096 work and is not claimed by this increment.
- 2026-08-24: completed AM-096's ledger-normalization slice without a new
  schema version. Bootstrap no longer executes tables owned by migrations
  4–10; migrations 2 and 7 have independent frozen column snapshots. Fresh
  and legacy temporary-SQLite fixtures converge through the existing ordered
  ledger. No live schema action, repair, or backfill ran.
