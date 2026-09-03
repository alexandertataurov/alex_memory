# Implementation Journal

## 2026-09-03 — Keyboard-first Command Palette routing

The Textual Command Palette now filters, highlights its first filtered command,
and invokes it with Enter. People/search/profile actions remain local to
Textual; Review, System Status, and Maintenance return distinct explicit
operation keys to the existing operational handler. This is navigation-only:
no schema, evidence, canonical state, or live operation changed.

## 2026-09-03 — Canonical blocked task lifecycle

Canonical task workflow now supports `open`, `waiting`, `blocked`, `done`, and
`canceled`, while due/scheduling, staleness, and certainty stay independent in
the bounded action read model. Migration 24 preserves every task row, manual
lock, source-claim lineage, and index, then restores the existing FTS-derived
task index from authoritative rows. No replay, backfill, repair, or live
migration ran.

## 2026-09-03 — Literal Textual source/model rendering

Dynamic Textual Labels, Statics, and profile/status updates now receive literal
Rich `Text`. Bracketed contact and message content therefore renders literally;
no source/model string can activate markup. This is presentation-only with no
schema, evidence, canonical-state, or writer change.

## 2026-09-03 — Topic-noise and project-context guardrails

The final Person Profile/Overview topic boundary rejects generic materialized
tokens. Automatic project creation now requires an operational task reference;
events and personal facts cannot qualify a project item for canonical creation.
This is bounded projection/presentation logic with synthetic tests only; no
schema, replay, backfill, repair, or live-state action ran.

## 2026-09-03 — Compact evidence affordance outside evidence views

Normal Person Profile Textual and Rich renderers now use `[E]` when exact
evidence exists, instead of exposing raw chat/message storage identifiers.
Record Detail and Evidence views retain the exact locator and source text.
This is presentation-only; evidence, canonical state, schema, and writers are
unchanged.

## 2026-09-03 — Human-readable Person Profile fields

The selected Notion Person Profile leaf now derives display-only section,
label, and value fields from existing canonical facts and profile claims.
Normal Textual and Rich profile views use those fields, suppressing empty,
unknown, and label-equals-value records and grouping profile rows by meaningful
section. It remains a bounded read-only presentation change: exact evidence,
claims, canonical state, schema, and writers are unchanged.

## 2026-09-03 — AM-124 owner acceptance and completion

The owner accepted and closed AM-124. Its final authorized V1 is the bounded
read-only shared-connections query: two independently capped authoritative
one-hop reads, typed canonical intersection, exact leg provenance, UTC-aware
temporal behavior, and no writes. The full repository verification gate passed.
There is no remaining acceptance gate and no authorization for further AM-124
implementation, traversal/ranking expansion, graph UI, reader cutover,
schema/writer work, repair, replay, backfill, or live-state action.

## 2026-09-03 — Notion-first work-control synchronization

Notion's **Codex — Ready & Authorized** view is now documented as the sole
authority for task existence, scope, status, priority, sequence, dependencies,
gates, authorization, completion, and the next executable leaf. Repository
`TASKS.md`, ExecPlans, changelog, docs, and GitHub task prose are synchronized
implementation mirrors; code and tests remain evidence of actual behavior.
The local mirror audit rejects a future claim that `TASKS.md` is an authoritative
queue. No application behavior, schema, migration, replay, repair, backfill,
or live-state action changed.

## 2026-09-03 — AM-120 ContextBuilder reader cutover

`ContextBuilder` now obtains relationships only from the already accepted,
bounded `current_authoritative_edges()` contract. It preserves the reader's
existing graph depth, 160-row per-frontier query bound, 80-row final cap,
endpoint traversal, and canonical UTC temporal behavior. Graph-authoritative
automatic rows retain claim lineage (or the historical event's exact
source-message locator) for evidence closure, while manual authority remains
explicitly manual. Compatibility-only, observed, confidence-only, expired,
rejected, and source-less automatic rows are excluded. No writer, schema,
conversion, replay, repair, backfill, or live-state action ran; no other reader
cutover is authorized by this increment.

## 2026-09-03 — AM-121 completed; multi-hop deferred

The owner accepted AM-121's implemented bounded one-hop intelligence scope as
sufficient. Multi-hop/shared-counterparty intelligence is recorded as separate
future task AM-124, with product and authority boundaries to be defined before
any implementation.

## 2026-09-02 — AM-121 bounded graph intelligence

`retrieve_related()` now presents the existing bounded authoritative graph
contract for person, company, and project scopes as one-hop connection results.
Automatic rows retain an exact claim-evidence or source-message citation;
manual rows remain explicitly manual, and observed rows are excluded. This does
not change ContextBuilder, compatibility relationship readers, graph writers,
or database state.

Company and Project profiles now render the identical one-hop connection
results. The query helper is shared rather than reimplemented, so the same
authority and evidence rules apply in both product surfaces.

Automatic graph connections now use the canonical semantic-claim evidence
column names when resolving their exact message citation; regression coverage
exercises this path directly.

Company and Project profiles also expose a bounded canonical event timeline.
Events without an exact source-message locator remain omitted.

Company and Project commitments now show their exact source message when one
is retained, or an explicit manual/canonical label when none exists.

## 2026-09-02 — Patch safety-hook path parsing

The pre-tool private-path guard now scans `apply_patch` file headers rather
than ordinary patch content. Protected paths remain rejected, while maintained
code that happens to use a field named `data` no longer produces a false
private-archive denial.

## 2026-09-02 — AM-120 graph-parity readiness accepted

The owner reran `make graph-parity` after the bounded historical-event authority
change. The result was non-truncated with zero grouped gaps and `ready: true`.
This accepts the first-reader readiness gate only; ContextBuilder still uses the
compatibility reader, and no live operation or reader cutover occurred.

## 2026-09-02 — AM-122 claim-grounding display correction

Claim-backed profile records are now omitted when their cited source is no
longer available. Manually created operational rows remain visible. This is a
read-only presentation change with temporary-SQLite regression coverage.

## 2026-09-02 — AM-120 event-authority diagnostic correction

The parity classifier previously named a missing task-or-event condition after
checking only tasks. It now checks the exact canonical-event reducer boundary
and reports absent events separately from incomplete event lineage. The tool
remains read-only and aggregate-only.

The historical event reducer now recovers an event and source item created
before either retained claim lineage only through matching endpoints and the
exact surviving source message. It exposes that source-message locator without
fabricating a claim ID, and remains a bounded read-time representation rather
than a compatibility-row promotion or maintenance action.

Event rejection reasons are now aggregate-safe and specific enough to separate
absent source items, missing claims, mismatches, timing, task ownership, and
missing evidence without returning record identifiers or content.

## 2026-09-02 — AM-122 aggregate-only owner acceptance harness

`make profile-acceptance PROFILE_CONTACTS="recent:… dormant:… ..."` now turns
the structural portion of AM-122's private 10–20-contact validation into a
read-only, aggregate-only check. The sample must contain every required contact
shape and distinct person IDs. The command builds the existing bounded profile
reader and reports only coverage and counts for missing profiles, ungrounded
display rows, uncertain claims leaked into canonical sections, a briefing
without last-interaction evidence, or a detected write. It does not emit names,
IDs, evidence text, or message content. It cannot replace the owner decision on
identity, historical coherence, useful connections, or conversation readiness.
Temporary-SQLite tests cover passing, ungrounded, and incomplete-shape samples;
no live archive inspection or profile maintenance ran.

## 2026-09-02 — Completed AM-074 plan-reference reconciliation

The completed AM-074 task record now links to its completed ExecPlan. This is a
repository-control correction only; no repair workflow, database state, or live
operation changed.

## 2026-09-02 — AM-120 read-only historical task-context parity

An owner-run, non-truncated ContextBuilder parity check reproduced the same
person/company-to-project compatibility gaps after persisted task-context graph
projection was introduced. The legacy ContextService and ContextGraphImprover
can retain those rows independently, including rows created before the graph
materialization existed. `current_authoritative_edges` now returns a clearly
labelled, read-only task-context result only when the current canonical task,
its source item, and its immutable claim match exactly and a manual task link
does not override it. It never reads `relationships` or upgrades confidence;
the fallback needs no replay, backfill, or live write. Temporary SQLite tests
cover the missing-materialization parity case. A fresh owner parity run remains
required before any reader cutover.

The first fresh owner run remained negative, so `make graph-parity` now also
reports grouped authority reasons for the bounded gaps without returning
relationship IDs, task/item IDs, or evidence text. This distinguishes a real
allowlisted-query omission from a compatibility row that lacks deterministic
task/claim authority or is stale after a manual override. It remains read-only.

That diagnostic then showed no matching current task for the remaining rows.
The non-task `ContextService` path has a separately canonical, exact-lineage
authority: it creates `context_events` from its source item before writing the
compatibility relationship. The graph now accepts that limited canonical-event
reducer only when the event, source item, immutable claim evidence, and
person/company/project endpoints agree exactly. Task-owned events are excluded
to avoid duplicate authority. A temporary-SQLite payment-event regression
proves both stored and read-only historical parity; no replay, backfill, or
live operation ran.

## 2026-09-02 — Completion-evidence consistency audit

`make tasks` now reports exact repository queue and active-ExecPlan
contradictions instead of only a single aggregate warning. Supplying
`NOTION_TASKS_JSON=export.json` checks an explicit metadata-only task export
for Done/Completed queue state, required Evidence Summary and Kind/Gate
metadata, and repository-ID agreement. It never reads task bodies or treats
Outcome prose as proof of completion. The initial audit exposes existing legacy
reconciliation findings rather than hiding them; no task state was rewritten.

The repository task ledger is now structurally reconciled: completed records
remain verbatim but reside only in Completed archive sections, and AM-074 and
AM-106 plans are catalogued as completed rather than active. `make tasks` now
passes against the checked-in queue.

## 2026-09-02 — Historical `as_of` timestamp canonicalization

