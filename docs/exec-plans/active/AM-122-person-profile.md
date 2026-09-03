# AM-122 — Person Profile v1

## Control-plane status

This ExecPlan is a synchronized repository mirror. Notion controls this task's
scope, status, dependencies, gates, authorization, and completion; this plan
cannot waive the parked owner-acceptance gate or authorize further AM-122 work.

## Objective

Make every canonical person readable through one bounded terminal profile that
is traceable to canonical state and exact Telegram evidence.

## Current and target state

The prior terminal profile mixed a small entity/task view with copy-only
`entity_memory` rows and contact materializations. The target is a read-only
person-specific composition of aliases, facts, relationships, projects,
operations, history, deterministic linked-chat statistics, and exact evidence.
`person_context_state` remains the only materialized current-profile row.

## Constraints

- Raw evidence, semantic claims, canonical state, manual authority, and
  temporal validity remain unchanged.
- No profile-memory table, source, dashboard, graph UI, scoring, backfill, or
  live maintenance action is introduced.
- AI output is presentation-only, bounded, cited, locally validated, and
  cannot create canonical state.

## Implementation sequence

1. Compose bounded person-profile reads from canonical tables and resolve every
   displayed source through claim evidence or a direct stored message reference.
2. Add migration 16 profile-summary fields to the existing person context row.
3. Run one bounded `AIWorkload.SUMMARY` request from the revisioned person
   refresh path; retain a previous completed summary on failure.
4. Render compact terminal sections and add temporary-SQLite profile, evidence,
   stats, summary, and renderer coverage.

## Validation and outcome

Synthetic fixtures prove direct claim evidence does not expand to newer messages
from the same chat; profile reads are bounded and do not write state. Summary
fixtures prove cited output persists only in `person_context_state` and creates
no fact. No live migration, corpus replay, graph maintenance, or profile
backfill has run.

Validation 2026-08-24: `make check` and `make docs-check` pass with 197
temporary-SQLite tests. `make verify` reaches its external `pip-audit` step but
cannot resolve `pypi.org` in this environment; its compile, test, lint, format,
type, lock, deptry, SQLite-integrity, and documentation steps pass. The first
summary is produced only after a normal person invalidation; refreshing
historical profiles remains an explicit future maintenance decision.

Follow-up increment: the terminal opens in People discovery, normal navigation
contains only People, Search People, Review, System Status, and Quit, and
recovery/development commands require explicit maintenance access. Profile reads now expose
identity-review state, current topics, compact drill-down sections, and direct
chat-only adjacent-message response timing. No schema, raw-evidence, claim,
graph, or live-state change is required.

## Contact-briefing increment

Validate the existing bounded profile reader with representative synthetic
contacts (long history, new/dormant, ambiguous, group mention, multiple
projects, changed roles, and mixed contexts). Add only a read-only "Before I
contact them" package derived from existing profile rows: last meaningful
source-backed interaction, waiting direction, active topics/projects,
unresolved items, recent changes, and useful direct connections. Every shown
claim must keep its exact evidence; absent support renders as unknown or is
omitted. This adds no stored score, summary, graph edge, source, migration,
backfill, or AI mutation.

Navigation follow-up: render the bounded People list as the terminal default.
Names and visible IDs open a profile, while `/` opens a searchable action
palette. Review, System Status, and Quit are palette actions; maintenance is
shown only after an explicit search. This changes presentation only and has no
data-path, schema, or live-maintenance effect.

## Enrichment audit follow-up

The manual Deep Scan remains a person-scoped history job with exact persisted
membership in the isolated `profile` lane. Its selection and worker claim path are covered together, so a
queued window cannot be reported as processed without being claimable by the
shared bounded worker. Profile-summary freshness is calculated from the bounded
canonical rows supplied to summary presentation and their exact evidence, not
from nearby chat recency. A provider/validation failure still preserves the
last completed summary and leaves the person invalidation retryable. No live
scan, replay, backfill, or rebuild is part of this work.

Profile extraction receives the full resolved direct-conversation window so it
can understand commitments and changes in context. Local validation still
requires every extracted profile item's cited source to be authored by the
resolved canonical person. This deliberately prefers a rejected item to
allowing a user's or third party's statement to create a current role,
capability, company, or relationship fact about the contact.

## Deep Person Profile increment

Profile extractor v2 records structured category-prefixed identity,
professional, capability, personal, relationship, commitment, event, and
connection rows as immutable semantic claims. Migration 19 stores person scope,
assertion kind (`direct`, `third_party`, or `inference`), and optional effective
dates on those claims. Direct claims retain the existing canonical projection
route; third-party/inference claims are bounded, traceable profile-only rows.
The terminal separates private direct details and uncertain assertions from
current canonical state, and communication rendering adds deterministic direct
initiation periods, long gaps, and recent activity. No live scan or rebuild is
authorized.

## Textual terminal increment

