from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from alex_memory.ai.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderTransientError,
)
from alex_memory.ai.providers.gemini import (
    GeminiProvider,
    _is_connection_error,
    _is_transient_server_error,
    _quota_failure_details,
    gemini_schema,
)
from alex_memory.ai.providers.groq import GroqProvider
from alex_memory.ai.repository import (
    claim_ai_jobs,
    ensure_history_jobs,
    fetch_unanalyzed_messages,
    fetch_unclassified_messages,
    release_ai_job,
    save_ai_failure,
    save_ai_success,
)
from alex_memory.ai.router import AIRouter
from alex_memory.ai.routing import (
    AIWorkload,
    ModelRegistry,
    QuotaTracker,
    RequestPriority,
)
from alex_memory.classification import (
    CLASSIFICATION_VERSION,
    classify_message,
    save_classification,
)
from alex_memory.config import Settings
from alex_memory.database import connect
from alex_memory.intelligence import set_chat_policy
from alex_memory.models import AIAnalysisResult, AIBatch, AIMessage


def settings_for(root: Path, **overrides) -> Settings:
    values = dict(
        root=root,
        env_path=root / ".env",
        data_dir=root / "data",
        db_path=root / "data" / "test.sqlite",
        session_path=root / "session",
        telegram_api_id=1,
        telegram_api_hash="test",
        group_full_threshold=1000,
        group_recent_limit=1000,
        write_queue_size=1000,
        commit_every=50,
        groq_api_key="groq-key",
        groq_model="groq-test",
        gemini_api_key="gemini-key",
        gemini_model="gemini-test",
        ai_primary_provider="gemini",
        ai_fallback_provider="groq",
        ai_daily_max_messages=100,
        ai_batch_messages=30,
        ai_batch_chars=9000,
        history_internal_concurrency=2,
        history_internal_batch_messages=60,
        history_internal_batch_chars=12000,
        ai_context_messages=2,
        ai_max_message_chars=3000,
        ai_max_retries=2,
        ai_retry_base_seconds=1,
        ai_report_batches=20,
        ai_include_groups=False,
        ai_routing_mode="legacy",
    )
    values.update(overrides)
    return Settings(**values)


def batch() -> AIBatch:
    message = AIMessage(
        1,
        1,
        2,
        "2026-08-22T10:00:00+00:00",
        "Please send the invoice.",
        False,
        "Alice",
        "user",
    )
    return AIBatch(1, "Alice", [message], "prompt")


def payload() -> dict:
    return {"summary": "Invoice requested.", "items": []}


class FakeGeminiModels:
    def __init__(self, responses: list[object]):
        self.responses = responses
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeGeminiClient:
    def __init__(self, responses: list[object]):
        self.models = FakeGeminiModels(responses)


class FakeResponse:
    def __init__(self, result: dict):
        self.parsed = result
        self.usage_metadata = None


class FakeProvider:
    def __init__(self, name: str, result: AIAnalysisResult | Exception):
        self.name = name
        self.model = f"{name}-model"
        self.result = result
        self.calls = 0

    async def analyze(self, value: AIBatch) -> AIAnalysisResult:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class SequenceProvider(FakeProvider):
    def __init__(self, name: str, results: list[AIAnalysisResult | Exception]):
        super().__init__(name, results[0])
        self.results = results

    async def analyze(self, value: AIBatch) -> AIAnalysisResult:
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeCompletions:
    def __init__(self):
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["response_format"]["type"] == "json_schema":
            error = RuntimeError("failed_generation")
            error.status_code = 400
            raise error
        content = json.dumps(payload())
        return type(
            "Completion",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Message", (), {"content": content})()},
                    )()
                ]
            },
        )()