External `as_of` datetimes now require an explicit timezone and are serialized
as canonical UTC before any ContextBuilder, conversation timeline/period, or
graph-parity SQLite comparison. Equivalent `+00:00` and `-04:00` instants have
identical temporary-SQLite results; naïve values fail before querying. The
graph diagnostic remains read-only. No schema, source-data, replay, repair, or
live operation ran.

## 2026-08-30 — Notion documentation control-plane reconciliation

Current documentation now reflects the existing Git baseline and configured
remote rather than the obsolete pre-initial-commit state. Architecture wording
names the People-first Textual UI as the normal product path and the retained
Rich renderer as compatibility/recovery maintenance UI. Historical task and
changelog records remain dated. No runtime or live-state behavior changed.

## 2026-08-30 — AM-120 deterministic task-context graph parity

The graph projector now derives person `involved_in` and company
`involved_in` / `associated_with` edges only from a task's current canonical
endpoints and that task's exact immutable claim. The bounded graph reader
requires both that reducer marker and claim evidence. A temporary SQLite
fixture proves parity with the equivalent legacy ContextService and
ContextGraphImprover relationships; confidence-only compatibility rows remain
outside the contract. No reader cutover, replay, repair, migration, or live
operation ran.

The same task-derived edges now receive a closing validity boundary when a
manual task-project decision supersedes the automatic task projection. The
regression covers all three person/company relationship kinds.

## 2026-08-30 — AM-077 project duplicate completion repair

Project creation now remains blocked whenever the normalized-name comparison
finds any candidate across non-merged canonical projects. The prior 80-row
cutoff and multi-candidate fall-through could create another project; Reviews
now retain the complete ordered candidate set for manual resolution. No schema,
source-data, or live operation ran.

## 2026-08-30 — AM-122 relationship and group-attribution correctness

Person Profile now uses entity type plus ID when selecting a relationship’s
other endpoint. For linked groups, Messages and communication statistics retain
only selected-person sender rows and explicit outgoing owner rows; unrelated
participants are excluded. Direct-chat totals are unchanged. The profile read
remains bounded and side-effect free.

## 2026-08-30 — AM-074 task-lifecycle repair unit

The fixture-only `task-lifecycle` unit selects only validated task items whose
immutable claim evidence closes over the item’s exact non-deleted source
message and whose lifecycle has no prior event or Review outcome. It stores
exact private item/claim/context membership, rejects stale dry-run scope, and
replays the existing `TaskReconciler` without re-resolving entities or projects.
Manual locks remain Review-only. No production apply command, migration,
backfill, or live operation was added.

## 2026-08-30 — AM-056 bounded cross-chat discovery

AM-056 now documents its supported V1 scope as Review-only cross-chat
person-to-project discovery. A candidate must include a project alias in its
exact source message as well as independent project evidence in another chat
for the same resolved person within 90 days. Unrelated same-person activity is
rejected; no canonical or graph state changes without existing manual Review
acceptance.

## 2026-08-30 — AM-120 owner parity command

`make graph-parity SEEDS="person:123"` runs the bounded ContextBuilder
readiness diagnostic through a read-only SQLite connection. It reports only
grouped relationship gaps, clipping, and a `ready` flag, allowing the owner to
establish the remaining real-reader gate without mutating or exposing the
relationship corpus.

## 2026-08-29 — AM-120 reader-parity diagnostic

The ContextBuilder cutover diagnostic now scores and caps compatibility
relationships exactly as the current reader does, instead of comparing an
unrelated first page of rows. A clipped seed/depth request is explicit and
cannot be treated as a green cutover result. The diagnostic remains read-only;
relationship authority and reader behavior are unchanged.

## 2026-08-29 — AM-074 segment repair unit

Fixture-only segment rebuilding now has the same receipt-gated, fingerprinted
restart contract as task-project repair. It selects exact chats privately,
rebuilds only task-anchored derived segments, rolls back a partial unit, and
returns the recorded outcome on retry. No operator command or live execution
exists.

## 2026-08-29 — AM-074 FTS repair unit

The fixture-only atomic FTS operation is now bound to a hash of its exact
authoritative inputs without exposing their content. Source changes reject stale
dry runs; the existing parity-checked writer and checkpoint complete together,
and a completed retry is a no-op. No operator command or live execution exists.

## 2026-08-29 — AM-074 conversation-context repair unit

Targeted context repair now carries the exact selected pending conversation
revisions through its dry run and checkpoint. It rejects stale scope and leaves
person/global invalidations pending, preventing profile/provider work from this
fixture-only path. No operator command or live execution exists.

## 2026-08-29 — AM-074 project-health repair unit

Project-health repair now fingerprints its bounded non-terminal project set,
canonical health inputs, and evaluation date. It uses the existing evaluator
without notifications, preserves terminal rows, rejects stale scope, and
returns the recorded result on retry. No operator command or live execution
exists.

## 2026-08-29 — AM-061 provider model registry

The registry now uses Groq's verified IDs and published local Developer-plan
limits for GPT-OSS 120B and Qwen 3.6, including a durable token-per-day guard.
120B is unavailable to ordinary extraction; Qwen is explicit ambiguous
reasoning; Compound Mini is an unstructured external-research route with no
canonical persistence caller. No provider request, migration, replay, backfill,
or live operation ran.

## 2026-08-29 — AM-087 materialization rebuild

Bounded active-person rebuild now reuses the sole contact materializer. It
clears only rows that writer owns, retains profile summaries and durable promise
loops, and is idempotent on temporary fixtures. No live operation ran.

## 2026-08-29 — AM-077 project quality

New project creation now requires a high-confidence project observation and an
explicit same-batch reference. Casual standalone labels remain observations,
while other names resolve existing aliases only. Likely duplicate names enter a
provenance-carrying Review; an accepted review links the observation to the
selected project. Existing project rows were not changed.

## 2026-08-29 — AM-056 cross-chat candidate discovery

The Context Graph operation can now queue bounded Review candidates from two
non-deleted exact source messages with the same resolved person across distinct
chats and time-local project evidence. Candidate payloads retain the evidence
path, confidence, and reason; Review acceptance remains the sole canonical
relationship path. No provider call, migration, replay, backfill, repair, or
live operation ran.

## 2026-08-29 — AM-108 historical-context truthfulness

An explicit `as_of` request now fails closed for mutable entity and task state,
global lifecycle totals, and current person materializations. It keeps only
identity anchors and interval/version/event-backed context, labels the package
partial, and excludes contact segments outside their half-open interval. No
migration, backfill, replay, or live operation ran.

## 2026-08-29 — AM-068 architecture review

The post-remediation review found no cohesive responsibility safe to extract
from remaining large modules. Existing packages retain their live ownership
boundaries; no architecture-only wrapper was added.

## 2026-08-29 — AM-065 supervised daemon example

Operations documentation now includes an optional portable systemd user-unit
template with explicit ownership, preflight, and a 30-second restart delay. No
host service was installed or enabled.

## 2026-08-29 — AM-097 evidence transaction ownership

EvidenceRepository no longer commits internally. Its current-state and version
history writes now participate atomically in the caller's transaction.

## 2026-08-29 — AM-090 relationship-path simplification

The sole runtime mutation of the inert `entity_relationships` compatibility
table is removed. Entity merge, retrieval, graph improvement, Ask, and Deep
Dive continue through the canonical temporal relationship model.

## 2026-08-29 — AM-064 configuration simplification

The legacy routing mode now resolves to quota-aware registry routing with a
diagnostic warning. Runtime screens show the effective registry and configured
models rather than a deprecated primary/fallback provider order.

## 2026-08-29 — AM-063 conversation freshness

Conversation materialization now advances its version only for semantic
content changes, while the evidence watermark follows archived source evidence.
Runtime status and profiles expose fresh, raw-pending, semantic-pending, and
materialization-dirty states without reading message content.

## 2026-08-29 — AM-060 Deep Dive truthfulness

Task Deep Dive's deterministic action is now labelled evidence lookup rather
than answer. It returns selected supporting evidence and citations only, or an
explicit unknown result; no provider synthesis is implied or performed.

## 2026-08-29 — AM-078 database integrity

Application connections now enable SQLite foreign keys before migrations and
runtime writes. The read-only database check also reports bounded logical
reference violations without a table rebuild, repair, replay, or live action.

## 2026-08-29 — AM-059 data-model truthfulness

Migration 23 adds structured and rendered global snapshot fields.
Existing snapshot text remains unchanged.

## 2026-08-29 — AM-058 routing fallback truthfulness

Typed daily quota exhaustion alone pins a compatible fallback. Other failures
stay temporary, and session-pinned fallback use retains its fallback telemetry
and explicit route kind. No schema, migration, replay, backfill, provider
request, or live operation ran.

## 2026-08-29 — AM-103 diagnostics truthfulness

History coverage now counts only current non-stale lifecycle records. Route
counts form one defined partition, unknown provider failures remain
router-attributed, and both monitors use actual routing state. The undefined
graph percentage is removed. No routing-policy, schema, migration, replay,
backfill, or live operation ran.

## 2026-08-29 — AM-091 generated text quality

Prompt speaker labels remain an internal AI protocol but are converted to
neutral human wording before derived summaries, item prose, and response
payloads are stored. Profile and discovery evidence displays use the same
neutral labels. Structured ownership and raw Telegram evidence remain
unchanged; no migration, replay, backfill, deletion, or live operation ran.

## 2026-08-29 — AM-112 Deep Dive session reproducibility

Migration 22 records investigation parameters and diagnostics. Session updates
replace selected evidence membership exactly; discovered-term selection uses the
stored evidence cutoff rather than wall-clock update time, and pins require
task-session evidence ownership. No live migration, replay, rebuild, or
source/canonical operation ran.

## 2026-08-29 — AM-111 multilingual Deep Dive

Deep Dive core concept discovery retains Unicode task terms without an
English-only stopword gate or a hard-coded current-deal thesaurus. Canonical
entities and evidence-derived terms provide bounded expansion. No migration,
replay, backfill, deletion, or live operation ran.

## 2026-08-29 — AM-110 conversation intervals

