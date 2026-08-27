# Data Model

The application maintains SQLite tables through idempotent schema creation and an ordered migration ledger in `src/alex_memory/database.py`. Back up a live database through `make db-backup` before any future schema migration.

## Schema summary

<!-- AUTO-GENERATED:START -->
| Table | Purpose | Primary/key columns | Important indexes |
| --- | --- | --- | --- |
| `schema_migrations` | Ordered record of applied SQLite schema migrations. | `version, name, applied_at` | `—` |
| `source_evidence` | Source-neutral current evidence records for future ingestors. | `evidence_id, source_name, source_account_id, conversation_id, source_item_id, content_type` … | `idx_source_evidence_conversation_time (source_name, source_account_id, conversation_id, occurred_at)` |
| `source_evidence_versions` | Prior source-evidence content retained across edits and deletions. | `version_id, evidence_id, content, captured_at, reason` | `idx_source_evidence_versions_evidence (evidence_id, version_id)` |
| `chats` | Archived Telegram dialog metadata. | `chat_id, title, username, chat_type, is_bot, updated_at` | `—` |
| `messages` | Raw Telegram evidence, including edit/deletion state. | `chat_id, message_id, sender_id, date, text, reply_to_message_id` … | `idx_messages_date (date), idx_messages_sender (sender_id)` |
| `message_versions` | Audit trail for edited or deleted message text. | `version_id, chat_id, message_id, text, captured_at, reason` | `idx_message_versions_message (chat_id, message_id, version_id)` |
| `sync_state` | Per-chat archive progress and bootstrap mode. | `chat_id, bootstrap_complete, bootstrap_mode, group_total_at_bootstrap, last_sync_at, updated_at` | `—` |
| `ai_batches` | Provider request/response diagnostics for analysis batches. | `batch_id, model, created_at, completed_at, message_count, chat_id` … | `—` |
| `ai_jobs` | Resumable daily and historical analysis work. | `job_id, lane, chat_id, first_message_id, last_message_id, date_from` … | `idx_ai_jobs_queue (lane, status, job_id)` |
| `ai_message_state` | Analysis state for individual source messages. | `chat_id, message_id, batch_id, analysis_version, context_version_used, analysis_stale` … | `—` |
| `message_classifications` | Versioned local routing classifications for archived messages. | `chat_id, message_id, conversation_type, content_type, actionability, importance` … | `idx_message_classifications_retrieval (importance, content_type, actionability, temporal_relevance)` |
| `conversation_analysis_state` | Per-chat durable history-analysis coverage checkpoints. | `chat_id, covered_until_message_id, covered_until_date, message_count_analyzed, classification_complete, semantic_analysis_complete` … | `—` |
| `ai_items` | Validated, source-backed extracted observations. | `item_id, batch_id, kind, title, details, status` … | `idx_ai_items_kind_status (kind, status), idx_ai_items_due_date (due_date)` |
| `app_meta` | Small application metadata values. | `key, value, updated_at` | `—` |
| `people` | Canonical people. | `person_id, canonical_name, telegram_user_id, telegram_username, status, created_at` … | `—` |
| `companies` | Canonical companies. | `company_id, canonical_name, status, created_at, updated_at` | `—` |
| `projects` | Canonical projects and health state. | `project_id, canonical_name, status, created_at, updated_at` | `—` |
| `entity_aliases` | Normalized names and aliases for entity resolution. | `alias_id, entity_type, entity_id, alias, normalized_alias, source` … | `idx_entity_aliases_lookup (entity_type, normalized_alias)` |
| `entity_relationships` | Observed entity relationships from AI items. | `relationship_id, from_type, from_id, to_type, to_id, relationship_type` … | `—` |
| `entity_merge_candidates` | Ambiguous identity merges awaiting review. | `candidate_id, entity_type, normalized_alias, entity_ids_json, reason, status` … | `—` |
| `review_queue` | Low-confidence or ambiguous decisions for review. | `review_id, review_type, subject_type, subject_id, payload_json, confidence` … | `—` |
| `tasks` | Canonical operational tasks and manual locks. | `task_id, title, normalized_title, details, status, owner` … | `idx_tasks_status_due (status, due_date), idx_tasks_match (normalized_title, source_chat_id, related_person_id)` |
| `task_events` | Audit history for task lifecycle changes. | `event_id, task_id, event_type, source, source_item_id, payload_json` … | `idx_task_events_task (task_id, created_at)` |
| `memory_chunks` | Durable summaries of completed AI batches. | `chunk_id, chat_id, batch_id, job_id, date_from, date_to` … | `idx_memory_chunks_chat_date (chat_id, date_from, date_to)` |
| `chat_daily_summaries` | Per-chat daily rollups. | `chat_id, summary_date, summary, chunk_count, updated_at` | `—` |
| `chat_monthly_summaries` | Per-chat monthly rollups. | `chat_id, summary_month, summary, day_count, updated_at` | `—` |
| `entity_memory` | Durable per-entity memory summaries. | `entity_type, entity_id, memory_key, summary, source_item_id, confidence` … | `—` |
| `daily_briefs` | Stored structured daily brief payloads. | `brief_date, data_json, created_at, updated_at` | `—` |
| `follow_ups` | Deduplicated operational follow-ups. | `follow_up_id, title, status, priority, person_id, company_id` … | `idx_follow_ups_status_due (status, due_at), idx_follow_ups_person (person_id, status)` |
| `chat_ai_policy` | Explicit per-chat AI inclusion policy. | `chat_id, mode, reason, updated_at` | `—` |
| `user_feedback` | Manual feedback on entities and decisions. | `feedback_id, feedback_type, entity_type, entity_id, payload_json, source` … | `idx_feedback_entity (entity_type, entity_id, feedback_type)` |
| `notification_outbox` | Deduplicated pending/sent attention notifications. | `notification_id, event_type, priority, title, body, entity_type` … | `idx_notification_pending (status, scheduled_at)` |
| `context_events` | Source-backed canonical events. | `event_id, event_type, title, description, occurred_at, observed_at` … | `idx_context_events_person_time (person_id, occurred_at), idx_context_events_project_time (project_id, occurred_at), idx_context_events_company_time (company_id, occurred_at)` |
| `context_facts` | Temporal facts with validity intervals. | `fact_id, subject_type, subject_id, predicate, value_json, valid_from` … | `idx_context_facts_current (subject_type, subject_id, is_current), idx_context_facts_predicate (predicate, is_current)` |
| `relationships` | Temporal relationships between canonical entities. | `relationship_id, from_type, from_id, to_type, to_id, relationship_type` … | `idx_relationships_from (from_type, from_id, is_current), idx_relationships_to (to_type, to_id, is_current)` |
| `context_conflicts` | Conflicting fact observations awaiting resolution. | `conflict_id, subject_type, subject_id, predicate, existing_fact_id, new_observation_id` … | `—` |
| `context_conflict_observations` | Proposed source-backed values for unresolved temporal conflicts. | `conflict_id, value_json, valid_from, confidence, source_chat_id, source_message_id` … | `—` |
| `context_conflict_decisions` | Append-only manual resolutions of temporal fact conflicts. | `decision_id, conflict_id, decision, resulting_fact_id, note, decided_at` | `idx_context_conflict_decisions_conflict (conflict_id, decided_at)` |
| `context_summary_versions` | Versioned contextual summaries. | `version_id, entity_type, entity_id, summary_type, summary, valid_from` … | `idx_context_summary_versions (entity_type, entity_id, valid_from)` |
| `global_state_snapshots` | Point-in-time global state summaries. | `snapshot_id, as_of, state_json, summary, created_at` | `—` |
| `pinned_memory` | User-pinned canonical memory. | `memory_id, entity_type, entity_id, content, created_at, updated_at` | `idx_pinned_memory_entity (entity_type, entity_id)` |
| `person_context_state` | Materialized current person context. | `person_id, relationship_type, communication_language, communication_style, typical_response_hours, last_contact_at` … | `—` |
| `temporal_resolutions` | Resolved relative/dependent time expressions. | `resolution_id, chat_id, message_id, raw_expression, resolved_at, resolution_type` … | `—` |
| `task_deep_dive_sessions` | Bounded task-investigation sessions and selected evidence metadata. | `session_id, task_id, status, summary_json, started_at, updated_at` | `idx_task_deep_dive_sessions_task (task_id, updated_at DESC)` |
| `task_deep_dive_evidence` | Evidence references discovered by a task-investigation session. | `session_id, evidence_type, evidence_id, relevance_score, discovered_at` | `—` |
| `task_notes` | User-authored notes attached to a canonical task. | `note_id, task_id, content, created_at, updated_at` | `idx_task_notes_task (task_id, updated_at DESC)` |
| `task_deep_dive_pins` | User-pinned evidence references for a canonical task. | `task_id, evidence_id, created_at` | `—` |
| `conversation_segments` | Application data. | `segment_id, chat_id, project_id, started_at, ended_at, anchor_count` … | `idx_conversation_segments_chat_time (chat_id, started_at, ended_at), idx_conversation_segments_project_time (project_id, started_at, ended_at)` |
| `conversation_contact_segments` | Application data. | `segment_id, person_id, source_type, conversation_id, chat_id, primary_project_id` … | `idx_contact_segments_person_time (person_id, started_at, ended_at), idx_contact_segments_conversation_time (source_type, conversation_id, started_at, ended_at)` |
| `current_conversation_context` | Application data. | `person_id, source_type, conversation_id, chat_id, primary_project_id, primary_company_id` … | `idx_current_conversation_context_person (person_id, updated_at DESC)` |
| `person_project_context` | Application data. | `person_id, project_id, role, status, first_activity_at, last_activity_at` … | `idx_person_project_context_project (project_id, status, last_activity_at DESC)` |
| `conversation_open_loops` | Application data. | `loop_id, person_id, project_id, source_type, conversation_id, loop_type` … | `idx_conversation_open_loops_person_status (person_id, status, updated_at DESC)` |
| `conversation_context_links` | Application data. | `link_id, person_id, link_type, from_chat_id, from_message_id, to_chat_id` … | `idx_conversation_context_links_person (person_id, created_at DESC)` |
<!-- AUTO-GENERATED:END -->

