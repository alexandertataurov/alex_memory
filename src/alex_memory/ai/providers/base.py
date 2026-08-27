from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import json

from ...models import AIAnalysisResult, AIAnswerResult, AIBatch
from ..schema import AI_RESPONSE_SCHEMA, AI_SYSTEM_PROMPT


ANSWER_SYSTEM_PROMPT = (
    "You are Alex Memory's grounded question-answering assistant. "
    "Never invent evidence or citations."
)


def extraction_input_parts(batch: AIBatch) -> tuple[str, str, str]:
    """Return every extraction instruction sent to a provider, without logging it."""
    return (
        AI_SYSTEM_PROMPT,
        batch.prompt,
        "Return one valid JSON object only, matching this schema:\n"
        + json.dumps(AI_RESPONSE_SCHEMA, separators=(",", ":")),
    )


@dataclass(frozen=True, slots=True)
class ProviderAnalysisRequest:
    """The router-authorized model invocation for one bounded batch."""

    batch: AIBatch
    provider: str
    model: str
    requests_per_minute: float | None


class ProviderError(RuntimeError):
    """A provider request failed and the router may try another provider."""


class ProviderConfigurationError(ProviderError):
    """A local provider configuration cannot execute a request."""


class ProviderResponseError(ProviderError):
    """A reachable provider returned an invalid or unusable response."""


class ProviderRetryableError(ProviderError):
    """All attempted routes failed temporarily; durable work may be deferred."""


class ProviderQuotaError(ProviderError):
    """A provider has rejected requests until its quota recovers."""

    def __init__(
        self,
        message: str,
        retry_after_seconds: float | None = None,
        *,
        dimension: str = "unknown",
    ):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.dimension = dimension


class ProviderTimeoutError(ProviderError):
    """A provider request exceeded the configured per-attempt deadline."""

    def __init__(self, message: str, *, termination_confirmed: bool = True):
        super().__init__(message)
        self.termination_confirmed = termination_confirmed


class ProviderConnectionError(ProviderError):
    """A provider could not be reached; this is distinct from quota exhaustion."""


class ProviderTransientError(ProviderError):
    """A provider responded with a retryable server failure.

    The service is reachable, so this must not trigger the router's
    provider-wide transport-health cooldown.
    """


class AIProvider(Protocol):
    name: str
    model: str

    async def analyze(self, request: ProviderAnalysisRequest) -> AIAnalysisResult:
        """Execute exactly the router-authorized provider/model request."""

    async def answer(self, prompt: str, model: str) -> AIAnswerResult:
        """Return one bounded grounded answer for the router-selected model."""
