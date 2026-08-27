from __future__ import annotations

import asyncio
import inspect
import json
import re
from typing import Any

from ...config import Settings
from ...models import AIAnalysisResult, AIAnswerResult, AIBatch
from ..schema import AI_RESPONSE_SCHEMA, AI_SYSTEM_PROMPT
from .base import (
    ProviderConnectionError,
    ProviderAnalysisRequest,
    ProviderError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderTransientError,
)
from .base import ANSWER_SYSTEM_PROMPT

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
    ):
        self.settings = settings
        self.model = settings.gemini_primary_model
        self._client = client
        self._owned_client: Any | None = None

    async def analyze(
        self, request: ProviderAnalysisRequest | AIBatch
    ) -> AIAnalysisResult:
        if isinstance(request, AIBatch):
            request = ProviderAnalysisRequest(
                batch=request,
                provider=self.name,
                model=self.model,
                requests_per_minute=self.settings.gemini_requests_per_minute,
            )
        if request.provider != self.name:
            raise ProviderError(f"Gemini cannot execute provider {request.provider!r}")
        batch, model = request.batch, request.model
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is missing")
        if (genai is None or types is None) and self._client is None:
            raise ProviderError("Google GenAI SDK is not installed; run uv sync")

        try:
            response = await self._request_with_timeout(batch, model)
        except Exception as error:
            raise _typed_error(error) from error
        parsed = getattr(response, "parsed", None)
        if parsed is None:
            text = getattr(response, "text", None)
            if not text:
                raise ProviderError("Gemini returned an empty response")
            parsed = json.loads(text)
        if hasattr(parsed, "model_dump"):
            parsed = parsed.model_dump()
        result = parsed
        return AIAnalysisResult(
            provider=self.name,
            model=model,
            summary=result.get("summary", "") if isinstance(result, dict) else "",
            items=result.get("items", []) if isinstance(result, dict) else [],
            usage=_usage(getattr(response, "usage_metadata", None)),
            raw_payload=result,
        )

    async def answer(self, prompt: str, model: str) -> AIAnswerResult:
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is missing")
        if (genai is None or types is None) and self._client is None:
            raise ProviderError("Google GenAI SDK is not installed")
        try:
            response = await asyncio.wait_for(
                self._answer_request(prompt, model),
                timeout=self.settings.ai_request_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError(
                "Gemini request timed out after "
                f"{self.settings.ai_request_timeout_seconds} seconds"
            ) from error
        except Exception as error:
            raise _typed_error(error) from error
        text = getattr(response, "text", None)
        if not text:
            raise ProviderError("Gemini returned an empty response")
        return AIAnswerResult(
            self.name,
            model,
            str(text),
            _usage(getattr(response, "usage_metadata", None)),
        )

    async def _request_with_timeout(self, batch: AIBatch, model: str | None = None):
        """Bound a cancellable SDK request so fallback never overlaps it."""
        try:
            return await asyncio.wait_for(
                self._request(batch, model),
                timeout=self.settings.ai_request_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError(
                "Gemini request timed out after "
                f"{self.settings.ai_request_timeout_seconds} seconds"
            ) from error

    async def close(self) -> None:
        """Release the async transport owned by this provider, if any."""
        if self._owned_client is None:
            return
        await self._owned_client.aio.aclose()
        self._owned_client = None

    def _client_for_request(self) -> Any:
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            self._owned_client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._owned_client

    async def _request(self, batch: AIBatch, model: str | None = None):
        client = self._client_for_request()
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
        result = getattr(client, "aio", client).models.generate_content(
            model=model or self.model,
            contents=batch.prompt,
            config=config,
        )
        return await result if inspect.isawaitable(result) else result

    async def _answer_request(self, prompt: str, model: str):
        client = self._client_for_request()
        config_values: dict[str, Any] = {
            "system_instruction": ANSWER_SYSTEM_PROMPT,
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
        result = getattr(client, "aio", client).models.generate_content(
            model=model, contents=prompt, config=config
        )
        return await result if inspect.isawaitable(result) else result


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


def _typed_error(error: Exception) -> ProviderError:
    if isinstance(error, ProviderError):
        return error
    if _is_quota_error(error):
        message, retry_after = _quota_failure_details(error)
        return ProviderQuotaError(message, retry_after_seconds=retry_after)
    if _is_connection_error(error):
        return ProviderConnectionError(
            "Gemini network connection failed; provider temporarily unavailable"
        )
    if _is_transient_server_error(error):
        return ProviderTransientError("Gemini server temporarily unavailable")
    return ProviderError(f"Gemini failed: {type(error).__name__}: {error}")


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
            "connection timeout",
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
