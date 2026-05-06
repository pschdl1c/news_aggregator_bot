import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import start, digest, chat
from bot.handlers import model as model_handler
from bot.handlers import deep_dive
from bot.middlewares.auth import WhitelistMiddleware
from config.settings import settings
from services.db_service import init_db


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(
        "logs/bot.log", maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    error_handler = RotatingFileHandler(
        "logs/errors.log", maxBytes=50 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, error_handler, stream_handler],
    )


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    await init_db()
    logger.info("Database initialized")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(WhitelistMiddleware())

    dp.include_router(start.router)
    dp.include_router(digest.router)
    dp.include_router(model_handler.router)
    dp.include_router(deep_dive.router)
    dp.include_router(chat.router)

    logger.info("Bot starting")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