Project and contact segments now share a 90-day `[started_at, ended_at)` rule.
Same-project activity after an inactive period begins a new segment, while
confidence counts distinct source anchors rather than duplicate rows. No
migration, rebuild, replay, or live operation ran.

## 2026-08-29 — AM-109 local graph repair

Automatic repair now requires an unambiguous project with two distinct source
message anchors in the candidate's 90-day neighbourhood. One anchor is
Review-only; stale, competing, and manually rejected evidence cannot establish
canonical state. Derived task, event, and fact links close when their support is
corrected or disappears. No migration, replay, backfill, deletion, or live
operation ran.

## 2026-08-29 — AM-079 temporal fact authority

Automatic task/document fact projection and predicate-suffix replacement rules
are removed. The temporal repository now defaults changed values to Review;
only an explicit deterministic or manual caller may request state replacement.
Pending conflict replays are idempotent when they have exact source identity,
and acceptance rechecks the current predicate state within its transaction.
No migration, backfill, replay, deletion, or live operation ran.

## 2026-08-28 — AM-107 Deep Dive evidence integrity

Deep Dive now retains only task-demonstrable evidence. Temporal fact IDs are
stable; contextual facts remain background; structured and raw records require
exact or conservative task membership; duplicate provenance is deterministic.

## 2026-08-28 — AM-094 Ask Memory evidence/router pipeline

Ask Memory now selects a bounded deterministic mix of task, canonical, summary,
and direct evidence. Structured context is explicit non-citable background;
only router/provider failures return the local answer.

## 2026-08-28 — AM-088 conversation open-loop lifecycle

Scoped refresh now removes task-derived loops without a matching canonical
open/waiting task. Heuristic question loops remain low-confidence derived state:
only adjacent substantive replies resolve them, and questions older than 90 days
become resolved history.

## 2026-08-28 — AM-086 duplicate observation-event removal

Ordinary accepted observations no longer create generic context-event wrappers.
Semantic task, promise, payment, and project events remain. Context and profile
event views exclude legacy wrappers, while related retrieval and contact
timelines use the original bounded `ai_items` observation. No migration,
replay, deletion, or live repair ran.

## 2026-08-28 — AM-085 entity-memory active-path removal

Projection no longer copies accepted observation text into `entity_memory`.
Context, retrieval, generic profiles, and FTS now use bounded direct
`ai_items` rows with item provenance. Existing `entity_memory` rows remain
inert legacy state; no automatic cleanup, migration, replay, or live operation
changed.

## 2026-08-28 — AM-057 graph-refresh scheduling

Graph improvement now records its affected canonical conversation, entity, task,
and global scopes in the revisioned context invalidation ledger. It no longer
marks all high/critical rows in an affected chat stale, avoiding a deterministic
graph-to-AI re-analysis loop. This is a derived-context scheduling change only;
freshness metrics remain subsequent AM-057 work. No schema, replay, or live
operation changed.

Runtime context freshness now includes pending, running, and failed revisioned
refresh scopes as well as stale source interpretation. A high-value surface can
therefore report refresh-pending rather than falsely calling derived context
fresh. This is read-only reporting; no schema, replay, or live operation
changed.

The bounded runtime coverage snapshot now separately reports eligible archived,
classified, semantic, canonicalized, context-integrated, and conservatively
current-enough messages. Current-enough requires an integrated batch and no
pending refresh scope; dependency-revision comparison remains later AM-057
precision work. No schema, replay, or live operation changed.

The active AM-057 ExecPlan now records the required forward-only,
per-message dependency-revision design. Existing batch invalidation memberships
are the source of truth; automatic legacy backfill is explicitly excluded.

Migration 21 implements that plan: an accepted batch's exact scoped refresh
revisions are persisted per exact message membership in the same projection
transaction. Current-enough compares those dependencies with the durable
invalidation ledger. Legacy messages remain explicitly partial; no source,
claim, canonical, replay, or live operation changed.

## 2026-08-28 — AM-099 override eligibility closure

Forced and session-pinned model keys are now applied only after the normal
workload and required-capability eligible set is computed. A forced model can
remain selected and an eligible session model can still move first, but neither
can admit a short-only or capability-ineligible profile. No provider/model
expansion, schema, migration, replay, or live operation changed.

## 2026-08-28 — AM-052 effective configuration closure

`Settings.gemini_model` was an unused mirror of `gemini_primary_model`; it is
removed, leaving one effective primary-model field in runtime and direct test
construction. `GEMINI_MODEL` and `GGEMINI_MODEL` remain lower-priority
configuration-boundary compatibility inputs with warnings. The provider-wide
conservative RPM ceiling remains deliberately distinct from model-specific
quota profiles and is documented as such. No provider request, schema,
migration, replay, or live operation changed.

## 2026-08-28 — AM-067 person-context writer closure

The source audit found two remaining SQL bypasses for `person_context_state`:
the bounded, locally validated presentation summary and canonical-person merge
relocation. Both now call explicit `ContactContextMaterializer` methods, so the
materializer owns the table's SQL writes while profile, operational, and refresh
callers retain their existing contracts. The state remains rebuildable derived
context; no evidence, temporal facts, authority, schema, replay, provider, or
live operation changed.

## 2026-08-28 — Global refresh ownership

The explicit terminal operational refresh now queues and drains the durable
`global` invalidation scope rather than directly invoking operational refresh.
The worker owns the resulting global snapshot, project-health, and follow-up
refresh. Temporary-SQLite coverage proves the scope's revision stays pending
until this work completes.

## 2026-08-28 — AM-074 derived-state repair readiness inventory

AM-074 now has a bounded read-only inventory for task-project, segment-chat,
and pending-context repair candidates. It returns capped counts only, writes
nothing, and does not expose message content. Apply/resume behavior remains
separately gated behind dry-run, recovery, and explicit operator approval.

The dry-run command requires explicit named operations and emits a deterministic
scope fingerprint from the capped inventory. It rejects missing/invalid limits
before opening SQLite, remains read-only, and has no apply or resume mode.

The first fixture-only apply unit covers task-project linkage. It accepts only
a matching dry-run fingerprint plus a separate recovery receipt, records the
checkpoint in the existing metadata table in the same transaction, and returns
the recorded outcome on retry. No operator apply command is exposed.

The checkpoint retains the exact selected task IDs privately; the dry-run
report exposes only a digest. Retries therefore cannot move to newly eligible
tasks after state changes.

## 2026-08-27 — AM-120 manual-relationship authority parity

An accepted `graph_link` review now writes a manual person/company-to-project
graph edge alongside its compatibility row. `SemanticGraphProjector` also
supports explicit manual person-company and company-project edges. Manual
edges are bounded, temporal, and intentionally have no fabricated AI claim
provenance. Existing compatibility rows inferred from model confidence remain
excluded from accepted-graph reads. The bounded read-only ContextBuilder
parity diagnostic reports only grouped missing kinds at an `as_of` boundary;
it does not expose edge content or mutate either layer. No reader cutover,
relationship conversion, migration, replay, repair, or live action ran.
Temporary-SQLite tests cover all three relationship kinds, review acceptance,
observed-edge exclusion, and temporal expiry.

## 2026-08-27 — AM-075 durable retry closure

Migration 20 adds nullable `ai_jobs.retry_after_at` and an eligible-queue
index. It preserves every job and its ordered source-message membership, then
requeues only existing failed history jobs for the forward retry policy. Future
temporary all-route and context failures return history work to pending with
capped backoff; configuration and response-contract failures remain terminal.
Structured Gemini retry headers now win over textual delay parsing. Temporary
SQLite migration, retry, restart, route, and terminal-failure tests pass. No
live migration, repair, or provider request ran.

## 2026-08-27 — AM-075 quota-domain normalization

Normalized quota errors retain RPM/TPM/RPD/TPD dimension. Daily quota
exhaustion no longer takes the short retry path and instead sets a model-local
cooldown through the next UTC reset. No schema migration or live action ran.

Expired cooldown state now clears from both the in-memory tracker and the
current UTC usage row. Failed history jobs remain durably reclaimable; delayed
retry is intentionally deferred until it has a dedicated persisted schedule.

Gemini now classifies structured HTTP 429 metadata before text heuristics,
retaining the quota dimension and retry delay even when the response text is
unhelpful. No integration, schema, or live action ran.

Configuration and malformed/empty response failures are now explicit permanent
types. Invalid provider JSON is rejected before persistence and does not enter a
retry path. No schema or live action ran.

## 2026-08-27 — AM-071 task lifecycle closure

Task reconciliation now has bounded, source-aware candidate matching and
idempotent manual/rejection authority. Conflicting anchors cannot merge by
title similarity; fuzzy matches require compatible task kind and temporally
near evidence; exact-title terminal lifecycle updates remain linked. Historical
repair remains explicitly AM-074 work. No migration, replay, backfill, or live
action ran.

## 2026-08-27 — AM-072 source-backed project health

Project health now derives activity from dated canonical task evidence,
project-linked observations, temporal events, and conversation intervals. A
real overdue open/waiting task is critical; a project without activity is stale,
and recent project evidence can be active without a task link. No migration,
backfill, or live recomputation ran.

## 2026-08-27 — AM-071 conservative task candidate matching

Task reconciliation now excludes a same-chat candidate whenever a populated
incoming person, company, or project anchor conflicts with that candidate's
populated anchor. Matching anchors are preferred; a sparse historical candidate
must have an exact normalized title. Candidate selection is bounded to 50 rows.
Temporary-SQLite coverage proves conflict prevention, anchored terminal update,
the existing unanchored boundary, and the shared manual rejection lifecycle
audit. No schema migration, historical replay, backfill, or live action ran.

## 2026-08-27 — AM-120 bounded graph reader contract

`current_authoritative_edges` now provides a bounded, read-only future-reader
contract over current canonical graph edges. Automatic output is restricted to
the existing task-to-project reducer allowlist and requires exact immutable
claim evidence; observed, source-less accepted, and expired edges are excluded.
Manual edges remain usable without fabricated AI provenance. No existing reader
uses this contract yet; temporary fixtures make the unsupported current
person/company relationship types explicit. No relationship conversion, schema
migration, replay, repair, provider request, or live action ran.

