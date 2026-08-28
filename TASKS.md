# Alex Memory Tasks

`TASKS.md` is the single authoritative, human-readable development queue.

Rules:
- Keep each unit of work under exactly one active section.
- Do not duplicate the same work under a second `Bugs` alias.
- Raw/source evidence and manual corrections outrank derived AI state.
- Every persisted derived layer must add information, have a clear consumer, and document how it becomes stale/rebuildable.
- Completed implementation history remains below; detailed chronology also lives in `CHANGELOG.md` / `docs/CHANGES.md`.

Alias-only AM-080–AM-083 and AM-066 were folded into their parent tasks AM-069, AM-070, AM-072, AM-073, and AM-062. No actual work was dropped.
- Public API names/parameters must match real behavior; no unused semantic parameters such as `as_of` and no “related” APIs that are only name searches.
- Functions presented as retrieval/read/query APIs must be side-effect free; derived writes belong to explicit projection/maintenance/background paths.
- Time-relative labels such as `current`, `stale`, and `recent` must derive from source time/as-of semantics or have an explicit refresh lifecycle; never persist a wall-clock snapshot as if it were timeless truth.
- A durable job must identify the exact evidence it owns; never reconstruct semantic work later from a loose numeric ID range.
- Provider success, observation persistence, canonical projection, and materialized-context refresh are distinct states and must not be collapsed into one generic success/failure flag.
- Stored confidence must never be made more authoritative by validation; out-of-range model confidence is rejected, not clamped upward.
- A router-selected model must be the exact model executed by the provider; hidden optional provider methods are not an acceptable contract.
- One physical provider API call must be counted exactly once for retry, RPM/TPM/RPD/TPD accounting, diagnostics, and cost/usage telemetry.
- Provider parsing may normalize transport shape, but must never silently repair semantic model errors into more trustworthy memory.
- Historical `as_of` context must be version/interval-backed or explicitly partial; current materialized rows may never masquerade as past truth.
- “Supporting evidence” must resolve to the exact source evidence of the selected claim; recent messages from the same chat are context, not proof.
- Automatic graph repair requires temporally local independent evidence; chat-wide consensus alone is not sufficient for canonical mutation.
- A materialized table has one authoritative writer. Competing writers with different semantics are a bug, not redundancy.
- A Deep Dive evidence row is not task evidence merely because it is in the same entity/chat context; task membership must be explicit and machine-explainable.
- Core retrieval must be Unicode/multilingual by default. Current deal names and ad-hoc business thesauri do not belong as hard-coded generic engine behavior.
- Investigation-session wall-clock time and evidence `as_of` time are separate dimensions and must never substitute for each other.

## Now

- [ ] AM-120 [P0] [Temporal knowledge graph / Projection] — Project resolved
  semantic claims into one temporal graph with explicit authority and exact
  edge evidence; derive canonical operational state only through allowlisted
  deterministic reducers or Review.
  - Plan: `docs/exec-plans/active/AM-120-semantic-graph-projection.md`.
  - Current increment: bounded accepted-graph query contract is implemented
    and fixture-tested. Explicit manual relationship authority now has parity
    for person/company/project edges; inferred compatibility rows remain
    intentionally excluded until independently reviewed. The bounded
    ContextBuilder parity-gap diagnostic is the first-reader readiness gate.
    No reader cutover, relationship conversion, replay, graph repair,
    migration, or live action is authorized.

- [ ] AM-118 [P0] [Architecture / Remediation] — Execute the evidence-backed
  application review remediation plan before further feature expansion.
  - Plan: `docs/exec-plans/active/AM-118-application-remediation.md`.
  - Scope: establish a reproducible quality baseline, then repair AI work
    ownership, canonical projection, derived-context ownership, evidence
    grounding, and only then rebuild affected state.
  - Guardrail: do not run a live repair, migration, or backfill under this task
    without a separately reviewed implementation task, a SQLite snapshot, and
    dry-run evidence.
  - Progress 2026-08-24: the version-2 extraction lifecycle increment is
    implemented and locally verified: exact job membership, strict local
    contract validation, transactional canonical projection, and revisioned
    refresh ownership. No live migration, repair, corpus replay, or graph
    maintenance action was run. Remaining remediation work stays in its
    existing task records.
  - Progress 2026-08-24: direct `Settings` construction now defaults to the
    same quota-aware mode as runtime loading and boolean typos are rejected.
    Ask Memory dispatches through `AIRouter`; entity-scoped retrieval no longer
    delegates to name search and enforces temporal fact bounds. The existing
    revisioned invalidation worker and single contact materializer writer were
    caller-verified. No schema migration, live repair, corpus replay, or
    provider request ran.
  - Progress 2026-08-24: restored the deterministic quality baseline after
    terminal navigation drift; `make check` now passes all 195 temporary-
    SQLite tests, Ruff, formatting, and MyPy. AM-096 bootstrap/ledger
    normalization remains separate forward-only migration work.
  - Progress 2026-08-24: AM-096 bootstrap/ledger normalization is implemented
    and fixture-verified. Migration 1 no longer creates migration 4–10 tables;
    migrations 2 and 7 apply independent immutable compatibility snapshots.
    Fresh and legacy temporary SQLite fixtures converge through the ordered
    ledger. No migration version, live schema action, repair, or backfill ran.
  - Progress 2026-08-24: AM-052 records deprecated AI input aliases as visible
    compatibility warnings while current inputs retain precedence.
  - Progress 2026-08-26: added a bounded Codex/Notion project-memory workflow:
    targeted skills, a context-only prompt cue, and selective durable write-back
    guidance. No product behavior, schema, migration, provider request, or live
    operation changed.
  - Progress 2026-08-26: reconciled the remediation plan and debt inventory
    against the current source and ordered 1–19 migration ledger. Historical
    findings already addressed by extraction lifecycle, canonical projection,
    invalidation ownership, configuration/routing, and AM-096 are now labelled
    as completed controls; AM-053 and AM-120 remain open under
    their existing bounded scopes. No runtime or live-state action ran.
  - Progress 2026-08-26: current-source audit reconfirmed the remaining
    lifecycle, provider-request, failure-taxonomy, materialization-ownership,
    and relationship-cutover boundaries. `make check` passes 223
    temporary-SQLite tests plus Ruff, formatting, and MyPy; `make docs-check`
    passes. The historical engineering-harness entry that reused AM-105 is now
    assigned the unused historical identifier `AM-123`, leaving AM-105 unambiguously assigned to provider
    request lifecycle. No product, schema, source-data, provider, or live
    maintenance action ran.

## In Progress

- [ ] AM-122 [P0] [Person Profile] — Deliver the single read-only,
  evidence-backed Person Profile product surface.
  - Plan: `docs/exec-plans/active/AM-122-person-profile.md`.
  - Scope: canonical identity, aliases, contact context, connected entities,
    current facts, operational commitments, history, deterministic linked-chat
    statistics, exact evidence, and one bounded presentation-only AI summary.
  - Guardrail: no live refresh, replay, backfill, new source, dashboard,
    scoring system, graph UI, or canonical graph mutation.
  - Progress 2026-08-24: profile composition, exact evidence closure,
    terminal rendering, migration 16, and summary refresh integration are
    implemented against temporary SQLite fixtures. `make check`, `make verify`,
    and generated-document validation pass. No live maintenance ran.
  - Progress 2026-08-24: normal terminal navigation is People-first; person
    discovery, compact profile sections, direct-chat response metrics, and
    recovery-only maintenance access are implemented with synthetic coverage.
  - Progress 2026-08-24: started the Textual relationship-intelligence
    replacement with bounded read-only People discovery, local fuzzy ranking,
    compact status, keyboard navigation, and a profile overview. Existing
    maintenance workflows remain protected while their native Textual parity
    is completed. No migration or source write ran.
  - Progress 2026-08-24: removed Textual search-path join amplification by
    loading discovery dimensions independently and debouncing input. Person
    detail now renders the existing bounded canonical profile composition with
    current context, items, projects, and exact citations instead of a sparse
    summary-only card. No migration or source write ran.
  - Progress 2026-08-24: Person detail now navigates every established bounded
    profile section, including contact briefing, loops, projects, facts,
    connections, timeline, communication, exact evidence, scan status, and
    clearly-labelled private or uncertain claim views. The command palette
    also exposes the complete protected operations workflow rather than hiding
    non-profile functionality.
  - Progress 2026-08-24: profile formatting now uses clear bounded sections
    rather than captured terminal tables. Deep Scan has an explicit status and
    queue screen: it discloses eligible/completed/pending/failed windows and
    queues at most two exact-evidence windows only after Enter.
    `make check` and `make docs-check` pass (197 temporary-SQLite tests);
    `make verify` is externally blocked only at `pip-audit` because this
    environment cannot resolve `pypi.org`.
  - Now: validate profile composition against representative contact shapes and
    add one deterministic, exact-evidence "Before I contact them" briefing.
    Prefer an explicit unknown/empty result to unsupported inference; no new
    persisted profile state, source, model work, graph projection, or live
    refresh is authorized.
  - Progress 2026-08-26: contact briefing coverage now proves that long,
    unlinked recent history cannot displace a direct group-context record;
    changed-context rows remain capped and retain their exact message evidence.
    Existing sparse/ambiguous and supported/unsupported-project fixtures cover
    the complementary unknown and mixed-project shapes. No schema, source,
    model, projection, or live operation changed.
  - Progress 2026-08-26: the representative briefing matrix also now proves a
    useful direct company connection appears only when the relationship keeps
    its exact cited message. No schema, source, model, projection, or live
    operation changed.
  - Progress 2026-08-26: restored the primary Textual profile path after the
    full quality gate found four missing presentation helpers. One bounded
    section/record model now renders all eight bound sections, preserves direct
    versus third-party/inference labels, and drills into exact evidence.
    Synthetic Textual coverage exercises every section plus fact-to-evidence
    navigation. No migration, scan, backfill, or live operation ran.
  - Progress 2026-08-26: command-palette filtering now waits for removed rows
    before mounting filtered commands, preventing duplicate widget IDs during
    normal typing. Temporary-SQLite Textual coverage proves exact filtering.
    No migration, source write, provider call, or live operation ran.
  - Progress 2026-08-26: Textual regressions now prove confirmation-gated task
    changes and person-scoped contact search rejects another person's matching
    task. No migration, source write, provider call, or live operation ran.

  - Progress 2026-08-24: the terminal defaults to a bounded People list.
    Name or visible-ID selection opens a profile; `/` opens a small searchable
    action palette, with maintenance shown only when explicitly searched.
  - Progress 2026-08-24: profile summaries are input-hash gated and a manual,
    bounded Deep Scan queues exact person-scoped message membership through the
    existing AI job/projection path. No live scan, backfill, or rebuild ran.
  - Progress 2026-08-24: audit coverage proves a queued Deep Scan window is
    claimable with its exact membership, and summary freshness includes both
    displayable canonical rows and their exact messages. Scan status now says
    when no eligible unscanned messages remain; failed windows remain retryable.
  - Progress 2026-08-24: migration 18 isolates manual Deep Scan work in the
    `profile` AI lane while preserving existing jobs and membership. Its
    source-authority validation prevents owner or third-party statements from
    automatically becoming person facts.
  - Progress 2026-08-24: Deep Scan now submits the complete resolved direct
    conversation as bounded chronological context. Local persistence rejects
    any extracted row whose cited source was not authored by the selected
    person, then completed projection follows the normal person invalidation
    and profile-refresh path.
  - Progress 2026-08-24: Deep Person Profile uses profile extractor v2 and
    migration 19 claim metadata to retain direct, third-party, and inference
    labels with effective dates. Only direct claims can create compatibility
    observations for canonical projection; uncertain claims remain traceable
    profile rows.
  - Progress 2026-08-25: audited profile action paths: the primary Textual
    Deep Scan now runs the same bounded processing workflow as the fallback
    terminal instead of leaving jobs queued. Summary packages exclude uncertain
    assertions completely. Explicit maintenance `full_refresh` /
    `resync_profiles` reconciles current permitted archive coverage, processes
    eligible history, and rebuilds all materialized person profiles without
    rewriting evidence, claims, canonical state, or manual decisions. No live
    operation ran.
  - Progress 2026-08-25: Deep Scan now drains pending profile windows before
    queueing more, so legacy queue-only backlogs shrink predictably. The
    profile-local screen distinguishes found evidence from ready work; Enter
    processes two windows and explicit `L` live-scans up to 64 existing windows.
  - Progress 2026-08-25: compacted the Textual Person Profile, corrected total
    communication statistics to aggregate all linked conversations, and added
    message-level AI coverage plus an explicit live bounded scan view. Removed
    only the unreachable Textual Ask screen; the fallback profile remains the
    recovery caller.
  - Progress 2026-08-25: fixed Textual scan lag by suppressing the competing
    Rich Live renderer only for the Textual caller and refreshing durable job
    state from shared-worker lifecycle callbacks.
  - Progress 2026-08-25: Textual Deep Scan now runs as one tracked background
    UI task, keeping the screen interactive while durable profile-lane job
    state progresses. Live polling avoids full history eligibility counts;
    bounded diagnostics expose claim authority mix, rejection reasons, and recent
    job outcomes without raw-message logging. Temporary-SQLite UI and worker
    tests pass; no live scan, migration, rebuild, or backfill ran.
  - Progress 2026-08-25: added evidence/window progress bars and corrected
    Deep Scan coverage by scoping visible counts, audit rows, and profile-job
    claims to the current extractor version. Legacy profile jobs remain durable
    history but cannot silently run or inflate v2 status. No live action ran.

