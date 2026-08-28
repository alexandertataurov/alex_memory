# Changelog

## 2026-08-26 — Repository control-plane reconciliation

- Reconciled current source, task ledger, active remediation plan, and the
  documentation gate. The local quality gate passes 223 temporary-SQLite tests
  with lint, formatting, and type checks; documentation is current.
- Preserved the completed engineering-harness history under unused ID `AM-123` to
  remove its collision with the active AM-105 provider-request-lifecycle task.
  This is task/documentation identity repair only; no runtime or live-state
  behavior changed.

All notable user- and developer-visible changes are recorded here. This project currently has no Git history in this directory; entries are grounded in reviewed local files and verification output.

## Unreleased

### Changed

- AM-107 makes Task Deep Dive evidence membership explicit: contextual facts
  stay background, events and messages require task-specific proof, Unicode
  matching is supported, and dedupe keeps strongest provenance.
- AM-094 balances bounded Ask Memory evidence by type, marks canonical context
  as non-citable background, and limits deterministic fallback to typed router
  failures.
- AM-088 makes conversation task loops an exact active-task projection and
  removes stale derived rows during scoped refresh. Heuristic question loops
  require an adjacent substantive opposite-author reply and age out of current
  state after 90 days while remaining historical.
- AM-086 stops projecting ordinary observations as duplicate
  `observation_recorded` context events. Event readers ignore legacy wrappers;
  related retrieval and contact timelines retain the original bounded
  source-backed observation. Existing rows are inert pending separate repair.
- AM-085 removes active copy-only `entity_memory` behavior. Projection no
  longer creates copies; context, retrieval, profiles, and FTS use bounded,
  source-backed accepted observations directly. Existing legacy rows remain
  inert; no deletion, migration, replay, or live action ran.

- AM-057 routes deterministic graph-improvement follow-up through scoped,
  revisioned context invalidations rather than broadly staling high/critical
  chat messages for AI re-analysis. No schema, replay, or live action ran.
- AM-057 context freshness now reports pending, running, and failed revisioned
  refresh scopes alongside stale source interpretation, so refresh work is not
  falsely shown as fresh. No schema, replay, or live action ran.
- AM-057 runtime coverage now separates archived eligibility, classification,
  semantic analysis, canonicalization, context integration, and conservative
  current-enough coverage. No schema, replay, or live action ran.
- AM-057 migration 21 records exact accepted batch scope/revision dependencies
  per message. Current-enough now checks those dependencies against the durable
  invalidation ledger; legacy state remains explicitly partial. No source,
  claim, canonical, replay, or live action ran.

- AM-099 now applies workload and structured-output eligibility before forced
  or session-pinned route selection. Overrides can choose only an eligible
  profile; excluded models remain unavailable and trigger no request. No
  provider/model expansion, schema, migration, replay, or live action ran.

- AM-052 removes the unused `Settings.gemini_model` mirror. Gemini primary
  model selection now has one effective settings field; deprecated environment
  aliases remain lower-priority inputs with diagnostics, and documented
  provider-wide RPM capping remains distinct from model quota profiles. No
  provider, schema, migration, replay, or live action ran.

- AM-067 consolidates all `person_context_state` writes in
  `ContactContextMaterializer`. Locally validated presentation summaries and
  canonical-person merge relocation now use its explicit methods, so profile
  and operational callers no longer write the materialized table directly. No
  migration, rebuild, replay, provider request, or live action ran.

- AM-053 routes the explicit terminal global refresh through the durable
  invalidation worker. Project health, follow-ups, and global snapshots no
  longer bypass the ledger on that path.

- Added AM-074's bounded, read-only derived-state repair inventory. It reports
  capped task-project, segment-chat, and pending-context candidate counts
  without reading message content or modifying SQLite state. No apply path,
  migration, replay, or production operation is included.
- Added an explicit AM-074 dry-run command. It requires one or more named
  operations, returns only capped counts and a deterministic scope fingerprint,
  and opens the database read-only only after validating its input. It has no
  apply or resume mode.
