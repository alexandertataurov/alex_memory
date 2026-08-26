"""Central model registry and quota accounting for bounded AI requests."""

from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ..config import Settings


class AIWorkload(StrEnum):
    MESSAGE_CLASSIFICATION = "message_classification"
    SIMPLE_EXTRACTION = "simple_extraction"
    CONTEXT_EXTRACTION = "context_extraction"
    SUMMARY = "summary"
    RECONCILIATION = "reconciliation"
    MEMORY_QA = "memory_qa"
    TASK_DEEP_DIVE = "task_deep_dive"
    GRAPH_IMPROVEMENT = "graph_improvement"


class RequestPriority(StrEnum):
    CRITICAL = "critical"
    INTERACTIVE = "interactive"
    BACKGROUND = "background"


class QuotaPressure(StrEnum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
    EXHAUSTED = "exhausted"
    COOLDOWN = "cooldown"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    key: str
    provider: str
    model: str
    rpm: int | None
    tpm: int | None
    rpd: int | None
    max_input_tokens: int | None
    structured_output: bool = True
    long_context: bool = False


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    profile: ModelProfile
    workload: AIWorkload
    estimated_input_tokens: int
    reason: str
    pressure: QuotaPressure


def estimate_tokens(text: str) -> int:
    """Conservative, tokenizer-independent prompt estimate for quota guarding."""
    return max(1, (len(text) + 2) // 3)


class ModelRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._profiles = {
            "gemini_35": ModelProfile(
                "gemini_35",
                "gemini",
                settings.gemini_primary_model,
                settings.gemini_primary_rpm,
                settings.gemini_primary_tpm,
                settings.gemini_primary_rpd,
                None,
                True,
                True,
            ),
            "gemini_31": ModelProfile(
                "gemini_31",
                "gemini",
                settings.gemini_secondary_model,
                settings.gemini_secondary_rpm,
                settings.gemini_secondary_tpm,
                settings.gemini_secondary_rpd,
                None,
                True,
                True,
            ),
            # Google documents gemma-4-31b-it as a hosted Gemini API model.
            "gemma": ModelProfile(
                "gemma",
                "gemini",
                settings.gemma_short_model,
                settings.gemma_short_rpm,
                settings.gemma_short_tpm,
                settings.gemma_short_rpd,
                settings.gemma_short_max_input_tokens,
                True,
                False,
            ),
            "groq": ModelProfile(
                "groq",
                "groq",
                settings.groq_model,
                None,
                None,
                None,
                None,
                True,
                False,
            ),
        }

    @property
    def profiles(self) -> tuple[ModelProfile, ...]:
        return tuple(self._profiles.values())

    def profile(self, key: str) -> ModelProfile:
        return self._profiles[key]

    def candidates(
        self,
        workload: AIWorkload,
        *,
        requires_structured_output: bool = True,
    ) -> list[ModelProfile]:
        """Return the policy-eligible route order for one bounded workload."""
        short_workloads = {
            AIWorkload.MESSAGE_CLASSIFICATION,
            AIWorkload.SIMPLE_EXTRACTION,
        }
        keys = (
            ("gemini_35", "gemini_31", "gemma", "groq")
            if workload in short_workloads
            else ("gemini_35", "gemini_31", "groq")
        )
        profiles = [self._profiles[key] for key in keys]
        if requires_structured_output:
            profiles = [profile for profile in profiles if profile.structured_output]
        return profiles

    def forced(self) -> ModelProfile | None:
        override = self.settings.ai_routing_override
        return {
            "force_gemini_35": self._profiles["gemini_35"],
            "force_gemini_31": self._profiles["gemini_31"],
            "force_gemma": self._profiles["gemma"],
            "force_groq": self._profiles["groq"],
        }.get(override)


class QuotaTracker:
    """Local quota state; durable daily counters and in-process rolling windows."""

    def __init__(
        self, conn: sqlite3.Connection | None = None, primary_reserve_percent: int = 20
    ):
        self.conn = conn
        self.primary_reserve_percent = primary_reserve_percent
        self._requests: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self._cooldowns: dict[str, tuple[float, str]] = {}

    def pressure(
        self, profile: ModelProfile, priority: RequestPriority
    ) -> QuotaPressure:
        now = datetime.now(UTC).timestamp()
        cooldown = self._cooldowns.get(profile.key)
        if cooldown and now < cooldown[0]:
            return QuotaPressure.COOLDOWN
        requests, _tokens = self._today(profile)
        if profile.rpd is not None:
            allowed = profile.rpd
            if profile.key == "gemini_35" and priority is RequestPriority.BACKGROUND:
                allowed = int(profile.rpd * (1 - self.primary_reserve_percent / 100))
            ratio = requests / max(1, allowed)
            if ratio >= 1:
                return QuotaPressure.EXHAUSTED
            if ratio >= 0.85:
                return QuotaPressure.HIGH
            if ratio >= 0.65:
                return QuotaPressure.ELEVATED
        return QuotaPressure.NORMAL

    def available(
        self, profile: ModelProfile, estimated_tokens: int, priority: RequestPriority
    ) -> tuple[bool, QuotaPressure, str]:
        pressure = self.pressure(profile, priority)
        if profile.max_input_tokens and estimated_tokens > profile.max_input_tokens:
            return (
                False,
                pressure,
                f"prompt estimate {estimated_tokens:,} exceeds input guard",
            )
        if pressure in {QuotaPressure.COOLDOWN, QuotaPressure.EXHAUSTED}:
            return False, pressure, pressure.value
        self._prune(profile.key)
        recent = self._requests[profile.key]
        if profile.rpm and len(recent) >= profile.rpm:
            return False, QuotaPressure.HIGH, "local RPM window is full"
        if (
            profile.tpm
            and sum(tokens for _, tokens in recent) + estimated_tokens > profile.tpm
        ):
            return False, QuotaPressure.HIGH, "local TPM window is full"
        return True, pressure, "quota available"

    def record_attempt(self, profile: ModelProfile, estimated_tokens: int) -> None:
        now = datetime.now(UTC)
        self._requests[profile.key].append((now.timestamp(), estimated_tokens))
        self._write(profile, attempts=1, estimated=estimated_tokens, at=now)

    def record_success(
        self, profile: ModelProfile, usage: dict[str, int | str]
    ) -> None:
        prompt = int(usage.get("prompt_token_count", 0) or 0)
        output = int(usage.get("candidates_token_count", 0) or 0)
        self._write(
            profile,
            successes=1,
            actual_input=prompt,
            output=output,
            at=datetime.now(UTC),
        )

    def record_failure(
        self, profile: ModelProfile, reason: str, cooldown_seconds: float | None
    ) -> None:
        until = None
        if cooldown_seconds is not None:
            until = datetime.now(UTC).timestamp() + max(1.0, cooldown_seconds)
            self._cooldowns[profile.key] = (until, reason)
        self._write(profile, error=reason, cooldown_until=until, at=datetime.now(UTC))

    def cooldown(self, profile: ModelProfile) -> tuple[float, str] | None:
        value = self._cooldowns.get(profile.key)
        if value is None and self.conn is not None:
            row = self.conn.execute(
                """SELECT cooldown_until,last_error FROM ai_model_usage
                   WHERE usage_date=? AND model_key=?""",
                (datetime.now(UTC).date().isoformat(), profile.key),
            ).fetchone()
            if row and row[0]:
                try:
                    until = datetime.fromisoformat(
                        str(row[0]).replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    until = 0.0
                if until > datetime.now(UTC).timestamp():
                    value = (until, str(row[1] or "persisted cooldown"))
                    self._cooldowns[profile.key] = value
        if value and datetime.now(UTC).timestamp() < value[0]:
            return value
        return None

    def status_rows(
        self, registry: ModelRegistry
    ) -> list[tuple[ModelProfile, int, int, int, QuotaPressure, str | None]]:
        rows = []
        for profile in registry.profiles:
            attempts, tokens = self._today(profile)
            cooldown = self.cooldown(profile)
            rows.append(
                (
                    profile,
                    attempts,
                    tokens,
                    profile.rpd or 0,
                    self.pressure(profile, RequestPriority.BACKGROUND),
                    cooldown[1] if cooldown else None,
                )
            )
        return rows

    def _today(self, profile: ModelProfile) -> tuple[int, int]:
        if self.conn is None:
            return 0, 0
        row = self.conn.execute(
            "SELECT attempt_count,estimated_input_tokens FROM ai_model_usage WHERE usage_date=? AND model_key=?",
            (datetime.now(UTC).date().isoformat(), profile.key),
        ).fetchone()
        return (int(row[0]), int(row[1])) if row else (0, 0)

    def _write(
        self,
        profile: ModelProfile,
        *,
        attempts: int = 0,
        successes: int = 0,
        estimated: int = 0,
        actual_input: int = 0,
        output: int = 0,
        error: str | None = None,
        cooldown_until: float | None = None,
        at: datetime,
    ) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            """INSERT INTO ai_model_usage(usage_date,model_key,provider,model,attempt_count,success_count,estimated_input_tokens,actual_input_tokens,output_tokens,last_request_at,last_success_at,last_error_at,last_error,cooldown_until)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(usage_date,model_key) DO UPDATE SET
                 attempt_count=attempt_count+excluded.attempt_count, success_count=success_count+excluded.success_count,
                 estimated_input_tokens=estimated_input_tokens+excluded.estimated_input_tokens,
                 actual_input_tokens=actual_input_tokens+excluded.actual_input_tokens, output_tokens=output_tokens+excluded.output_tokens,
                 last_request_at=COALESCE(excluded.last_request_at,last_request_at), last_success_at=COALESCE(excluded.last_success_at,last_success_at),
                 last_error_at=COALESCE(excluded.last_error_at,last_error_at), last_error=COALESCE(excluded.last_error,last_error), cooldown_until=COALESCE(excluded.cooldown_until,cooldown_until)""",
            (
                at.date().isoformat(),
                profile.key,
                profile.provider,
                profile.model,
                attempts,
                successes,
                estimated,
                actual_input,
                output,
                at.isoformat() if attempts else None,
                at.isoformat() if successes else None,
                at.isoformat() if error else None,
                error,
                datetime.fromtimestamp(cooldown_until, UTC).isoformat()
                if cooldown_until
                else None,
            ),
        )
        self.conn.commit()

    def _prune(self, key: str) -> None:
        cutoff = datetime.now(UTC).timestamp() - 60
        recent = self._requests[key]
        while recent and recent[0][0] <= cutoff:
            recent.popleft()