FTS5 indexes current non-empty messages, tasks, entities, durable memory, and
batch summaries where the local SQLite build supports it. These are rebuildable
derived tables: deleted messages and merged entities are excluded, and migration
12 recreates their contents from authoritative current rows. `make db-check`
and `make health` report source/index coverage; a broken present FTS index is a
failure, while an SQLite build without FTS5 uses bounded SQL retrieval.

For a Telegram direct chat (`chats.chat_type='user'`), `chats.chat_id` is the
deterministic peer identity. The matching `people.telegram_user_id` is the only
canonical owner for that conversation. Display names and aliases can suggest a
manual merge but cannot assign direct-chat ownership.

## Extraction lifecycle (migration 13)

`ai_jobs` records `analysis_version` and a deterministic selection fingerprint;
`ai_job_messages` stores each job's exact ordered message membership. Historic
range jobs remain visible, but unfinished rows without recoverable membership
are `superseded`. `ai_batches` separately records provider acceptance,
projection attempt/status/error, and context integration completion.

`ai_items.project_name` preserves the explicit project name cited by an
observation. `ai_item_rejections` retains individually invalid model items.
`context_invalidations` is the coalesced scope/revision ledger, and
`ai_batch_invalidations` retains which revisions each batch must see completed
before its context phase is integrated.