## 2026-08-26 — AM-106 physical provider request ownership

Providers now perform exactly one cancellable Gemini or Groq transport attempt.
The router owns per-physical-attempt retries, conservative model pacing,
quota/event accounting, and success/failure telemetry for extraction and
grounded Q&A. It estimates system, schema, and user content without retaining
prompt text, and normalizes returned Gemini/Groq usage for durable counters.
An unconfirmed Groq cancellation is recorded but cannot overlap a fallback.
Temporary-SQLite/fake coverage proves retries, schema overhead, answer usage,
and the withheld-fallback path. No migration, replay, provider request, or live
action ran.

## 2026-08-26 — Repository control-plane reconciliation

The current-source audit confirms that the remediation baseline is historical,
while the open implementation boundaries remain AM-053, AM-071, AM-075,
AM-104–AM-106, and AM-120. `make check` passes 223 temporary-SQLite tests with
Ruff, formatting, and MyPy; `make docs-check` passes. The completed
engineering-harness record that reused the active AM-105 identifier is assigned
unused ID `AM-123`, so AM-105 now unambiguously means provider request lifecycle.
No product behavior, schema, source data, provider request, replay, repair, or
live maintenance action changed.

The AM-062 documentation-reconciliation leaf also updates stale AM-053 and
AM-067 task evidence: the revisioned invalidation ledger and single
person-context writer are implemented controls, not missing foundations. The
remaining work is limited to any caller-proven scope or ownership gaps.

## 2026-08-26 — AM-102 strict-contract closure

AM-102's reported silent-repair gaps were already closed in the current
provider-neutral extraction contract. Providers preserve decoded transport JSON;
the repository validates the unchanged top-level payload before acceptance,
records top-level failures as diagnostics, and retains invalid individual items
as durable rejections. The contract covers confidence bounds, task/informational
status combinations, canceled tasks, and explicit nullable project association.
Focused provider, repository, and semantic-projection tests pass. No code,
migration, replay, or live action ran.

## 2026-08-26 — AM-104 selected-provider execution

The router now sends one explicit provider analysis request containing the
selected provider, model, and applicable RPM limit. Gemini and Groq share this
contract; Groq invokes the selected model rather than always using its default.
The router validates returned execution identity before success accounting, so
it cannot rewrite a mismatched result into apparent compliance. No model
expansion, migration, replay, or live action ran.

## 2026-08-26 — AM-105 cancellable Gemini lifecycle

Gemini now sends analysis and answer requests through the official async client
instead of a worker thread. A timeout cancels the in-flight coroutine before
the router moves to fallback; internally owned Daily and History routers close
their provider client, while injected routers remain caller-owned. No migration,
replay, or live action ran.

## 2026-08-26 — AM-100 source-mutation reanalysis

The Telegram archive writer now marks existing AI interpretation and local
classification stale when an accepted source edit or first deletion changes a
message. An eligible edit can use the existing versioned exact-membership job
path; deletion retains source history but stays excluded from provider work.
Repeated deletion creates no duplicate version. Temporary-SQLite writer and
job tests pass. No migration, replay, reconciliation, or live action ran.

## 2026-08-26 — AM-098 lifecycle truthfulness

The Telegram SQLite writer now advances its saved-message counter and signals
automatic analysis only after a successful commit. Reconciliation and shutdown
race the queue drain against the writer task, so a failed writer is propagated
instead of leaving callers blocked on unfinished queue work. Daemon startup
does not claim active after local-mode recovery, scheduled briefs skip stale
data after reconciliation failure, and incomplete cleanup is reported without
masking an earlier failure. Fake and temporary SQLite tests cover each path.
No schema, migration, replay, or live operation ran.

## 2026-08-26 — AM-099 routing truthfulness

Automatic Daily analysis now consumes the background quota priority while a
manual Daily run retains interactive priority. The existing registry has
distinct short and context-workload candidate policies, filters profiles that
cannot meet a structured-output request, records a deterministic policy reason
with route diagnostics, and no longer exposes an unused long-context flag. No
provider/model expansion, migration, or live operation ran.

## 2026-08-26 — AM-101 saved-result recovery

Daily and History processing now distinguish provider failure from work that
happens after a provider result has been durably saved. Pending or failed
projection/integration resumes from the saved batch before new provider work;
an injected post-save error leaves one successful batch and does not reclaim
the completed job. Context-assembly failure records a retryable failed job
instead of stranding it as running. No migration or live operation ran.

## 2026-08-26 — AM-093 scoped contact search and exact context evidence

The Textual “Search this contact” path now uses explicit canonical person
retrieval instead of global lexical retrieval. ContextBuilder's supporting
evidence now closes only over exact source chat/message pairs from selected
canonical rows or their immutable claim evidence; a newer unrelated message
from the same chat is rejected. Unresolved ordinary context requests no longer
fall through to global tasks or events. Retrieval ranking preserves distinct
chat/date provenance for daily and monthly summaries without numeric source IDs,
and related historical retrieval omits future task state while selecting the
fact interval valid at `as_of`.
Task Deep Dive no longer imports raw context evidence as related-chat expansion
input. No source, canonical state, schema, migration, replay, repair, or live
action changed.

## 2026-08-26 — AM-093 SQL and FTS candidate parity

SQL fallback now requires the same bounded all-term candidate set as FTS, while
remaining independent of query word order. Temporary SQLite coverage proves a
matching message is selected in either word order and that a partial-term-only
message is rejected by both retrieval stages. No source, canonical state,
schema, migration, replay, repair, or live action changed.

## 2026-08-26 — AM-122 direct-connection briefing evidence

The representative Person Profile briefing fixtures now include a direct
company connection and prove it retains only its exact cited message. This is
read-only presentation coverage; no schema, source, model, projection, or live
operation changed.

## 2026-08-26 — AM-122 command-palette regression

Textual command filtering now awaits row removal before mounting filtered
commands, preventing duplicate widget IDs during normal keyboard use. No
schema, source, provider, migration, or live action changed.

## 2026-08-26 — AM-122 profile-workflow regressions

Textual profile coverage now proves task changes require explicit confirmation
and contact search excludes matching records owned by another person. No
schema, source, provider, migration, or live action changed.

## 2026-08-26 — AM-118 current-state reconciliation

Reconciled the initial application-review findings against the current source,
tests, and ordered migration ledger. Exact AI job membership, strict local
validation, durable projection states, transactional canonical projection,
revisioned invalidation, the single contact materializer, quota-aware settings,
routed Ask Memory, and frozen migration ownership are implemented controls,
not current gaps. `DATABASE_MIGRATIONS.md` now lists migration 16 with the
complete 1–19 sequence. The remaining remediation stays with AM-053, AM-071,
AM-075, and AM-120; no runtime, schema, replay, repair, or live action ran.

## 2026-08-26 — AM-120 relationship cutover inventory

AM-120's required caller inventory confirms that `relationships` remains an
active compatibility model for context traversal, deterministic project
resolution, Person Profile/scan evidence closure, People discovery, and
diagnostics. Its writers include accepted-item context projection, graph
improvement, and Review acceptance. The semantic graph's only automatic
accepted edge is task-to-project, so an immediate reader conversion would
discard or over-authorize person/company-to-project state. The next increment
must establish bounded graph-query and projection-authority parity before any
consumer moves. No schema or runtime behavior changed, and no replay, repair,
or live action ran.

## 2026-08-26 — AM-075 transient provider classification

Gemini now classifies reachable HTTP 500/502/503/504 responses as a typed
transient server failure rather than a provider-transport outage. The bounded
retry/fallback path remains available, but the router does not suppress sibling
Gemini models with its five-minute transport-health cooldown. Exact
DNS/connectivity failures remain provider-scoped. Focused temporary-SQLite
provider and router tests pass; no migration, provider request, or live action
ran.

## 2026-08-26 — AM-122 contact-briefing representative coverage

The deterministic, read-only pre-contact briefing now has synthetic coverage
for long unlinked history plus a newer direct group-context record. Its last
interaction remains the canonical row's exact message rather than a nearby raw
message; changed-context output remains bounded and each row retains the same
source reference. Existing sparse/ambiguous and supported/unsupported-project
fixtures cover unknown and mixed-project cases. No schema, source, AI,
projection, or live operation changed.

## 2026-08-26 — Targeted Notion project-memory workflow

Added project-native Codex skills for targeted Notion context, search, status,
task matching, and selective write-back. The project lifecycle hooks remain
deterministic and private-safe: SessionStart states that context is lazy,
UserPromptSubmit only emits a short history cue, and Stop asks for a durability
check without automatic persistence. Repository evidence and current code stay
authoritative for implementation; Notion supplements product intent and prior
decisions. No Alex Memory product behavior, schema, source data, provider call,
migration, or live maintenance action changed.

## 2026-08-26 — AM-118 baseline and Textual profile recovery

The AM-118 quality baseline reproduced a fresh-router cooldown failure: routing
telemetry writes its day in UTC, while cooldown reload used the host-local day.
Reload now uses UTC consistently, so persisted active cooldowns remain visible
after restart across a date boundary. This is a routing-only correction; it
does not affect evidence, observations, canonical projection, schema, or live
state.

The same full gate exposed the queued AM-122 primary Textual profile blocker:
the mounted `ProfileScreen` referenced four absent presentation helpers. One
bounded section/record model now drives all eight bound sections, record
details, and exact-evidence drill-down. Synthetic Textual coverage opens each
section and verifies a cited fact reaches its exact message. No migration,
scan, backfill, or live maintenance action ran.

## 2026-08-25 — Person Profile action-path audit

The primary Textual Deep Scan screen previously only created profile-lane jobs;
the fallback Rich screen also claimed and processed them. Both now call the
same bounded `enrich_person()` path, so a requested scan actually reaches the
existing validated extraction, projection, invalidation, and profile-refresh
flow. The profile summary package also excludes third-party and inference rows
entirely, rather than merely filtering their source selection.

