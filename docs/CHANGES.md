# Implementation Journal

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