## Semantic claims and graph projection (migrations 14–15)

`semantic_claims` is the immutable AI-understanding layer. Each row stores its
extractor version, provider/model, bounded confidence, structured payload, and
authority state. `semantic_claim_evidence` records one or more exact submitted
Telegram messages; context alone cannot support a claim. Entity surface forms
stay in `semantic_claim_entity_refs` until deterministic resolution or Review.

`ai_items.source_claim_id` ties each new compatibility observation back to the
immutable claim it projects. Tasks plus newly written context events/facts
retain that lineage as well. `semantic_claims.projection_status` records graph
projection without changing claim authority.

`SemanticGraphProjector` is the sole writer of `graph_nodes`, `graph_edges`,
and `graph_edge_claims`. It creates observed claim links and canonical entity
nodes; only a task-to-project link already accepted by the deterministic task
reducer becomes an accepted edge. Each automatic edge has exact claim evidence,
temporal first/last-seen values, a validity interval, confidence, and authority
status.
An active manual task-to-project edge blocks later automatic replay and sends
the new claim projection to Review without deleting either record.
The old `relationships` table is still compatibility-only until its active
callers move to graph queries; no historical conversion occurs at startup.
`current_authoritative_edges` is a bounded, read-only contract for a future
consumer: it returns only current canonical-node edges, admitting automatic
edges solely for the existing `task --belongs_to--> project` reducer allowlist
with immutable claim evidence. Manual edges remain manual without fabricated
claim lineage. It does not yet replace any compatibility reader.

## Intelligence coverage

`message_classifications` stores a versioned interpretation of a Telegram
message without duplicating its text: conversation/content type, actionability,
importance, scope, temporal relevance, normalized topics, confidence, and the
context version used. `conversation_analysis_state` is a derived per-chat
checkpoint for classification and semantic coverage. Both tables are additive;
raw `messages`, AI batches, and accepted observations remain the evidence of
record. Classifier v2 persists `dated`/`unknown` rather than a wall-clock age
snapshot; age-relative labels are derived at the caller's `as_of`. Legacy rows
are selectively revisited through bounded classification work, while approved
manual classification reviews are not overwritten.