The interactive default is moving from blocking prompts to a Textual
People-first shell. It retains existing process entry points and daemon mode,
adds local fuzzy discovery and timezone-relative labels, and keeps the command
palette separate from deterministic search. The discovery read model is
bounded and read-only; no schema or canonical write path changes.

## Profile action-path audit and recovery increment

The primary Textual Deep Scan action must call the established `enrich_person`
workflow, not only queue jobs. This preserves one bounded writer/processor
path for exact job membership, local claim validation, projection, invalidation,
and profile refresh. The summary package must exclude third-party/inference
claims from both prompt rows and selected evidence.

An explicit maintenance-only `full_refresh` / `resync_profiles` command may
reconcile the permitted current archive, finish currently eligible semantic
history work, then refresh every canonical person's materialized profile using
the existing contact materializer and hash-gated summary contract. It never
deletes or rewrites raw messages, claims, canonical facts, temporal intervals,
or manual decisions. Provider/summary failures are isolated per person and
leave prior valid summaries intact; rerunning the command is safe. This is not
a historical Telegram-policy override or a profile Deep Scan backfill.

## Deep Scan backlog follow-up

When prior UI behavior has already queued many profile windows, a normal scan
resume must claim those pending windows before creating more. The profile-local
screen therefore makes evidence coverage and queued backlog distinct: Enter
processes two exact windows, and an explicit `L` action drains up to 64 existing
pending windows. This is still bounded at the provider-request level and stops
before retrying failed windows; failed work remains durable and visible for a
later deliberate retry.

## Compact profile and live scan follow-up

The Textual profile prioritizes overview, briefing, actionable loops, work,
context, communication, and evidence in a compact local menu. Communication
totals are calculated across all linked conversations; the bounded conversation
list remains only a breakdown. Deep Scan reports the durable message-level
coverage (`completed / eligible`), pending/running/failed windows, and updates
the profile-local screen during an explicit bounded live run. The unreachable
Textual Ask screen is removed after caller search; the fallback Rich profile is
retained because it remains the explicit recovery UI.

## Scan responsiveness and audit follow-up

The Textual Deep Scan key action creates a tracked background task for the
already-bounded `enrich_person` or queued-window drain operation. It preserves
the existing job claim, validation, projection, invalidation, and retry path;
the UI only observes it. While active, the screen polls compact durable job
counts and records assertion-kind totals, bounded rejection reasons, and recent job
metadata for operator assessment. It does not add a raw-message log, new audit
table, or another profile pipeline. The expensive evidence-eligibility count is
sampled on screen entry/completion rather than every progress tick. No live
scan, migration, rebuild, or backfill is part of this change.

The screen renders separate exact-evidence and durable-window progress bars.
Both the displayed counts and the profile worker claim use the current profile
extractor version, avoiding legacy extractor windows inflating current coverage
or being silently claimed during a v2 scan.

## Owner validation gate

Final acceptance requires the owner to inspect 10–20 real canonical contacts;
synthetic fixtures remain regression evidence only. Select contacts spanning a
recent direct conversation, dormant history, group-only context, multiple
projects, an ambiguous identity, and limited or absent evidence. For each
profile, verify that identity, commitments, current work, communication, and
the contact briefing either link to the exact cited source or are explicitly
unknown/omitted. Confirm that third-party and inference labels remain distinct
from current canonical state, and that opening the profile performs no source,
canonical, graph, or refresh write. Record only aggregate pass/fail findings
and any reproducible profile IDs for follow-up; do not place conversation
content in the validation record.

`make profile-acceptance` automates the safe, structural portion of that gate.
The owner supplies 10–20 distinct `shape:person-id` values using every required
shape. It opens SQLite read-only, builds the existing bounded profiles, and
emits aggregate-only coverage and violation counts. It rejects missing profiles,
displayed canonical rows without exact evidence, uncertain profile claims
appearing in canonical sections, a briefing last-interaction without evidence,
or any observed profile write. It deliberately does not decide identity truth,
historical coherence, connection usefulness, or briefing usefulness; those are
the owner's private review. The report contains no names, IDs, or source text.

The qualitative owner review is an acceptance gate for AM-122 alone, not a
blocker for another repository task. Keep it parked until the owner supplies
the representative-contact review. A demonstrated Identity, Attribution,
History, Connection, Commitment, Briefing, or Grounding defect may reopen only
that bounded fix; otherwise no further AM-122 implementation is authorized.

## Attribution correctness increment — 2026-08-30

Claim-backed profile records with no remaining cited source are omitted from the
read-only presentation. Manual operational records have no claim and stay
visible. Regression coverage protects both boundaries.

Relationship display now selects the other endpoint by canonical entity type
and ID, so independently numbered person/company/project rows cannot be
confused. Linked group-message history and communication aggregates include
only the selected person's sender rows plus explicit outgoing owner messages;
unrelated participants are excluded rather than presented as the contact.
Direct-chat communication remains unchanged. Temporary-SQLite regressions cover
both boundaries. No source, canonical, graph, refresh, migration, or live
operation changed.
