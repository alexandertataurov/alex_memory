# Development

Use Python 3.12 and the locked repository virtual environment. Dependencies live
in `pyproject.toml` and `uv.lock`; do not use ad-hoc `pip install` commands for
project dependencies.

```bash
# Install uv first: https://docs.astral.sh/uv/getting-started/installation/
uv sync
code .
```

Copy `.env.example` to `.env` and provide your Telegram credentials. Tests use temporary SQLite databases and must not authenticate with Telegram.

## Work control

Notion's **Codex — Ready & Authorized** view is the sole source of truth for
development work control. Start from its lowest-sequence unblocked
implementation leaf, and read its Prompt, dependencies, and gates before
coding. Repository code and tests are behavioral evidence; `TASKS.md`,
ExecPlans, changelog, and documentation are synchronized mirrors and cannot
independently authorize, promote, reprioritize, unblock, or close work. A
missing `Repo ID` does not gate an otherwise authorized Notion leaf.

After implementation and verification, update the authoritative Notion task's
outcome/status/gates first, then synchronize repository mirrors and commit. If
code or tests contradict a Notion assumption, record and resolve that conflict
in Notion before changing scope.

## Environment reference

<!-- AUTO-GENERATED:START -->
| Variable | Example/default | Meaning |
| --- | --- | --- |
| `AI_AUTO_ACCEPT_CONFIDENCE` | `0.90` | Confidence at which operational updates are automatic. |
| `AI_AUTO_ANALYZE_INTERVAL_MINUTES` | `15` | Minutes between automatic AI runs. |
| `AI_AUTO_ANALYZE_NEW_MESSAGES` | `true` | Enable periodic AI analysis of new messages. |
| `AI_BATCH_CHARS` | `9000` | Maximum characters in one AI request. |
| `AI_BATCH_MESSAGES` | `30` | Maximum messages in one AI request. |
| `AI_CONTEXT_MESSAGES` | `10` | Prior messages included as bounded AI context. |
| `AI_DAILY_MAX_MESSAGES` | `3000` | Maximum messages considered in one daily run. |
| `AI_FALLBACK_PROVIDER` | `groq` | Fallback AI provider: gemini or groq. |
| `AI_INCLUDE_GROUPS` | `false` | Allow group messages to be analyzed by AI. |
| `AI_MAX_MESSAGE_CHARS` | `3000` | Maximum characters retained per message for AI. |
| `AI_MAX_OUTPUT_TOKENS` | `1200` | Maximum tokens reserved for an AI response. |
| `AI_MAX_RETRIES` | `4` | Attempts for a recoverable AI-provider failure. |
| `AI_PRIMARY_PROVIDER` | `gemini` | Primary AI provider: gemini or groq. |
| `AI_PROFILE_SUMMARIES_ENABLED` | `true` | See `Settings` in `config.py`. |
| `AI_REPORT_BATCHES` | `20` | Recent AI batches retained in diagnostics output. |
| `AI_REQUEST_TIMEOUT_SECONDS` | `45` | See `Settings` in `config.py`. |
| `AI_RETRY_BASE_SECONDS` | `3` | Base delay for AI retry backoff. |
| `AI_REVIEW_CONFIDENCE` | `0.65` | Confidence at which findings enter review. |
| `APP_TIMEZONE` | `Asia/Tbilisi` | IANA timezone used for temporal interpretation. |
| `CONTEXT_MAX_CHARS` | `50000` | Character cap for contextual-memory assembly. |
| `CONTEXT_MAX_COMPANIES` | `8` | Maximum companies selected for a context package. |
| `CONTEXT_MAX_EVENTS` | `30` | Event limit for contextual memory. |
| `CONTEXT_MAX_FACTS` | `50` | Fact limit for contextual memory. |
| `CONTEXT_MAX_GRAPH_DEPTH` | `2` | Maximum relationship hops from resolved entities. |
| `CONTEXT_MAX_PEOPLE` | `8` | Maximum people selected for a context package. |
| `CONTEXT_MAX_PROJECTS` | `8` | Maximum projects selected for a context package. |
| `CONTEXT_MAX_RAW_MESSAGES` | `30` | Raw-evidence limit for contextual memory. |
| `CONTEXT_MAX_SUMMARIES` | `15` | Summary limit for contextual memory. |
| `CONTEXT_MAX_TASKS` | `30` | Task limit for contextual memory. |
| `DAILY_BRIEF_AUTO_GENERATE` | `false` | Enable scheduled daily-brief generation. |
| `DAILY_BRIEF_TIME` | `08:00` | Local time for daily brief generation. |
| `FOLLOW_UP_WAITING_AFTER_DAYS` | `3` | Waiting age before a follow-up is created. |
| `GEMINI_API_KEY` | `replace_me` | Gemini API key; optional unless Gemini is selected. |
| `GEMINI_PRIMARY_RPD` | `500` | See `Settings` in `config.py`. |
| `GEMINI_PRIMARY_RPM` | `15` | See `Settings` in `config.py`. |
| `GEMINI_PRIMARY_TPM` | `250000` | See `Settings` in `config.py`. |
| `GEMINI_SECONDARY_RPD` | `500` | See `Settings` in `config.py`. |
| `GEMINI_SECONDARY_RPM` | `15` | See `Settings` in `config.py`. |
| `GEMINI_SECONDARY_TPM` | `250000` | See `Settings` in `config.py`. |
| `GEMMA_SHORT_MAX_INPUT_TOKENS` | `10000` | See `Settings` in `config.py`. |
| `GEMMA_SHORT_MODEL` | `gemma-4-31b-it` | See `Settings` in `config.py`. |
| `GEMMA_SHORT_RPD` | `14400` | See `Settings` in `config.py`. |
| `GEMMA_SHORT_RPM` | `30` | See `Settings` in `config.py`. |
| `GEMMA_SHORT_TPM` | `16000` | See `Settings` in `config.py`. |
| `GROQ_API_KEY` | `gsk_replace_me` | Groq API key; optional unless Groq is selected. |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq model identifier. |
| `GROUP_FULL_THRESHOLD` | `1000` | Archive full history for groups at or below this size. |
| `GROUP_RECENT_LIMIT` | `1000` | Recent-message limit for large groups. |
| `HISTORY_AUTO_ANALYZE` | `false` | Run resumable history analysis only while live ingestion is quiet. |
| `HISTORY_AUTO_ANALYZE_INTERVAL_MINUTES` | `60` | Minutes between quiet-time history-analysis checks. |
| `HISTORY_INTERNAL_BATCH_CHARS` | `12000` | Character limit for each provider-safe history window. |
| `HISTORY_INTERNAL_BATCH_MESSAGES` | `60` | Message limit for each provider-safe history window. |
| `HISTORY_INTERNAL_CONCURRENCY` | `20` | Maximum provider-safe history jobs claimed in one run. |
| `NOTIFICATION_REPEAT_HOURS` | `24` | Minimum interval between duplicate notifications. |
| `PROJECT_CRITICAL_STALE_DAYS` | `21` | Days without activity before critical status. |
| `PROJECT_STALE_DAYS` | `10` | Days without activity before a project is stale. |
| `QA_MAX_CONTEXT_CHARS` | `45000` | Character cap for question-answering context. |
| `QA_MAX_MEMORIES` | `20` | Memory-item limit for question-answering context. |
| `QA_MAX_RAW_MESSAGES` | `40` | Raw evidence limit for question answering. |
| `QA_MAX_SUMMARIES` | `15` | Summary limit for question-answering context. |
| `QA_MAX_TASKS` | `20` | Task limit for question-answering context. |
| `QA_USE_LLM` | `true` | Use an AI provider after deterministic retrieval. |
| `TASK_DEEP_DIVE_CONTEXT_AFTER` | `5` | Messages after a selected item shown as conversation context. |
| `TASK_DEEP_DIVE_CONTEXT_BEFORE` | `5` | Messages before a selected item shown as conversation context. |
| `TASK_DEEP_DIVE_MAX_CONTEXT_CHARS` | `60000` | Rendering character cap for task-deep-dive context. |
| `TASK_DEEP_DIVE_MAX_EVIDENCE` | `100` | Maximum selected evidence items for one task deep dive. |
| `TASK_DEEP_DIVE_MAX_GRAPH_DEPTH` | `2` | Documented task-deep-dive relationship traversal limit. |
| `TASK_DEEP_DIVE_MAX_QUERIES_PER_ROUND` | `8` | Maximum deterministic message queries in one deep-dive round. |
| `TASK_DEEP_DIVE_MAX_RAW_MESSAGES` | `60` | Maximum raw Telegram messages selected for one task deep dive. |
| `TASK_DEEP_DIVE_MAX_SEARCH_ROUNDS` | `3` | Maximum bounded expansion rounds in a task investigation. |
| `TELEGRAM_API_HASH` | `replace_me` | Telegram application hash (required). |
| `TELEGRAM_API_ID` | `12345678` | Telegram application identifier (required). |
| `TG_COMMIT_EVERY` | `500` | Messages written before a Telegram sync commit. |
| `TG_ITER_MESSAGES_WAIT_SECONDS` | `0.0` | Delay between Telegram history requests. |
| `TG_RECONCILE_ENABLED` | `true` | Enable periodic incremental reconciliation. |
| `TG_RECONCILE_INTERVAL_MINUTES` | `30` | Minutes between reconciliation passes. |
| `TG_WRITE_QUEUE_SIZE` | `10000` | Bounded SQLite write queue capacity. |
<!-- AUTO-GENERATED:END -->

Run `make docs` after changing `Settings` or the database schema, and `make docs-check` in review.

`make check` is the fast deterministic gate. `make verify` also validates the
lockfile, dependency declarations, known package vulnerabilities, SQLite
integrity, generated documentation, and task-queue structure.

Use `make help` to list the local commands. This workspace has existing Git
history and a configured remote. Review `git status`, stage only intended
files, and do not change remote or history settings without owner approval.
