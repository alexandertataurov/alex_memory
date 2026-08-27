"""Workload-aware routing with local quota guards and bounded fallback."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from ..config import Settings
from ..models import AIAnalysisResult, AIAnswerResult, AIBatch, AIRequest
from .providers import (
    AIProvider,
    GeminiProvider,
    GroqProvider,
    ProviderAnalysisRequest,
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaError,
    ProviderRetryableError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderTransientError,
)
from .providers.base import ANSWER_SYSTEM_PROMPT, extraction_input_parts
from .routing import (
    AIWorkload,
    ModelProfile,
    ModelRegistry,
    QuotaTracker,
    RequestPriority,
    estimate_tokens,
)


class AIRouter:
    """Route bounded requests by workload, capability, local quota and health."""

    def __init__(
        self,
        settings: Settings,
        providers: dict[str, AIProvider] | None = None,
        *,
        conn: sqlite3.Connection | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.settings = settings
        self.providers = providers or {
            "gemini": GeminiProvider(settings),
            "groq": GroqProvider(settings),
        }
        self.registry = ModelRegistry(settings)
        self.quota = QuotaTracker(conn, settings.ai_primary_daily_reserve_percent)
        self.conn = conn
        self.requests = self.fallbacks = self.errors = 0
        self._clock, self._sleep = clock, sleep
        self.active_provider: str | None = None
        self.active_model: str | None = None
        self.active_state = "idle"
        self.last_error: str | None = None
        self.retry_at: float | None = None
        self.session_provider: str | None = None
        self.session_model_key: str | None = None
        self.last_decision: str | None = None
        self._unavailable: dict[str, tuple[float, str]] = {}
        self._provider_unavailable: dict[str, tuple[float, str]] = {}
        self._next_request_at: dict[str, float] = {}
        self._rate_lock = asyncio.Lock()

    async def analyze(
        self,
        batch: AIBatch,
        *,
        workload: AIWorkload = AIWorkload.CONTEXT_EXTRACTION,
        priority: RequestPriority = RequestPriority.BACKGROUND,
    ) -> AIAnalysisResult:
        if self.settings.ai_routing_mode == "legacy":
            return await self._analyze_legacy(batch)
        return await self.analyze_request(
            AIRequest(batch=batch, workload=workload.value, priority=priority.value)
        )

    async def close(self) -> None:
        """Close provider transports owned by this router's default providers."""
        for provider in self.providers.values():
            close = getattr(provider, "close", None)
            if close is not None:
                await close()

    async def _analyze_legacy(self, batch: AIBatch) -> AIAnalysisResult:
        """Keep pre-AM-049 explicit-primary behavior for compatible callers."""
        names = [self.settings.ai_primary_provider]
        if self.settings.ai_fallback_provider not in names:
            names.append(self.settings.ai_fallback_provider)
        if self.session_provider:
            names = [
                self.session_provider,
                *[name for name in names if name != self.session_provider],
            ]
        errors: list[str] = []
        retryable_failure = False
        for index, name in enumerate(names):
            unavailable = self._unavailable.get(name)
            if unavailable and self._clock() < unavailable[0]:
                errors.append(f"{name}: {unavailable[1]}")
                continue
            self._unavailable.pop(name, None)
            provider = self.providers.get(name)
            if provider is None:
                errors.append(f"{name}: unavailable")
                continue
            for attempt in range(2):
                self.requests += 1
                self.active_provider, self.active_model = (
                    name,
                    getattr(provider, "model", None),
                )
                self.active_state = "provider request in flight"
                try:
                    result = await provider.analyze(
                        ProviderAnalysisRequest(
                            batch=batch,
                            provider=name,
                            model=provider.model,
                            requests_per_minute=None,
                        )
                    )
                    result.fallback_used = index > 0
                    if result.fallback_used:
                        self.fallbacks += 1
                        result.usage["fallback_reason"] = (
                            errors[-1] if errors else "primary unavailable"
                        )
                        self.session_provider = name
                    else:
                        self.last_error = None
                    self.active_state = "response received"
                    return result
                except Exception as error:
                    retryable_failure = retryable_failure or isinstance(
                        error,
                        (
                            ProviderQuotaError,
                            ProviderConnectionError,
                            ProviderTimeoutError,
                            ProviderTransientError,
                        ),
                    )
                    reason = f"{type(error).__name__}: {error}"
                    self.last_error = f"{name}: {reason}"
                    errors.append(self.last_error)
                    retry_after = (
                        error.retry_after_seconds
                        if isinstance(error, ProviderQuotaError)
                        else None
                    )
                    if (
                        index == 0
                        and attempt == 0
                        and retry_after is not None
                        and retry_after <= 60
                    ):
                        self.retry_at = self._clock() + retry_after
                        self.active_state = (
                            f"quota cooldown; retrying primary after {retry_after:.1f}s"
                        )
                        await self._sleep(retry_after)
                        self.retry_at = None
                        continue
                    if isinstance(error, ProviderQuotaError):
                        self._unavailable[name] = (
                            self._clock() + (retry_after or 60),
                            reason,
                        )
                    break
        self.errors += 1
        self.active_state = "all providers failed"
        error_type = ProviderRetryableError if retryable_failure else ProviderError
        raise error_type("All AI providers failed — " + " | ".join(errors))

    async def analyze_request(self, request: AIRequest) -> AIAnalysisResult:
        workload, priority = (
            AIWorkload(request.workload),
            RequestPriority(request.priority),
        )
        estimated = request.estimated_input_tokens or self._extraction_estimate(
            request.batch
        )
        policy_reasons = self.registry.candidate_explanations(
            workload, requires_structured_output=request.requires_structured_output
        )
        errors: list[str] = []
        retryable_failure = False
        candidates = self._candidates(
            workload, requires_structured_output=request.requires_structured_output
        )
        for index, profile in enumerate(candidates):
            provider_health = self._provider_unavailable.get(profile.provider)
            if provider_health and self._clock() < provider_health[0]:
                self._set_active(profile, "model cooldown; trying next route")
                errors.append(f"{profile.key}: {provider_health[1]}")
                retryable_failure = True
                continue
            self._provider_unavailable.pop(profile.provider, None)
            provider = self.providers.get(profile.provider)
            if provider is None:
                errors.append(f"{profile.key}: provider unavailable")
                continue
            for attempt in range(self.settings.ai_max_retries):
                reason = await self._begin_attempt(
                    workload, priority, profile, estimated, policy_reasons[profile.key]
                )
                if reason is None:
                    errors.append(f"{profile.key}: quota unavailable")
                    retryable_failure = True
                    break
                try:
                    result = await self._request_provider(
                        provider, request.batch, profile
                    )
                except Exception as error:
                    retryable_failure = retryable_failure or isinstance(
                        error,
                        (
                            ProviderQuotaError,
                            ProviderConnectionError,
                            ProviderTimeoutError,
                            ProviderTransientError,
                        ),
                    )
                    detail = self._record_failure(
                        workload, priority, profile, estimated, reason, error
                    )
                    if self._fallback_is_unsafe(error):
                        self.errors += 1
                        self.active_state = "request termination unconfirmed"
                        raise ProviderError(
                            f"{profile.key}: {detail}; fallback withheld"
                        ) from error
                    delay = self._retry_delay(error, attempt)
                    if delay is not None:
                        self.retry_at = self._clock() + delay
                        self.active_state = f"{profile.key} retrying after {delay:.1f}s"
                        await self._sleep(delay)
                        self.retry_at = None
                        continue
                    errors.append(f"{profile.key}: {detail}")
                    self._mark_provider_unavailable(profile, error)
                    break
                result.fallback_used = index > 0
                if result.fallback_used:
                    self.fallbacks += 1
                    result.usage["fallback_reason"] = (
                        errors[-1] if errors else "policy route"
                    )
                self.quota.record_success(profile, result.usage)
                self._record_event(
                    workload, priority, profile, estimated, reason, "success"
                )
                self.active_state, self.last_error = "response received", None
                if index > 0:
                    self.session_provider, self.session_model_key = (
                        profile.provider,
                        profile.key,
                    )
                return result
        route_chain = " → ".join(profile.key for profile in candidates)
        self.active_state = (
            f"all eligible routes unavailable: {route_chain}"
            if route_chain
            else "all eligible routes unavailable"
        )
        self.errors += 1
        error_type = ProviderRetryableError if retryable_failure else ProviderError
        raise error_type(
            "All AI routes unavailable — "
            + " | ".join(errors)
            + (f" (tried: {route_chain})" if route_chain else "")
        )

    async def answer(self, prompt: str) -> str:
        """Route a bounded grounded-answer request through the normal policy.

        Answers intentionally share quota, health, and telemetry ownership with
        extraction. They do not create an AI batch or canonical state.
        """
        workload = AIWorkload.MEMORY_QA
        priority = RequestPriority.INTERACTIVE
        estimated = self._answer_estimate(prompt)
        errors: list[str] = []
        for index, profile in enumerate(self._candidates(workload)):
            health = self._provider_unavailable.get(profile.provider)
            if health and self._clock() < health[0]:
                errors.append(f"{profile.key}: {health[1]}")
                continue
            self._provider_unavailable.pop(profile.provider, None)
            provider = self.providers.get(profile.provider)
            if provider is None:
                errors.append(f"{profile.key}: provider unavailable")
                continue
            for attempt in range(self.settings.ai_max_retries):
                reason = await self._begin_attempt(
                    workload, priority, profile, estimated, "eligible: answer policy"
                )
                if reason is None:
                    errors.append(f"{profile.key}: quota unavailable")
                    break
                try:
                    answer = await provider.answer(prompt, profile.model)
                    if not isinstance(answer, AIAnswerResult):
                        raise ProviderError(
                            "provider returned an invalid answer result"
                        )
                    if (
                        answer.provider != profile.provider
                        or answer.model != profile.model
                    ):
                        raise ProviderError("provider execution identity mismatch")
                    if not answer.text.strip():
                        raise ProviderError("provider returned an empty answer")
                except Exception as error:
                    detail = self._record_failure(
                        workload, priority, profile, estimated, reason, error
                    )
                    if self._fallback_is_unsafe(error):
                        self.errors += 1
                        self.active_state = "request termination unconfirmed"
                        raise ProviderError(
                            f"{profile.key}: {detail}; fallback withheld"
                        ) from error
                    delay = self._retry_delay(error, attempt)
                    if delay is not None:
                        self.retry_at = self._clock() + delay
                        await self._sleep(delay)
                        self.retry_at = None
                        continue
                    errors.append(f"{profile.key}: {detail}")
                    self._mark_provider_unavailable(profile, error)
                    break
                self.quota.record_success(profile, answer.usage)
                self._record_event(
                    workload, priority, profile, estimated, reason, "success"
                )
                self.active_state, self.last_error = "response received", None
                if index:
                    self.fallbacks += 1
                    self.session_provider, self.session_model_key = (
                        profile.provider,
                        profile.key,
                    )
                return answer.text.strip()
        self.errors += 1
        self.active_state = "all eligible routes unavailable"
        raise ProviderError("All AI routes unavailable — " + " | ".join(errors))

    def _extraction_estimate(self, batch: AIBatch) -> int:
        return sum(estimate_tokens(part) for part in extraction_input_parts(batch))

    def _answer_estimate(self, prompt: str) -> int:
        return estimate_tokens(ANSWER_SYSTEM_PROMPT) + estimate_tokens(prompt)

    async def _begin_attempt(
        self,
        workload: AIWorkload,
        priority: RequestPriority,
        profile: ModelProfile,
        estimated: int,
        policy_reason: str,
    ) -> str | None:
        available, _pressure, quota_reason = self.quota.available(
            profile, estimated, priority
        )
        if not available:
            self._set_active(profile, f"skipped: {quota_reason}")
            return None
        await self._wait_for_request_slot(profile)
        reason = f"{profile.key}: {policy_reason}; {quota_reason} for {workload.value}"
        self.last_decision = reason
        self._record_event(workload, priority, profile, estimated, reason, "attempt")
        self.quota.record_attempt(profile, estimated)
        self.requests += 1
        self._set_active(profile, "provider request in flight")
        return reason

    async def _wait_for_request_slot(self, profile: ModelProfile) -> None:
        """Preserve the established model-specific RPM endpoint margin."""
        if profile.rpm is None:
            return
        interval = 60.0 / max(1, profile.rpm - 1)
        async with self._rate_lock:
            now = self._clock()
            slot = max(now, self._next_request_at.get(profile.key, 0.0))
            delay = slot - now
            if delay > 0:
                await self._sleep(delay)
            self._next_request_at[profile.key] = slot + interval

    def _record_failure(
        self,
        workload: AIWorkload,
        priority: RequestPriority,
        profile: ModelProfile,
        estimated: int,
        reason: str,
        error: Exception,
    ) -> str:
        detail = f"{type(error).__name__}: {error}"
        cooldown = (
            self._quota_cooldown(error)
            if isinstance(error, ProviderQuotaError)
            else None
        )
        self.quota.record_failure(profile, detail, cooldown)
        self.last_error = f"{profile.key}: {detail}"
        self._record_event(
            workload, priority, profile, estimated, reason, "failed", detail
        )
        return detail

    def _retry_delay(self, error: Exception, attempt: int) -> float | None:
        if isinstance(error, ProviderQuotaError):
            if error.dimension in {"rpd", "tpd"}:
                return None
            delay = error.retry_after_seconds
            return delay if delay is not None and delay <= 60 and attempt == 0 else None
        if isinstance(error, (ProviderConnectionError, ProviderTransientError)):
            if attempt + 1 < self.settings.ai_max_retries:
                return min(60.0, self.settings.ai_retry_base_seconds * (2**attempt))
        return None

    @staticmethod
    def _quota_cooldown(error: ProviderQuotaError) -> float | None:
        if error.dimension not in {"rpd", "tpd"}:
            return error.retry_after_seconds
        now = datetime.now(UTC)
        next_day = datetime.combine(
            now.date() + timedelta(days=1), datetime.min.time(), UTC
        )
        return max(1.0, (next_day - now).total_seconds())

    def _mark_provider_unavailable(
        self, profile: ModelProfile, error: Exception
    ) -> None:
        if isinstance(error, ProviderConnectionError):
            seconds = 300
            self._provider_unavailable[profile.provider] = (
                self._clock() + seconds,
                f"network connection failed; retry after {seconds:g} seconds",
            )

    @staticmethod
    def _fallback_is_unsafe(error: Exception) -> bool:
        return (
            isinstance(error, ProviderTimeoutError) and not error.termination_confirmed
        )

    def _route_chain(self, workload: AIWorkload) -> str:
        return " → ".join(profile.key for profile in self._candidates(workload))

    def _remaining_route_chain(self, workload: AIWorkload, index: int) -> str:
        candidates = self._candidates(workload)
        return " → ".join(profile.key for profile in candidates[index + 1 :])

    def _candidates(
        self,
        workload: AIWorkload,
        *,
        requires_structured_output: bool = True,
    ) -> list[ModelProfile]:
        if self.settings.ai_routing_mode == "legacy":
            keys = (
                "groq" if name == "groq" else "gemini_35"
                for name in (
                    self.settings.ai_primary_provider,
                    self.settings.ai_fallback_provider,
                )
            )
            return list(dict.fromkeys(self.registry.profile(key) for key in keys))
        forced = self.registry.forced()
        if forced:
            return [forced]
        candidates = self.registry.candidates(
            workload, requires_structured_output=requires_structured_output
        )
        if self.session_model_key:
            selected = self.registry.profile(self.session_model_key)
            return [
                selected,
                *[item for item in candidates if item.key != selected.key],
            ]
        return candidates

    async def _request_provider(
        self, provider: AIProvider, batch: AIBatch, profile: ModelProfile
    ) -> AIAnalysisResult:
        result = await provider.analyze(
            ProviderAnalysisRequest(
                batch=batch,
                provider=profile.provider,
                model=profile.model,
                requests_per_minute=profile.rpm,
            )
        )
        if result.provider != profile.provider or result.model != profile.model:
            raise ProviderResponseError(
                "provider execution identity mismatch: selected "
                f"{profile.provider}/{profile.model}, returned "
                f"{result.provider}/{result.model}"
            )
        return result

    def _set_active(self, profile: ModelProfile, state: str) -> None:
        self.active_provider, self.active_model, self.active_state = (
            profile.provider,
            profile.model,
            state,
        )

    def _record_event(
        self,
        workload: AIWorkload,
        priority: RequestPriority,
        profile: ModelProfile,
        estimated: int,
        reason: str,
        outcome: str,
        error: str | None = None,
    ) -> None:
        if self.conn is None:
            return
        from ..utils import utc_now

        self.conn.execute(
            "INSERT INTO ai_route_events(created_at,workload,priority,model_key,provider,model,estimated_input_tokens,decision_reason,outcome,error) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                utc_now(),
                workload.value,
                priority.value,
                profile.key,
                profile.provider,
                profile.model,
                estimated,
                reason,
                outcome,
                error,
            ),
        )
        self.conn.commit()
