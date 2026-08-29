# Architecture

Alex Memory is a local, source-backed operational memory system. Telegram is the current ingestion source; Gmail, WhatsApp, iMessage, and Drive are future sources that should feed the same evidence model rather than bypass it.

## Data flow

```text
Raw evidence → immutable semantic claims → temporal knowledge graph
→ canonical operational state → bounded context → intelligence and products
```

## Components

- `telegram/`: `TelegramSyncService` owns inventory, policy-driven bootstrap/catch-up, live handlers, periodic reconciliation, normalization, and the bounded SQLite writer queue.
- `ai/`: bounded provider routing, a single committed-evidence scheduler for automatic live/history work, resumable history coverage, strict source-backed semantic claims, and read-only analytics queries kept separate from persistence.
- `classification.py`: versioned, local multi-dimensional routing (conversation/content type, information scope, actionability, importance, temporal relevance, topics, and state-change potential) before semantic work; it never replaces raw evidence.
- `chat_ai_policy`: per-chat routing overrides: automatic, forced semantic inclusion, classification-only archive, external-news-only semantic work, or exclusion.
- `operational.py`: canonical entities, source-first direct-chat peer identity,
  tasks, review queue, briefs, and idempotent accepted-batch projection. Its
  projection emits revisioned context invalidations and invokes the sole
  deterministic semantic-graph projector after canonical resolution; the
  refresh worker owns materialization.
- `context/`: purpose-aware entity resolution, bounded relationship traversal, deterministic ranking, temporal facts and manual conflict decisions, contextual builders, diagnostics, and global snapshots.
- `tasks/deep_dive/`: task-specific, deterministic investigation over canonical context and bounded, ranked raw evidence; it persists only session metadata, notes, and pins.
- `ui/`: the Rich terminal application and shared safe rendering primitives for navigation, operational data, progress, and detail views. The normal product flow is People and read-only Person Profiles, including a deterministic "Before I contact them" briefing assembled only from exact-evidence canonical rows. Engineering operations remain explicit maintenance commands.
- `ui/ai_analytics.py`: dedicated read-only AI analytics screen composed from `ai/analytics.py` queries.
- `database.py`: ordered, idempotent SQLite migration ledger and connection lifecycle recorded in `schema_migrations`; see [Database Migrations](DATABASE_MIGRATIONS.md).
- `schema_support.py`: declarative compatibility-column, source-evidence, and optional FTS migration support called only by the ledger.
- `runtime_status.py`: one bounded, read-only runtime snapshot spanning live
  Telegram state, writer health, AI work/route quota telemetry, context/graph
  freshness, review load, and database-quality indicators.
- `evidence.py`: source-neutral evidence identity and version-preserving storage; Telegram adapts to it without copying raw messages. See [Source-Neutral Evidence](SOURCE_EVIDENCE.md).
- `intelligence.py`: classification-aware bounded retrieval, grounded Q&A, follow-ups, profiles, and notifications. See [Intelligence Workflow](INTELLIGENCE_WORKFLOW.md).
- `retrieval.py`: staged SQL-first canonical, summary, message, and FTS retrieval with the same bounded, order-independent all-term candidate rule across SQL fallback and FTS.

## Invariants

Raw messages remain traceable. AI findings become immutable semantic claims only
after local validation against submitted source messages; claims are not
canonical truth. Deterministic reducers and manual Review decide canonical
state. Manual task state beats later AI inference. Current and historical facts
are distinct. An explicit historical context request returns only
interval/version/event-backed state; mutable current rows are omitted and the
package declares partial fidelity. Provider failure must not stop Telegram
ingestion.

For a direct Telegram chat, its peer ID is source metadata and establishes the
conversation owner before prompt context or AI aliases are considered. A named
third party remains an observation/entity, and ambiguous historical name matches
go to Review rather than silently changing the peer's canonical identity.

## Context path

```text
New message / question
→ resolve canonical entities and chat-linked state
→ bounded relationship expansion
→ rank current facts, open loops, events, summaries, and exact source evidence
→ render purpose-specific context
→ extraction or grounded answer
```

The context package is structured until rendering. Raw evidence is the
lowest-ranked layer and never replaces canonical state. When shown as
supporting evidence, it closes only over exact source chat/message pairs from
the selected canonical records or their immutable claim evidence; nearby chat
messages are not silently promoted to proof.

An unresolved ordinary context request does not receive global tasks or events.
Those aggregates are available only to the explicit daily-brief and global-state
purposes.

## Intelligence workflow

```text
Telegram evidence → durable classification and route → resumable semantic analysis
→ accepted canonical task/entity state → source-backed graph improvement
→ classification-aware retrieval and contextual answers
```

Noise is archive-only; forwarded/broadcast news is isolated as external news;
operational requests, promises, payments, meetings, and decisions receive the
semantic path. Provider work is bounded and durable, but normal progress reports
only coverage and safe pause/resume status. Graph improvement only connects
records already anchored by accepted source-backed state.

## Telegram lifecycle

```text
connect → load dialog inventory → apply one bootstrap policy → catch up
→ continue live events → periodic policy-driven reconciliation
```

Personal chats and small groups receive full first bootstrap; large groups use
a bounded recent first bootstrap; channels remain outside the archive policy.
The same planner is used at startup and later reconciliation, so a new group
cannot bypass the large-group bound.

## Runtime status

The terminal home and full status screen consume one `RuntimeStatusService`
snapshot rather than inferring health from the existence of a service object.
The live service reports `STARTING`, `HEALTHY`, `DEGRADED`, `RETRYING`, or
`FAILED`; shutdown is `OFFLINE`. `RETRYING` is reserved for the periodic
reconciliation worker after it has scheduled supervised recovery. A startup
failure is `FAILED` and does not promise an unregistered retry. A completed
writer task with an exception is fatal even if the Telegram client still says
it is connected. The snapshot reads bounded database aggregates only and never
writes evidence, canonical state, queue state, or provider telemetry.

## Task Deep Dive path

```text
Canonical task → task-scoped context → bounded round-one concepts
→ FTS/SQL candidate retrieval → evidence-derived bounded round expansion
→ stop when a round adds no evidence or concepts → local relevance validation
→ source-cited timeline, current state, unknowns, notes, and pins
```

Task investigation is deliberately separate from generic question answering. Cross-chat messages need an entity anchor, or a graph-related chat plus multiple task concepts; this keeps weak lexical matches out of a task record.