The default interactive shell remains People-first and `/` opens its compact
action palette. Only People, Review, System Status, and explicit Maintenance
are exposed there. Maintenance now includes `full_refresh` (also
`resync_profiles`): it runs the existing current-archive reconciliation and
eligible history analysis, then rebuilds materialized person context and only
hash-changed presentation summaries. It preserves raw evidence, semantic
claims, canonical state, temporal history, and manual authority. No live
operation was run for this change.

Follow-up: queued profile windows are now drained before new windows are
created, preventing a previous queue-only backlog from growing on every resume.
The Deep Scan screen labels the ready backlog separately from eligible evidence:
Enter processes the next two windows, while explicit `L` processes at most 64
already queued windows. Each underlying provider request remains an exact,
bounded durable job; failed windows remain visible and retryable.

Follow-up: Person Profile presentation is more compact. Its communication
total now aggregates all linked conversations independently of the bounded
conversation breakdown. Deep Scan exposes `AI completed / eligible evidence
messages`, separates pending and running work, and updates the local screen
while an explicit live run processes up to 64 queued windows. The unreachable
Textual Ask screen was removed; the retained Rich profile is still the recovery
terminal caller and was not removed.

Follow-up: the Textual Deep Scan action now returns from its key handler before
provider work completes. It owns one tracked UI task that observes the existing
bounded profile-lane worker, so the screen remains interactive and renders
durable running/completed/failed state. The live tick avoids re-counting the
entire eligible message history; detailed eligibility refreshes on entry and
completion. A metadata-only analysis audit shows persisted direct/third-party/
inference claim counts, bounded rejection reasons, and recent job outcomes. It
does not expose raw messages, model payloads, or new persistent logs. No live
scan, migration, rebuild, or backfill ran.

Follow-up: Deep Scan now renders separate evidence and window progress bars.
The current extractor version constrains the visible status, audit, and shared
profile-worker claims, so legacy profile jobs cannot inflate v2 coverage or run
behind a v2 scan. No live scan, migration, rebuild, or backfill ran.

## 2026-08-24 — Deep Person Profile claim authority

Migration 19 adds nullable Deep Person Profile metadata to immutable semantic
claims: selected person, assertion kind, and effective interval. Profile
extractor v2 emits this metadata under the existing bounded profile job lane.
Local persistence validates direct sources against the Telegram identity of the
selected person; direct rows use the established observation/projection path,
while third-party and inference rows remain evidence-backed semantic claims
only. The profile reader renders those uncertain claims separately, with exact
message ID, timestamp, speaker, confidence, and effective-period data; direct
private details stay in a separate section. No live migration, scan, rebuild,
or backfill ran.

## 2026-08-24 — Textual terminal increment

Added a Textual People-first home screen backed by bounded read-only canonical
discovery, deterministic fuzzy ranking, relative display dates, compact
runtime status, a person overview, and Ctrl+K palette. Startup and daemon
contracts are unchanged; no migration or source write ran.

Follow-up: discovery now debounces typing and reads its one-to-many search
dimensions independently, avoiding join amplification. Person detail renders
the existing bounded canonical profile sections and exact citations rather
than a summary-only card.

Person detail now navigates contact brief, loops, context, relationships,
timeline, communication, exact evidence, scan state, private-direct details,
and uncertainty. The command palette provides complete protected operations.

Deep Scan now has a profile-local status and queue screen. It explains the
bounded exact-evidence job and shows eligible, completed, pending, and failed
windows before a deliberate Enter queues work.

## 2026-08-24 — Deep Scan authority and lane isolation

Migration 18 reconstructs only `ai_jobs` to add the durable `profile` lane,
copying all existing job metadata and retaining the separately stored exact
job-message membership untouched. Manual Deep Scan now claims only that lane.
Its selected messages must be authored by the resolved canonical person; this
keeps a user's or third party's statement from automatically changing the
contact's facts, role, capability, company, or relationships. The tradeoff is
explicit: missing/ambiguous authorship leaves a window unscanned rather than
inferring authority. Temporary-SQLite tests cover job preservation, membership
preservation, profile-lane insertion, exact worker claim, and unresolved-author
exclusion. No live migration, scan, rebuild, or backfill ran.

## 2026-08-24 — Full direct-history Deep Scan context

Deep Scan now queues the complete resolved direct conversation in bounded,
chronological windows, rather than only the contact's individual messages.
This gives profile extraction the conversational context needed to understand
commitments and changes. Before saving any profile-lane item, the persistence
boundary confirms its exact cited message was authored by the selected canonical
person; items cited to owner or other participants are stored as rejection
diagnostics and create no claim, observation, or canonical state. Accepted
items continue through the existing projection, invalidation, materialization,
and presentation-summary refresh path. No migration, live scan, rebuild, or
backfill ran.

## 2026-08-24 — Person Profile enrichment audit

Audited the manual Deep Scan handoff and profile-summary freshness without
opening a live database. The temporary-SQLite regression fixture proves a
person-scoped window is claimable through the shared worker using precisely its
persisted message membership. Deep Scan feedback distinguishes failed retryable
windows from an empty scan, and the profile panel no longer calls an empty
candidate set ready. Summary freshness now hashes the bounded, displayable
canonical profile rows as well as their exact evidence messages, so canonical
projection changes request a new presentation-only summary even if they cite an
existing message. No migration, scan, rebuild, backfill, or canonical write
path was added.

## 2026-08-24 — AM-096 migration ownership

Migration 1 now creates only its stable baseline. Tables owned by migrations
4–10 are not pre-created during bootstrap, so a fresh temporary database
executes their named ledger entries rather than receiving a hybrid schema.
The historical compatibility additions are fixed snapshots: migration 2 owns
only pre-ledger tables, while migration 7 owns the later classification column.
The tests prove bootstrap omission, fixed runtime maps, fresh convergence, and
legacy adoption. No schema version was added, no live database was opened, and
no repair/backfill ran.

## 2026-08-24 — Person-first terminal workflow

Refocused normal terminal navigation on People discovery and Person Profiles.
The read-only profile now has compact overview and detail sections, canonical
identity-review state, current topics, and direct-chat-only response metrics.
Discovery is person-only and bounded over existing names, aliases, Telegram
accounts, projects, and current facts. Non-profile operations remain intact but
are hidden behind `:maintain`. No migration, backfill, graph mutation, or live
database action ran.

## 2026-08-24 — Routed Ask and truthful scoped retrieval

Ask Memory now sends its bounded grounded-answer prompt through `AIRouter`.
Gemini and Groq implement the same router-selected answer contract; normal
route telemetry, quota checks, provider health, and the local deterministic
fallback remain in effect. The model receives a bounded retrieval evidence set
with stable numbered citation identities, while presentation-only canonical
context stays non-citable background.

`retrieve_related()` now queries explicit canonical task/event/fact links
instead of delegating to name search. Its temporal fact query honours `as_of`;
current materializations are deliberately not emitted as historical truth.
Temporary-SQLite configuration, retrieval, routing, context, and migration
fixtures pass. No live migration, repair, replay, or provider request ran.

## 2026-08-24 — Person Profile v1

Added a bounded, read-only terminal Person Profile from canonical people,
aliases, facts, relationships, tasks, follow-ups, conversation context, events,
and explicitly linked Telegram chats. Evidence resolves by source claim first,
then by direct stored message reference; it never substitutes a newer message
from the same chat. Migration 16 adds a presentation-only cited AI summary to
the existing `person_context_state` row. The summary runs through the existing
router during person invalidation refresh, cannot create canonical state, and
leaves the prior completed summary intact when its refresh fails. No live
migration, profile backfill, graph maintenance, or corpus replay was run.

## 2026-08-24 — Temporal graph projection

Added forward migration 15 and `SemanticGraphProjector`, the only writer for
new graph rows. New compatibility observations reference their immutable claim;
accepted task-to-project reductions receive an exact claim-linked temporal
graph edge, while claim links remain observed. Canonical tasks and newly
written context events/facts retain claim lineage. The old relationship table
is still an active compatibility path, so this increment does not convert
historic rows, declare the table read-only, replay a corpus, or run live
maintenance. Focused temporary-SQLite graph lineage, non-acceptance, and
idempotency coverage passes; an active manual task-project edge blocks an
automatic replay.

## 2026-08-24 — Semantic claim foundation

Added migration 14 and an immutable semantic-claim persistence boundary.
Validated legacy observations now produce a deduplicated claim in the same
transaction, with exact source-message rows and optional unresolved entity
references. The migration also creates temporal graph tables and claim lineage
columns, but has no graph projector or historical conversion: current canonical
behavior remains intact until AM-120. Focused temporary-SQLite claim,
AI-pipeline, and migration tests pass.

## 2026-08-24 — Application review and remediation plan

Reviewed architecture, source ownership boundaries, persistence handoffs,
failure paths, task backlog, quality signals, and the temporary-SQLite test
suite. Added AM-118 as the cross-cutting execution plan that orders existing
work by prerequisite rather than creating a competing implementation backlog.
The review made no application, schema, or live-state changes. The full check
once reported one AI router/job failure after 176 passing tests; the focused and
adjacent router suites then passed, so AM-118 requires a reproducible baseline
before accepting related changes.

## 2026-08-24 — End-to-end AI extraction lifecycle

Changed the extraction path to contract version 2. Provider transport parsing
now preserves malformed top-level output as a durable batch diagnostic; local
validation accepts valid observations independently and stores rejected items
with stable reasons. Migration 13 adds exact job membership/fingerprints,
projection and integration state, explicit project names, and revisioned
context invalidations.

Canonical projection is a transactional, idempotent `process_ai_batch` phase;
provider calls are never repeated for a projection failure. Its downstream
work is now the bounded `refresh_pending_context` worker. This change did not
run a live migration, repair, corpus replay, or graph-maintenance action.

## 2026-08-24 — Task-project links

Task projection now resolves project links from bounded deterministic evidence.
Strong candidates apply automatically; weaker candidates are reviewable and
deduplicated. Existing links remain authoritative, and repair is explicit,
bounded, and rebuilds only affected conversation periods.

## 2026-08-24 — Direct-chat identity