- Added the first fixture-only AM-074 apply unit for task-project linkage. It
  requires the matching dry-run fingerprint and a separate recovery receipt;
  the bounded repair and checkpoint commit together, and retries return the
  recorded outcome. No operator apply command is exposed.
- AM-074 task-project checkpoints now retain the exact selected task IDs
  privately while dry-run output exposes only their digest, preventing a retry
  from drifting to a newly eligible task set.

### Added

- AM-120 now projects explicitly accepted manual person/company/project
  relationships into the temporal graph without fabricating AI claim lineage.
  Unreviewed compatibility inference remains excluded from accepted-graph
  reads. A bounded read-only ContextBuilder diagnostic reports grouped parity
  gaps before any reader cutover; no migration, replay, or live action ran.

- AM-075 completes durable failure-domain closure. Migration 20 adds a
  restart-safe schedule for retryable history work without changing exact job
  membership; malformed responses and local configuration failures remain
  terminal. Structured Gemini retry headers now take precedence over textual
  delay parsing. No live migration or repair ran.

- AM-075 now preserves quota dimension through normalization. Daily request/
  token exhaustion is model-local until the next UTC reset, while minute-scale
  quotas retain bounded short retry. No migration or live action ran.

- AM-075 also clears expired quota cooldowns deterministically from in-memory
  and persisted current-UTC usage state. No schema or live action ran.

- AM-075 prefers structured Gemini HTTP 429 quota metadata to text heuristics,
  retaining quota dimension and retry delay. No integration, schema, or live
  action ran.

- AM-075 adds explicit permanent configuration and response-contract failure
  types; malformed/empty responses are rejected locally before persistence.
  No schema or live action ran.

- AM-071 completes its code-verifiable task lifecycle scope: source-aware,
  bounded reconciliation protects entity/project anchors; terminal lifecycle
  evidence links to the canonical task; and repeated manual/rejection actions
  are idempotent. Historical repair remains AM-074 work. No migration, replay,
  backfill, or live action ran.

- AM-072 project health now uses dated canonical task evidence, project-linked
  observations, temporal events, and conversation intervals. A real overdue
  open/waiting task is critical; missing task links alone are not. No migration,
  backfill, or live recomputation ran.

- AM-071 begins conservative task reconciliation: same-chat matching now
  rejects conflicting populated person/company/project anchors before title
  similarity can merge records, while exact-title continuation with a matching
  anchor remains supported. Candidate reads are bounded to 50 rows. Temporary
  fixtures retain the shared manual update/rejection audit contract. No
  migration, replay, backfill, or live action ran.

- AM-120 adds a bounded, read-only graph query contract for current canonical
  relationships. It admits the existing accepted task-to-project projection
  only with immutable claim evidence, excludes observed, source-less, and
  expired edges, and preserves manual authority without invented AI lineage.
  Fixtures also record the person/company relationship parity gap. No runtime
  reader, migration, replay, repair, or live action ran.

- AM-106 gives every physical Gemini/Groq extraction and grounded-answer call
  one router-owned retry, conservative model pacing, quota/event record, and
  usage boundary. Transmitted system/schema/user overhead is estimated without
  storing prompts; Gemini and Groq SDK usage is normalized for both paths.
  Unconfirmed Groq cancellation records the attempt and withholds fallback.
  No migration or live action ran.

- AM-105 makes Gemini requests cancellable at the SDK async-client boundary.
  Timed-out Gemini routes finish cancellation before fallback, and owned clients
  close with their Daily or History router. No migration or live action ran.

- AM-104 replaces selected-model duck typing with one explicit provider request
  contract. Gemini and Groq execute its selected model, and the router rejects
  a mismatched returned provider/model before success accounting or persistence.
  No model expansion, migration, or live action ran.

- AM-102 is closed as a verified contract-parity task: the provider-neutral
  response contract already rejects malformed semantic output without repair,
  preserves raw payloads for repository validation, and records top-level and
  per-item failures without accepting broken analysis. No code, migration, or
  live action ran.

- AM-101 separates provider failure from post-provider recovery: saved batches
  replay canonical projection and context integration from durable state without
  another model call, and post-save failures cannot create a synthetic provider
  failure batch or reclaim the completed job. Context-assembly failure returns
  the claimed job to a durable retryable state. No migration or live action ran.