- [x] AM-067 [P0] [Context ownership / Anti-slop] — Give each materialized context table exactly one writer and remove competing person-state projections.
  - Historical evidence: the original review found competing `ContextService`
    and `ContactContextMaterializer` writes to `person_context_state`.
  - Current source: `ContactContextMaterializer` is the sole person-context
    writer and refresh ownership runs through the revisioned invalidation path.
    Keep this task open only for a caller or test that proves a remaining
    competing writer or stale-summary retention defect.
  - Acceptance:
    - one authoritative writer per materialized table;
    - one defined person-context projection contract with deterministic inputs;
    - history/version rows capture the final committed semantic revision, not intermediate writer output;
    - removal/relink of bad source state can remove stale derived summaries rather than preserving them by default;
    - all materialized refresh ownership runs through AM-053 invalidation/revision scheduling;
    - shrink `process_ai_batch()` to canonical projection + dirty marking, not downstream recomputation.
  - Anti-slop constraint: do not solve this by wrapping both writers in additional manager/factory layers; delete the redundant writer/path.
  - Verification: same batch with waiting task + conversation context, corrected project/person link, empty-after-cleanup summary, no-op refresh, version history, and deterministic rebuild tests.
  - Completed 2026-08-28: source audit found the remaining profile-summary and
    canonical-person-merge table writes. Both now delegate to
    `ContactContextMaterializer`, leaving it as the sole SQL writer for
    `person_context_state`; merge relocation retains its existing behavior.
    No migration, rebuild, replay, provider request, or live operation ran.

- [x] AM-052 [P0] [Configuration correctness] — Make effective AI configuration have one value per concept and identical defaults across every construction path.
  - Code evidence: the `Settings` dataclass default is `ai_routing_mode="legacy"`, while `load_settings()` defaults `AI_ROUTING_MODE` to `quota_aware`. Tests or internal code that instantiate `Settings(...)` directly can therefore run a different routing architecture than the real application with no explicit override.
  - Code evidence: the same concepts exist twice: `gemini_model` vs `gemini_primary_model`, and `gemini_requests_per_minute` vs `gemini_primary_rpm`; legacy provider fields also coexist with the model registry.
  - Code evidence: `_bool()` silently converts every unrecognized value to `False` (`tru`, `enabled`, typo, etc.) instead of failing configuration validation, while `AI_INCLUDE_GROUPS` duplicates its own hand-written boolean parser.
  - Code evidence: the typo alias `GGEMINI_MODEL` is accepted as a normal resolution source with no deprecation visibility.
  - Acceptance:
    - one authoritative default source for runtime/tests/manual Settings construction;
    - one resolved primary Gemini model and one authoritative rate-limit concept per provider/model;
    - invalid boolean/config values fail loudly with the variable name and value;
    - all booleans use one parser;
    - compatibility aliases are explicit, tested, diagnostic-visible, and lower priority than current names;
    - direct `Settings(...)` test fixtures and `load_settings()` resolve the same behavior unless a test deliberately overrides it.
  - Verification: explicit settings, defaults, legacy-only settings, mixed settings, boolean typos, typo alias, direct dataclass construction, and effective-router configuration tests.
  - Completed 2026-08-28: removed the unused `Settings.gemini_model` mirror;
    `gemini_primary_model` is the sole effective Gemini primary-model field.
    Deprecated environment aliases remain boundary-only, lower-priority inputs
    with visible warnings. Per-model RPM remains bounded by the separately
    documented provider-wide conservative ceiling. No provider, schema,
    migration, replay, or live action ran.

## Next

- [ ] AM-121 [P1] [People and projects / Intelligence] — Add bounded,
  read-only graph queries and source-backed People/Project intelligence for
  timelines, commitments, recency, interactions, shared counterparties, and
  explicit blockers/dependencies. Defer graph-ranking algorithms.

- [ ] AM-072 [P0] [Projects] — Repair project health/state after task-project linking and stop marking every extracted project `critical`.
  - Evidence from live DB: all **100/100 projects** currently have status `critical`. With zero task→project links, project-health scoring has no reliable operational activity signal.
  - Acceptance: project state derives from real recent activity, linked open/waiting/overdue tasks, temporal events, conversation segments, and explicit project state—not absence of task links. Support `active`, `waiting`, `stale`, `critical`, `completed`, and `archived` where current domain rules allow.
  - Backfill: recompute all project health only after AM-070/AM-071 repair.
  - Verification: active recent project is not stale; historical project can be archived/completed; real overdue blockers can still become critical.
  - Plan: `docs/exec-plans/active/AM-072-project-health.md`.
  - Progress 2026-08-27: health now uses dated task evidence, project-linked
    observations, temporal events, and conversation intervals. Only a real
    overdue open/waiting task is `critical`; no activity is `stale`, while
    recent non-task evidence can be `active`. No recomputation/backfill/live
    action ran.

## Next

- [ ] AM-074 [P1] [Data repair] — Add a safe, resumable derived-state repair/backfill command for the existing live database after logic fixes.
  - Plan: `docs/exec-plans/active/AM-074.md`.
  - Progress 2026-08-28: bounded read-only inventory now reports capped
    task-project, segment-chat, and pending-context candidate counts without
    exposing content or writing rows. The dry-run/apply workflow, run ledger,
    and any production operation remain unimplemented.
  - Progress 2026-08-28: an explicit operation-selected dry-run now produces a
    deterministic scope fingerprint from those capped counts. Apply/resume and
    any production operation remain unimplemented.
  - Progress 2026-08-28: fixture-only task-project apply now requires the
    matching dry-run fingerprint and a separate recovery receipt, commits its
    bounded operation and checkpoint together, and is retry-safe. No operator
    apply command or production execution is authorized.
  - Progress 2026-08-28: task-project checkpoints retain the exact selected
    task IDs privately while dry-run output exposes only their digest; retry
    cannot drift to a newly eligible task set.
  - Scope: FTS rebuild, task-project backfill, task lifecycle reconciliation, project-health recompute, selective classification refresh, conversation-segment rebuild, and targeted context refresh.
  - Safety: raw `messages`, message versions, AI evidence, manual feedback, pinned memory, and manually locked task state must never be deleted or rewritten. Require SQLite API backup for any migration/table rebuild.
  - UX: dry-run/report mode first, then bounded/resumable apply mode with exact before/after counts.
  - Verification: run on copied fixture DB twice with no duplicate side effects.

- [ ] AM-056 [P1] [Context graph] — Add a non-mutating semantic graph-discovery pass for candidate cross-chat relationships that deterministic repair cannot prove.
  - Acceptance: AI may propose person/project/company/task/event/topic links only as source-backed candidates; canonical graph state changes only through existing high-confidence deterministic rules or manual Review acceptance.
  - Diagnostics: show candidate confidence, evidence, relationship path, and why the candidate was proposed.
  - Verification: true cross-chat discovery, false lexical match rejection, idempotent candidate creation, and review-acceptance tests.

