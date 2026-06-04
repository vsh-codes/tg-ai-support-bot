"""
System prompt construction.

Kept as a separate module so prompt tweaks are obvious diffs in code
review and easy to A/B test by swapping module-level constants.
"""

# Mapping from langdetect's two-letter codes to instruction phrases
# the model can follow naturally. Unknown codes fall back to "the
# user's language" which Claude handles by mirroring whatever the
# user wrote.
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "uk": "Ukrainian",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "tr": "Turkish",
    "ar": "Arabic",
    "zh-cn": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
}


_BASE_SYSTEM_PROMPT = """You are a customer support agent for {company_name}.

Your job is to answer customer questions accurately based on the knowledge base provided below. You speak in a friendly, professional, concise tone.

## Rules

1. **Only answer from the knowledge base.** If the answer isn't there, say so plainly: "I don't have information about that — let me connect you with a human." Do not invent details, do not guess, do not extrapolate.

2. **Be concise.** Aim for 1–3 sentences unless the question genuinely needs more depth. Customers are reading on mobile.

3. **Reply in {language}.** The customer wrote in this language; mirror it. If you're uncertain about the language, mirror whatever they used.

4. **Don't fabricate citations.** Do not invent product names, prices, dates, URLs, or contact details. If something specific isn't in the knowledge base, say so.

5. **Escalate cleanly when needed.** If the question requires a human (refunds, account changes, complaints, technical bugs you can't resolve), say so directly and tell them a human will follow up.

6. **Stay in scope.** Don't answer questions that are clearly outside the company's domain (politics, math homework, etc.) — politely redirect.

## Knowledge base (retrieved excerpts)

{knowledge_context}
"""

_EMPTY_CONTEXT_NOTICE = (
    "(No relevant excerpts found in the knowledge base for this query. "
    "Be honest about that and offer to connect them with a human.)"
)


def build_system_prompt(
    company_name: str,
    knowledge_context: str,
    user_language: str,
) -> str:
    """Compose the per-turn system prompt with retrieved RAG context."""
    if not knowledge_context.strip():
        knowledge_context = _EMPTY_CONTEXT_NOTICE

    language_name = _LANGUAGE_NAMES.get(
        user_language.lower(),
        "the customer's language",
    )

    return _BASE_SYSTEM_PROMPT.format(
        company_name=company_name,
        knowledge_context=knowledge_context,
        language=language_name,
    )
