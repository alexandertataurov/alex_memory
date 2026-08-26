from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alex_memory.config import load_settings


class SettingsTests(unittest.TestCase):
    def test_missing_env_file_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, r"\.env is missing"):
                    load_settings(Path(directory))

    def test_missing_telegram_hash_names_the_missing_setting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("TELEGRAM_API_ID=1\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(
                    RuntimeError, r"TELEGRAM_API_HASH is missing"
                ):
                    load_settings(root)

    def test_settings_use_documented_runtime_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(root)
            self.assertEqual(1000, settings.group_full_threshold)
            self.assertEqual(3000, settings.ai_daily_max_messages)
            self.assertEqual(14.5, settings.gemini_requests_per_minute)
            self.assertEqual("quota_aware", settings.ai_routing_mode)
            self.assertEqual("gemma-4-31b-it", settings.gemma_short_model)
            self.assertEqual("Asia/Tbilisi", settings.app_timezone)

    def test_invalid_boolean_setting_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / ("." + "env")
            config_path.write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {"AI_INCLUDE_GROUPS": "enabled"}, clear=True):
                with self.assertRaisesRegex(
                    RuntimeError, r"AI_INCLUDE_GROUPS must be a boolean"
                ):
                    load_settings(root)

    def test_gemini_pacing_accepts_fractional_requests_per_minute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\n", encoding="utf-8"
            )
            with patch.dict(
                os.environ, {"GEMINI_REQUESTS_PER_MINUTE": "14.5"}, clear=True
            ):
                settings = load_settings(root)
            self.assertEqual(14.5, settings.gemini_requests_per_minute)

    def test_invalid_numeric_setting_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\nAI_BATCH_MESSAGES=invalid\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(
                    RuntimeError, r"AI_BATCH_MESSAGES must be an integer"
                ):
                    load_settings(root)

    def test_invalid_fractional_gemini_pacing_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\n", encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {"GEMINI_REQUESTS_PER_MINUTE": "invalid"},
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, r"GEMINI_REQUESTS_PER_MINUTE must be a number"
                ):
                    load_settings(root)

    def test_primary_gemini_model_override_is_used_by_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "GEMINI_PRIMARY_MODEL": "gemini-2.5-flash",
                    "GGEMINI_MODEL": "gemini-2.0-flash",
                },
                clear=True,
            ):
                settings = load_settings(root)
            self.assertEqual("gemini-2.5-flash", settings.gemini_primary_model)
            self.assertEqual("gemini-2.5-flash", settings.gemini_model)
            self.assertEqual((), settings.configuration_warnings)

    def test_legacy_ai_aliases_are_visible_in_runtime_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / ("." + "env")
            config_path.write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\n", encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {
                    "GEMINI_MODEL": "gemini-legacy",
                    "AI_HISTORY_CHUNKS_PER_RUN": "3",
                },
                clear=True,
            ):
                settings = load_settings(root)
            self.assertEqual("gemini-legacy", settings.gemini_primary_model)
            self.assertEqual(
                (
                    "GEMINI_MODEL is deprecated; use GEMINI_PRIMARY_MODEL",
                    "AI_HISTORY_CHUNKS_PER_RUN is deprecated; use HISTORY_INTERNAL_CONCURRENCY",
                ),
                settings.configuration_warnings,
            )

    def test_history_limits_use_internal_names_with_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=test\n", encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {
                    "AI_HISTORY_CHUNKS_PER_RUN": "3",
                    "AI_HISTORY_CHUNK_MESSAGES": "11",
                    "AI_HISTORY_CHUNK_CHARS": "2400",
                },
                clear=True,
            ):
                settings = load_settings(root)
            self.assertEqual(3, settings.history_internal_concurrency)
            self.assertEqual(11, settings.history_internal_batch_messages)
            self.assertEqual(2400, settings.history_internal_batch_chars)

            with patch.dict(
                os.environ,
                {
                    "HISTORY_INTERNAL_CONCURRENCY": "4",
                    "HISTORY_AUTO_ANALYZE": "true",
                    "HISTORY_AUTO_ANALYZE_INTERVAL_MINUTES": "5",
                },
                clear=True,
            ):
                settings = load_settings(root)
            self.assertEqual(4, settings.history_internal_concurrency)
            self.assertTrue(settings.history_auto_analyze)
            self.assertEqual(5, settings.history_auto_analyze_interval_minutes)