- [x] AM-057 [P1] [Context freshness] — Add explicit freshness/current-enough metrics and selective stale-work scheduling based on dependency footprint.
  - Plan: `docs/exec-plans/completed/AM-057-context-freshness.md`.
  - Acceptance: distinguish archived, classified, semantically analyzed, canonicalized, context-integrated, and current-enough coverage; high-value operations detect stale materialized context before presenting it as current.
  - Current DB baseline: all 65,475 non-bot personal text messages are classified, but only 45,976 are semantically analyzed; 241/389 tracked conversations are not semantically complete.
  - Code evidence: graph improvement currently marks **every high/critical message in an affected chat** `context_stale` / `analysis_stale` after a graph change, even when only one entity/link changed. This can trigger unnecessary broad re-analysis and feedback loops.
  - Acceptance:
    - invalidation is tied to affected entity/message/context revisions, not whole-chat importance buckets;
    - compare `context_version_used`/analysis version with the dependency revision that actually changed;
    - a deterministic graph/materialization change should normally refresh derived context without re-calling the LLM unless interpretation of specific source evidence is genuinely stale.
  - Integration: person/project profiles, Ask Memory, Task Deep Dive, history status, runtime status, and AM-053 dirty queue.
  - Verification: identity merge/project relink/relationship change marks only dependent state stale; unrelated corpus remains untouched; no graph→AI→graph reanalysis loop.
  - Progress 2026-08-28: graph improvement now records only its affected
    conversation/person/company/project/task scopes plus global state in the
    revisioned invalidation ledger. It no longer marks whole-chat
    classifications or AI analyses stale, so deterministic repair does not
    requeue unrelated source messages. Freshness metrics remain this task's
    next increment. No schema, replay, or live action ran.
  - Progress 2026-08-28: runtime context freshness now includes pending,
    running, and failed revisioned refresh scopes, rather than treating only
    source-message stale flags as dirty. This is read-only status reporting;
    no schema, replay, or live action ran.
  - Progress 2026-08-28: the runtime coverage snapshot now distinguishes
    eligible archived, classified, semantic, canonicalized, context-integrated,
    and conservatively current-enough messages. Current-enough requires a
    committed integrated batch and no pending refresh scope. The remaining
    precision increment is dependency-revision comparison for
    `context_version_used`; no schema, replay, or live action ran.
  - Completed 2026-08-28: migration 21 records each accepted batch's exact
    canonical scope/revision dependencies against its exact message membership.
    Current-enough now checks those rows against the revisioned ledger; legacy
    rows remain explicitly partial and are never auto-backfilled. No source,
    claim, canonical, replay, or live action ran.

- [x] AM-093 [P0] [Retrieval / Context grounding / Anti-vibe] — Completed related, temporal, and supporting-evidence retrieval alignment.
  - Progress 2026-08-26: active Person Intelligence leaf. Textual “Search this
    contact” now uses canonical person-scoped retrieval; ContextBuilder closes
    supporting evidence over exact canonical chat/message pairs or immutable
    claim evidence, and Task Deep Dive no longer widens related chats through
    raw context evidence. Temporary-SQLite regression coverage rejects a newer
    unlinked message from the same chat and proves claim-backed facts resolve
    their exact submitted message. Unresolved ordinary context requests now
    fail closed for tasks/events instead of receiving global operational state.
    Retrieval ranking now preserves distinct chat/date provenance for summaries
    without a numeric source ID rather than deduplicating them together.
    Historical related retrieval is regression-proven to omit future task state
    and select the temporal-fact interval valid at `as_of`.
    SQL fallback and FTS now share a bounded all-term candidate rule, so a
    reversed multi-word query selects the same qualifying message and excludes
    partial-term matches. Temporary-SQLite coverage exercises SQL-only forward
    and reverse word order plus FTS parity. No migration or live action ran.
    Completed 2026-08-26: all listed acceptance and verification boundaries are
    covered by temporary-SQLite regressions; no migration or live action ran.
  - Existing retrieval evidence: `retrieve_related(..., as_of=...)` accepts `as_of` but does not use it, and mostly falls back to name search for entity scopes.
  - ContextBuilder evidence: when no entity/task/chat links resolve, `_tasks()` and `_events()` can fall back to global recent/open state and inject unrelated operational data into an ordinary Ask/context request.
  - ContextBuilder evidence: `_evidence()` collects source **chat IDs** from selected facts/tasks/events/relationships and then returns the newest messages from those chats instead of the exact `source_message_id` rows. `LIMITED SUPPORTING EVIDENCE` can therefore be unrelated to the claim it appears to support.
  - Task Deep Dive evidence: `_related_chats()` further imports chat IDs from `context.evidence`; noisy “supporting evidence” can therefore widen Deep Dive's raw-search neighbourhood and amplify the original grounding error.
  - Resolved retrieval evidence: result dedup preserves distinct daily/monthly
    summaries without numeric source IDs, and SQL/FTS candidate matching is
    bounded and independent of query word order.
  - Acceptance:
    - real entity-scoped retrieval or honest API naming; no “related” wrapper around generic name search;
    - no global task/event fallback for a scoped/query context merely because entity resolution found nothing; global state is opt-in by purpose;
    - exact source-message closure for selected canonical facts/tasks/events/relationships comes first;
    - optional surrounding chat messages are separately labelled `context window`, never `supporting evidence`;
    - related-chat expansion may use only canonical relationships/segments/exact evidence, not already-broadened raw context;
    - every result has a stable provenance/evidence identity;
    - `as_of` is enforced where supported and explicitly unavailable where underlying state is not historical;
    - SQL fallback is bounded and order-insensitive.
  - Verification: unresolved query with no global leakage, exact source-message grounding, noisy related-chat rejection, unrelated latest-chat-message rejection, person/company/project/task scope, historical `as_of`, multiple summaries, word-order fallback, and FTS/SQL parity tests.

- [x] AM-085 [P1] [Memory / Anti-slop] — Remove copy-only `entity_memory` behavior and keep only memory that adds information.
  - Plan: `docs/exec-plans/completed/AM-085-entity-memory-removal.md`.
  - Evidence from live DB: **753/753** `entity_memory.summary` rows are exact copies of `ai_items.title + ": " + ai_items.details`.
  - Code evidence: `process_ai_batch()` persists `f"{title}: {details}"` into `entity_memory`; there is no consolidation, supersession, multi-source merge, or state transition.
  - Context-engine evidence: `ContextBuilder._summaries()` reads this copied layer as `DURABLE SUMMARIES`, and `ContextService._refresh_person_state()` also uses it to build person current/long-term summaries. The duplicate observation therefore contaminates more authoritative-looking context layers.
  - Acceptance: either make `entity_memory` a true consolidated multi-observation memory with a distinct consumer/invariant, or remove it from active retrieval/context/profile paths and use source-backed observations/facts/events directly.
  - Anti-slop rule: no persisted layer may exist solely to rename/copy another derived record.
  - Verification: retrieval/context/profile parity before deprecation/removal, provenance retained, and no copied summaries recreated after repair.
  - Completed 2026-08-28: removed active projection, context, retrieval,
    generic-profile, and FTS paths. Bounded source-backed `ai_items` now serve
    those consumers directly with item provenance. Existing rows are inert
    legacy state; no deletion, migration, replay, or live action ran.

- [ ] AM-094 [P0] [Ask Memory / AI routing / Anti-vibe] — Rebuild Ask Memory around one real retrieval→evidence→router pipeline and remove its private provider stack.
  - Code evidence: `answer_question_with_ai()` directly calls `_gemini_qa()` and then `_groq_qa()`; it never uses the quota-aware `AIRouter`, model registry, workload policy, persistent model usage, cooldown reasons, or configured fallback chain.
  - Code evidence: `answer_question()` reduces retrieval to at most **5** selected rows. If any returned task is `WAITING`, it discards all non-waiting evidence and returns only waiting tasks; `answer_question_with_ai()` then sends that already-truncated set to the model.
  - Code evidence: the prompt includes structured canonical context but says only numbered retrieval rows may be cited; `validate_citations()` accepts only `[n]` against that small selected set. Canonical facts that appear only in structured context are therefore uncitable under the function's own contract.
  - Code evidence: broad `except Exception` around each provider call treats programming/config/schema bugs the same as recoverable provider failures.
  - Acceptance:
    - deterministic retrieval produces a bounded candidate set independent of the human-readable fallback answer;
    - evidence selection uses the configured context budget and keeps a balanced mix of canonical/task/summary/raw evidence according to the actual question;
    - waiting-task specialization happens only when the question is actually about waiting/follow-up state;
    - QA dispatches one typed high-priority `AIRequest` through the central `AIRouter`;
    - remove direct Gemini/Groq SDK helpers from `intelligence.py`;
    - every factual source available to the model has a stable allowed citation identity, or is explicitly marked non-citable background;
    - provider fallback is handled by router-classified failures, not blanket exception swallowing;
    - offline/local deterministic answer remains available when AI is disabled/unavailable.
  - Verification: broad person/project history question, waiting-state question, mixed evidence, quota fallback/accounting, citation validity, provider failure, and no-LLM fallback tests.

- [ ] AM-096 [P1] [Database migrations / Anti-slop] — Make schema evolution have one truthful source of behavior and freeze old migrations.
  - Code evidence: the giant `SCHEMA` bootstrap already creates tables that are later “added” again by migrations 4–10 (`source_evidence`, classification state, conflict review, conversation segments, conversation intelligence, etc.).
  - Code evidence: migration 2 and migration 7 both delegate to the same mutable `COMPATIBILITY_COLUMNS` map. Changing that shared map changes what old migration versions do on a fresh/legacy adoption path, violating immutable migration semantics.
  - Code evidence: a fresh database therefore receives a hybrid sequence: migration 1 creates much of the future schema, migration 2 fills omitted columns, later migrations often no-op, and migration 8 rebuilds a policy table that bootstrap already created in its current form.
  - Code evidence: `_cleanup_legacy_empty_ai_marks()` is a semantic data repair executed on every normal `connect()` outside the migration ledger; interrupted-job requeue is valid runtime recovery, but one-time historical cleanup is not the same thing.
  - Acceptance:
    - choose one model: true sequential immutable migrations, or a current-schema bootstrap that marks fresh DBs at current version plus separate legacy upgrade migrations;
    - old migration functions contain frozen explicit behavior and never depend on a shared map that evolves later;
    - one-time semantic/data repairs are versioned repair/migration steps, not hidden startup behavior;
    - runtime recovery (`running`→`pending`) remains explicit and idempotent;
    - fresh and every supported legacy fixture converge to the same schema and invariants.
  - Safety: do not rewrite migration history already recorded in the live database; introduce forward-only fixes.
  - Verification: fresh DB, pre-ledger DB, each representative legacy schema, interrupted migration/reopen, and schema-diff tests.


- [ ] AM-103 [P1] [Analytics / Diagnostics truthfulness] — Stop diagnostics from presenting guessed, stale, or dimensionally invalid metrics as system health.
  - Existing evidence: AI failure rows can be stored with `provider=NULL` / Groq model fallback and analytics `COALESCE(provider,'groq')`, falsely attributing unknown/router failures to Groq.
  - Existing evidence: history coverage counts classification rows without requiring current classification version/non-stale state; raw `ai_items` are presented as open actions instead of canonical tasks.
  - Context diagnostics evidence: `graph_diagnostics().heuristic_coverage` computes `(entity_count - orphan_task_count) / entity_count`, subtracting **tasks from entities**. The percentage has no coherent denominator and can claim graph “coverage” without measuring graph coverage.
  - Context diagnostics evidence: route totals are derived by subtracting archive/news/operational/state-change counts even though those predicates can overlap, so `route_contextual_memory` is not a true partition.
  - History monitor evidence: preferred/next-route text is hard-coded and can disagree with the actual registry/session-pinned route.
  - Acceptance:
    - every diagnostic metric has a documented numerator/denominator/domain;
    - unknown attribution stays unknown/legacy;
    - coverage requires current versions and non-stale state;
    - distinguish extracted observations, canonical tasks, integrated context, and graph linkage;
    - routing monitor renders actual candidate chain/decision/quota state;
    - remove any metric that cannot be defined coherently rather than inventing a percentage.
  - Verification: stale/versioned rows, provider/router failures, canonical-vs-observation counts, graph coverage fixture, overlapping routing categories, Gemma/session-pinned route, and zero-data state.







