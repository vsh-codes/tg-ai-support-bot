"""
Unit tests for language detection.

We use deterministic seeding in `ai.language`, so these results are
stable across runs.
"""

import pytest

from ai.language import detect_language


class TestDetectLanguage:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Hello, how do I reset my password?", "en"),
            ("Привет, как мне сбросить пароль?", "ru"),
            ("Привіт, як мені скинути пароль?", "uk"),
            ("Hola, ¿cómo puedo restablecer mi contraseña?", "es"),
        ],
    )
    def test_detects_common_languages(self, text: str, expected: str) -> None:
        assert detect_language(text) == expected

    @pytest.mark.parametrize("text", ["", "  ", "ab"])
    def test_too_short_returns_unknown(self, text: str) -> None:
        assert detect_language(text) == "unknown"
