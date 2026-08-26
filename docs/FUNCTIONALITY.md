# Functionality Inventory

This inventory records implemented functionality, not a roadmap. It is the
architecture audit for AM-014.

## CORE — KEEP

| Feature | Entry point | Modules | Database tables | Used by | Recommendation |
| --- | --- | --- | --- | --- | --- |
| Telegram evidence archive and unified sync | automatic on start / `Sync` | `telegram/TelegramSyncService` | `chats`, `messages`, `message_versions`, `sync_state` | all intelligence | Keep one policy-driven lifecycle; Smart Sync is removed. |
| Validated AI extraction | automatic daily/history work | `ai/router.py`, `ai/service.py`, `operational.py` | `ai_jobs`, `ai_batches`, `ai_message_state`, `ai_items` | tasks, memory, briefs | Keep one router and one post-save projection. |
| Canonical temporal context | projection and context queries | `operational.py`, `context/` | entities, tasks, events, facts, relationships | retrieval, briefs, profiles | Keep; corrections and historical intervals remain authoritative. |
| Grounded retrieval | Ask, Search, Deep Dive | `intelligence.py`, `tasks/deep_dive/` | canonical/context tables and FTS | Ask, search, Deep Dive | Keep SQL-first retrieval and one bounded context builder. |

## USEFUL — SIMPLIFY

| Feature | Entry point | Modules | Database tables | Used by | Recommendation |
| --- | --- | --- | --- | --- | --- |
| History analysis and AI monitor | `Analyze all history` / `AI monitor` | `ai/history.py`, `ai/repository.py`, `ai/analytics.py` | jobs, batches, and coverage state | operational projection | Keep provider-safe windows internally; show visual live request, pacing, fallback, and error state. |
| Message routing classification | new messages and history | `classification.py` | `message_classifications` | semantic routing, history, retrieval | Keep as the central route and version it. |
| Chat analysis policy | `Chat policy` | `chat_policy.py`, `app.py`, `ai/repository.py` | `chat_ai_policy` | archive, semantic routing | Keep explicit, enforceable modes; classification-only and news-only have bounded tested routing. |
| Context graph maintenance | `Context graph → improve` / Deep Dive improve | `context/improver.py`, `context/segments.py` | `relationships`, events, tasks, review queue, conversation segments, app metadata | context, retrieval | Keep conservative/idempotent; repair orphan task/event/fact links only from strong local evidence and derive time-bounded project periods from task anchors. |
| Contact conversation intelligence | accepted-batch projection / person-scoped retrieval | `context/conversation.py`, `context/contact_materializer.py` | contact segments, conversation state, person/project context, open loops, context links | extraction, person profile, Ask, global context | Keep materialization and bounded contact queries separate; never duplicate raw evidence or tasks. |
| Terminal UI | Rich home screen | `ui/`, `app.py` | — | interactive app | Keep eleven product-level actions; legacy aliases are hidden compatibility. |

## EXPERIMENTAL — REVIEW

| Feature | Entry point | Modules | Database tables | Used by | Recommendation |
| --- | --- | --- | --- | --- | --- |
| Source-neutral evidence | Python API and Deep Dive origin lookup | `evidence.py`, `telegram/evidence.py` | `source_evidence*` | future ingestors | Keep isolated until a second source needs write integration. |
| Task Deep Dive sessions | task `dive` action | `tasks/deep_dive/` | `task_deep_dive_*`, notes, pins | task investigation | Keep: it has a distinct task-scoped retrieval responsibility. |

## DUPLICATED — MERGE

| Feature | Entry point | Modules | Database tables | Used by | Recommendation |
| --- | --- | --- | --- | --- | --- |
| History progress | prior queue/status views | repository and UI | jobs/message state | diagnostics | Merge into coverage metrics; retain jobs only for recovery and diagnostics. |
| Telegram bootstrap and live reconciliation | former Smart Sync and live service | `telegram/service.py`, `telegram/live.py` | `sync_state` | all intelligence | Merged into `TelegramSyncService`; obsolete Smart Sync module removed. |

## OBSOLETE — REMOVE

| Feature | Entry point | Modules | Database tables | Used by | Recommendation |
| --- | --- | --- | --- | --- | --- |
| History queue screen | none after AM-014 | former `show_history_queue` | jobs retained | none | Removed; no production table was dropped. |
| Top-level daily/history-queue concepts | hidden legacy aliases only | navigation | — | compatibility | Removed from the normal menu. |

## PLANNED — NOT IMPLEMENTED

| Feature | Entry point | Modules | Database tables | Used by | Recommendation |
| --- | --- | --- | --- | --- | --- |
| Gmail, WhatsApp, iMessage, Drive ingestion | none | source-neutral contract only | `source_evidence*` | future sources | Continue AM-004; do not create source-specific pipelines yet. |