- [ ] AM-107 [P0] [Task Deep Dive / Evidence integrity] — Make every Deep Dive evidence row demonstrably belong to the investigated task.
  - Crash bug: `structured_evidence()` builds fact IDs with `fact['fact_id']`, but `current_facts()`/`ContextBuilder._facts()` do not return `fact_id`. Any Deep Dive with non-empty temporal facts can raise `KeyError`.
  - Contamination bug: event filtering treats `task_id=NULL` as acceptable because `None` is explicitly in the allowed tuple. Therefore **every unlinked context event** returned by the broader task context is accepted as task evidence without `_event_matches_task()` being required.
  - This is especially dangerous because many existing task lifecycle events have `task_id=NULL`.
  - Contamination bug: every `context.fact` in the broader entity context is promoted to task evidence without an explicit task/source relationship.
  - Matching bug: `_event_matches_task()` extracts task terms with ASCII-only `[a-z0-9]`; non-Latin task titles cannot use the fallback matcher.
  - Dedupe bug: `_dedupe_and_limit()` uses `{evidence_id: item}` and therefore lets a later duplicate silently overwrite an earlier stronger representation (for example exact origin evidence can be replaced by a lower-scored raw-search copy of the same message).
  - Dead-code smell: `_task_events()` always returns `[]` while lifecycle evidence is actually loaded through a separate path; remove the fake abstraction.
  - Acceptance:
    - ContextBuilder/current-fact records expose stable fact IDs where a fact is citeable;
    - event evidence requires exact canonical `task_id`, exact source linkage, or an explicit conservative task-match rule; `NULL` is never an automatic match;
    - entity-context facts are labelled contextual background unless they have a task-specific link/source reason;
    - evidence dedupe retains/merges the strongest provenance representation deterministically;
    - remove dead `_task_events()` path;
    - no evidence item enters the report without a machine-readable `why this belongs to task` reason.
  - Verification: fact-bearing task (no crash), unrelated `task_id=NULL` event, correctly linked event, Russian task title, contextual entity fact, duplicate origin/raw message, and lifecycle evidence tests.

- [ ] AM-108 [P0] [Historical context / `as_of`] — Make historical context and Task Deep Dive fail-closed; prevent current state from leaking into past views.
  - ContextBuilder evidence: chat entity seeds come from current open tasks and `ai_items` without consistently applying `request.as_of`; future observations can influence a historical query.
  - ConversationContextService evidence: `_project_contexts(person_id)` ignores `as_of`; `_historical_conversation()` does not require the selected segment to still be active at the cutoff.
  - Global-state evidence: people-requiring-attention uses current open loops with no `as_of` cutoff; current task/project rows cannot reconstruct historical lifecycle merely from `updated_at<=as_of`.
  - Task Deep Dive evidence: `_task(task_id)` always loads the **current** task row. A Deep Dive `as_of` before a later completion/title/due-date/status change can therefore display today's task state as if it were historical.
  - Task Deep Dive evidence: lifecycle rows are filtered by event `created_at`, while canonical task state itself has no corresponding versioned reconstruction in the report.
  - Acceptance:
    - every field returned in an `as_of` context/report is interval/version/event-backed for that instant or explicitly omitted/marked unavailable;
    - entity seed selection, project context, open loops, task/project state, summaries, and segments all respect the same cutoff;
    - reconstruct task lifecycle from authoritative `task_events`/manual history where possible;
    - current materialized rows are never silently reused as historical truth;
    - report/diagnostics state when historical fidelity is partial.
  - Verification: Deep Dive before/after completion, title/due-date change after cutoff, project relink after cutoff, future contact project, ended segment, future AI observation, and current open loop absent from past snapshot.

- [ ] AM-109 [P0] [Context graph repair / Canonical safety] — Make deterministic graph repair truly local in evidence and time before it is allowed to mutate canonical links.
  - Code evidence: `_chat_project_consensus()` treats all project-linked tasks in a chat as one consensus regardless of when they occurred.
  - Code evidence: with two anchors to one project, `_repair_orphan_records()` auto-assigns **every** fully orphan open task, event, and person/company fact in that chat to the project, with no temporal proximity to the anchors/source message.
  - Example failure: two Project A tasks from 2021 can auto-link an unrelated orphan 2026 task/fact in the same long-lived chat to Project A.
  - Code evidence: `_accepted_item_links()` equates `confidence >= 0.90` with accepted evidence and does not exclude manually rejected/ignored source observations.
  - Code evidence: a targeted `improve(person/project/task)` still calls `_repair_temporal_segments()` globally, so “targeted” graph maintenance can mutate unrelated fact timelines.
  - Acceptance:
    - automatic repair requires independent source anchors in the same bounded temporal/source neighbourhood, not merely the same chat;
    - facts/events/tasks use occurrence time and conversation segment boundaries when proposing a project;
    - manually rejected/ignored evidence cannot regenerate relationships;
    - targeted improvement never mutates unrelated global state;
    - insufficient evidence creates Review candidates only;
    - relationships carry source provenance and can be superseded/removed when their canonical support is corrected.
  - Verification: years-apart same-chat anchors, two independent nearby anchors, competing projects, manual rejection, targeted person improvement with unrelated fact timeline, and relink/removal tests.



- [ ] AM-110 [P1] [Conversation segmentation] — Make project/contact periods represent bounded activity intervals instead of anchor-count illusions.
  - Code evidence: `ConversationSegmenter` starts a new project period only when `project_id` changes. Two anchors for the same project separated by years are merged into one period; the 90-day expiry is applied only after the **last** anchor, so the segment can incorrectly span the entire multi-year gap.
  - Code evidence: confidence becomes `0.95` merely because there are two anchors, even if they are not temporally close or independent.
  - Contact-materializer evidence: contact segments use a different 60-day split rule and `_segment_end()` ends a multi-record segment at its last activity; historical conversation lookup then ignores `ended_at`, so the two segment systems have incompatible interval semantics.
  - Acceptance:
    - split same-project anchors when inactivity exceeds the configured period;
    - define one interval convention for project and contact conversation segments (`[started_at, ended_at)`), including open/expired periods;
    - confidence uses independent/temporally coherent anchors, not raw count alone;
    - historical lookup requires the segment to be active at `as_of` when asking for active state, while timeline views may list completed periods;
    - rebuild is deterministic/idempotent.
  - Verification: same project after 2 years, 89/91-day gaps, A→B→A return, one/two duplicated anchors, historical midpoint query, and contact/project segment consistency.





- [ ] AM-111 [P1] [Task Deep Dive / Multilingual anti-slop] — Remove English-only concept extraction and hard-coded current-deal vocabulary from the core retrieval engine.
  - Code evidence: `task_concepts()` and `_evidence_terms()` use `[a-z0-9...]` regexes, so Cyrillic/Georgian/non-Latin words are mostly discarded even though the archive is multilingual.
  - Code evidence: `_STOP_WORDS` is effectively English-only.
  - Code evidence: `_DOMAIN_TERMS` hard-codes current business vocabulary such as `tbc`, `hedging`, `flow-of-funds`, `fx`, and `spread` into generic Task Deep Dive core logic.
  - Consequence: real Russian/Georgian task concepts may never be searched, while one specific deal domain gets privileged expansion across unrelated tasks.
  - Acceptance:
    - Unicode-aware tokenization/casefolding throughout concept discovery and task matching;
    - language-appropriate minimal stopword handling only where it measurably improves retrieval;
    - canonical aliases/entities/relationships and evidence-derived terms drive expansion by default;
    - any domain thesaurus is explicit configurable/domain-context data with provenance, not hard-coded to one user's current deals in core code;
    - SQLite LIKE fallback limitations for non-ASCII case matching are tested/documented; prefer working FTS for multilingual search.
  - Verification: Russian, Georgian, English, mixed-language task titles/messages, morphology/punctuation, TBC-like entity as canonical alias rather than magic token, and unrelated-domain regression tests.



- [ ] AM-112 [P1] [Task Deep Dive / Session state] — Make investigation sessions reproducible, versioned, and internally consistent instead of being a loose write-side cache.
  - Code evidence: session `summary_json` stores only `concepts` and `evidence_ids`; it does not persist the query, `as_of`, deeper/search mode, retrieval/config version, or diagnostics needed to reproduce why evidence was selected.
  - Code evidence: `_discovered_terms(task_id, as_of)` compares **session `updated_at`** to evidence `as_of`. Investigation wall-clock time and historical evidence cutoff are different time axes.
  - Code evidence: updating an existing session inserts/replaces current evidence rows but does not delete evidence rows that disappeared from the session's new `evidence_ids`, leaving the session table with stale membership.
  - Code evidence: `pin_evidence()` accepts any arbitrary string without verifying that the evidence belongs to this task/session.
  - Acceptance:
    - persist query/mode/as_of/retrieval-version and enough diagnostics to explain/reproduce a session;
    - session creation/update time is never used as a substitute for evidence-time cutoff;
    - replacing session evidence makes persisted membership exactly equal to the current selected evidence set;
    - pins validate task/session evidence ownership, while intentionally persistent pins are migrated explicitly between sessions;
    - build/search/ask side effects are documented as investigation-session persistence, not hidden retrieval mutation.
  - Verification: historical session created today, repeat search with evidence removed, retrieval-version change, invalid pin, session replay/explain output, and previous-session extension tests.

- [ ] AM-079 [P0] [Canonical facts / Anti-slop] — Replace keyword/suffix-driven “temporal facts” with a small explicit state-projection contract, or remove the layer.
  - Evidence from live DB: 550 `important_fact` AI items exist (536 at confidence >= 0.90), but `context_facts` has only 30 rows and **all 30 use `corporate_documents_status`**.
  - Code evidence: any person-linked AI item containing the substring `document` can update that person's `corporate_documents_status`; this is a hard-coded heuristic, not a well-defined domain fact.
  - Code evidence: every project-linked task/follow-up/deadline/promise can overwrite one global `project_work_status={"status": task_status, "title": task_title}`. The latest task is not the state of the project; once AM-070 starts linking projects this would generate large amounts of false canonical state.
  - Code evidence: `set_temporal_fact()` decides whether a predicate is mutable state by checking whether its **name ends with** `_status`, `_state`, or `_progress`.
  - Acceptance:
    - explicit registry/spec per supported predicate: subject type, value schema, transition semantics, source kinds, consumer, and conflict policy;
    - task lifecycle remains task state unless an explicit deterministic projector derives a real project/deal state;
    - remove `document` substring projection and generic suffix semantics;
    - no new temporal predicate without a real consumer and tests;
    - conflict resolution revalidates the latest predicate timeline transactionally so a stale pending conflict cannot create two current facts;
    - duplicate conflict observations from the same source are idempotent.
  - Dependency: fix this before large task→project backfill/reprojection creates `project_work_status` slop.
  - Verification: multiple simultaneous project tasks, document mention unrelated to KYB, legitimate document-status transition, stale conflict resolution, duplicate replay, and predicate-contract tests.