Direct-chat ownership now uses the Telegram peer identifier before prompt
assembly and canonical projection. Explicit unclaimed usernames may attach an
existing person; display-name collisions create a peer-keyed person and merge
review candidate. Direct-chat materialization belongs only to that peer contact.
The new repair helper is bounded and caller-controlled; no live action occurred.

## 2026-08-24 — Read-only terminal workflow

Changed terminal navigation, confirmation, filtering, evidence detail, and
local-only recovery behavior. No database migration was required.

Follow-up and Today selections now resolve their canonical task or exact source
message, and review detail accepts both direct and source-prefixed references.

Follow-ups now support explicit confirmed state changes after evidence preview.
The manual decision is append-only feedback; completed and cancelled rows get a
resolution time, while reopening clears it. No migration or backfill was
required.

Task updates now use separate task-ID and constrained action prompts. The
existing source preview, manual-status confirmation, and Deep Dive action are
unchanged. No migration or backfill was required.

Follow-ups remain persisted because they capture explicit operator reminder
state. Their automatic waiting-task projection now reconciles on operational
refresh: it cancels obsolete automatic reminders and reopens them if the
waiting condition recurs, without overwriting manually recorded state. No
migration or backfill was required.

Opening Daily Brief now reads only today's stored payload. The separate
Generate Daily brief command is the explicit write path. No migration or
backfill was required.

## 2026-08-24 — Durable background intelligence scheduling

Changed:

- Replaced competing periodic Daily and History callbacks with one scheduler
  woken after a committed message batch. It coalesces bursts, independently
  rechecks SQLite evidence and durable jobs at startup and a maximum delay,
  and serializes automatic work through the existing analysis lock.
- Live Daily work now blocks History dispatch. A new durable live message makes
  an in-flight History run yield before its next provider call; unfinished
  History jobs remain pending. Provider errors are recorded for runtime status
  and a later wakeup may retry without affecting Telegram ingestion.

Database:

- No migration or backfill. The scheduler uses existing raw messages,
  classifications, and `ai_jobs` as durable state.

Verification:

- Temporary-SQLite tests cover committed-writer wakeups, restart recovery,
  burst coalescing, busy work, live-over-history priority, failure recovery,
  and the maximum-delay recheck.

## 2026-08-24 — Measured Codex workflow guardrails

Changed:

- Added six scoped project skills and project-local Codex hooks for session
  context, canonical environment guidance, private-path and destructive-command
  checks, changed-Python feedback, verification evidence, and legacy/AI-slop
  review.
- Added `make codex-hooks-check`; it validates hook JSON, compiles scripts in
  memory, and exercises private-safe sample events without reading private
  project data.
- Installed only distinct Codex integrations: Plugin Eval, Context7, selected
  Trail of Bits testing/security skills, and the curated Python simplifier.
  Codex Security was evaluated then removed because its static score was F/8,
  with high instruction cost and an overlapping scan role.

Fixed:

- Removed a dead runtime-status binding and restored missing UI imports found
  during the cleanup audit. This is behavior-neutral and returns static checks
  and UI collection to green.

Database:

- No migration and no source/archive data changes.

Verification:

- Hook validation, six skill validations, Plugin Eval static analysis, all 13
  UI tests, Ruff, formatting, MyPy, and compilation pass. The full `make check`
  run was stopped after the pre-existing AI-router suite emitted no output for
  90 seconds; it reported no failure before interruption.

## 2026-08-24 — Authoritative runtime status

Changed:

- Added one read-only `RuntimeStatusService` and routed both the terminal home
  panel and full status screen through its snapshot. It reports Telegram
  connection/archive lag, SQLite writer state, AI backlog/current route/quota
  cooldown, history coverage, context/graph maintenance, review load, compact
  recent errors, and data-quality ratios.
- Added explicit live-sync lifecycle phases. A failed startup is `FAILED`;
  `RETRYING` is reserved for a periodic reconciliation recovery path that is
  actually scheduled. A completed writer task with an exception becomes a
  fatal runtime state even when the Telegram client remains connected.
- Added quality indicators for FTS coverage, task-project links, actionable
  tasks, project-health validity, classification unknown rate, source-contact
  identity coverage, and context freshness.

Database:

- No migration, backfill, or live data change. The status service makes only
  bounded read-only SQLite queries over existing durable evidence and derived
  state.

Verification:

- Synthetic temporary-database snapshots cover healthy, processing, behind,
  startup-failed, retrying, rate-limited, offline, data-quality-warning,
  writer-crash, and fatal states. Home and status rendering both consume the
  same snapshot.

## 2026-08-24 — Truthful versioned message classification

Changed:

- Bumped deterministic classification to v2. Forwarded provenance no longer
  forces external-news scope; actual news requires news evidence, and private
  groups remain private by default.
- Reordered content classification so operational requests/payments/meetings
  win over generic question syntax. Added bounded English, Russian, and Georgian
  signals for common requests, promises, decisions, payments, and meetings.
- Persisted only source-time-stable `dated`/`unknown` relevance. Consumers derive
  `current` versus `historical` at an explicit `as_of` time. Context signals now
  use source message time/order, not reclassification time.
- Existing bounded classification work selectively revisits v1 unknown, stale,
  high-value, forwarded, and actionable-question rows without provider calls;
  approved manual classification reviews are excluded.

Database:

- No migration and no live data changes. `message_classifications` remains
  rebuildable derived state sourced from current raw messages and bounded local
  context; raw evidence and manual review authority are preserved.

Verification:

- Focused tests cover multilingual operational fixtures, decision/payment/
  meeting/promise routing, forwarded private evidence versus news, private
  groups, source-time context, as-of age derivation, selective reclassification,
  and manual-review preservation.

## 2026-08-24 — Engineering harness and temporal Daily Brief repair

Changed:

- Moved project dependencies to PEP 621 and created `uv.lock`; added
  reproducible sync, dependency declaration, and vulnerability-audit commands.
- Added compact quality/security/plan documentation, repository-local Codex
  skills, read-only review roles, destructive-command guardrails, and editor
  tasks. The fast check now also validates maintained developer tooling.
- Replaced the requirements-file installation path with `uv sync` throughout
  developer-facing documentation and actionable dependency errors.
- Reconciled the newly initialized, uncommitted Git workspace in developer
  guidance and change reporting; session-lock files are ignored as private
  session material.

Fixed:

- Daily Brief task creation now uses the immutable `task_events.created`
  source evidence date, so a later task update cannot move historical work
  into the wrong brief.
- An FTS-rebuild failure now rolls back all dropped/rebuilt derived tables,
  triggers, parity work, and its migration-ledger record; a regression forces
  trigger creation to fail and confirms the previous FTS state survives.

Database:

- Took a SQLite API backup, then applied the existing migration 12
  (`fts_lifecycle_rebuild`). It rebuilds only derived FTS indexes; raw evidence
  and canonical records were not altered. The database is now at schema
  version 12 with source/index parity. FTS5 capability is explicit, all active
  indexes are maintained across insert/update/delete, and only a genuinely
  unavailable FTS5 module uses SQL fallback.

Verification:

- Full pytest/Ruff/MyPy gate, generated-document check, lock check, deptry,
  pip-audit, SQLite integrity check, Codex rule evaluation, and skill
  validation are recorded in the AM-092 ExecPlan.

## 2026-08-24 — Repository quality hooks

Changed:

- Initialized local Git metadata and added `make hooks` for reproducible
  pre-commit installation.
- Aligned the Ruff hook with the locked 0.16.4 toolchain and added an
  `uv-lock` hook to keep dependency metadata synchronized.

Database:

- No migration and no data changes.

Verification:

- The hook configuration validates; `make lock-check`, `make hooks`, and
  `make docs-check` pass. A full hook run has no files to select until this new
  local repository has tracked files.
- `make check` was interrupted while the existing router test suite was still
  running; it emitted no failure before interruption.

## 2026-08-22 — Gemini quota provider-wide fallback

Changed:

- A Gemini quota response now cools down the provider as a whole for Google's supplied retry period, so the router does not probe Gemini 3.1 before Groq.

Verification:

- `tests/test_ai_router_and_jobs.py` verifies that one quota response creates one Gemini attempt and one Groq request.

## 2026-08-22 — Gemini connection-health fallback

Changed:

- Classify Gemini DNS and network connection failures separately from quota responses.
- A connection failure now places the Gemini provider on a five-minute in-process health cooldown, skips the second Gemini model, and routes immediately to Groq for the rest of the active history run.

Verification:

- `tests/test_ai_router_and_jobs.py` verifies that a Gemini connection failure triggers exactly one Gemini attempt and one Groq fallback.

## 2026-08-22 — Workload-aware AI routing

Changed:

- Added a central model registry for Gemini 3.5 Flash Lite, Gemini 3.1 Flash Lite, hosted Gemma 4 31B, and Groq, with workload-specific preference order and operator overrides.
- Added conservative token estimation, Gemma input guarding, local RPM/TPM admission checks, a primary daily reserve, and route pinning after a successful alternative.
- Added `AI_ROUTING_MODE=quota_aware` and documented model/quota configuration. Existing direct provider settings remain supported through `legacy` mode.
- Expanded the AI monitor with today’s per-model aggregate usage, cooldown/error status, and recent decision outcomes.

Database:

- Migration 11 (`ai_routing_usage`) creates `ai_model_usage` and `ai_route_events`. These tables retain only aggregate counters, route metadata, compact errors, and timestamps; no prompts, raw provider responses, or credentials.

Verification:

- Routing tests cover Gemma preference and input-guard fallback; migration, configuration, existing provider, and UI monitor coverage remain green.

This journal records consequential technical changes. Entries must be grounded in reviewed implementation and schema changes; it is not a substitute for `CHANGELOG.md`.

## 2026-08-22 — Local environment normalization

Changed:

- Explicitly pinned every current non-secret runtime default in the local
  `.env`, covering retry/output budgets, bounded history work, contextual
  memory selection, and Task Deep Dive limits.
- Retained the three existing unconsumed local keys as inert compatibility
  entries; they do not alter runtime behavior.

