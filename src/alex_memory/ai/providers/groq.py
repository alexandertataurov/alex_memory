from __future__ import annotations

import asyncio
import json
import re
from contextlib import suppress
from typing import Any

from ...config import Settings
from ...models import AIAnalysisResult, AIBatch
from ..extraction_contract import ExtractionContractError, validate_response
from ..schema import AI_RESPONSE_SCHEMA, AI_SYSTEM_PROMPT
from .base import ProviderError, ProviderQuotaError, ProviderTimeoutError

try:
    from groq import AsyncGroq as AsyncGroqClient
except ImportError:
    AsyncGroqClient = None  # type: ignore[assignment,misc]


class GroqProvider:
    name = "groq"

    def __init__(self, settings: Settings, client: Any | None = None):
        self.settings = settings
        self.model = settings.groq_model
        self._client = client

    async def analyze(self, batch: AIBatch) -> AIAnalysisResult:
        if not self.settings.groq_api_key:
            raise ProviderError("GROQ_API_KEY is missing")
        if self._client is not None:
            client = self._client
        else:
            if AsyncGroqClient is None:
                raise ProviderError("Groq SDK is not installed; run uv sync")
            client = AsyncGroqClient(api_key=self.settings.groq_api_key)
        try:
            result = await self._with_retries(client, batch)
            return AIAnalysisResult(
                provider=self.name,
                model=self.model,
                summary=result.get("summary", "") if isinstance(result, dict) else "",
                items=result.get("items", []) if isinstance(result, dict) else [],
                raw_payload=result,
            )
        finally:
            if self._client is None:
                await _close(client)

    async def answer(self, prompt: str, model: str) -> str:
        if not self.settings.groq_api_key:
            raise ProviderError("GROQ_API_KEY is missing")
        client = self._client or (
            AsyncGroqClient(api_key=self.settings.groq_api_key)
            if AsyncGroqClient is not None
            else None
        )
        if client is None:
            raise ProviderError("Groq SDK is not installed")
        try:
            completion = await self._request_with_timeout(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are Alex Memory's grounded question-answering "
                                "assistant. Never invent evidence or citations."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_completion_tokens=self.settings.ai_max_output_tokens,
                    stream=False,
                )
            )
            content = completion.choices[0].message.content
            if not content:
                raise ProviderError("Groq returned an empty response")
            return str(content)
        finally:
            if self._client is None:
                await _close(client)

    async def _with_retries(self, client: Any, batch: AIBatch) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.settings.ai_max_retries):
            try:
                # gpt-oss-20b rejects the strict-schema preflight for some
                # otherwise valid extractions. Start with its compatible JSON
                # object mode so a fallback is one bounded request, not two.
                raw = await self._request_with_timeout(
                    _request_json_object(
                        client,
                        batch,
                        self.model,
                        self.settings.ai_max_output_tokens,
                    )
                )
                # Semantic validation is deliberately deferred until the
                # repository records the exact provider response as a durable
                # diagnostic. A malformed response is not a transport retry.
                return raw
            except Exception as error:
                last_error = error
                if _is_quota_error(error):
                    message, retry_after = _quota_failure_details(error)
                    raise ProviderQuotaError(
                        message,
                        retry_after_seconds=retry_after,
                    ) from error
                if attempt + 1 >= self.settings.ai_max_retries or not _is_retryable(
                    error
                ):
                    break
                await asyncio.sleep(_retry_after_seconds(error, attempt, self.settings))
        raise ProviderError(
            f"Groq failed: {type(last_error).__name__}: {last_error}"
        ) from last_error

    async def _request_with_timeout(self, request):
        task = asyncio.create_task(request)
        done, _ = await asyncio.wait(
            {task}, timeout=self.settings.ai_request_timeout_seconds
        )
        if task in done:
            return task.result()
        task.cancel()
        task.add_done_callback(_consume_background_result)
        raise ProviderTimeoutError(
            "Groq request timed out after "
            f"{self.settings.ai_request_timeout_seconds} seconds"
        )


async def _request_json_object(
    client: Any, batch: AIBatch, model: str, max_output_tokens: int
) -> dict:
    fallback = (
        batch.prompt
        + "\n\nReturn one valid JSON object only, matching this schema:\n"
        + json.dumps(AI_RESPONSE_SCHEMA, separators=(",", ":"))
    )
    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": fallback},
        ],
        response_format={"type": "json_object"},
        reasoning_effort="low",
        temperature=0,
        max_completion_tokens=max_output_tokens,
        stream=False,
    )
    return _parse_completion(completion)


def _parse_completion(completion: Any) -> dict:
    content = completion.choices[0].message.content
    if not content:
        raise ProviderError("Groq returned an empty response")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ProviderError("Groq result is not a JSON object")
    return parsed


def normalize_result(result: dict) -> dict:
    """Keep the legacy name while refusing semantic repair of model output."""
    try:
        return validate_response(result)
    except ExtractionContractError as error:
        raise ProviderError(f"invalid extraction response: {error}") from error


def _is_quota_error(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    text = str(error).lower()
    return status == 429 or any(
        token in text
        for token in (
            "rate_limit_exceeded",
            "rate limit",
            "tokens per day",
            "tpd",
            "quota exceeded",
            "quota reached",
        )
    )


def _quota_failure_details(error: Exception) -> tuple[str, float | None]:
    headers = getattr(getattr(error, "response", None), "headers", None)
    retry_after = None
    if headers and headers.get("retry-after"):
        try:
            retry_after = max(1.0, float(headers["retry-after"]))
        except (TypeError, ValueError):
            retry_after = None

    message = str(error)
    if retry_after is None:
        match = re.search(
            r"try again in\s*(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?",
            message,
            flags=re.IGNORECASE,
        )
        if match:
            minutes = float(match.group(1) or 0)
            seconds = float(match.group(2) or 0)
            retry_after = max(1.0, minutes * 60 + seconds)

    if retry_after is None:
        retry_after = 60.0
    if "tokens per day" in message.lower() or "tpd" in message.lower():
        sanitized = "Groq daily token quota reached; please try again later."
    else:
        sanitized = "Groq rate limit reached; please try again later."
    return sanitized, retry_after


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, ProviderTimeoutError):
        return False
    status = getattr(error, "status_code", None)
    text = str(error).lower()
    return status in {408, 409, 429, 500, 502, 503, 504} or any(
        token in text
        for token in ("rate limit", "timeout", "connection", "network", "temporar")
    )


def _retry_after_seconds(error: Exception, attempt: int, settings: Settings) -> float:
    headers = getattr(getattr(error, "response", None), "headers", None)
    if headers and headers.get("retry-after"):
        try:
            return max(1.0, float(headers["retry-after"]))
        except (TypeError, ValueError):
            pass
    return min(60.0, settings.ai_retry_base_seconds * (2**attempt))


async def _close(client: Any) -> None:
    try:
        task = asyncio.create_task(client.close())
        done, _ = await asyncio.wait({task}, timeout=5)
        if task not in done:
            task.cancel()
            task.add_done_callback(_consume_background_result)
            return
        task.result()
    except Exception:
        pass


def _consume_background_result(task: asyncio.Task) -> None:
    """Avoid unhandled-task warnings after a non-blocking provider timeout."""
    with suppress(asyncio.CancelledError, Exception):
        task.result()