- [x] AM-086 [P1] [Events / Anti-slop] — Stop creating generic `observation_recorded` context events that duplicate AI observations.
  - Plan: `docs/exec-plans/completed/AM-086-observation-event-removal.md`.
  - Evidence from live DB: **612/612** `context_events(event_type='observation_recorded')` copy the source AI item's title and details exactly.
  - Acceptance: retain only semantic events that represent an actual dated/state occurrence (task lifecycle, promise lifecycle, payment, meeting, decision, project change, etc.); ordinary observations remain in `ai_items`.
  - Consumers must use the original observation when an event adds no semantics instead of relying on a duplicate wrapper.
  - Repair: safely remove/rebuild only duplicate derived events after consumers are migrated.
  - Completed 2026-08-28: ordinary observations stay as source-backed
    `ai_items`; only explicit semantic mappings create events. Context,
    profile, related retrieval, and contact timeline readers ignore retained
    legacy wrappers and retain the direct observation. No migration, replay,
    deletion, or live repair ran.
  - Verification: timelines, Search, context packages, and Deep Dive retain evidence coverage without duplicate entries.

- [ ] AM-087 [P1] [Conversation intelligence] — Rebuild contact/conversation materializations after source-identity and freshness fixes.
  - Depends on: AM-084 and AM-053.
  - Acceptance: rebuild `conversation_contact_segments`, `current_conversation_context`, `person_project_context`, `conversation_open_loops`, and related contact summaries only from corrected canonical identity and accepted source-backed state.
  - Safety: never rewrite raw Telegram messages, AI evidence, manual feedback, task locks, notes, or pins.
  - Verification: rebuild is bounded/idempotent and a second run produces no duplicate materialized state.

- [x] AM-088 [P0] [Open loops / Anti-slop] — Give conversation open loops a real lifecycle instead of append-only heuristic memory.
  - Plan: `docs/exec-plans/completed/AM-088-open-loop-lifecycle.md`.
  - Evidence from live DB: 629 open/waiting loops; **440** are older than 90 days and **193** are older than one year.
  - Code evidence: `_materialize_open_loops()` selects only currently open/waiting tasks and upserts them, but never resolves/removes an existing loop when its canonical task later becomes `done` or `canceled`. This directly creates stale task loops.
  - Code evidence: question→answer linking scans only the latest 120 messages and can resolve the latest opposite-author question when a later message merely contains weak tokens such as `yes`, `sent`, `confirmed`, `готов`, `отправ` or a percentage.
  - Acceptance:
    - task-backed loops mirror canonical task lifecycle exactly and cannot remain open after the task is done/canceled;
    - explicit promises/follow-ups keep durable lifecycle;
    - heuristic unanswered questions are low-confidence derived UI state, not equivalent to canonical tasks;
    - question resolution requires bounded conversational adjacency/direction and stronger evidence; ambiguous matches remain unresolved/reviewable;
    - ordinary historical questions age out of Current while remaining queryable in history;
    - rebuild removes stale materialized loops rather than only inserting/updating rows.
  - Verification: waiting→done/canceled task, old stale loop cleanup, multiple nearby questions, unrelated `yes`, percentage reply, answer outside bounded window, restart/rebuild, and manual keep/pin cases.
  - Completed 2026-08-28: task loops now mirror scoped open/waiting canonical
    tasks, removing stale/done/canceled/orphaned derived rows on refresh.
    Question loops resolve only to an adjacent substantive opposite-author
    reply and age to resolved history after 90 days.

- [ ] AM-091 [P1] [Generated text quality] — Remove prompt-internal `ME` terminology from user-facing derived text.
  - Evidence from live DB: the internal marker appears in hundreds of derived records, including AI item details, task details, memory chunks, daily/monthly summaries, and context summary versions.
  - Acceptance: keep `owner=me` as structured metadata; generated prose uses the configured user display name or neutral wording. Raw Telegram evidence is never rewritten.
  - Verification: prompt parsing still uses structured ownership while rendered/persisted human-readable summaries contain no internal control-token leakage.

- [ ] AM-077 [P1] [Project quality] — Add project qualification, deduplication, and merge/review so casual plans and near-duplicate deal names do not pollute canonical projects.
  - Evidence from live DB: 100 projects include clear near-duplicates and items that look more like events/plans than durable projects (for example repeated cash-to-crypto variants, duplicate IT-product descriptions, meetings/road trips/BBQ-style items).
  - Acceptance: project creation requires durable-project evidence; likely duplicates become merge candidates with provenance; casual/social/event items remain events/tasks/topics instead of canonical projects.
  - Verification: duplicate project fixture, false-project fixture, manual merge authority, and no loss of historical source references.

- [ ] AM-058 [P1] [AI routing] — Make fallback/session pinning reason-aware and make fallback telemetry truthful.
  - Current behavior: after any successful non-first route, `session_model_key` is promoted to the front for later requests regardless of why fallback happened.
  - Code evidence: once a fallback model is session-pinned to index 0, later requests report `fallback_used=False` even though routing is still intentionally displaced from the normal preferred chain; analytics therefore undercount prolonged fallback usage.
  - Policy:
    - daily/RPD exhaustion may strongly pin an alternative for the relevant run/day;
    - provider-health faults use cooldown-based displacement;
    - RPM/TPM pressure waits or temporarily reroutes according to priority;
    - isolated 5xx/schema/JSON/programming failures must not permanently reroute unrelated later work;
    - pinning is workload-compatible and must not inject a model that is ineligible for a future workload.
  - Telemetry must distinguish `preferred_route`, `temporary_fallback`, `session_pinned_fallback`, and `forced_override`.
  - Verification: RPD exhaustion, RPM/TPM pressure, provider outage, schema failure, one-off server error, recovery, cross-workload request, and fallback-count accuracy.

- [ ] AM-061 [P1] [AI model registry] — Expand the registry only after provider execution and quota/capability routing are real.
  - Add `openai/gpt-oss-120b`, `qwen/qwen3.6-27b`, and a separate `groq/compound-mini` explicit external-research route.
  - Dependency: AM-104 must guarantee the selected Groq profile actually invokes that exact model; AM-106 must account for physical requests/usage; AM-099 must enforce workload/capability eligibility.
  - Current code evidence: the existing Groq `ModelProfile` has `rpm=None`, `tpm=None`, `rpd=None`, so quota-aware admission does not enforce the account limits already known for Groq.
  - Current code evidence: model/account limits include daily token limits, but `ModelProfile`/`QuotaTracker` do not model token-per-day at all.
  - Acceptance:
    - encode real per-model local guards (RPM/TPM/RPD and token/day where applicable);
    - 120B is reserved for high-value reasoning;
    - Qwen is available for multilingual/ambiguous reasoning;
    - Compound Mini is never ordinary internal-memory fallback and may only run under explicit `EXTERNAL_RESEARCH` with provenance isolation;
    - verify actual provider model IDs/capabilities before hard-coding;
    - the model reported in result/usage/diagnostics must equal the selected registry profile.
  - Verification: model-limit admission, daily-token pressure, exact selected-model execution, workload suitability, prompt-size guards, external-research separation, and fallback behavior.

- [ ] AM-062 [P1] [Documentation truthfulness] — Repair current documentation drift and make docs checks catch claims that are not true in runtime.
  - Progress 2026-08-26: the migration ledger is unique and ordered through
    migration 19 (including migration 16); TD-006/TD-007 now describe the
    remaining bounded debt instead of removed foundations; AM-118 identifies
    its review baseline as historical. Current source confirms routed Ask
    Memory and classifier version 2, so the prior mismatch claims are now
    historical rather than current runtime evidence.
  - Acceptance:
    - docs describe current behavior, not intended architecture;
    - when a task is not implemented yet, docs explicitly label it planned/degraded rather than presenting it as live;
    - generated config/schema docs come from effective authoritative definitions;
    - add focused checks for unique/ordered migration numbers and other machine-verifiable invariants.
  - Verification: `make docs-check` plus focused migration/config/runtime-contract checks.

## Backlog

- [ ] AM-078 [P1] [Database integrity] — Enforce and audit logical referential integrity instead of merely declaring relationships in schema prose.
  - Evidence from live DB: 91 application tables exist but only two declared SQLite foreign keys; sampled logical-reference checks found no current orphans.
  - Code evidence: `database.connect()` does **not** execute `PRAGMA foreign_keys=ON`, so even the declared foreign keys are not enforced by SQLite on normal application connections.
  - Acceptance:
    - enable foreign-key enforcement for every application connection before migrations/runtime writes;
    - add `make db-check` logical-reference checks for references not represented as SQLite FKs (tasks→entities/items, AI items→source messages/entities, relationships→entities/messages, open loops→tasks, conversation context→people/projects, evidence versions→evidence);
    - do not add risky FK table rebuilds merely for architectural purity; use application checks where safer.
  - Verification: injected-orphan fixtures are detected with actionable table/key output, declared FK violations fail at write time, and current DB passes after repair.

- [ ] AM-059 [P2] [Data model truthfulness] — Document every persisted layer by source-of-truth, consumer, rebuildability, and actual stored representation.
  - Acceptance: every important table is labelled SOURCE / CANONICAL / MATERIALIZED / WORK-DIAGNOSTIC / deterministic rollup, with exact rebuild inputs and stale/invalidated behavior.
  - Code evidence: daily/monthly “summaries” are deterministic dedupe/concatenate rollups rather than fresh semantic summaries; document them accordingly.
  - Code evidence: `snapshot_global_state()` inserts `BuiltContext.render(...)` plain text into a column named `global_state_snapshots.state_json`. Either store actual JSON matching the column/consumer contract or rename/migrate the representation; do not keep a field name that lies about its contents.
  - Goal: prevent future changes from treating caches as evidence, derived observations as canonical state, or text blobs as structured JSON merely because the schema name says so.

