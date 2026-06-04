"""
Lightweight language detection wrapper around `langdetect`.

Used to choose the response language hint in the system prompt.
We catch detection failures (very short messages, mixed scripts)
and fall back to an "unknown" code, which the prompt builder
turns into "the customer's language".
"""

from langdetect import DetectorFactory, LangDetectException, detect

# Make langdetect deterministic (it has a tiny stochastic component).
DetectorFactory.seed = 0


def detect_language(text: str) -> str:
    """Return ISO-639 language code, or 'unknown' on failure."""
    if not text or len(text.strip()) < 3:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"