class RouterAndJobTests(unittest.IsolatedAsyncioTestCase):
    def test_quota_cooldown_is_reloaded_after_tracker_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_routing_mode="quota_aware")
            conn = connect(settings)
            profile = next(
                profile
                for profile in ModelRegistry(settings).profiles
                if profile.key == "gemini_35"
            )
            QuotaTracker(conn).record_failure(profile, "quota", 60)

            restored = QuotaTracker(conn).cooldown(profile)

            self.assertIsNotNone(restored)
            self.assertEqual("quota", restored[1])

    async def test_quota_aware_simple_work_prefers_primary_gemini_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_routing_mode="quota_aware")
            gemini = FakeProvider(
                "gemini", AIAnalysisResult("gemini", "ignored", "Gemini result", [])
            )
            router = AIRouter(
                settings,
                {
                    "gemini": gemini,
                    "groq": FakeProvider("groq", ProviderError("unused")),
                },
            )

            result = await router.analyze(
                batch(),
                workload=AIWorkload.SIMPLE_EXTRACTION,
                priority=RequestPriority.BACKGROUND,
            )

            self.assertEqual(settings.gemini_primary_model, result.model)
            self.assertEqual(1, gemini.calls)

    async def test_quota_aware_candidate_policy_differs_for_short_and_context_work(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_routing_mode="quota_aware")
            router = AIRouter(settings)
            self.assertEqual(
                [
                    "gemini_35",
                    "gemini_31",
                    "gemma",
                    "groq",
                ],
                [
                    item.key
                    for item in router.registry.candidates(AIWorkload.SIMPLE_EXTRACTION)
                ],
            )
            self.assertEqual(
                [
                    "gemini_35",
                    "gemini_31",
                    "groq",
                ],
                [
                    item.key
                    for item in router.registry.candidates(
                        AIWorkload.CONTEXT_EXTRACTION
                    )
                ],
            )

    def test_structured_output_requirement_filters_ineligible_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = ModelRegistry(
                settings_for(Path(directory), ai_routing_mode="quota_aware")
            )
            registry._profiles["gemma"] = replace(
                registry.profile("gemma"), structured_output=False
            )

            self.assertEqual(
                ["gemini_35", "gemini_31", "groq"],
                [
                    profile.key
                    for profile in registry.candidates(
                        AIWorkload.SIMPLE_EXTRACTION,
                        requires_structured_output=True,
                    )
                ],
            )

    async def test_quota_aware_skips_gemma_when_prompt_exceeds_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(
                Path(directory),
                ai_routing_mode="quota_aware",
                gemma_short_max_input_tokens=1,
            )
            gemini = FakeProvider(
                "gemini", AIAnalysisResult("gemini", "ignored", "Primary", [])
            )
            router = AIRouter(
                settings,
                {
                    "gemini": gemini,
                    "groq": FakeProvider("groq", ProviderError("unused")),
                },
            )

            result = await router.analyze(
                batch(), workload=AIWorkload.SIMPLE_EXTRACTION
            )

            self.assertEqual(settings.gemini_primary_model, result.model)

    async def test_router_skips_other_gemini_models_after_connection_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_routing_mode="quota_aware")

            class ModelAwareGemini:
                def __init__(self) -> None:
                    self.calls: list[str] = []

                async def analyze_model(
                    self, batch: AIBatch, model: str, requests_per_minute: float | None
                ) -> AIAnalysisResult:
                    self.calls.append(model)
                    if model == settings.gemini_primary_model:
                        raise ProviderConnectionError(
                            "temporary network issue for gemini-3.5-flash-lite"
                        )
                    return AIAnalysisResult(
                        "gemini",
                        model,
                        "Recovered via secondary gemini route",
                        [],
                    )

            provider = ModelAwareGemini()
            router = AIRouter(
                settings,
                {
                    "gemini": provider,
                    "groq": FakeProvider(
                        "groq", AIAnalysisResult("groq", "ignored", "Fallback", [])
                    ),
                },
            )

            result = await router.analyze(batch())

            self.assertEqual("groq", result.provider)
            self.assertEqual([settings.gemini_primary_model], provider.calls)

    async def test_network_failure_skips_other_gemini_models_and_uses_groq(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_routing_mode="quota_aware")
            gemini = FakeProvider("gemini", ProviderConnectionError("DNS unavailable"))
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "ignored", "Fallback", [])
            )
            router = AIRouter(settings, {"gemini": gemini, "groq": groq})

            result = await router.analyze(batch())

            self.assertEqual("groq", result.provider)
            self.assertEqual(1, gemini.calls)
            self.assertEqual(1, groq.calls)
            self.assertEqual("groq", router.session_provider)

    async def test_server_failure_does_not_set_provider_health_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_routing_mode="quota_aware")
            gemini = FakeProvider(
                "gemini",
                ProviderTransientError("Gemini server temporarily unavailable"),
            )
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "ignored", "Fallback", [])
            )
            router = AIRouter(settings, {"gemini": gemini, "groq": groq})

            result = await router.analyze(batch())

            self.assertEqual("groq", result.provider)
            self.assertNotIn("gemini", router._provider_unavailable)
            self.assertEqual(2, gemini.calls)

    async def test_quota_failure_skips_secondary_gemini_and_uses_groq(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_routing_mode="quota_aware")
            gemini = FakeProvider(
                "gemini", ProviderQuotaError("quota reached", retry_after_seconds=20)
            )
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "ignored", "Fallback", [])
            )
            router = AIRouter(settings, {"gemini": gemini, "groq": groq})

            result = await router.analyze(batch())

            self.assertEqual("groq", result.provider)
            self.assertEqual(2, gemini.calls)
            self.assertEqual(1, groq.calls)

    async def test_groq_token_quota_raises_provider_quota_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))

            class FakeGroqChatCompletions:
                async def create(self, **kwargs):
                    raise RuntimeError(
                        "Rate limit reached for model openai/gpt-oss-20b; "
                        "Used 199994, Requested 6135. Please try again in 44m7.728s."
                    )

            class FakeGroqClient:
                def __init__(self):
                    self.chat = type(
                        "FakeChat",
                        (),
                        {"completions": FakeGroqChatCompletions()},
                    )()

            with self.assertRaises(ProviderQuotaError):
                await GroqProvider(settings, FakeGroqClient()).analyze(batch())

    async def test_gemini_connection_error_strings_are_detected(self) -> None:
        self.assertTrue(
            _is_connection_error(
                RuntimeError(
                    "Connection failed: temporary network issue for gemini-3.1-flash-lite"
                )
            )
        )
        self.assertTrue(
            _is_connection_error(
                RuntimeError(
                    "Service unavailable; temporary failure in name resolution"
                )
            )
        )

    async def test_gemini_server_unavailability_is_not_a_connection_failure(
        self,
    ) -> None:
        error = RuntimeError("503 Service unavailable")
        error.status_code = 503  # type: ignore[attr-defined]

        self.assertFalse(_is_connection_error(error))
        self.assertTrue(_is_transient_server_error(error))

    async def test_gemini_terminal_503_is_typed_without_provider_cooldown(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_max_retries=1)
            error = RuntimeError("503 Service unavailable")
            error.status_code = 503  # type: ignore[attr-defined]
            provider = GeminiProvider(settings, FakeGeminiClient([error]))

            with self.assertRaises(ProviderTransientError):
                await provider.analyze(batch())

    async def test_gemini_schema_converts_nullable_json_schema_fields(self) -> None:
        converted = gemini_schema(
            {"type": ["string", "null"], "additionalProperties": False}
        )
        self.assertEqual(converted, {"type": "string", "nullable": True})

    async def test_gemini_success_and_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            client = FakeGeminiClient(
                [RuntimeError("connection timeout"), FakeResponse(payload())]
            )
            result = await GeminiProvider(settings, client).analyze(batch())
            self.assertEqual(result.provider, "gemini")
            self.assertEqual(result.summary, "Invoice requested.")
            self.assertEqual(client.models.calls, 2)

    async def test_gemini_transient_connection_error_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            client = FakeGeminiClient(
                [
                    RuntimeError(
                        "Connection failed: temporary network issue for gemini-3.1-flash-lite"
                    ),
                    FakeResponse(payload()),
                ]
            )
            result = await GeminiProvider(settings, client).analyze(batch())
            self.assertEqual(result.provider, "gemini")
            self.assertEqual(result.summary, "Invoice requested.")
            self.assertEqual(client.models.calls, 2)

    async def test_gemini_paces_every_request_at_configured_rpm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), gemini_requests_per_minute=14.5)
            client = FakeGeminiClient(
                [FakeResponse(payload()), FakeResponse(payload())]
            )
            now = [0.0]
            delays: list[float] = []

            async def sleep(seconds: float) -> None:
                delays.append(seconds)
                now[0] += seconds

            provider = GeminiProvider(
                settings,
                client,
                clock=lambda: now[0],
                sleep=sleep,
            )
            await provider.analyze(batch())
            await provider.analyze(batch())

            self.assertEqual([60 / 13.5], delays)
            self.assertEqual(2, client.models.calls)

    async def test_gemini_retry_reserves_a_new_rate_limited_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), gemini_requests_per_minute=14.5)
            client = FakeGeminiClient(
                [RuntimeError("connection timeout"), FakeResponse(payload())]
            )
            now = [0.0]
            delays: list[float] = []

            async def sleep(seconds: float) -> None:
                delays.append(seconds)
                now[0] += seconds

            provider = GeminiProvider(
                settings,
                client,
                clock=lambda: now[0],
                sleep=sleep,
            )
            result = await provider.analyze(batch())

            self.assertEqual("gemini", result.provider)
            self.assertEqual([1, 60 / 13.5 - 1], delays)
            self.assertEqual(2, client.models.calls)

    async def test_gemini_quota_error_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            client = FakeGeminiClient(
                [RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")]
            )

            with self.assertRaises(ProviderQuotaError):
                await GeminiProvider(settings, client).analyze(batch())

            self.assertEqual(1, client.models.calls)

    async def test_gemini_quota_error_keeps_retry_delay_without_raw_error(self) -> None:
        error = RuntimeError(
            "429 RESOURCE_EXHAUSTED: {'quotaId': "
            "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', "
            "'retryDelay': '55s'}"
        )

        message, retry_after = _quota_failure_details(error)

        self.assertEqual(55.0, retry_after)
        self.assertIn("GenerateRequestsPerDayPerProjectPerModel-FreeTier", message)
        self.assertNotIn("RESOURCE_EXHAUSTED", message)

    async def test_gemini_request_timeout_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_request_timeout_seconds=0.001)
            provider = GeminiProvider(settings, FakeGeminiClient([]))
            provider._request = lambda _batch: time.sleep(0.05)  # type: ignore[method-assign]

            with self.assertRaisesRegex(ProviderTimeoutError, "timed out after"):
                await provider._request_with_timeout(batch())

    async def test_router_uses_groq_after_gemini_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            gemini = FakeProvider("gemini", ProviderError("offline"))
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "groq-test", "Fallback summary", [])
            )
            router = AIRouter(settings, {"gemini": gemini, "groq": groq})
            result = await router.analyze(batch())
            self.assertTrue(result.fallback_used)
            self.assertEqual(result.provider, "groq")
            self.assertEqual(router.fallbacks, 1)

    async def test_router_skips_exhausted_gemini_after_first_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            gemini = FakeProvider(
                "gemini", ProviderQuotaError("Gemini quota is exhausted")
            )
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "groq-test", "Fallback summary", [])
            )
            router = AIRouter(settings, {"gemini": gemini, "groq": groq})

            first = await router.analyze(batch())
            first_used_fallback = first.fallback_used
            second = await router.analyze(batch())

            self.assertTrue(first_used_fallback)
            self.assertFalse(second.fallback_used)
            self.assertEqual(1, gemini.calls)
            self.assertEqual(2, groq.calls)
            self.assertEqual(1, router.fallbacks)

    async def test_router_retries_gemini_after_quota_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            gemini = FakeProvider(
                "gemini", ProviderQuotaError("Gemini quota is exhausted")
            )
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "groq-test", "Fallback summary", [])
            )
            router = AIRouter(settings, {"gemini": gemini, "groq": groq})

            await router.analyze(batch())
            gemini.result = AIAnalysisResult("gemini", "gemini-test", "Recovered", [])
            router.session_provider = None
            router._unavailable["gemini"] = (0.0, "quota window elapsed")
            result = await router.analyze(batch())

            self.assertEqual("gemini", result.provider)
            self.assertEqual(2, gemini.calls)
            self.assertEqual(1, groq.calls)

    async def test_router_honors_short_gemini_retry_delay_before_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            gemini = SequenceProvider(
                "gemini",
                [
                    ProviderQuotaError("short cooldown", retry_after_seconds=5),
                    AIAnalysisResult("gemini", "gemini-test", "Recovered", []),
                ],
            )
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "groq-test", "Fallback", [])
            )
            delays: list[float] = []

            async def sleep(seconds: float) -> None:
                delays.append(seconds)

            router = AIRouter(
                settings,
                {"gemini": gemini, "groq": groq},
                clock=lambda: 0.0,
                sleep=sleep,
            )
            result = await router.analyze(batch())

            self.assertEqual("gemini", result.provider)
            self.assertFalse(result.fallback_used)
            self.assertEqual([5], delays)
            self.assertEqual(2, gemini.calls)
            self.assertEqual(0, groq.calls)

    async def test_router_keeps_a_successful_fallback_for_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            gemini = FakeProvider("gemini", ProviderError("offline"))
            groq = FakeProvider(
                "groq", AIAnalysisResult("groq", "groq-test", "Fallback", [])
            )
            router = AIRouter(settings, {"gemini": gemini, "groq": groq})

            first = await router.analyze(batch())
            first_used_fallback = first.fallback_used
            second = await router.analyze(batch())

            self.assertTrue(first_used_fallback)
            self.assertFalse(second.fallback_used)
            self.assertEqual("groq", router.session_provider)
            self.assertEqual(1, gemini.calls)
            self.assertEqual(2, groq.calls)

    async def test_groq_uses_the_configured_output_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_max_output_tokens=800)
            completions = FakeCompletions()
            client = type(
                "Client", (), {"chat": type("Chat", (), {"completions": completions})()}
            )()

            await GroqProvider(settings, client).analyze(batch())

            self.assertEqual(800, completions.calls[0]["max_completion_tokens"])

    async def test_groq_uses_json_object_without_a_strict_schema_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            completions = FakeCompletions()
            client = type(
                "Client", (), {"chat": type("Chat", (), {"completions": completions})()}
            )()
            result = await GroqProvider(settings, client).analyze(batch())
            self.assertEqual(result.summary, "Invoice requested.")
            self.assertEqual(
                [call["response_format"]["type"] for call in completions.calls],
                ["json_object"],
            )

    async def test_groq_json_object_result_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))

            class ValidationCompletions(FakeCompletions):
                async def create(self, **kwargs):
                    self.calls.append(kwargs)
                    content = json.dumps(payload())
                    return type(
                        "Completion",
                        (),
                        {
                            "choices": [
                                type(
                                    "Choice",
                                    (),
                                    {
                                        "message": type(
                                            "Message", (), {"content": content}
                                        )()
                                    },
                                )()
                            ]
                        },
                    )()

            completions = ValidationCompletions()
            client = type(
                "Client", (), {"chat": type("Chat", (), {"completions": completions})()}
            )()
            result = await GroqProvider(settings, client).analyze(batch())

            self.assertEqual("Invoice requested.", result.summary)
            self.assertEqual(
                [call["response_format"]["type"] for call in completions.calls],
                ["json_object"],
            )

    async def test_groq_timeout_does_not_wait_for_sdk_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory), ai_request_timeout_seconds=0.001)
            blocked = asyncio.Event()

            class HangingCompletions:
                async def create(self, **_kwargs):
                    await blocked.wait()

            client = type(
                "Client",
                (),
                {"chat": type("Chat", (), {"completions": HangingCompletions()})()},
            )()

            with self.assertRaisesRegex(ProviderError, "timed out after"):
                await asyncio.wait_for(
                    GroqProvider(settings, client).analyze(batch()), 1
                )

    async def test_both_provider_failures_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            router = AIRouter(
                settings,
                {
                    "gemini": FakeProvider("gemini", ProviderError("offline")),
                    "groq": FakeProvider("groq", ProviderError("offline")),
                },
            )
            with self.assertRaises(ProviderError):
                await router.analyze(batch())