- [ ] AM-060 [P1] [Task Deep Dive / QA truthfulness] — Either implement real evidence-grounded Deep Dive Q&A or rename the current helper so it does not pretend to answer questions.
  - Code evidence: `TaskDeepDiveService.ask()` is not semantic Q&A. It splits the question and evidence on whitespace, selects evidence with exact token overlap, and otherwise returns the first five selected evidence rows as bullet text.
  - Consequence: morphology, punctuation, synonyms, Russian inflection, and conceptual questions are missed; when nothing matches, unrelated high-ranked evidence is presented as an “answer”.
  - Acceptance:
    - deterministic retrieval/timeline/evidence remains authoritative and fully usable offline;
    - the non-AI path is honestly named/presented as evidence lookup, not synthesized answer;
    - optional AI synthesis uses the central AIRouter/`TASK_DEEP_DIVE` workload, receives only selected evidence IDs, and cites only those IDs;
    - AI distinguishes fact / inference / recommendation and never controls retrieval;
    - no answer is produced when the selected evidence does not support one; return explicit unknown instead.
  - Verification: Russian/English question variants, punctuation/morphology, unsupported question, mixed evidence, valid/invalid citations, router fallback, and offline evidence-only mode.

- [ ] AM-063 [P1] [Conversation intelligence / Freshness] — Make context revisions and evidence-through markers mean actual content freshness, not refresh count.
  - Code evidence: `current_conversation_context.context_version` increments on **every** refresh, even if the resulting state is identical. The version therefore measures executions, not semantic revision.
  - Code evidence: `evidence_through_at` is set to the last task/AI activity record, not the latest archived/classified/semantically integrated source evidence; raw messages can be newer without the field explaining whether that is expected or stale.
  - Code evidence: `person_context_state` has no matching content revision and can be rewritten by multiple producers (resolved by AM-067).
  - Acceptance:
    - track separate source/archive, classification, semantic, canonical, and materialized revision/freshness boundaries where needed;
    - increment materialized context version only when content/dependency revision changes;
    - expose `context_updated_at`, dependency revision, new evidence since materialization, and pending semantic/refresh work without scanning lifetime history;
    - RuntimeStatus and profiles can distinguish `fresh`, `new raw evidence pending`, `semantic pending`, and `materialization dirty`.
  - Verification: no-op refresh, new irrelevant raw message, new relevant semantic evidence, task-state update, project relink, and restart tests.

- [ ] AM-064 [P2] [Configuration simplification] — Remove the legacy provider/model configuration surface after AM-052 establishes one authoritative effective configuration.
  - Current duplication: `AI_PRIMARY_PROVIDER` / `AI_FALLBACK_PROVIDER`, `GEMINI_MODEL`, `gemini_model`, `gemini_primary_model`, `GEMINI_REQUESTS_PER_MINUTE`, and per-model quota fields describe overlapping routing concepts.
  - Acceptance: the model registry + workload policy become authoritative; legacy names are compatibility inputs only at the configuration boundary and never flow through business logic as a second routing system.
  - Diagnostics must show both the effective resolved value and any deprecated alias that supplied it.
  - Remove compatibility aliases only through a documented deprecation step, not a surprise breaking change.

- [ ] AM-090 [P2] [Relationships / Simplification] — Deprecate the legacy `entity_relationships` runtime path if no active consumer remains.
  - Evidence from live DB: `entity_relationships` has 0 rows while the temporal `relationships` table is the active context-graph representation.
  - Code evidence: `_merge_entities()` still updates/deletes both `relationships` and `entity_relationships`, so the obsolete representation continues to expand merge complexity despite carrying no data.
  - Acceptance: audit call sites, remove duplicate runtime/documentation/merge paths, keep the old table only for compatibility until a future safe migration proves it can be dropped.
  - Verification: relationship retrieval, graph improvement, Ask, merge, and Deep Dive continue through the canonical temporal relationship model.

- [ ] AM-097 [P2] [Source-neutral evidence / Transactions] — Give `EvidenceRepository` explicit caller-owned transaction semantics before adding a second ingestion source.
  - Code evidence: `EvidenceRepository.save()` calls `self.conn.commit()` internally after every item.
  - Problem: a repository method can accidentally commit unrelated caller work, prevents a future Gmail/Drive importer from batching evidence atomically, and makes transaction ownership invisible.
  - Acceptance:
    - repository save/update/version operations participate in the caller's transaction and never commit unrelated work;
    - add an explicit batch/unit-of-work path if a future ingestor needs high-volume writes;
    - current-state row and version-history mutation remain atomic;
    - retain the source-neutral contract without creating source-specific duplicate pipelines.
  - Priority remains P2 until a real second source writes through this repository.
  - Verification: outer transaction rollback, multi-record batch rollback, edit/delete version history, and standalone usage tests.

- [ ] AM-065 [P2] [Operations] — Add an optional supervised daemon deployment example once local runtime paths and ownership are finalized.
  - Scope: documented systemd user unit or equivalent; no hard-coded personal paths; restart policy must not create tight crash loops.

## Tech Debt

- [ ] AM-068 [P2] [Architecture] — Re-run `make review` after AM-053–AM-058 and extract only genuinely cohesive responsibilities from remaining >500-line core modules; avoid architecture-only rewrites.

## Completed

- [x] AM-053 [P0] [Context runtime] — Completed 2026-08-28. Accepted
  projection coalesces scoped revisions; bounded workers preserve failures,
  cannot clear newer revisions, and own global snapshots/project health/
  follow-ups. The explicit terminal refresh now uses that same ledger.
  Verification covers dedupe, restart, failure retry, revision race, and no
  global refresh for a non-global scope. No migration or live action ran.

- [x] AM-075 [P0] [AI routing / Failure taxonomy] — Completed 2026-08-27.
  Migration 20 adds a durable retry schedule for temporary history work.
  It keeps the exact membership unchanged and distinguishes terminal local
  failures from scheduled temporary failures. Temporary SQLite coverage passes.

- [x] AM-071 [P0] [Task lifecycle / Reconciliation] — Completed 2026-08-27.
  Same-chat candidate matching is bounded and rejects conflicting populated
  entity/project anchors; fuzzy matches require compatible task kind and
  source evidence within 180 days, while exact-title lifecycle continuity stays
  supported. Terminal completion/cancellation links retain their task event,
  and unchanged manual actions/rejections are idempotent with exactly one
  lifecycle event and rejection feedback record. Historical repair remains
  explicitly owned by AM-074. No migration, replay, backfill, or live action
  ran. Verification: temporary-SQLite matching, terminal lifecycle, authority,
  and idempotency coverage.

- [x] AM-106 [P0] [Retry / Rate limit / Usage accounting] — Completed
  2026-08-26. Providers perform one cancellable transport attempt while the
  router owns every physical retry, conservative model pacing, quota/event
  record, transmitted-input estimate, and normalized extraction/Q&A usage.
  An unconfirmed Groq cancellation is counted and cannot overlap fallback. No
  migration or live action ran. Verification: 48 focused router/job tests,
  temporary-SQLite usage coverage, Ruff, formatting, and MyPy.

- [x] AM-105 [P0] [Provider request lifecycle] — Completed 2026-08-26.
  Gemini uses the cancellable SDK async client; timeout cancellation completes
  before fallback. Provider-owned clients close with internally created Daily
  and History routers while injected routers remain caller-owned. No migration
  or live action ran. Verification: 67 focused router/service/history tests,
  Ruff, formatting, MyPy, docs, and diff checks.

- [x] AM-104 [P0] [Provider contract / Multi-model] — Completed 2026-08-26.
  The router passes an explicit selected provider/model/RPM request to both
  providers; Groq invokes that selected model. Returned execution identity is
  validated before success accounting, so it cannot be rewritten into apparent
  compliance. No model expansion, migration, or live action ran. Verification:
  91 focused AI tests, Ruff, formatting, and MyPy.

- [x] AM-102 [P0] [AI schema / Validation / Anti-slop] — Completed
  2026-08-26 as a verified closure. The provider-neutral contract already
  defines the response shape, kinds, owners, statuses, confidence range,
  project association, and cross-field rules; providers preserve raw JSON
  without semantic repair. Top-level failures remain diagnostics and item
  failures remain durable rejections. No code, migration, or live action ran.
  Verification: 51 focused provider, repository, and semantic-projection tests.

- [x] AM-101 [P0] [AI persistence / Canonical projection] — Completed
  2026-08-26. Saved provider output replays projection/integration from its
  durable batch before new provider work. Post-save failure cannot create a
  synthetic provider failure or reclaim a done job; context assembly failure is
  retryable rather than stranded. No migration or live action ran. Verification:
  72 focused tests, Ruff, formatting, and MyPy.

- [x] AM-099 [P0] [AI router / Anti-slop] — Completed 2026-08-28. Automatic
  Daily/Brief analysis uses background priority while manual Daily analysis is
  interactive. Existing short/context workload policies now differ,
  structured-output admission is enforced, route events retain deterministic
  policy reasons, and the unused long-context flag is removed. Forced and
  session-pinned models can reorder or select only from the normal
  workload/capability eligible set; they cannot admit an excluded profile. No
  provider/model expansion, migration, or live action ran. Verification: 49
  focused router/app tests, Ruff, formatting, MyPy, docs check, and review.

- [x] AM-098 [P1] [Application lifecycle / Reliability] — Completed
  2026-08-26. Writer counters and AI wakeups follow successful commits; failed
  writers cannot strand queue drains. Daemon/local startup, scheduled-brief,
  commit, disconnect, and original-error failure paths are covered. No schema
  migration, replay, or live action ran. Verification: focused fake/temp-SQLite
  failure-path tests, Ruff, formatting, MyPy, and docs gate.

- [x] AM-100 [P0] [AI jobs / Re-analysis] — Completed 2026-08-26. Archive
  edits and first deletions now mark only their existing AI interpretation and
  classification stale in the writer transaction. The existing version-2 exact
  membership path requeues an edited eligible message; deleted messages retain
  source history but never re-enter provider work. Repeated deletion is
  idempotent. No migration, replay, network mutation reconciliation, or live
  action ran. Verification: `make check` passes 235 tests.

- [x] AM-119 [P0] [Semantic claims / Evidence] — Added migration 14 with
  immutable claim, direct-evidence, unresolved entity-reference, and future
  temporal-graph tables. Every newly validated legacy observation writes one
  deduplicated direct-evidence claim in the same transaction; no historical
  conversion or graph mutation occurs at startup.
- [x] AM-117 [P2] [Read/write boundaries / Terminal workflow] — Daily Brief
  now reads only today's saved payload; an explicit Maintain command generates
  and stores it. No migration or backfill.

- [x] AM-089 [P1] [Follow-ups / Simplification] — Persisted Follow-ups are the
  operator-facing manual reminder lifecycle. Their derived waiting-task rows
  now reconcile on refresh: obsolete automatic reminders close, a recurring
  stale wait reopens, and manual states remain authoritative. No migration or
  backfill.

- [x] AM-070 [P0] [Tasks / Context graph] — Task projection resolves bounded
  project candidates, preserves established links, and provides idempotent
  selective repair with derived conversation-period refresh.

