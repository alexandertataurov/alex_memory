from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

load_dotenv: Any
try:
    from dotenv import load_dotenv
except ImportError:  # Keep non-runtime tools (such as tests) importable.
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    root: Path
    env_path: Path
    data_dir: Path
    db_path: Path
    session_path: Path

    telegram_api_id: int
    telegram_api_hash: str
    group_full_threshold: int
    group_recent_limit: int
    write_queue_size: int
    commit_every: int

    groq_api_key: str
    groq_model: str
    gemini_api_key: str
    gemini_model: str
    ai_primary_provider: str
    ai_fallback_provider: str
    ai_daily_max_messages: int
    ai_batch_messages: int
    ai_batch_chars: int
    history_internal_concurrency: int
    history_internal_batch_messages: int
    history_internal_batch_chars: int
    ai_context_messages: int
    ai_max_message_chars: int
    ai_max_retries: int
    ai_retry_base_seconds: int
    ai_report_batches: int
    ai_include_groups: bool = False
    ai_profile_summaries_enabled: bool = True
    gemini_requests_per_minute: float = 14.5
    ai_max_output_tokens: int = 1200
    ai_request_timeout_seconds: int = 45
    ai_auto_accept_confidence: float = 0.90
    ai_review_confidence: float = 0.65
    tg_reconcile_enabled: bool = True
    tg_reconcile_interval_minutes: int = 30
    ai_auto_analyze_new_messages: bool = True
    ai_auto_analyze_interval_minutes: int = 15
    history_auto_analyze: bool = False
    history_auto_analyze_interval_minutes: int = 60
    daily_brief_auto_generate: bool = False
    daily_brief_time: str = "08:00"
    app_timezone: str = "Asia/Tbilisi"
    tg_message_request_delay: float = 0.0
    qa_max_raw_messages: int = 40
    qa_max_tasks: int = 20
    qa_max_memories: int = 20
    qa_max_summaries: int = 15
    qa_max_context_chars: int = 45000
    follow_up_waiting_after_days: int = 3
    project_stale_days: int = 10
    project_critical_stale_days: int = 21
    notification_repeat_hours: int = 24
    qa_use_llm: bool = True
    context_max_chars: int = 50000
    context_max_raw_messages: int = 30
    context_max_events: int = 30
    context_max_facts: int = 50
    context_max_tasks: int = 30
    context_max_summaries: int = 15
    context_max_people: int = 8
    context_max_projects: int = 8
    context_max_companies: int = 8
    context_max_graph_depth: int = 2
    task_deep_dive_max_search_rounds: int = 3
    task_deep_dive_max_queries_per_round: int = 8
    task_deep_dive_max_evidence: int = 100
    task_deep_dive_max_raw_messages: int = 60
    task_deep_dive_context_before: int = 5
    task_deep_dive_context_after: int = 5
    task_deep_dive_max_graph_depth: int = 2
    task_deep_dive_max_context_chars: int = 60000
    # Direct construction is used by the temporary-SQLite tests and must use
    # the same runtime architecture as ``load_settings``.
    ai_routing_mode: str = "quota_aware"
    ai_routing_override: str = "auto"
    gemini_primary_model: str = "gemini-3.5-flash-lite"
    gemini_secondary_model: str = "gemini-3.1-flash-lite"
    gemma_short_model: str = "gemma-4-31b-it"
    ai_primary_daily_reserve_percent: int = 20
    gemini_primary_rpm: int = 15
    gemini_primary_tpm: int = 250000
    gemini_primary_rpd: int = 500
    gemini_secondary_rpm: int = 15
    gemini_secondary_tpm: int = 250000
    gemini_secondary_rpd: int = 500
    gemma_short_rpm: int = 30
    gemma_short_tpm: int = 16000
    gemma_short_rpd: int = 14400
    gemma_short_max_input_tokens: int = 10000
    configuration_warnings: tuple[str, ...] = ()