- AM-099 makes existing quota-aware routing semantics real: automatic Daily
  work is background priority while manual work remains interactive; short and
  context workloads have distinct bounded candidate policies; structured-output
  admission and deterministic policy reasons are enforced; and the unused
  long-context capability flag is removed. No provider/model expansion,
  migration, or live action ran.

- AM-098 makes lifecycle status truthful: writer counters follow commits;
  failed writers surface during sync/close; daemon startup avoids false active
  status; stale scheduled briefs are skipped; and incomplete shutdown is
  reported without masking earlier failures. No schema, migration, replay, or
  live action ran.

- Fixed Textual command-palette filtering so row replacement awaits removal,
  preventing duplicate widget IDs while typing. No migration or live action ran.

- Added Textual regressions for confirmation-gated profile task updates and
  person-scoped contact search. No migration or live action ran.

- Extended AM-122 contact-briefing coverage to require exact-message evidence
  for useful direct connections. No migration or live maintenance ran.

- AM-093 retrieval now applies one bounded all-term candidate rule to SQL
  fallback and FTS stages. Reversed multi-word queries therefore retain their
  qualifying results while partial-term matches remain excluded. No migration
  or live maintenance ran.

- Tightened the active AM-093 Person Intelligence boundary: Textual contact
  search is now canonical-person scoped, supporting context evidence closes
  over exact canonical message IDs or immutable claim evidence, and Task Deep
  Dive no longer imports raw context evidence as related chats. Unresolved
  ordinary context requests no longer fall through to global tasks/events, and
  distinct daily/monthly summaries retain stable chat/date provenance. Related
  historical retrieval is covered for future-task exclusion and fact intervals.
  No migration or live maintenance ran.

- Reconciled AM-118's remediation/debt records with current controls and
  documented the complete migration 1–19 ledger, including the previously
  omitted person-profile summary migration. Remaining work stays in AM-053,
  AM-071, AM-075, and AM-120; no migration or live maintenance ran.

- Reconciled the AM-062 documentation leaf with current source: task records
  now label the implemented invalidation and person-context ownership controls
  as historical findings, while retaining only their verified remaining scope.

- Mark archive edits and first deletions as stale interpretation boundaries.
  Existing exact-membership AI jobs can requeue an edited eligible message;
  deletion remains idempotent and never reopens provider work for deleted source.

- Documented the AM-120 relationship-model caller inventory and its authority
  boundary: compatibility consumers cannot yet move to the semantic graph
  because accepted graph projection currently covers task-to-project only.

- Distinguished reachable Gemini 5xx server failures from provider transport
  failures. Typed 500/502/503/504 responses retain bounded retry/fallback but
  cannot place all Gemini models on the transport-health cooldown.

- Extended Person Profile contact-briefing coverage to prove long unlinked
  history cannot replace exact group-context evidence, while changed-context
  records remain bounded and evidence-linked.

- Added bounded Notion-aware Codex project workflows: targeted context lookup,
  search, status comparison, task de-duplication, and selective durable
  write-back. Project hooks only remind Codex about lazy Notion use and a final
  durability check; they never retrieve or persist workspace content.

- Initial Textual People-first terminal shell with live local search, keyboard
  navigation, compact runtime status, a person overview, and Ctrl+K palette.
  No migration or source write is part of this UI increment.
- Debounced Textual discovery and removed one-to-many join amplification;
  person detail now presents bounded profile context, work items, projects,
  and exact evidence citations.
- Added keyboard navigation for all bounded Person Profile sections and access
  to the complete protected operations workflow from the command palette.
- Added an explicit Deep Scan status/queue screen and clearer scrollable
  profile-section formatting.
- Deep Scan now drains an existing profile backlog before creating more work;
  its screen distinguishes evidence found from windows ready to process and
  offers an explicit bounded run of up to 64 queued windows.
- Compacted the Textual Person Profile navigation and removed its unreachable
  Ask screen. Communication totals now cover every linked conversation rather
  than only the eight-row display breakdown; Deep Scan shows completed versus
  eligible evidence-message coverage and has a live bounded scan view.
