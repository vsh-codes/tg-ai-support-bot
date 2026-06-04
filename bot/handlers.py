"""
Command and message handlers.

Flow for a regular user message:
  1. Rate-limit check
  2. Save user message to history
  3. Check for explicit human-request keyword → escalate if yes
  4. RAG retrieval over the knowledge base
  5. Stream Claude response into a Telegram message (editing as it grows)
  6. Save assistant response
  7. Check response for uncertainty markers → escalate if yes
  8. Update dead-end counter; escalate if threshold crossed

Admin commands: /stats, /history <uid>, /takeover <uid>, /reload
"""

import asyncio
import time
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from loguru import logger

from ai.client import ClaudeClient
from ai.knowledge_base import KnowledgeBase
from ai.language import detect_language
from ai.prompts import build_system_prompt
from bot import escalation, messages
from bot.keyboards import takeover_keyboard
from config import Settings
from db.storage import Storage

router = Router(name="ai-support")

# Edit the streaming Telegram message at most every N seconds.
# Telegram's per-message edit rate limit is ~1 Hz; we stay below that.
_STREAM_EDIT_INTERVAL = 1.5


# ---------------------------------------------------------------------------
# /start, /help, /human, /cancel
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    await message.answer(
        messages.WELCOME.format(company_name=settings.company_name)
    )


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    await message.answer(
        messages.WELCOME.format(company_name=settings.company_name)
    )


@router.message(Command("human"))
async def cmd_human(
    message: Message,
    storage: Storage,
    bot: Bot,
    settings: Settings,
) -> None:
    """Explicit human request — escalate immediately."""
    await _escalate(
        bot=bot,
        storage=storage,
        admin_chat_id=settings.admin_chat_id,
        user=message.from_user,
        reason="User typed /human",
    )
    await message.answer(messages.ESCALATION_USER_MESSAGE)


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------

@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    storage: Storage,
    kb: KnowledgeBase,
    settings: Settings,
) -> None:
    if message.from_user.id != settings.admin_chat_id:  # type: ignore[union-attr]
        await message.answer(messages.ADMIN_ONLY)
        return

    stats = await storage.get_stats()
    await message.answer(
        messages.ADMIN_STATS_TEMPLATE.format(
            **stats,
            kb_chunks=len(kb),
        )
    )


@router.message(Command("reload"))
async def cmd_reload(
    message: Message,
    kb: KnowledgeBase,
    settings: Settings,
) -> None:
    if message.from_user.id != settings.admin_chat_id:  # type: ignore[union-attr]
        await message.answer(messages.ADMIN_ONLY)
        return

    files_count = await kb.reload()
    await message.answer(
        messages.KB_RELOADED.format(chunks=len(kb), files=files_count)
    )


# ---------------------------------------------------------------------------
# Main chat handler — everything else
# ---------------------------------------------------------------------------