Database:

- No migration and no data changes.

Verification:

- Confirmed that settings load successfully without rendering credentials and
  that all active settings are now explicit.

## 2026-08-22 — Focused architecture boundaries

Changed:

- Moved bounded AI prompt-context assembly out of `ai.repository` into
  `ai/context.py`; durable job claiming and result persistence remain in the
  repository.
- Split contact-context materialization from query/package assembly. The new
  `context/contact_materializer.py` owns incremental derived-state updates,
  while `ConversationContextService` owns bounded retrieval and rendering.
- Moved canonical entity-profile rendering from the general terminal screen
  module into `ui/profile.py`.

Compatibility:

- Public application and context APIs are unchanged. This is a behavior-neutral
  refactor; no migration or data rewrite is required.

## 2026-08-22 — Visual AI request monitor

Changed:

- Replaced text-only history activity lines with visual committed-message, request, fallback, and Gemini-pace metrics.
- Added the **AI monitor** terminal entry and show it automatically during **Analyze all history**, with current jobs, provider/model route, configured pacing, last-hour request totals, fallback/error counts, and recent request reasons.
- While a provider request is in flight, history now keeps an animated live panel on screen with the active chat, model route, pace, run totals, and latest error.
- The monitor now separates direct Gemini and completed Groq requests for the last hour and preserves the fallback reason on successful fallback rows.

Database:

- No migration and no data changes. The monitor reads existing jobs and batch diagnostics.

## 2026-08-22 — Stall-resistant AI history

Changed:

- A history window is now marked `running` only while it is actually being
  sent to a provider; other bounded windows remain queued.
- The live panel refreshes its elapsed time plus the current provider/model,
  provider state, and latest provider error while the request is active.
- Gemini quota fallback has a 60-second cooldown, then Gemini is eligible
  again instead of being disabled for the rest of the full-history run.
- Gemini quota feedback now preserves the provider's quota category and retry
  delay in a compact, non-raw diagnostic, making a real daily quota response
  distinguishable from an RPM pacing issue.
- Interrupting the animated history request now requeues its active job instead
  of recording event-loop shutdown messages as provider failures.
- A short Gemini `RetryInfo` cooldown now waits and retries Gemini once before
  selecting Groq; the live request panel shows the remaining primary retry
  time instead of showing a Groq fallback immediately.
- Groq fallback starts directly with JSON-object output rather than making its
  incompatible strict-schema preflight and then a second request.
- Groq request and client-close cancellation are now detached after bounded
  deadlines, so an SDK task that ignores cancellation cannot freeze history.
- A successful fallback is pinned for the rest of a history run, avoiding
  repeated attempts against a provider that has already rejected the session.
- Gemini and Groq calls have a configurable 45-second default timeout. Groq
  now recognizes its `Failed to validate JSON` strict-schema response and
  retries in JSON-object mode.

Database:

- No migration. Interrupted jobs continue to be returned safely to `pending`
  when the application starts.
- The existing three event-loop-shutdown artifact rows were removed only after
  a SQLite API backup, and their associated history jobs were returned to
  `pending`.

## 2026-08-22 — Unified conversation intelligence

Changed:

- Added `ConversationContextService`, a source-grounded contact perspective over
  the existing context graph. It materializes contact periods, a lightweight
  current thread, person/project context, and reusable open loops without
  duplicating tasks or raw evidence.
- Accepted batches refresh only their affected people/conversations. A
  single-resolved-person dialog receives compact contact background before
  semantic extraction; the prompt explicitly forbids treating it as new
  evidence.
- Person profiles and person-scoped answers now surface contact summaries,
  active projects, and linked operational context. Contact timelines combine
  canonical events, tasks, and classified important source messages with
  deduplication.
- Added bounded, conservative question-to-answer links. Both endpoints remain
  source chat/message references and no automatic fact is created from the
  link.

Database:

- Migration 10 (`conversation_intelligence`) additively creates
  `conversation_contact_segments`, `current_conversation_context`,
  `person_project_context`, `conversation_open_loops`, and
  `conversation_context_links`. A SQLite API backup was created before the
  migration work; existing evidence, task, and segment tables are unchanged.

Compatibility:

- Existing task-anchored `conversation_segments` remain available for
  classification, retrieval, and Deep Dive. Contact materialization is a
  complementary, person-scoped view and does not assume that every segment has
  a project.

## 2026-08-22 — Conservative Gemini history pacing

Changed:

- Lowered the default Gemini request pace from 15 to 14.5 RPM and accept a fractional `GEMINI_REQUESTS_PER_MINUTE` setting. The pace reserves extra room below the nominal limit for provider rolling-window accounting.

Database:

- No migration and no data changes.

Compatibility:

- Integer existing values remain valid. The local `.env` is now set to 14.5 and takes effect after the next application restart.

## 2026-08-22 — Authoritative reviews and enforceable chat policy

Changed:

- Review acceptance applies entity merges, accepted task changes, message-classification edits, and graph task/event/fact links to canonical state while retaining append-only feedback. The queue also renders its rationale and available chat/message provenance.
- Added a terminal chat-policy editor. `classify_only` retains local archive metadata without provider work; `news_only` sends only classified external-news messages to semantic analysis.
- Graph maintenance repairs invalid temporal-fact validity boundaries without replacing raw evidence, fact values, or source references.
- Moved chat-policy persistence into its own module and removed the unused legacy operational search implementation; existing intelligence callers retain a compatibility import.
- Expanded graph diagnostics with unclassified backlog, stored routing counts, stale work, and conversation segments lacking task evidence.
- Audited developer documentation and VS Code tasks against the Makefile; `make help` now lists every supported developer command.

Database:

- Migration 8 (`enforceable_chat_ai_policies`) rebuilds the small policy table with enforceable modes and maps legacy `daily_only` and `history_only` values to `auto`. A SQLite API backup is created before applying the table rewrite.
- Migration 9 (`conversation_segments`) additively stores derived time-bounded chat/project periods.

Compatibility:

- Existing automatic, include, and exclude policy records remain valid. Old lane-only records continue as automatic routing; raw Telegram evidence is not modified.

## 2026-08-22 — Gemini quota and Groq fallback reliability

Changed:

- Classify Gemini `429 RESOURCE_EXHAUSTED` responses as quota exhaustion, skip retries, and route the current and later batches in that run directly to Groq.
- Limited optional canonical context and prior-message context to 2,000 characters each; source-message windows remain intact.
- Added `AI_MAX_OUTPUT_TOKENS`, defaulting to 1,200, for both Gemini and Groq requests.

Database:

- No migration and no data changes. Failed batches remain durable diagnostic records; later successful fallback batches are recorded normally.

Compatibility:

- Existing configuration remains valid. The new output limit is optional and defaults safely when absent from an existing `.env`.

## 2026-08-22 — Development workspace baseline

Changed:

- Added a VS Code workspace, Make targets, and project-local quality configuration.
- Added `AGENTS.md`, `TASKS.md`, an anti-slop review workflow, and a technical-debt log.
- Added `scripts/dev_tools.py` for safe health, SQLite integrity, backup, task, change, documentation, and review commands.
- Added generated markers for environment and schema documentation; manual architecture prose remains outside those markers.

Database:

- No migration and no database data changes. The tooling reads metadata or uses SQLite's backup API.

Compatibility:

- Existing `data/telegram.sqlite` and Telegram session files remain untouched.

Follow-up:

- Add an explicit schema-version/migration ledger before the next database evolution.
- Establish the existing lint, formatting, and typing baseline before treating `make check` as a passing gate.

## 2026-08-22 — Configuration and context-view reliability

Changed:

- `load_settings()` now gives an actionable error when `.env` is absent and identifies missing Telegram credential names individually.
- Aligned the example Telegram worker and group-threshold values with current runtime defaults.
- Added regression coverage for missing configuration, invalid numeric configuration, runtime defaults, and context-view rendering.
- Removed stale context-view output that referenced an undefined UI table.

Database:

- No migration and no database data changes.

## 2026-08-22 — Ranked context engine

Changed:

- Extended context requests with purpose, chat/task seeds, and raw-evidence control.
- Added deterministic ranking, bounded relationship traversal, temporal-history separation, provenance-aware diagnostics, and independent context budgets.
- Added a context preamble to every claimed AI job; it is explicitly background and cannot be cited as new evidence.
- Routed Ask Alex Memory and daily-brief generation through the central context layer.
- Expanded terminal diagnostics to person, project, company, global, and query contexts.

Database:

- No migration. The implementation uses existing temporal-fact, relationship, pinned-memory, task, summary, and event tables.

Compatibility:

- Existing context callers retain their previous person/project/company/global entry points.

## 2026-08-22 — Terminal navigation and usability

Changed:

- Replaced the flat 16-item home menu with responsive Focus, Explore, and Maintain groups and a compact live-sync health panel.
- Added memorable letters and command-name aliases while preserving all original numeric shortcuts.
- Made Ask the safe Enter default and made blank questions, searches, context queries, and ID prompts return without starting work.
- Added filtered entity lists before profile and entity-context prompts, clearer task status/source presentation, and informative empty states.
- Fixed the read-only settings screen so its prepared table is actually rendered.

Database:

- No migration and no database data changes.

Compatibility:

- Original commands `1` through `16` and `q` continue to resolve to the same actions.
- The interface remains Rich-based and works in narrow terminals by stacking command groups.

## 2026-08-22 — Task Deep Dive

Changed:

- Added a dedicated `tasks/deep_dive` service that starts from canonical task state and composes the existing context builder with deterministic, bounded raw-message retrieval.
- Added source-cited evidence, same-chat conversation windows, a chronological timeline, explicit known/unknown/recommendation sections, a grounded answer mode, and terminal commands through `ID dive`.
- Added persistent task-investigation sessions, evidence references, notes, and pins. Sessions retain metadata instead of duplicating raw Telegram content.

Database:

- Additive schema creation for `task_deep_dive_sessions`, `task_deep_dive_evidence`, `task_notes`, and `task_deep_dive_pins`. A SQLite API backup was created before the schema change; no existing table is rewritten or removed.