- Textual Deep Scan now suppresses the competing Rich live renderer and updates
  its own panel from the shared durable-worker lifecycle; fallback terminal
  progress output is unchanged.
- Deep Scan now starts its bounded durable run in a background Textual task, so
  the screen stays interactive while it polls running/completed/failed job
  state. The screen includes a privacy-safe analysis audit: assertion-kind
  counts, bounded rejection reasons, and recent durable job/provider outcomes;
  it never displays or persists raw message content as diagnostic logs.
- Deep Scan now renders separate exact-evidence and window progress bars. Its
  current extractor version scopes status, diagnostics, and durable job claims
  consistently, preventing legacy scan jobs from inflating v2 coverage.

- Deprecated AI setting aliases now appear as runtime compatibility warnings.

- Made historical migration ownership executable: migration 1 no longer
  pre-creates tables introduced by migrations 4–10, while migrations 2 and 7
  use separate immutable compatibility-column snapshots. Fresh and legacy
  temporary SQLite databases still converge through the complete ordered
  ledger; no new migration version or live schema action is required.

- Person-first terminal navigation: Alex Memory opens in bounded People
  discovery, the normal menu is limited to person work, Review, System Status,
  and Quit, and legacy operational controls stay behind explicit maintenance
  access.
- Simplified the terminal interaction: People are rendered by default, names
  and visible IDs open profiles directly, and `/` opens a small searchable
  action palette. Maintenance appears there only after an explicit search.
- Person profiles now expose identity-review status, current topics, compact
  sections, and deterministic direct-chat response-time medians based only on
  consecutive opposite-direction messages within seven days.
- Added a deterministic "Before I contact them" Person Profile action. It
  presents only exact-evidence last interactions, commitments by owner,
  evidence-backed active projects, unresolved questions, recent changes, and
  direct connections; unsupported context is explicitly unknown.
- Person Profile enrichment now refreshes its AI summary only when its exact
  evidence package changes and offers a bounded manual Deep Scan history action
  with durable, person-scoped scan membership and status.
- Person Profile audit hardens Deep Scan feedback and summary freshness: queued
  profile windows are verified claimable with their exact membership, failed
  windows are reported as retryable, and canonical-row changes refresh the
  presentation summary even when the cited messages are unchanged.
- Deep Scan now uses a separate durable `profile` AI-job lane and accepts only
  source messages authored by the resolved contact, preventing owner and
  third-party statements from automatically enriching that person's profile.
- Deep Scan now includes the complete resolved direct conversation for context,
  while locally rejecting any extracted profile item that cites a message not
  authored by the selected person. Completed accepted projection refreshes the
  Person Profile through its existing invalidation path.
- Deep Person Profile adds profile-scoped semantic-claim metadata for direct,
  third-party, and inference assertions with optional effective periods. The
  terminal now shows exact speaker/timestamp evidence, private direct details,
  uncertain claims, and deterministic direct-chat activity metrics.
- Textual Deep Scan now uses the same `enrich_person()` path as the fallback
  terminal, so Enter processes bounded durable profile work rather than only
  queueing it. The profile command palette is limited to People, Review,
  System Status, and explicit Maintenance.
- Added an explicit maintenance `full_refresh` / `resync_profiles` operation:
  it reconciles the permitted current Telegram archive, completes eligible
  semantic history work, then rebuilds every materialized person profile from
  existing canonical state. Raw evidence, claims, and manual decisions are not
  rewritten.

- Routed Ask Memory through the central `AIRouter` with the normal model
  selection, quota accounting, health cooldown, and deterministic offline
  fallback. Provider-owned bounded answer methods replace the private
  Gemini/Groq SDK calls in `intelligence.py`; citable model evidence stays
  separate from the compact deterministic answer presentation.
- Made `retrieve_related()` genuinely entity-scoped. It returns only canonical
  task, event, and temporal-fact rows linked to the requested entity, honours
  temporal `as_of` bounds where source intervals support them, and no longer
  turns an entity request into a name search.