class JobPersistenceTests(unittest.TestCase):
    def test_classify_only_policy_never_creates_semantic_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Alice','user')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id,message_id,text) VALUES (1,1,'Please send it')"
            )
            set_chat_policy(conn, 1, "classify_only")
            message = fetch_unclassified_messages(
                conn, 10, settings, CLASSIFICATION_VERSION
            )[0]
            save_classification(conn, message, classify_message(conn, message))

            self.assertEqual([], fetch_unanalyzed_messages(conn, 10, settings))
            self.assertEqual(0, ensure_history_jobs(conn, settings))
            conn.close()

    def test_news_only_policy_only_queues_external_news(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Alice','user')"
            )
            conn.executemany(
                "INSERT INTO messages(chat_id,message_id,text,is_forwarded) VALUES (1,?,?,?)",
                [(1, "Bank announces a regulation", 1), (2, "Please send it", 0)],
            )
            set_chat_policy(conn, 1, "news_only")
            for message in fetch_unclassified_messages(
                conn, 10, settings, CLASSIFICATION_VERSION
            ):
                save_classification(conn, message, classify_message(conn, message))

            queued = fetch_unanalyzed_messages(conn, 10, settings)
            self.assertEqual([1], [message.message_id for message in queued])
            conn.close()

    def test_history_job_survives_restart_and_marks_exact_messages_on_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats (chat_id, title, chat_type) VALUES (1, 'Alice', 'user')"
            )
            conn.executemany(
                "INSERT INTO messages (chat_id, message_id, date, text) VALUES (1, ?, ?, ?)",
                [
                    (1, "2026-08-20T10:00:00+00:00", "One"),
                    (2, "2026-08-20T10:01:00+00:00", "Two"),
                ],
            )
            conn.commit()
            self.assertEqual(ensure_history_jobs(conn, settings), 1)
            claimed = claim_ai_jobs(conn, "history", 1, settings)
            self.assertEqual(len(claimed), 1)
            job_id, work = claimed[0]
            conn.close()

            conn = connect(settings)
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM ai_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()[0],
                "pending",
            )
            claimed = claim_ai_jobs(conn, "history", 1, settings)
            job_id, work = claimed[0]
            result = AIAnalysisResult("gemini", "gemini-test", "Two messages.", [])
            save_ai_success(conn, work, result, settings, lane="history", job_id=job_id)
            states = conn.execute(
                "SELECT message_id FROM ai_message_state ORDER BY message_id"
            ).fetchall()
            self.assertEqual(states, [(1,), (2,)])
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM ai_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()[0],
                "done",
            )
            conn.close()

    def test_claim_supersedes_exact_job_when_a_selected_message_is_deleted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Alice','user')"
            )
            conn.executemany(
                "INSERT INTO messages(chat_id,message_id,text) VALUES (1,?,?)",
                [(3, "First"), (9, "Second")],
            )
            conn.commit()

            self.assertEqual(1, ensure_history_jobs(conn, settings))
            job_id = conn.execute("SELECT job_id FROM ai_jobs").fetchone()[0]
            self.assertEqual(
                [(3,), (9,)],
                conn.execute(
                    "SELECT message_id FROM ai_job_messages WHERE job_id=? ORDER BY ordinal",
                    (job_id,),
                ).fetchall(),
            )
            conn.execute(
                "UPDATE messages SET is_deleted=1 WHERE chat_id=1 AND message_id=9"
            )
            conn.commit()

            self.assertEqual([], claim_ai_jobs(conn, "history", 1, settings))
            self.assertEqual(
                "superseded",
                conn.execute(
                    "SELECT status FROM ai_jobs WHERE job_id=?", (job_id,)
                ).fetchone()[0],
            )
            self.assertEqual(
                0, conn.execute("SELECT COUNT(*) FROM ai_message_state").fetchone()[0]
            )
            conn.close()

    def test_failed_job_is_retryable_and_does_not_mark_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats (chat_id, title, chat_type) VALUES (1, 'Alice', 'user')"
            )
            conn.execute(
                "INSERT INTO messages (chat_id, message_id, text) VALUES (1, 1, 'One')"
            )
            conn.commit()
            ensure_history_jobs(conn, settings)
            job_id, work = claim_ai_jobs(conn, "history", 1, settings)[0]
            save_ai_failure(
                conn,
                work,
                RuntimeError("both providers unavailable"),
                settings,
                lane="history",
                job_id=job_id,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM ai_message_state").fetchone()[0], 0
            )
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM ai_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()[0],
                "failed",
            )
            self.assertEqual(len(claim_ai_jobs(conn, "history", 1, settings)), 1)
            conn.close()

    def test_interrupted_running_job_returns_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats (chat_id, title, chat_type) VALUES (1, 'Alice', 'user')"
            )
            conn.execute(
                "INSERT INTO messages (chat_id, message_id, text) VALUES (1, 1, 'One')"
            )
            conn.commit()
            ensure_history_jobs(conn, settings)
            job_id, _ = claim_ai_jobs(conn, "history", 1, settings)[0]
            release_ai_job(conn, job_id)
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM ai_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()[0],
                "pending",
            )
            conn.close()

    def test_group_messages_remain_excluded_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats (chat_id, title, chat_type) VALUES (2, 'Group', 'group')"
            )
            conn.execute(
                "INSERT INTO messages (chat_id, message_id, text) VALUES (2, 1, 'Group message')"
            )
            conn.commit()
            self.assertEqual(fetch_unanalyzed_messages(conn, 10, settings), [])
            self.assertEqual(ensure_history_jobs(conn, settings), 0)
            conn.close()

    def test_history_job_creation_respects_the_configured_chunk_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_for(
                Path(directory),
                history_internal_concurrency=2,
                history_internal_batch_messages=60,
            )
            conn = connect(settings)
            for chat_id in range(1, 6):
                conn.execute(
                    "INSERT INTO chats (chat_id, title, chat_type) VALUES (?, ?, 'user')",
                    (chat_id, f"Chat {chat_id}"),
                )
                conn.execute(
                    "INSERT INTO messages (chat_id, message_id, text) VALUES (?, 1, 'Message')",
                    (chat_id,),
                )
            conn.commit()
            self.assertEqual(ensure_history_jobs(conn, settings), 2)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM ai_jobs WHERE lane = 'history'"
                ).fetchone()[0],
                2,
            )
            conn.close()