def load_settings(root: Path | None = None) -> Settings:
    project_root = root or Path(__file__).resolve().parents[2]
    env_path = project_root / ".env"
    if load_dotenv is None:
        raise RuntimeError("python-dotenv is not installed. Run: uv sync")
    if not env_path.is_file():
        raise RuntimeError(
            "Configuration error: .env is missing. Copy .env.example to .env, "
            "then set TELEGRAM_API_ID and TELEGRAM_API_HASH."
        )
    load_dotenv(env_path)

    configuration_warnings: list[str] = []
    gemini_primary_model, gemini_model_source = _env_value_with_source(
        "GEMINI_PRIMARY_MODEL",
        "GEMINI_MODEL",
        "GGEMINI_MODEL",
        default="gemini-3.5-flash-lite",
    )
    if gemini_model_source in {"GEMINI_MODEL", "GGEMINI_MODEL"}:
        configuration_warnings.append(
            f"{gemini_model_source} is deprecated; use GEMINI_PRIMARY_MODEL"
        )
    gemini_model = gemini_primary_model

    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

    missing = [
        name
        for name, value in (
            ("TELEGRAM_API_ID", api_id),
            ("TELEGRAM_API_HASH", api_hash),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Configuration error: "
            f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing "
            "from .env. See .env.example."
        )

    telegram_api_id = _positive_int("TELEGRAM_API_ID", api_id, minimum=1)

    return Settings(
        root=project_root,
        env_path=env_path,
        data_dir=project_root / "data",
        db_path=project_root / "data" / "telegram.sqlite",
        session_path=project_root / "alex_memory",
        telegram_api_id=telegram_api_id,
        telegram_api_hash=api_hash,
        group_full_threshold=_positive_int("GROUP_FULL_THRESHOLD", "1000", minimum=1),
        group_recent_limit=_positive_int("GROUP_RECENT_LIMIT", "1000", minimum=1),
        write_queue_size=_positive_int("TG_WRITE_QUEUE_SIZE", "10000", minimum=1000),
        commit_every=_positive_int("TG_COMMIT_EVERY", "500", minimum=50),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=gemini_model,
        ai_primary_provider=_provider_name("AI_PRIMARY_PROVIDER", "gemini"),
        ai_fallback_provider=_provider_name("AI_FALLBACK_PROVIDER", "groq"),
        ai_daily_max_messages=_positive_int(
            "AI_DAILY_MAX_MESSAGES",
            "3000",
            minimum=1,
        ),
        ai_batch_messages=_positive_int("AI_BATCH_MESSAGES", "30", minimum=1),
        ai_batch_chars=_positive_int("AI_BATCH_CHARS", "9000", minimum=2000),
        history_internal_concurrency=_positive_int(
            "HISTORY_INTERNAL_CONCURRENCY",
            _history_default(
                "HISTORY_INTERNAL_CONCURRENCY",
                "AI_HISTORY_CHUNKS_PER_RUN",
                "20",
                configuration_warnings,
            ),
            minimum=1,
        ),
        history_internal_batch_messages=_positive_int(
            "HISTORY_INTERNAL_BATCH_MESSAGES",
            _history_default(
                "HISTORY_INTERNAL_BATCH_MESSAGES",
                "AI_HISTORY_CHUNK_MESSAGES",
                "60",
                configuration_warnings,
            ),
            minimum=1,
        ),
        history_internal_batch_chars=_positive_int(
            "HISTORY_INTERNAL_BATCH_CHARS",
            _history_default(
                "HISTORY_INTERNAL_BATCH_CHARS",
                "AI_HISTORY_CHUNK_CHARS",
                "12000",
                configuration_warnings,
            ),
            minimum=2000,
        ),
        ai_context_messages=_positive_int("AI_CONTEXT_MESSAGES", "10", minimum=0),
        ai_max_message_chars=_positive_int("AI_MAX_MESSAGE_CHARS", "3000", minimum=500),
        ai_max_retries=_positive_int("AI_MAX_RETRIES", "4", minimum=1),
        ai_retry_base_seconds=_positive_int("AI_RETRY_BASE_SECONDS", "3", minimum=1),
        ai_report_batches=_positive_int("AI_REPORT_BATCHES", "20", minimum=1),
        ai_include_groups=_bool("AI_INCLUDE_GROUPS", "false"),
        ai_profile_summaries_enabled=_bool("AI_PROFILE_SUMMARIES_ENABLED", "true"),
        gemini_requests_per_minute=_positive_float(
            "GEMINI_REQUESTS_PER_MINUTE", "14.5", minimum=1
        ),
        ai_max_output_tokens=_positive_int("AI_MAX_OUTPUT_TOKENS", "1200", minimum=256),
        ai_request_timeout_seconds=_positive_int(
            "AI_REQUEST_TIMEOUT_SECONDS", "45", minimum=5
        ),
        ai_auto_accept_confidence=_confidence("AI_AUTO_ACCEPT_CONFIDENCE", "0.90"),
        ai_review_confidence=_confidence("AI_REVIEW_CONFIDENCE", "0.65"),
        tg_reconcile_enabled=_bool("TG_RECONCILE_ENABLED", "true"),
        tg_reconcile_interval_minutes=_positive_int(
            "TG_RECONCILE_INTERVAL_MINUTES", "30", minimum=1
        ),
        ai_auto_analyze_new_messages=_bool("AI_AUTO_ANALYZE_NEW_MESSAGES", "true"),
        ai_auto_analyze_interval_minutes=_positive_int(
            "AI_AUTO_ANALYZE_INTERVAL_MINUTES", "15", minimum=1
        ),
        history_auto_analyze=_bool("HISTORY_AUTO_ANALYZE", "false"),
        history_auto_analyze_interval_minutes=_positive_int(
            "HISTORY_AUTO_ANALYZE_INTERVAL_MINUTES", "60", minimum=1
        ),
        daily_brief_auto_generate=_bool("DAILY_BRIEF_AUTO_GENERATE", "false"),
        daily_brief_time=_clock_time("DAILY_BRIEF_TIME", "08:00"),
        app_timezone=_timezone("APP_TIMEZONE", "Asia/Tbilisi"),
        tg_message_request_delay=_nonnegative_float(
            "TG_ITER_MESSAGES_WAIT_SECONDS", "0.0"
        ),
        qa_max_raw_messages=_positive_int("QA_MAX_RAW_MESSAGES", "40", minimum=1),
        qa_max_tasks=_positive_int("QA_MAX_TASKS", "20", minimum=1),
        qa_max_memories=_positive_int("QA_MAX_MEMORIES", "20", minimum=1),
        qa_max_summaries=_positive_int("QA_MAX_SUMMARIES", "15", minimum=1),
        qa_max_context_chars=_positive_int(
            "QA_MAX_CONTEXT_CHARS", "45000", minimum=1000
        ),
        follow_up_waiting_after_days=_positive_int(
            "FOLLOW_UP_WAITING_AFTER_DAYS", "3", minimum=1
        ),
        project_stale_days=_positive_int("PROJECT_STALE_DAYS", "10", minimum=1),
        project_critical_stale_days=_positive_int(
            "PROJECT_CRITICAL_STALE_DAYS", "21", minimum=1
        ),
        notification_repeat_hours=_positive_int(
            "NOTIFICATION_REPEAT_HOURS", "24", minimum=1
        ),
        qa_use_llm=_bool("QA_USE_LLM", "true"),
        context_max_chars=_positive_int("CONTEXT_MAX_CHARS", "50000", minimum=1000),
        context_max_raw_messages=_positive_int(
            "CONTEXT_MAX_RAW_MESSAGES", "30", minimum=1
        ),
        context_max_events=_positive_int("CONTEXT_MAX_EVENTS", "30", minimum=1),
        context_max_facts=_positive_int("CONTEXT_MAX_FACTS", "50", minimum=1),
        context_max_tasks=_positive_int("CONTEXT_MAX_TASKS", "30", minimum=1),
        context_max_summaries=_positive_int("CONTEXT_MAX_SUMMARIES", "15", minimum=1),
        context_max_people=_positive_int("CONTEXT_MAX_PEOPLE", "8", minimum=1),
        context_max_projects=_positive_int("CONTEXT_MAX_PROJECTS", "8", minimum=1),
        context_max_companies=_positive_int("CONTEXT_MAX_COMPANIES", "8", minimum=1),
        context_max_graph_depth=_positive_int(
            "CONTEXT_MAX_GRAPH_DEPTH", "2", minimum=0
        ),
        task_deep_dive_max_search_rounds=_positive_int(
            "TASK_DEEP_DIVE_MAX_SEARCH_ROUNDS", "3", minimum=1
        ),
        task_deep_dive_max_queries_per_round=_positive_int(
            "TASK_DEEP_DIVE_MAX_QUERIES_PER_ROUND", "8", minimum=1
        ),
        task_deep_dive_max_evidence=_positive_int(
            "TASK_DEEP_DIVE_MAX_EVIDENCE", "100", minimum=1
        ),
        task_deep_dive_max_raw_messages=_positive_int(
            "TASK_DEEP_DIVE_MAX_RAW_MESSAGES", "60", minimum=1
        ),
        task_deep_dive_context_before=_positive_int(
            "TASK_DEEP_DIVE_CONTEXT_BEFORE", "5", minimum=0
        ),
        task_deep_dive_context_after=_positive_int(
            "TASK_DEEP_DIVE_CONTEXT_AFTER", "5", minimum=0
        ),
        task_deep_dive_max_graph_depth=_positive_int(
            "TASK_DEEP_DIVE_MAX_GRAPH_DEPTH", "2", minimum=0
        ),
        task_deep_dive_max_context_chars=_positive_int(
            "TASK_DEEP_DIVE_MAX_CONTEXT_CHARS", "60000", minimum=1000
        ),
        ai_routing_mode=_choice(
            "AI_ROUTING_MODE", "quota_aware", {"quota_aware", "legacy"}
        ),
        ai_routing_override=_choice(
            "AI_ROUTING_OVERRIDE",
            "auto",
            {"auto", "force_gemini_35", "force_gemini_31", "force_gemma", "force_groq"},
        ),
        gemini_primary_model=gemini_primary_model,
        gemini_secondary_model=os.getenv(
            "GEMINI_SECONDARY_MODEL", "gemini-3.1-flash-lite"
        ).strip(),
        gemma_short_model=os.getenv("GEMMA_SHORT_MODEL", "gemma-4-31b-it").strip(),
        ai_primary_daily_reserve_percent=_percentage(
            "AI_PRIMARY_DAILY_RESERVE_PERCENT", "20"
        ),
        gemini_primary_rpm=_positive_int("GEMINI_PRIMARY_RPM", "15", minimum=1),
        gemini_primary_tpm=_positive_int("GEMINI_PRIMARY_TPM", "250000", minimum=1),
        gemini_primary_rpd=_positive_int("GEMINI_PRIMARY_RPD", "500", minimum=1),
        gemini_secondary_rpm=_positive_int("GEMINI_SECONDARY_RPM", "15", minimum=1),
        gemini_secondary_tpm=_positive_int("GEMINI_SECONDARY_TPM", "250000", minimum=1),
        gemini_secondary_rpd=_positive_int("GEMINI_SECONDARY_RPD", "500", minimum=1),
        gemma_short_rpm=_positive_int("GEMMA_SHORT_RPM", "30", minimum=1),
        gemma_short_tpm=_positive_int("GEMMA_SHORT_TPM", "16000", minimum=1),
        gemma_short_rpd=_positive_int("GEMMA_SHORT_RPD", "14400", minimum=1),
        gemma_short_max_input_tokens=_positive_int(
            "GEMMA_SHORT_MAX_INPUT_TOKENS", "10000", minimum=1
        ),
        configuration_warnings=tuple(configuration_warnings),
    )


def _env_value_with_source(*names: str, default: str) -> tuple[str, str | None]:
    """Return the first configured environment value and its exact source."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value, name
    return default.strip(), None


def _positive_int(name: str, default: str, minimum: int) -> int:
    """Read a bounded integer setting with an actionable error message."""
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer; got {raw!r}") from error

    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}; got {value}")
    return value


def _positive_float(name: str, default: str, minimum: float) -> float:
    """Read a positive decimal setting with an actionable error message."""
    raw = os.getenv(name, default).strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number; got {raw!r}") from error
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}; got {value}")
    return value


def _provider_name(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in {"gemini", "groq"}:
        raise RuntimeError(f"{name} must be 'gemini' or 'groq'; got {value!r}")
    return value


def _choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in choices:
        rendered = ", ".join(sorted(choices))
        raise RuntimeError(f"{name} must be one of {rendered}; got {value!r}")
    return value


def _percentage(name: str, default: str) -> int:
    value = _positive_int(name, default, minimum=0)
    if value >= 100:
        raise RuntimeError(f"{name} must be less than 100; got {value}")
    return value


def _history_default(
    current_name: str, legacy_name: str, default: str, warnings: list[str]
) -> str:
    """Resolve a legacy history input only when the current input is absent."""
    if os.getenv(current_name, "").strip():
        return default
    legacy = os.getenv(legacy_name, "").strip()
    if legacy:
        warnings.append(f"{legacy_name} is deprecated; use {current_name}")
        return legacy
    return default


def _confidence(name: str, default: str) -> float:
    raw = os.getenv(name, default).strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(
            f"{name} must be a number between 0 and 1; got {raw!r}"
        ) from error
    if not 0 <= value <= 1:
        raise RuntimeError(f"{name} must be between 0 and 1; got {value}")
    return value


def _bool(name: str, default: str) -> bool:
    raw = os.getenv(name, default).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean; got {raw!r}")


def _clock_time(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    try:
        hour, minute = (int(part) for part in value.split(":", maxsplit=1))
    except ValueError as error:
        raise RuntimeError(f"{name} must be HH:MM; got {value!r}") from error
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise RuntimeError(f"{name} must be a valid local time; got {value!r}")
    return f"{hour:02d}:{minute:02d}"


def _timezone(name: str, default: str) -> str:
    value = os.getenv(name, default).strip() or default
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(
            f"{name} must be a valid IANA timezone; got {value!r}"
        ) from error
    return value


def _nonnegative_float(name: str, default: str) -> float:
    raw = os.getenv(name, default).strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(
            f"{name} must be a non-negative number; got {raw!r}"
        ) from error
    if value < 0:
        raise RuntimeError(f"{name} must be non-negative; got {value}")
    return value