- Aligned direct `Settings` construction with the runtime quota-aware routing
  default, and made every configuration boolean fail loudly on an invalid
  value. The compatibility-column migration helper now snapshots its declared
  column definitions before application instead of iterating a mutable map.

- Person Profile v1: a bounded read-only terminal view of canonical identity,
  aliases, contact context, facts, relationships, projects, open commitments,
  history, and deterministic linked-Telegram-chat statistics. Important records
  resolve only to their exact claim or stored-message evidence.
- A presentation-only, cited Person Profile AI summary through the existing
  summary router and revisioned person refresh path. Migration 16 adds its
  fields to the existing `person_context_state` row; no profile-memory table,
  graph mutation, replay, or backfill is introduced.

- Version-2 end-to-end AI extraction: a provider-neutral strict response
  contract, durable item rejections, exact ordered analysis-job membership,
  selection fingerprints, idempotent canonical projection state, and a
  revisioned context-invalidation ledger. Malformed top-level provider output
  is retained as a diagnostic without marking source messages analyzed.
- A bounded `refresh_pending_context` worker for conversation, person, and
  global materialization after canonical projection. It coalesces scope
  revisions, preserves retryable refresh failures, and records batch context
  integration only after its linked revisions complete. The contact
  materializer is now the only writer of person context state.

- Immutable semantic claims for every newly validated legacy AI observation,
  with exact submitted-message evidence, extraction/provider/model provenance,
  bounded confidence, and idempotent deduplication. New claim lineage and the
  deterministic SQLite graph projector create observed claim links and only
  allowlisted accepted task-to-project edges. Historic observation and legacy
  relationship conversion remain deliberately deferred.
- An evidence-backed application remediation plan that sequences the existing
  safety, projection, context, retrieval, routing, and repair work by durable
  dependency. It records the current quality baseline and does not change
  runtime behavior, schema, or live state.
- Deterministic task-project resolution during accepted batch projection, with
  bounded repair for existing unlinked tasks and selective conversation-period
  rebuild. Existing links are preserved; weaker candidates are deduplicated in
  Review rather than applied automatically.
- Deterministic Telegram direct-chat peer ownership before prompt assembly and
  accepted AI projection, plus a bounded caller-controlled identity repair
  helper. Explicit unclaimed usernames can attach an existing person;
  display-name collisions create a merge review candidate instead of changing
  ownership. Contact context for direct chats now materializes only for the
  peer contact.
- A visible, read-only **Today** action, Follow-ups entry, explicit
  **Refresh operational state** command, current-actionable task view,
  text-filtered entity/chat pickers, source drill-down for Search/Ask, review
  evidence previews, task-update confirmation, and focused diagnostics views.
- Today and Follow-ups now open their linked task or exact message evidence;
  review previews resolve both direct and source-prefixed message references.
- Follow-ups can now be manually reopened, snoozed, completed, or cancelled
  after an evidence preview and explicit confirmation. Each state transition
  records append-only operator feedback.
- The Tasks screen now guides operators through separate task-ID and action
  prompts instead of requiring a compact `ID status` command.
- Follow-ups now reconcile their derived waiting-task condition: automatic
  reminders close when the condition ends and can reopen if it recurs, while
  explicit operator states remain authoritative.
- Daily Brief is now a read-only viewer. Generating and saving today's brief is
  a separately named Maintain action.
- One committed-evidence background-intelligence scheduler for automatic Daily
  and optional History analysis. It coalesces message-write wakeups, rechecks
  durable work on startup and a bounded timeout, preserves live-over-history
  priority, and keeps provider failures separate from Telegram ingestion.

- Project-local Codex hooks for concise session context, canonical environment
  guidance, private-data and destructive-command guardrails, focused Python
  checks, verification evidence, and a lightweight legacy/AI-slop diff review.
- Six focused Alex Memory Codex skills covering memory-pipeline invariants,
  SQLite integrity, async worker debugging, LLM extraction evaluations, legacy
  removal, and AI-slop cleanup; `make codex-hooks-check` validates the hook
  configuration without reading private data.
- Repository-local pre-commit installation via `make hooks`, with whitespace,
  YAML, large-file, Ruff 0.16.4, and `uv.lock` checks.