@router.message(F.text)
async def handle_message(
    message: Message,
    bot: Bot,
    storage: Storage,
    kb: KnowledgeBase,
    claude: ClaudeClient,
    settings: Settings,
) -> None:
    if not message.text or not message.from_user:
        return

    user = message.from_user
    text = message.text.strip()

    # 1. Rate limit
    over_limit = await storage.is_rate_limited(
        user_id=user.id,
        per_hour=settings.rate_limit_per_hour,
    )
    if over_limit:
        await message.answer(messages.RATE_LIMITED)
        return

    # 2. Save user message
    await storage.add_message(user_id=user.id, role="user", content=text)

    # 3. Explicit human request → short-circuit
    decision = escalation.check_user_request(text)
    if decision.should_escalate:
        await _escalate(
            bot=bot,
            storage=storage,
            admin_chat_id=settings.admin_chat_id,
            user=user,
            reason=decision.reason,
        )
        await message.answer(messages.ESCALATION_USER_MESSAGE)
        return

    # 4. RAG retrieval
    rag_chunks = await kb.search(text)
    context_text = "\n\n---\n\n".join(
        f"[Source: {c.source}]\n{c.text}" for c in rag_chunks
    )

    # 5. Build system prompt + conversation history
    user_language = detect_language(text)
    system_prompt = build_system_prompt(
        company_name=settings.company_name,
        knowledge_context=context_text,
        user_language=user_language,
    )
    history = await storage.get_recent_history(
        user_id=user.id,
        max_turns=settings.max_history_turns,
    )

    # 6. Stream response
    thinking_msg = await message.answer(messages.THINKING)
    try:
        full_response = await _stream_to_telegram(
            bot=bot,
            chat_id=thinking_msg.chat.id,
            message_id=thinking_msg.message_id,
            claude=claude,
            system_prompt=system_prompt,
            history=history,
        )
    except Exception as exc:
        logger.exception("Claude streaming failed: {}", exc)
        await thinking_msg.edit_text(messages.ERROR_GENERIC)
        return

    # 7. Save assistant response
    await storage.add_message(user_id=user.id, role="assistant", content=full_response)

    # 8. Check escalation triggers on response
    no_context = len(rag_chunks) == 0
    streak = await storage.update_dead_end_streak(user_id=user.id, no_context=no_context)

    uncertainty = escalation.check_response_uncertainty(full_response)
    dead_end = escalation.check_dead_end_streak(streak)

    if uncertainty.should_escalate:
        await _escalate(
            bot=bot,
            storage=storage,
            admin_chat_id=settings.admin_chat_id,
            user=user,
            reason=uncertainty.reason,
        )
    elif dead_end.should_escalate:
        await _escalate(
            bot=bot,
            storage=storage,
            admin_chat_id=settings.admin_chat_id,
            user=user,
            reason=dead_end.reason,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _stream_to_telegram(
    bot: Bot,
    chat_id: int,
    message_id: int,
    claude: ClaudeClient,
    system_prompt: str,
    history: list[dict],
) -> str:
    """
    Stream Claude's response into an existing Telegram message.

    We accumulate characters and edit the message at most every
    _STREAM_EDIT_INTERVAL seconds to stay under Telegram's edit rate limit.
    """
    buffer = ""
    last_edit_at = 0.0
    last_edit_text = ""

    async for chunk in claude.stream(system=system_prompt, messages=history):
        buffer += chunk
        now = time.monotonic()
        if now - last_edit_at >= _STREAM_EDIT_INTERVAL and buffer != last_edit_text:
            await _safe_edit(bot, chat_id, message_id, buffer + " ▌")
            last_edit_at = now
            last_edit_text = buffer

    # Final edit with the complete text (no cursor)
    if buffer != last_edit_text or buffer.endswith(" ▌"):
        await _safe_edit(bot, chat_id, message_id, buffer)

    return buffer


async def _safe_edit(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    """Edit a message, swallowing the 'message is not modified' error."""
    try:
        await bot.edit_message_text(
            text=text[:4000],  # Telegram message limit
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


async def _escalate(
    bot: Bot,
    storage: Storage,
    admin_chat_id: int,
    user,
    reason: str,
) -> None:
    """Send an escalation notification to the admin."""
    history = await storage.get_recent_history(user_id=user.id, max_turns=5)
    transcript_lines = []
    for msg in history:
        role = "🧑" if msg["role"] == "user" else "🤖"
        # Trim long messages in the transcript
        content = msg["content"]
        if len(content) > 200:
            content = content[:200] + "…"
        transcript_lines.append(f"{role} {content}")
    transcript = "\n\n".join(transcript_lines) or "(no messages yet)"

    username = f"@{user.username}" if user.username else ""
    full_name = user.full_name or "Unknown"

    text = messages.ADMIN_ESCALATION_TEMPLATE.format(
        full_name=full_name,
        username=username,
        user_id=user.id,
        reason=reason,
        transcript=transcript,
    )
    try:
        await bot.send_message(
            chat_id=admin_chat_id,
            text=text,
            reply_markup=takeover_keyboard(user.id),
        )
        await storage.mark_escalation(user_id=user.id, reason=reason)
        logger.info("Escalated user {} — {}", user.id, reason)
    except Exception as exc:
        logger.warning("Failed to send escalation: {}", exc)
