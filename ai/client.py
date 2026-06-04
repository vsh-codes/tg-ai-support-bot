"""
Thin async wrapper around the Anthropic SDK with streaming.

Exposes a single method `stream()` that yields response chunks as they
arrive. The handler layer accumulates them and edits the Telegram
message — this module knows nothing about Telegram.
"""

from typing import AsyncIterator

from anthropic import AsyncAnthropic
from loguru import logger


# Max tokens per response. Telegram caps single messages at 4096
# characters, and longer answers feel like bot output anyway.
_MAX_TOKENS = 1024


class ClaudeClient:
    """Streams completions from Claude."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def stream(
        self,
        system: str,
        messages: list[dict],
    ) -> AsyncIterator[str]:
        """
        Yield text chunks as they stream in from Claude.

        `messages` should be a list of {"role": "user"|"assistant", "content": str}.
        The final message must be from the user — Anthropic's API requires it.
        """
        if not messages or messages[-1]["role"] != "user":
            raise ValueError("Last message must be from user")

        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            logger.exception("Claude streaming error: {}", exc)
            raise
