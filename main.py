"""
Entry point for the AI support bot.

Wires together aiogram, Claude client, knowledge base, and storage,
then starts long-polling. Graceful shutdown on SIGINT/SIGTERM.
"""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from ai.client import ClaudeClient
from ai.knowledge_base import KnowledgeBase
from bot.handlers import router as main_router
from config import settings
from db.storage import Storage


def configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "{message}"
        ),
        colorize=True,
    )
    logger.add(
        "logs/bot.log",
        level=settings.log_level,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
    )


async def main() -> None:
    configure_logging()
    logger.info("Starting tg-ai-support-bot with model {}", settings.claude_model)

    # Storage
    storage = Storage(settings.database_path)
    await storage.initialize()

    # Knowledge base — loads and embeds documents
    kb = KnowledgeBase(
        knowledge_dir=settings.knowledge_dir,
        top_k=settings.rag_top_k,
    )
    await kb.initialize()
    logger.info("Knowledge base ready with {} chunks", len(kb))

    # Claude client
    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
    )

    # Bot + dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Inject dependencies for handlers
    dp["storage"] = storage
    dp["kb"] = kb
    dp["claude"] = claude
    dp["settings"] = settings

    dp.include_router(main_router)

    logger.info("Bot ready, starting polling")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await storage.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down on interrupt")