- A locked PEP 621 Python environment (`uv.lock`), dependency declaration
  checks, a known-vulnerability audit, three focused repository skills,
  constrained Codex review roles, command guardrails, execution-plan guidance,
  and VS Code tasks for the quality workflow.
- Workload-aware AI routing with verified hosted Gemma 4 (`gemma-4-31b-it`), Gemini 3.5/3.1 routes, and Groq fallback.
- Durable daily per-model usage counters, local RPM/TPM guards, quota cooldown diagnostics, and recent routing-decision telemetry with no prompt content stored.
- A visual AI request monitor with live queue state, provider/model routing, Gemini pacing, hourly fallback/error totals, and recent request outcomes.
- An animated live request panel during history analysis, so provider latency is visible instead of appearing stalled.
- Per-provider hourly request totals and the specific fallback reason in the AI monitor.
- Live history-request elapsed time and the active provider/model state.
- VS Code workspace configuration, safe Make targets, task tracking, project instructions, and lightweight developer-quality checks.
- Generated configuration and database-schema documentation with drift detection.
- Ranked, bounded context packages for AI extraction, Ask Alex Memory, daily briefs, and terminal diagnostics.
- Task Deep Dive: source-cited task investigation with bounded cross-chat retrieval, temporal context, sessions, notes, and pinned evidence.
- Shared terminal UI primitives for consistent panels, data tables, status labels, empty states, progress displays, narrow layouts, and literal rendering of untrusted text.
- A `make help` command and VS Code documentation-check task for the local workspace baseline.
- Ordered SQLite migration ledger with visible schema versions and legacy-adoption coverage.
- Source-neutral evidence contract and version-preserving storage for future non-Telegram ingestors.
- Resumable full-history analysis with versioned contextual message classifications and aggregate coverage reporting.
- Provenance-preserving, idempotent context-graph improvement following accepted batch projection.
- Manual temporal-fact conflict review with source evidence, validity-safe acceptance, and append-only decision history.
- Broader bounded contextual classification, evidence-backed graph-link candidates, and quiet-time automatic history scheduling.
- Refactored entity-hint retrieval to use a bounded SQL filter instead of a Python scan across every alias.
- Paced all Gemini attempts, including retries, to the configured 15-RPM default.
- Kept history analysis visible during rate-limited runs with immediate and per-request committed-work updates.
- Continued history analysis after isolated provider failures, pausing only after three consecutive failures.
- Forwarded Telegram provenance, persisted information scope, selective semantic-analysis staleness, bounded multi-round Task Deep Dive retrieval, and durable generic review decisions.
- Bounded, source-chat-consensus repair of orphan tasks, events, and facts, with ambiguous links sent to review.
- Time-bounded, task-anchored conversation segments for period-aware classification, context, Deep Dive discovery, and retrieval ranking.
- Authoritative review decisions for canonical merges, task reconciliation, graph links, temporal-fact conflicts, and validated classification edits; review rows now show their rationale and source provenance.
- Context diagnostics now show unclassified backlog, routing mix, stale analysis, and derived-segment evidence gaps.
- Expanded the documented developer-command inventory to include formatting, documentation, task, change, and Codex workflow checks.
- A terminal chat-analysis policy editor with automatic, forced-inclusion, classification-only, news-only, and exclusion routing.
- Unified contact conversation intelligence: materialized contact periods, current thread state, person/project contexts, source-backed open loops, conservative question/answer links, and person-scoped retrieval.
- Focused architecture modules for AI prompt context, contact-context materialization, and terminal profile rendering.
- One authoritative, read-only runtime-status snapshot for the home and
  diagnostics screens, including Telegram/archive freshness, writer health, AI
  backlog/route/quota state, context/graph maintenance, review load, recent
  errors, and data-quality coverage indicators.

### Changed

- AI jobs now claim their persisted exact message membership, rechecking
  deletion and policy eligibility before dispatch. Changed membership is
  superseded rather than silently reconstructed from a numeric range; old
  extraction results are only reconsidered by explicit bounded history runs.
