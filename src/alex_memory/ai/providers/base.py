from __future__ import annotations

from typing import Protocol

from ...models import AIAnalysisResult, AIBatch


class ProviderError(RuntimeError):
    """A provider request failed and the router may try another provider."""


class ProviderQuotaError(ProviderError):
    """A provider has rejected requests until its quota recovers."""

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeoutError(ProviderError):
    """A provider request exceeded the configured per-attempt deadline."""


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

    async def analyze(self, batch: AIBatch) -> AIAnalysisResult:
        """Return a locally-normalized structured analysis for one chat batch."""

    async def answer(self, prompt: str, model: str) -> str:
        """Return one bounded grounded answer for the router-selected model."""