- [x] AM-116 [P2] [Terminal workflow] — The task screen now asks separately
  for a task ID and constrained action. Deep Dive, evidence preview, and
  explicit manual-status confirmation remain available. No migration or
  backfill.

- [x] AM-115 [P2] [Terminal workflow] — Follow-ups now support evidence-first,
  confirmed manual open, snoozed, done, and cancelled states. Each transition
  is append-only operator feedback; completed/cancelled rows receive a
  resolution time and reopening clears it. No migration or backfill.

- [x] AM-084 [P0] [Identity / Conversation intelligence] — Direct Telegram
  conversation ownership now uses the deterministic peer identifier.

- [x] AM-114 [P2] [Terminal workflow] — Finished the operational drill-down
  path for Today, Follow-ups, and review evidence.

- [x] AM-095 [P1] [Read/write boundaries / Terminal workflow] — Read views are
  side-effect free; operational refresh is explicit. Bounded terminal filters,
  focused diagnostics, drill-down, confirmation, and local-only recovery are
  available. No migration or backfill; temporary-database tests cover the
  read/write boundary and terminal safety.

- [x] AM-055 [P1] [Background intelligence] — Replaced automatic Daily and
  History callbacks with one committed-evidence scheduler. It coalesces
  wakeups, rechecks durable work at startup and a maximum delay, keeps live
  work ahead of History, and leaves provider failure isolated from ingestion.
  No migration or backfill; temporary-SQLite coverage verifies writer commit,
  busy/burst/restart/failure/priority/maximum-delay paths.

- [x] AM-054 [P0] [Runtime status] — Added one authoritative, read-only runtime-status service.
  - Completed: 2026-08-24. The home and diagnostics screens share explicit `STARTING`, `HEALTHY`, `DEGRADED`, `RETRYING`, `FAILED`, and `OFFLINE` snapshots rather than treating a live-sync object as health. Archive lag, writer failure, AI route/quota/work, context/graph/history/review state, bounded recent errors, and requested data-quality ratios are visible.
  - Database: no migration, backfill, derived-state rebuild, or live data action.
  - Verification: 22 focused runtime/UI/live-sync tests and 42 related deterministic tests, Ruff, formatting, MyPy, docs/task checks, review signals, and read-only SQLite integrity/FTS checks pass. The broader router suite again stalled in the existing Gemini pacing test and was interrupted without a failure.

- [x] AM-113 [P1] [Codex workflow] — Added measured, project-local Codex workflow guardrails without replacing the Python quality harness.
  - Completed: 2026-08-24. Installed and retained Plugin Eval, Context7, four focused Trail of Bits skills, and the curated Python simplifier; Codex Security was evaluated then removed for high unmeasured instruction cost and overlapping review scope.
  - Database: no migration and no source/archive data action.
  - Verification: six skills validate and score A/100 in Plugin Eval static analysis; hook validation, 13 UI tests, Ruff, formatting, MyPy, compilation, docs, and lock checks pass. `make check` was interrupted after the pre-existing AI-router suite produced no output for 90 seconds and reported no failure.

- [x] AM-073 [P0] [Classification / Anti-slop] — Make the classifier truthful, versioned, multilingual-aware, and safe enough to drive semantic routing.
  - Completed: 2026-08-24. Classifier v2 separates forwarded provenance from scope, classifies private groups as private by default, routes actionability/state change ahead of generic questions, and persists only source-time-stable date presence.
  - Reclassification: no schema migration or live backfill. Existing bounded work selectively revisits v1 unknown, stale, high-value, forwarded, and actionable-question rows without a provider; approved manual reviews remain authoritative.
  - Verification: hand-reviewed English/Russian/Georgian fixture is 7/7 correct with 0 unknown operational classifications; focused history/workflow/review/migration tests (38), Ruff, MyPy, docs, task-queue, and read-only DB checks pass.

- [x] AM-092 [P1] [Engineering harness] — Established a compact, reproducible Codex/Python quality harness and restored the full baseline gate.
  - Completed: 2026-08-24.
  - Database: applied existing migration 12 after a SQLite API backup; derived FTS indexes are at source parity and raw/canonical records were not changed.
  - Verification: `make verify` passes 134 tests plus Ruff, formatting, MyPy, docs, lock, deptry, pip-audit, SQLite/FTS checks, rule checks, skill validation, and independent review.

- [x] AM-069 [P0] [Search / Database] — Repair FTS coverage/lifecycle and stop hiding index defects as “FTS unavailable”.
  - Completed: 2026-08-24. Migration 12 atomically rebuilds all six derived FTS indexes from current authoritative rows and maintains them on insert/update/delete; deleted/empty rows and merged entities are excluded.
  - Verification: 23 focused migration/retrieval/Deep Dive tests, Ruff, formatting, MyPy, `make docs-check`, and `make db-check` pass. The live read-only check reports schema 12, integrity `ok`, no foreign-key violations, and exact index/source parity. `make check` was interrupted after an existing Gemini pacing-test stall before FTS tests ran.

- [x] AM-123 [P1] [Engineering harness] — Install repository-local quality hooks that match the locked Python toolchain.
  - Completed: 2026-08-24.
  - Historical identifier reconciliation: this entry originally reused
    `AM-105`, which is the active provider-request-lifecycle task above. It is
    assigned unused ID `AM-123` solely to preserve the completed engineering
    record and make AM-105 unambiguous.
  - Verification: the configuration validates; `make lock-check`, `make hooks`, and `make docs-check` pass. The hook run has no files to select until this new local repository has tracked files.
  - Limitation: `make check` was interrupted while the existing `test_ai_router_and_jobs.py` suite was still running; it emitted no failure before interruption.

- [x] AM-051 [P0] [AI routing] — Skip all Gemini routes immediately after a Gemini quota response and select Groq for the active history run.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py` verifies one Gemini quota attempt proceeds directly to one Groq request; full quality checks pass.

- [x] AM-050 [P0] [AI reliability] — Treat Gemini DNS/connectivity faults as provider-health failures and route directly to Groq.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py` verifies a network failure skips the second Gemini route and pins Groq; full quality checks pass.

- [x] AM-049 [P0] [AI routing] — Add workload-aware, quota-aware multi-model routing with durable usage accounting and visible routing diagnostics.
  - Completed: 2026-08-22.
  - Verification: `make check` passes 118 tests with Ruff and MyPy; `make docs-check`, `make db-check` (schema version 11), and `make codex-check` pass.

- [x] AM-048 [P0] [AI routing] — Use Groq as the active local primary route, cap local provider waits at 30 seconds, and lock a successful fallback for the rest of a history run.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py` covers the session fallback lock; `make test` passes 116 tests.

- [x] AM-047 [P0] [AI reliability] — Enforce a non-blocking Groq deadline when SDK cancellation does not complete promptly.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py` verifies a hanging Groq SDK request returns at the configured deadline; `make check` passes 115 tests and `make db-check` passes with schema version 10.

- [x] AM-046 [P0] [AI reliability] — Eliminate Groq's incompatible strict-schema preflight so a Gemini fallback has one bounded JSON-object request.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py` covers direct Groq JSON-object output and output-budget propagation; `make test` passes 114 tests.

- [x] AM-045 [P0] [AI reliability] — Honor short Gemini provider retry delays before falling back to Groq, with visible primary-provider cooldown state.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py` verifies a short Gemini quota cooldown retries Gemini without invoking Groq; `make test` passes 114 tests.

- [x] AM-044 [P0] [AI reliability] — Make interrupted live history requests requeue cleanly without creating false provider failures during event-loop shutdown.
  - Completed: 2026-08-22.
  - Verification: `tests/test_history_intelligence.py` covers interruption while a live provider request is active; `make check`, `make docs-check`, `make db-check`, and `make codex-check` pass with schema version 10. Three identified false failure rows were backed up, removed, and requeued.

- [x] AM-043 [P0] [AI reliability] — Surface Gemini's actual quota dimension and retry delay, and align the active local RPM setting with the configured safety margin.
  - Completed: 2026-08-22.
  - Verification: quota-detail sanitization is covered in `tests/test_ai_router_and_jobs.py`; `make check`, `make docs-check`, and `make db-check` pass with schema version 10.

- [x] AM-042 [P0] [AI reliability] — Prevent stalled provider calls and misleading multi-job RUNNING history status while preserving Gemini fallback recovery.
  - Completed: 2026-08-22.
  - Verification: provider-timeout, Groq JSON-validation fallback, Gemini cooldown recovery, active-job status, and live-monitor render coverage; `make check`, `make docs-check`, `make db-check`, and `make codex-check` pass with schema version 10.

- [x] AM-041 [P1] [Configuration] — Normalize the local environment configuration to the active settings surface and verify it without exposing credentials.
  - Completed: 2026-08-22.
  - Verification: exact local-file validation confirms 66 active variables are explicit with no duplicate keys; `make check` (107 tests), `make docs-check`, and `make db-check` pass.

- [x] AM-040 [P1] [AI UI] — Make Gemini versus Groq hourly request counts and fallback reasons explicit in the live monitor.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ui.py` covers direct Gemini totals and fallback-reason rendering; full project checks pass with schema version 10.

- [x] AM-039 [P1] [AI UI] — Keep a visibly live request-status panel on screen while each history provider request is in flight.
  - Completed: 2026-08-22.
  - Verification: `tests/test_history_intelligence.py` verifies the live history-monitor render; full project checks pass with schema version 10.

- [x] AM-036 [P2] [Architecture] — Extract the remaining cohesive review, AI repository, context, and terminal-screen responsibilities identified by `make review` without changing public behavior.
  - Completed: 2026-08-22.
  - Verification: existing AI, conversation, and UI tests cover the extracted prompt-context, contact-context, and profile-rendering paths; `make check`, `make docs-check`, `make db-check`, and `make review` pass.

- [x] AM-038 [P1] [AI UI] — Show the visual AI request monitor directly in the history-analysis workflow.
  - Completed: 2026-08-22.
  - Verification: `tests/test_history_intelligence.py` verifies that Analyze all history renders the request monitor; full project checks pass with schema version 10.