- Canonical projection no longer performs synchronous graph or broad context
  fan-out. Replays avoid duplicate context events, temporal conflicts, and
  task lifecycle entries while preserving manual task locks and Review
  authority.

- Telegram's SQLite writer now commits an idle batch before notifying automatic
  intelligence, so a scheduler wakeup always follows durable message evidence.

- Consolidated Python dependency declarations in `pyproject.toml`; obsolete
  requirements files and stale installation guidance were removed. The fast
  gate now also lints, formats, and type-checks maintained developer tooling.
- Semantic history and daily extraction now declare context-extraction workload and use quota-aware routing when enabled; legacy explicit provider routing remains available for compatibility.
- Normalized the local `.env` to explicitly pin every active non-secret runtime
  default, including bounded history analysis, context assembly, and Task Deep
  Dive controls; legacy unconsumed keys remain inert for compatibility.
- Expanded `.env.example` to cover the settings currently implemented by `Settings`.
- Reworked the terminal home screen around Focus, Explore, and Maintain groups, with memorable command aliases, live-sync health, safer defaults, visible entity choices, and clear empty states. Existing numeric commands remain compatible.
- Adopted Ruff formatting and a clean MyPy baseline across the Python source tree; `make check` is now a passing local gate.
- Ranked intelligence retrieval now uses local message-classification importance alongside source evidence.
- History-analysis limits now use internal `HISTORY_INTERNAL_*` names while retaining `AI_HISTORY_*` as compatibility fallbacks for existing local configuration.
- Classification now uses bounded task and recent high-importance context; uncertain project links are queued for review rather than accepted automatically.
- Classifier v2 separates forwarded provenance from information scope, routes
  actionable questions by actionability/state change, supports bounded
  English/Russian/Georgian operational signals, and derives age-relative labels
  from caller `as_of` rather than persisting a wall-clock snapshot. Legacy rows
  are selectively reclassified through bounded local work without provider calls.
- Separated deterministic message content routing from temporal and topic enrichment, keeping the classification decision path compact without changing its persisted contract.
- Consolidated pre-ledger additive column upgrades into the migration registry's table-to-column map and expanded legacy-schema coverage.
- Split read-only AI findings, batch diagnostics, lane statistics, and aggregate analytics from queue/result persistence; callers use the dedicated query module directly.
- Split bounded retrieval into staged canonical, summary, message, FTS, and ranking queries while retaining the public intelligence API.
- Separated declarative SQLite migration support from the ledger and connection lifecycle without changing migration versions or schema behavior.
- Moved the read-only AI analytics terminal screen out of the general screen collection.
- Separated untrusted model-item validation from the transactional AI-item insert path.
- Unified Telegram startup and reconciliation behind `TelegramSyncService`; new-message analysis now defaults to automatic after local classification.
- Replaced inert `daily_only` and `history_only` chat-policy labels with enforceable routing modes; migration preserves their intent as automatic routing.
- Semantic extraction now prefers a bounded contact package for a dialog with exactly one resolved person, while preserving the rule that background context is never new evidence.
- AI job persistence, contact query assembly, and general terminal screens now delegate their distinct prompt, materialization, and profile-rendering responsibilities to focused modules without changing public APIs.
- Moved chat-policy persistence to `chat_policy.py` while retaining the prior intelligence import as a compatibility re-export; removed the unused legacy operational search path.

### Fixed

- Restored the primary Textual Person Profile presentation path. All bound
  sections now use one bounded record/dashboard model, preserve claim-authority
  labels and exact-evidence drill-down, and no longer reference missing helper
  functions. The fallback Rich renderer and Deep Scan workflow are unchanged.
- Reload persisted AI route cooldowns using the same UTC day used to write
  `ai_model_usage`, so a fresh router continues to enforce an active cooldown
  across a local/UTC date boundary.
- Profile-summary packages now exclude third-party claims and inferences both
  from the selected evidence and from the canonical rows given to the summary
  model.

- Telegram startup failure after the local database opens now leaves an
  interactive local-read terminal rather than exiting; sync and analysis explain
  their unavailable state. Attention queries no longer create follow-ups,
  change project timestamps, or enqueue notifications. Notification cooldowns
  now use elapsed time instead of calendar buckets.
