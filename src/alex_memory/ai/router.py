"""Workload-aware routing with local quota guards and bounded fallback."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Awaitable, Callable

from ..config import Settings
from ..models import AIAnalysisResult, AIBatch, AIRequest
from .providers import (
    AIProvider,
    GeminiProvider,
    GroqProvider,
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaError,
)
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
                    result = await provider.analyze(batch)
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
        raise ProviderError("All AI providers failed — " + " | ".join(errors))

    async def analyze_request(self, request: AIRequest) -> AIAnalysisResult:
        workload, priority = (
            AIWorkload(request.workload),
            RequestPriority(request.priority),
        )
        estimated = request.estimated_input_tokens or estimate_tokens(
            request.batch.prompt
        )
        errors: list[str] = []
        candidates = self._candidates(
            workload, requires_structured_output=request.requires_structured_output
        )
        for index, profile in enumerate(candidates):
            provider_health = self._provider_unavailable.get(profile.provider)
            if provider_health and self._clock() < provider_health[0]:
                self._set_active(profile, "model cooldown; trying next route")
                errors.append(f"{profile.key}: {provider_health[1]}")
                continue
            self._provider_unavailable.pop(profile.provider, None)
            available, _pressure, reason = self.quota.available(
                profile, estimated, priority
            )
            if not available:
                self._set_active(profile, f"skipped: {reason}")
                errors.append(f"{profile.key}: {reason}")
                continue
            provider = self.providers.get(profile.provider)
            if provider is None:
                errors.append(f"{profile.key}: provider unavailable")
                continue
            self.last_decision = f"{profile.key}: {reason} for {workload.value}"
            self._record_event(
                workload, priority, profile, estimated, self.last_decision, "attempt"
            )
            self.quota.record_attempt(profile, estimated)
            self.requests += 1
            self._set_active(profile, "provider request in flight")
            try:
                result = await self._request_provider(provider, request.batch, profile)
            except Exception as error:
                detail = f"{type(error).__name__}: {error}"
                next_routes = " → ".join(item.key for item in candidates[index + 1 :])
                self.last_error = f"{profile.key}: {detail}" + (
                    f"; next: {next_routes}" if next_routes else ""
                )
                errors.append(self.last_error)
                cooldown = (
                    error.retry_after_seconds
                    if isinstance(error, ProviderQuotaError)
                    else None
                )
                self.quota.record_failure(profile, detail, cooldown)
                if isinstance(error, ProviderConnectionError):
                    seconds = 300
                    self._provider_unavailable[profile.provider] = (
                        self._clock() + seconds,
                        f"network connection failed; retry after {seconds:g} seconds",
                    )
                self.active_state = (
                    f"{profile.key} failed; trying {next_routes}"
                    if next_routes
                    else f"{profile.key} failed; no remaining route"
                )
                self._record_event(
                    workload,
                    priority,
                    profile,
                    estimated,
                    self.last_decision,
                    "failed",
                    detail,
                )
                continue
            result.provider, result.model = profile.provider, profile.model
            result.fallback_used = index > 0
            if result.fallback_used:
                self.fallbacks += 1
                result.usage["fallback_reason"] = (
                    errors[-1] if errors else "policy route"
                )
            self.quota.record_success(profile, result.usage)
            self._record_event(
                workload, priority, profile, estimated, self.last_decision, "success"
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
        raise ProviderError(
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
        estimated = estimate_tokens(prompt)
        errors: list[str] = []
        for index, profile in enumerate(self._candidates(workload)):
            health = self._provider_unavailable.get(profile.provider)
            if health and self._clock() < health[0]:
                errors.append(f"{profile.key}: {health[1]}")
                continue
            self._provider_unavailable.pop(profile.provider, None)
            available, _pressure, reason = self.quota.available(
                profile, estimated, priority
            )
            if not available:
                errors.append(f"{profile.key}: {reason}")
                continue
            provider = self.providers.get(profile.provider)
            if provider is None:
                errors.append(f"{profile.key}: provider unavailable")
                continue
            self.last_decision = f"{profile.key}: {reason} for {workload.value}"
            self._record_event(
                workload, priority, profile, estimated, self.last_decision, "attempt"
            )
            self.quota.record_attempt(profile, estimated)
            self.requests += 1
            self._set_active(profile, "provider request in flight")
            try:
                answer = await provider.answer(prompt, profile.model)
            except Exception as error:
                detail = f"{type(error).__name__}: {error}"
                errors.append(f"{profile.key}: {detail}")
                cooldown = (
                    error.retry_after_seconds
                    if isinstance(error, ProviderQuotaError)
                    else None
                )
                self.quota.record_failure(profile, detail, cooldown)
                if isinstance(error, ProviderConnectionError):
                    self._provider_unavailable[profile.provider] = (
                        self._clock() + 300,
                        "network connection failed; retry after 300 seconds",
                    )
                self._record_event(
                    workload,
                    priority,
                    profile,
                    estimated,
                    self.last_decision,
                    "failed",
                    detail,
                )
                continue
            if not answer.strip():
                errors.append(f"{profile.key}: empty response")
                continue
            self.quota.record_success(profile, {})
            self._record_event(
                workload, priority, profile, estimated, self.last_decision, "success"
            )
            self.active_state, self.last_error = "response received", None
            if index:
                self.fallbacks += 1
                self.session_provider, self.session_model_key = (
                    profile.provider,
                    profile.key,
                )
            return answer.strip()
        self.errors += 1
        self.active_state = "all eligible routes unavailable"
        raise ProviderError("All AI routes unavailable — " + " | ".join(errors))

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
        analyze_model = getattr(provider, "analyze_model", None)
        if analyze_model is not None:
            return await analyze_model(batch, profile.model, profile.rpm)
        return await provider.analyze(batch)

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