- [x] AM-037 [P1] [AI UI] — Add a visual request monitor for live AI job state, provider/model selection, configured pace, fallback use, and recent errors.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ui.py` covers monitor route, pacing, and error rendering; full project checks pass with schema version 10.

- [x] AM-034 [P1] [Conversation intelligence] — Materialize source-grounded, temporal contact context across segments, open loops, person/project pairs, retrieval, and semantic-analysis context.
  - Completed: 2026-08-22.
  - Verification: `tests/test_conversation_intelligence.py` covers materialization and retrieval; schema version 10 was applied after a SQLite API backup and verified with `make db-check`.

- [x] AM-035 [P1] [AI reliability] — Lower Gemini history pacing below the nominal rolling limit and accept fractional RPM configuration.
  - Completed: 2026-08-22.
  - Verification: fractional-configuration parsing and deterministic 14.5-RPM pacing are covered by `tests/test_config.py` and `tests/test_ai_router_and_jobs.py`; full project checks pass.

- [x] AM-033 [P2] [Documentation] — Re-audit product documentation, configuration categories, commands, and VS Code tasks after the remaining consolidation work.
  - Completed: 2026-08-22.
  - Verification: `make help`, generated environment/schema documentation, VS Code tasks, and `make docs-check` were audited against the Makefile and current runtime configuration.

- [x] AM-032 [P2] [Diagnostics] — Expand coverage and classification diagnostics with actionable orphan, stale, routing, and integration metrics.
  - Completed: 2026-08-22.
  - Verification: `tests/test_history_intelligence.py` covers route and unclassified-backlog metrics; the full quality gate passes.

- [x] AM-031 [P2] [Architecture] — Extract cohesive responsibilities from `operational.py`, `intelligence.py`, and the remaining oversized repository/UI modules identified by `make review`.
  - Completed: 2026-08-22.
  - Verification: `tests/test_intelligence.py`, `tests/test_ai_router_and_jobs.py`, and `tests/test_ui.py` retain policy behavior; the full quality gate passes with the obsolete `search_memory` path removed.

- [x] AM-030 [P1] [Chat policy] — Add a user-facing chat-analysis policy editor and enforce only supported FULL, ARCHIVE ONLY, and IGNORE modes; design CLASSIFY ONLY and NEWS ONLY only with tested routing semantics.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py`, `tests/test_migrations.py`, and `tests/test_ui.py` cover enforceable classification-only/news-only routing, legacy policy adoption, and the policy command.

- [x] AM-029 [P1] [Review] — Apply authoritative domain effects for entity merge/alias, task, fact, relationship, and classification review decisions.
  - Completed: 2026-08-22.
  - Verification: `tests/test_operational_memory.py`, `tests/test_history_intelligence.py`, `tests/test_context_conflicts.py`, and `tests/test_ui.py` cover canonical merge/reconciliation, graph relationships, temporal-fact decisions, classification edits, and review provenance rendering.

- [x] AM-028 [P1] [Context graph] — Add temporal conversation segments and use them in classification, Deep Dive, retrieval, and graph repair.
  - Completed: 2026-08-22.
  - Verification: segment reconstruction, time-bounded classification, context, Deep Dive discovery, retrieval ranking, and migration coverage are in `tests/test_history_intelligence.py`, `tests/test_context_quality.py`, `tests/test_task_deep_dive.py`, `tests/test_intelligence.py`, and `tests/test_migrations.py`.

- [x] AM-027 [P1] [Context graph] — Add bounded, idempotent orphan task/event/fact repair passes with source-backed automatic links and review candidates.
  - Completed: 2026-08-22.
  - Verification: `tests/test_history_intelligence.py` covers strong-consensus repair, single-anchor review routing, and a second-run duplicate check.

- [x] AM-025 [P0] [Consolidation] — Unify synchronization and intelligence routing; complete graph, Deep Dive, review, versioning, and documentation audit.
  - Completed: 2026-08-22.
  - Verification: 85 tests pass; Ruff, formatting, MyPy, documentation, SQLite integrity, foreign-key, and Codex checks pass. Live database migrated additively to schema version 7 after a SQLite API backup.

- [x] AM-026 [P1] [AI reliability] — Prevent Gemini quota exhaustion and oversized Groq fallbacks from producing avoidable failed history batches.
  - Completed: 2026-08-22.
  - Verification: quota short-circuiting, fallback routing, and output-budget propagation are covered by `tests/test_ai_router_and_jobs.py`; `make check`, `make docs-check`, and `make db-check` pass.

- [x] AM-024 [P2] [AI storage] — Separate model-item validation from AI-item persistence.
  - Completed: 2026-08-22.
  - Verification: malformed amount, date, confidence, source-reference, and mixed valid/invalid model item handling remain covered by `tests/test_ai_pipeline.py`.

- [x] AM-023 [P2] [UI] — Separate the AI analytics screen from general terminal screens.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ui.py` and `tests/test_ai_pipeline.py` cover analytics rendering and its read-only query path; the full quality gate passes.

- [x] AM-022 [P2] [Database] — Separate declarative migration support from ledger execution.
  - Completed: 2026-08-22.
  - Verification: fresh and multi-table legacy adoption, evidence storage, optional FTS fallback, and full project checks are covered by `tests/test_migrations.py`, `tests/test_evidence.py`, and `tests/test_intelligence.py`.

- [x] AM-019 [P2] [Intelligence] — Separate bounded retrieval stages and remove transitional AI analytics aliases.
  - Completed: 2026-08-22.
  - Verification: retrieval ranking, bounded entity hints, terminal rendering, and direct analytics imports are covered by `tests/test_intelligence.py`, `tests/test_intelligence_workflow.py`, `tests/test_ui.py`, and `tests/test_ai_pipeline.py`.

- [x] AM-021 [P2] [AI storage] — Separate read-only AI analytics from queue and result persistence.
  - Completed: 2026-08-22.
  - Verification: terminal analytics and direct query-module imports remain covered by `tests/test_ui.py` and `tests/test_ai_pipeline.py`; the full quality gate passes.

- [x] AM-007 [P2] [Database] — Replace ad-hoc compatibility helpers with an explicit migration registry.
  - Completed: 2026-08-22.
  - Verification: ordered ledger application, idempotent reopen, and multi-table legacy compatibility columns are covered in `tests/test_migrations.py`.

- [x] AM-000 [P1] [Development workspace] — Added VS Code/Codex workspace baseline, safe developer commands, documentation generation, task tracking, and anti-slop policy.
  - Completed: 2026-08-22.
  - Verification: see the corresponding entry in `CHANGELOG.md` and `docs/CHANGES.md`.

- [x] AM-003 [P1] [Configuration] — Added settings tests and actionable configuration errors.
  - Completed: 2026-08-22.
  - Verification: missing `.env`, missing credential, invalid numeric setting, and core runtime defaults are covered in `tests/test_config.py`.

- [x] AM-006 [P1] [Configuration] — Differentiated a missing `.env` from missing Telegram credentials.
  - Completed: 2026-08-22.
  - Verification: startup errors identify the missing file or specific setting without rendering values.

- [x] AM-009 [P1] [UI] — Removed undefined context-view table rendering.
  - Completed: 2026-08-22.
  - Verification: `tests/test_context_engine.py` renders the context view through Rich.

- [x] AM-010 [P1] [Context engine] — Added ranked, purpose-aware context to extraction, Ask Alex Memory, daily briefs, and diagnostics.
  - Completed: 2026-08-22.
  - Verification: cross-chat, temporal, graph-depth, budget, conflict, manual pinning, and context-aware extraction tests are in `tests/test_context_quality.py`.

- [x] AM-011 [P1] [UI] — Made the terminal interface safer and easier to navigate.
  - Completed: 2026-08-22.
  - Verification: alias compatibility, grouped navigation, live status, filtered entity choices, settings rendering, and empty states are covered in `tests/test_ui.py`.

- [x] AM-012 [P1] [Task Deep Dive] — Investigate one task across canonical context and bounded cross-chat evidence.
  - Completed: 2026-08-22.
  - Verification: cross-chat relevance, historical cutoffs, source provenance, sessions, notes, pins, and grounded answers are covered in `tests/test_task_deep_dive.py`.

- [x] AM-013 [P1] [UI] — Apply one coherent UI/UX system across the complete terminal interface.
  - Completed: 2026-08-22.
  - Verification: navigation, empty states, entity/profile rendering, settings, responsive layouts, and literal untrusted Deep Dive content are covered in `tests/test_ui.py`.

- [x] AM-001 [P1] [Development workspace] — Validate and adopt the new workspace baseline.
  - Completed: 2026-08-22.
  - Verification: VS Code selects `.venv`; `make check` and `make docs-check` pass; local commands are discoverable through `make help` and VS Code tasks; Git initialization was intentionally deferred because no repository policy was provided.

- [x] AM-002 [P1] [Database] — Introduce an explicit schema-version/migration ledger.
  - Completed: 2026-08-22.
  - Verification: fresh and legacy schema adoption, ordered ledger records, and idempotent reopen behavior are covered in `tests/test_migrations.py`.

- [x] AM-004 [P2] [Ingestion] — Define source-neutral evidence interfaces before adding Gmail, WhatsApp, iMessage, or Drive ingestion.
  - Completed: 2026-08-22.
  - Verification: source identity, provenance, edit/delete version history, and Telegram lifecycle adaptation are covered in `tests/test_evidence.py`.

- [x] AM-014 [P1] [Architecture] — Simplify the intelligence workflow around automatic history analysis, contextual message classification, and incremental context-graph improvement.
  - Completed: 2026-08-22.
  - Verification: history classification freshness and retrieval ranking plus scoped, source-backed idempotent graph improvement are covered in `tests/test_intelligence_workflow.py`.

- [x] AM-005 [P2] [Context] — Add a review workflow for temporal-fact conflicts.
  - Completed: 2026-08-22.
  - Verification: temporal conflict listing, source provenance, acceptance history, and keep-existing decisions are covered in `tests/test_context_conflicts.py`.

- [x] AM-015 [P1] [Intelligence] — Extend context-aware classification, evidence-backed graph improvement, and safe automatic history scheduling.
  - Completed: 2026-08-22.
  - Verification: quiet-queue yielding, contextual classification, direct evidence links, and reviewable ambiguous graph candidates are covered in `tests/test_history_intelligence.py`.

- [x] AM-008 [P2] [Quality] — Address the largest modules identified by `make review` where responsibility boundaries justify it.
  - Completed: 2026-08-22.
  - Verification: SQL-filtered entity hints and contextual classification remain covered by `tests/test_intelligence.py` and `tests/test_history_intelligence.py`; the complete quality gate passes.

- [x] AM-016 [P1] [AI reliability] — Pace Gemini provider requests at 15 RPM.
  - Completed: 2026-08-22.
  - Verification: `tests/test_ai_router_and_jobs.py` covers conservative 15-RPM rolling-window spacing and retry-slot reservation; provider, configuration, and full project checks pass.

- [x] AM-017 [P1] [History UX] — Keep rate-limited history analysis visibly active in the terminal.
  - Completed: 2026-08-22.
  - Verification: `tests/test_history_intelligence.py` covers immediate and per-request history progress output.

- [x] AM-020 [P1] [History reliability] — Continue history analysis after isolated provider failures.
  - Completed: 2026-08-22.
  - Verification: `tests/test_history_intelligence.py` covers isolated-failure continuation and the three-consecutive-failure safety threshold.