- Removed an unused runtime-status SQL binding and restored the UI imports that
  current status/navigation code requires, returning Ruff/MyPy and UI tests to
  a clean state.
- Daily Brief task creation now derives its date from immutable creation
  evidence rather than a mutable current task source pointer or wall-clock
  projection time. History-monitor tests now assert the current rendered UI
  copy.
- Applied the existing FTS lifecycle migration after a SQLite API backup;
  all six derived indexes now match their authoritative source rows, stay
  synchronized across source edits/deletions and entity merges, and report
  private-content-safe coverage diagnostics. Broken present FTS errors no
  longer silently fall back to SQL.
- Made the FTS rebuild transactionally atomic across index removal, rebuild,
  parity validation, and migration-ledger recording; a failure-path regression
  proves the prior derived state remains intact.
- Fixed the active model-selection bug so an explicit `GEMINI_PRIMARY_MODEL` drives the live Gemini provider, QA requests, and UI routing instead of silently falling back to stale defaults or the deprecated typoed `GGEMINI_MODEL` alias.
- A Gemini 3.5 quota response now skips Gemini 3.1 and sends the next request directly to Groq, preserving fallback-session continuity.
- Gemini DNS and network connection failures now put the Gemini provider on a short health cooldown and move directly to Groq, rather than trying a second Gemini model and adding another stalled request.
- Provider calls now time out after 45 seconds instead of leaving a history job
  marked `RUNNING`; Groq retries its known strict-JSON validation rejection in
  JSON-object mode.
- History now marks only the request actually at a provider as `RUNNING`, and
  Gemini quota cooldowns expire after 60 seconds instead of lasting for an
  entire history run.
- Gemini quota failures now report Google's quota category and retry delay
  without persisting the raw API response; the active local pace is 14.5 RPM.
- Interrupting the live history panel now requeues its active job without
  recording event-loop shutdown artifacts as failed provider requests.
- Removed the three existing false event-loop shutdown diagnostics after a
  SQLite backup and returned their jobs to the pending history queue.
- Short Google-directed Gemini retry delays are now honored before the router
  selects Groq; the live panel shows the primary-provider retry countdown.
- Groq fallback now starts directly in JSON-object mode, avoiding the
  configured model's strict-schema rejection and an additional long request.
- Groq SDK request cancellation and shutdown now have non-blocking deadlines,
  preventing a stalled HTTP task from holding the history queue indefinitely.
- A successful fallback is now pinned for the remainder of a history run. The
  local route is configured Groq-first with a 30-second provider deadline.
- Gemini history pacing now defaults to 14.5 requests per rolling minute,
  leaving additional headroom below the provider's nominal 15-RPM limit.
- Gemini quota responses now bypass retries and use Groq for the rest of the
  active run, preventing repeated quota failures from being persisted.
- Bounded optional analysis context and reduced the output reservation so Groq
  fallback requests fit its configured 8,000 TPM allowance.
- Temporal graph maintenance now repairs invalid fact validity intervals without
  changing their evidence or values.
- Context-view rendering no longer references an undefined table.
- The read-only settings screen now prints the table it prepares.
- Startup distinguishes a missing `.env` from missing Telegram credentials and names missing settings without exposing values.
- New-message extraction now receives relevant canonical context without treating it as new evidence.
- Task investigation filters generic lexical matches unless they have a task entity anchor or multiple concepts in a graph-related chat.
- Task Deep Dive renders source text literally instead of interpreting it as terminal markup.
- Narrow Telegram-sync progress retains the active chat and mode instead of dropping that context when space is constrained.
- Runtime health no longer treats a non-null live-sync object as availability:
  failed startup is explicit, supervised retry is named only when scheduled,
  archive lag becomes visible, and a crashed SQLite writer is fatal.

### Removed

- The separate Smart Sync product/runtime entry point; bootstrap and reconciliation now use one service and one policy.

### Security

- Development tools inspect SQLite metadata and configuration presence only; they do not print secrets, Telegram messages, or session contents.
