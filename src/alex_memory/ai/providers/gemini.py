from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ...config import Settings
from ...models import AIAnalysisResult, AIBatch
from ..schema import AI_RESPONSE_SCHEMA, AI_SYSTEM_PROMPT
from .base import (
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderTransientError,
)

genai: Any
types: Any
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.settings = settings
        self.model = settings.gemini_primary_model
        self._client = client
        self._clock = clock
        self._sleep = sleep
        self._next_request_at: dict[str, float] = {}
        self._rate_lock = asyncio.Lock()

    async def analyze(self, batch: AIBatch) -> AIAnalysisResult:
        return await self.analyze_model(
            batch, self.model, self.settings.gemini_requests_per_minute
        )

    async def analyze_model(
        self, batch: AIBatch, model: str, requests_per_minute: float | None
    ) -> AIAnalysisResult:
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is missing")
        if (genai is None or types is None) and self._client is None:
            raise ProviderError("Google GenAI SDK is not installed; run uv sync")

        last_error: Exception | None = None
        for attempt in range(self.settings.ai_max_retries):
            try:
                await self._wait_for_request_slot(model, requests_per_minute)
                response = await self._request_with_timeout(batch, model)
                parsed = getattr(response, "parsed", None)
                if parsed is None:
                    text = getattr(response, "text", None)
                    if not text:
                        raise ProviderError("Gemini returned an empty response")
                    parsed = json.loads(text)
                if hasattr(parsed, "model_dump"):
                    parsed = parsed.model_dump()
                result = parsed
                usage = _usage(getattr(response, "usage_metadata", None))
                return AIAnalysisResult(
                    provider=self.name,
                    model=model,
                    summary=result.get("summary", "")
                    if isinstance(result, dict)
                    else "",
                    items=result.get("items", []) if isinstance(result, dict) else [],
                    usage=usage,
                    raw_payload=result,
                )
            except Exception as error:
                last_error = error
                if _is_quota_error(error):
                    message, retry_after = _quota_failure_details(error)
                    raise ProviderQuotaError(
                        message, retry_after_seconds=retry_after
                    ) from error
                if _is_connection_error(error):
                    if attempt + 1 >= self.settings.ai_max_retries:
                        raise ProviderConnectionError(
                            "Gemini network connection failed; provider temporarily unavailable"
                        ) from error
                    await self._sleep(
                        min(60, self.settings.ai_retry_base_seconds * (2**attempt))
                    )
                    continue
                if _is_transient_server_error(error):
                    if attempt + 1 >= self.settings.ai_max_retries:
                        raise ProviderTransientError(
                            "Gemini server temporarily unavailable"
                        ) from error
                    await self._sleep(
                        min(60, self.settings.ai_retry_base_seconds * (2**attempt))
                    )
                    continue
                if attempt + 1 >= self.settings.ai_max_retries or not _is_retryable(
                    error
                ):
                    break
                await self._sleep(
                    min(60, self.settings.ai_retry_base_seconds * (2**attempt))
                )
        raise ProviderError(
            f"Gemini failed: {type(last_error).__name__}: {last_error}"
        ) from last_error

    async def answer(self, prompt: str, model: str) -> str:
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is missing")
        if (genai is None or types is None) and self._client is None:
            raise ProviderError("Google GenAI SDK is not installed")
        await self._wait_for_request_slot(model, None)
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._answer_request, prompt, model),
                timeout=self.settings.ai_request_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError(
                "Gemini request timed out after "
                f"{self.settings.ai_request_timeout_seconds} seconds"
            ) from error
        text = getattr(response, "text", None)
        if not text:
            raise ProviderError("Gemini returned an empty response")
        return str(text)

    async def _request_with_timeout(self, batch: AIBatch, model: str | None = None):
        """Bound one blocking SDK call so a history job cannot remain running."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._request, batch)
                if model is None
                else asyncio.to_thread(self._request, batch, model),
                timeout=self.settings.ai_request_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError(
                "Gemini request timed out after "
                f"{self.settings.ai_request_timeout_seconds} seconds"
            ) from error

    async def _wait_for_request_slot(
        self, model: str, requests_per_minute: float | None
    ) -> None:
        """Space all Gemini attempts so one router stays within the configured RPM."""
        # A provider can count both endpoints of a rolling 60-second window.
        # Dividing by RPM would schedule requests at 0s and 60s, which can be
        # observed as an extra request at the rolling-window endpoint. The
        # configured 14.5 RPM leaves a fractional-request safety margin, while
        # the subtraction still avoids counting both endpoints as a full slot.
        rpm = requests_per_minute or self.settings.gemini_requests_per_minute
        # Preserve the established 14.5 RPM safety margin for the primary model.
        if model == self.settings.gemini_primary_model:
            rpm = min(rpm, self.settings.gemini_requests_per_minute)
        interval = 60.0 / max(1, rpm - 1)
        async with self._rate_lock:
            now = self._clock()
            slot = max(now, self._next_request_at.get(model, 0.0))
            delay = slot - now
            if delay > 0:
                await self._sleep(delay)
            self._next_request_at[model] = slot + interval

    def _request(self, batch: AIBatch, model: str | None = None):
        client = self._client or genai.Client(api_key=self.settings.gemini_api_key)
        config_values: dict[str, Any] = {
            "system_instruction": AI_SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": gemini_schema(AI_RESPONSE_SCHEMA),
            "temperature": 0,
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "automatic_function_calling": (
                types.AutomaticFunctionCallingConfig(disable=True)
                if types is not None
                else {"disable": True}
            ),
        }
        config = (
            types.GenerateContentConfig(**config_values)
            if types is not None
            else config_values
        )
        return client.models.generate_content(
            model=model or self.model,
            contents=batch.prompt,
            config=config,
        )

    def _answer_request(self, prompt: str, model: str):
        client = self._client or genai.Client(api_key=self.settings.gemini_api_key)
        config_values: dict[str, Any] = {
            "system_instruction": (
                "You are Alex Memory's grounded question-answering assistant. "
                "Never invent evidence or citations."
            ),
            "temperature": 0,
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "automatic_function_calling": (
                types.AutomaticFunctionCallingConfig(disable=True)
                if types is not None
                else {"disable": True}
            ),
        }
        config = (
            types.GenerateContentConfig(**config_values)
            if types is not None
            else config_values
        )
        return client.models.generate_content(
            model=model, contents=prompt, config=config
        )


def gemini_schema(schema: object) -> object:
    """Adapt standard JSON Schema nullable unions to Gemini's Schema model.

    Gemini's Python SDK accepts an equivalent dict schema, but its `type`
    field is a single enum rather than JSON Schema's list of alternatives.
    """
    if isinstance(schema, list):
        return [gemini_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema

    converted = {
        key: gemini_schema(value)
        for key, value in schema.items()
        if key != "additionalProperties"
    }
    types_value = converted.get("type")
    if isinstance(types_value, list) and "null" in types_value:
        actual = [value for value in types_value if value != "null"]
        if len(actual) == 1:
            converted["type"] = actual[0]
            converted["nullable"] = True
    return converted


def _usage(metadata: object) -> dict[str, int | str]:
    if metadata is None:
        return {}
    result: dict[str, int | str] = {}
    for name in ("prompt_token_count", "candidates_token_count", "total_token_count"):
        value = getattr(metadata, name, None)
        if value is not None:
            result[name] = int(value)
    return result


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, ProviderTimeoutError):
        return False
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "429",
            "rate",
            "timeout",
            "connection",
            "temporar",
            "500",
            "502",
            "503",
            "504",
        )
    )


def _is_quota_error(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text and (
        "resource_exhausted" in text or "quota exceeded" in text or "quota" in text
    )


def _is_connection_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "connecterror",
            "connection error",
            "connection failed",
            "failed to connect",
            "failed to establish connection",
            "network error",
            "network is unreachable",
            "no route to host",
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "dns",
            "connection reset",
            "connection aborted",
            "server disconnected",
            "broken pipe",
            "socket",
            "unreachable",
        )
    )


def _is_transient_server_error(error: Exception) -> bool:
    """Classify a reachable HTTP server failure without string overreach."""
    status = getattr(error, "status_code", None)
    if status in {500, 502, 503, 504}:
        return True
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "500 internal server error",
            "502 bad gateway",
            "503 service unavailable",
            "504 gateway timeout",
        )
    )


def _quota_failure_details(error: Exception) -> tuple[str, float | None]:
    """Keep provider quota feedback useful without storing the raw API error."""
    text = str(error)
    quota = re.search(r"quotaId': '([^']+)", text)
    retry = re.search(r"(?:retry in |retryDelay': ')([0-9.]+)s", text, re.I)
    retry_after = float(retry.group(1)) if retry else None
    detail = quota.group(1) if quota else "Gemini provider quota"
    retry_text = f"; retry after {retry_after:g}s" if retry_after else ""
    return (
        f"Gemini quota limit reached ({detail}{retry_text}).",
        retry_after,
    )