Compatibility:

- Existing task status syntax remains unchanged; `ID dive` is an additional Tasks action.
- When FTS is unavailable or has no candidate rows, bounded SQL text matching remains available.

## 2026-08-22 — Coherent terminal UI

Changed:

- Standardized navigation, operational tables, detail screens, sync/AI progress, empty states, status/priority labels, metrics, and narrow-terminal layouts around `ui/components.py`.
- Routed Task Deep Dive through the same visual primitives and made source-derived task titles, summaries, facts, and evidence literal Rich `Text` rather than markup.
- Added UI regression coverage for wide/narrow briefs, compact sync progress, AI progress meters, narrow Deep Dive rendering, and source strings containing Rich-like markup.

Database:

- No migration and no database data changes.

Compatibility:

- Existing commands and task actions are unchanged; visual updates are presentation-only.

## 2026-08-22 — Development workspace adoption

Changed:

- Verified VS Code selects the repository virtual environment and exposes the local test, quality, database, and documentation tasks.
- Added `make help` and a VS Code **Check Docs** task so local commands are discoverable without reading the Makefile.
- Applied the repository formatter, removed stale imports, and corrected typing at SQLite ID, optional provider-SDK, queue, writer-state, and application-lifecycle boundaries.
- Deliberately deferred Git initialization because this directory had no repository metadata and no repository/history policy was supplied.

Database:

- No migration and no database data changes.

Verification:

- `make check` passes with the complete test suite, Ruff lint, Ruff formatting, MyPy, and bytecode compilation.

## 2026-08-22 — SQLite migration ledger

Changed:

- Replaced ad-hoc bootstrap ordering with an ordered `Migration` registry and `schema_migrations` ledger.
- Added schema-version visibility to `make db-check`, legacy-adoption tests, and recovery/authoring guidance in `docs/DATABASE_MIGRATIONS.md`.

Database:

- Added the `schema_migrations` table. Existing databases adopt the idempotent baseline migrations on their next successful open; no existing data is rewritten or removed.

Compatibility:

- Existing compatibility-column and optional-FTS behavior remains intact, now with ordered ledger entries.

## 2026-08-22 — Source-neutral evidence boundary

Changed:

- Added `EvidenceRecord`, `EvidenceSource`, and `EvidenceRepository` so future sources retain provider-native source/account/conversation/item IDs, provenance, timestamps, edits, and deletions.
- Added a Telegram adapter and routed Task Deep Dive task-origin lookup through the shared contract without copying Telegram raw messages.

Database:

- Added `source_evidence` and `source_evidence_versions` through the ordered migration ledger. A SQLite API backup was created before applying the additive schema change.

Compatibility:

- Telegram `messages` and `message_versions` remain authoritative raw evidence; the adapter is read-only over those tables.

## 2026-08-22 — Incremental intelligence workflow

Changed:

- Added a user-facing full-history analysis flow that reports aggregate coverage and resumes durable eligible work after a safe provider pause.
- Added versioned local message classifications that inform bounded retrieval while retaining raw evidence as authoritative.
- Added incremental context-graph improvement after accepted batch projection, scoped to the source chat and idempotent through source-backed relationships.
- Standardized provider-safe history settings on `HISTORY_INTERNAL_*`; prior `AI_HISTORY_*` values remain compatibility fallbacks.
- Added optional quiet-queue background history scheduling and evidence-backed graph-link review candidates; live and daily work retain priority.

Database:

- Added `message_classifications` and `conversation_analysis_state` through migration 5, `intelligence_coverage`. The migration is additive; it does not rewrite raw Telegram evidence.

Compatibility:

- Existing AI jobs remain durable and retain their provider-failure behavior. Internal bounded windows are no longer presented as user workflow stages.

## 2026-08-22 — Temporal conflict review

Changed:

- Added terminal listing and manual keep, accept, or ignore decisions for pending temporal-fact conflicts.
- Displayed both competing values with their source chat/message references and preserved an optional reviewer note.
- Accepting a newer observation closes the prior validity interval; an older accepted observation is retained as historical state.

Database:

- Added `context_conflict_observations` and `context_conflict_decisions` through migration 6, `context_conflict_review`. A SQLite API backup was created before applying the additive migration.

Compatibility:

- Existing pending conflicts remain visible. Newly created conflicts retain the full proposed observation required for an explicit decision.

## 2026-08-22 — Safe incremental intelligence automation

Changed:

- Extended local classification with bounded task and recent-message context for short updates, business scope, decisions, and historical relevance.
- Derived direct graph relationships only from high-confidence accepted evidence and routed an unambiguous chat-project suggestion to review rather than accepting it automatically.
- Added optional automatic history scheduling that starts only while live ingestion is quiet and yields safely when new writes arrive.

Database:

- No migration. The workflow uses existing versioned classifications, accepted AI items, relationships, review records, and resumable history jobs.

Compatibility:

- Automatic history analysis is opt-in through `HISTORY_AUTO_ANALYZE=false` by default. Existing manual history analysis remains available.

## 2026-08-22 — Bounded intelligence retrieval

Changed:

- Moved entity-hint discovery inside the large intelligence retrieval path from an unbounded Python alias scan to a SQL-filtered, 48-result boundary.
- Added regression coverage that verifies irrelevant aliases are excluded and the bounded query path is used.

Database:

- No migration and no database data changes.

## 2026-08-22 — Classification routing boundary

Changed:

- Split deterministic content-routing decisions from the surrounding contextual classification orchestration. The classifier retains the same precedence, classification payload, and versioned persistence contract while keeping temporal relevance and topic enrichment independent of routing.

Database:

- No migration and no database data changes.

## 2026-08-22 — Gemini request pacing

Changed:

- Added `GEMINI_REQUESTS_PER_MINUTE`, defaulting to 15, and paced all Gemini provider attempts—including retries—to that limit.
- Added deterministic provider coverage for conservative 60/14-second spacing at 15 RPM, including retry-slot reservation.

Database:

- No migration and no database data changes.

## 2026-08-22 — Visible history progress

Changed:

- Added an immediate history-analysis status and a concise update after each successful semantic commit, so 15-RPM pacing no longer leaves the terminal blank.

Database:

- No migration and no database data changes.

## 2026-08-22 — Resilient history continuation

Changed:

- Changed history analysis so an isolated failed provider batch is deferred while subsequent queued work continues.
- Added a three-consecutive-failure circuit breaker to preserve the safe pause during a genuine provider outage.

Database:

- No migration and no database data changes.

## 2026-08-22 — Migration compatibility registry

Changed:

- Replaced table-specific compatibility upgrade functions with one declared table-to-column map applied only by migration 2, `compatibility_columns`.
- Added a valid multi-table pre-ledger fixture that verifies every declared additive column is adopted through the ordered ledger.

Database:

- No new migration or data rewrite. Existing migration 2 retains its version and idempotent additive behavior.

## 2026-08-22 — AI analytics query boundary

Changed:

- Moved terminal-facing, read-only AI findings, diagnostics, lane statistics, and aggregate analytics into `ai/analytics.py`.
- Routed terminal and test callers to the dedicated query module; `ai/repository.py` retains only queue and result persistence.

Database:

- No migration and no database data changes.

## 2026-08-22 — Staged intelligence retrieval

Changed:

- Moved the SQL-first retrieval implementation into `retrieval.py`, separating canonical task, entity/memory, summary, raw-message, FTS, and ranking stages.
- Retained `alex_memory.intelligence.retrieve` and `SearchResult` as the public interface for existing intelligence callers.

Database:

- No migration and no database data changes.

## 2026-08-22 — Declarative migration support boundary

Changed:

- Moved compatibility-column maps, source-evidence DDL, and optional FTS DDL into `schema_support.py`.
- Kept migration ordering, application transactions, the ledger, bootstrap schema, and connection lifecycle in `database.py`.

Database:

- No new migration or data rewrite. Existing versions 2 through 4 retain their names, order, and idempotent behavior.

## 2026-08-22 — AI analytics screen boundary

Changed:

- Moved the read-only AI analytics terminal screen from `ui/screens.py` to `ui/ai_analytics.py`.
- The application now calls that screen directly; general terminal screens remain focused on operational navigation and detail views.

Database:

- No migration and no database data changes.

## 2026-08-22 — AI item validation boundary

Changed:

- Separated model-item validation from transactional `ai_items` persistence while retaining source-reference checks and rejection reasons.

Database:

- No migration and no database data changes.

## 2026-08-22 — Consolidated sync and intelligence routing

Changed:

- Replaced the separate Smart Sync runtime with `TelegramSyncService`, which starts live capture before applying the existing per-dialog bootstrap policy and uses that same planner for later reconciliation.
- Made persisted classification the new-message semantic-work boundary; forwarded content is recorded and classified as external news, and automatic new-message analysis is enabled by default.
- Added bounded, evidence-derived Deep Dive search rounds, task-scoped graph improvement, and generic review decisions recorded as user feedback.

Database:

- Migration 7 (`intelligence_versions`) additively records Telegram forward provenance, `information_scope`, and per-message analysis version/context/staleness. Existing messages and AI findings are retained unchanged.

## 2026-08-22 — Bounded orphan-context repair

Changed:

- Context Graph improvement now repairs orphan tasks, entity-free events, and person/company facts only when two independent tasks anchor their source chat to the same project.
- A single source-chat project anchor creates an idempotent review candidate rather than changing canonical state.

Database:

- No migration. Existing task, event, fact, relationship, review, and feedback records are reused with source chat provenance.

## 2026-08-22 — Temporal conversation segments

Changed:

- Added deterministic, task-anchored project periods for each source chat. A period ends at the next project period or 90 days after its last anchor, preventing historical project discussions from being treated as a permanent chat assignment.
- Used matching message-time periods for `project` classification scope, active context, Deep Dive cross-chat discovery, and a bounded project-aware message retrieval boost.

Database:

- Migration 9 (`conversation_segments`) adds only the derived segment table and indexes. Raw messages, AI output, canonical task links, and historical facts are unchanged.
