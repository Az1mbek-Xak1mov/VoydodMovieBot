import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import ErrorEvent

from app.core.config import settings
from app.database.engine import AsyncSessionLocal, init_db
from app.handlers import admin, restore, user
from app.middlewares.auth import AdminAuthMiddleware
from app.middlewares.db import DbSessionMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> None:
    """Swallow transient network errors; log everything else with traceback."""
    if isinstance(event.exception, TelegramNetworkError):
        logger.warning("Transient Telegram network error: %s", event.exception)
        return
    logger.exception("Unhandled update error", exc_info=event.exception)


async def main() -> None:
    await init_db()
    logger.info("Database initialized.")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Inject a DB session into every handler call.
    dp.update.outer_middleware(DbSessionMiddleware(AsyncSessionLocal))

    # Gate the admin routers exclusively behind admin verification.
    restore.router.message.middleware(AdminAuthMiddleware())
    admin.router.message.middleware(AdminAuthMiddleware())
    admin.router.callback_query.middleware(AdminAuthMiddleware())

    # Restore first so "#restore" videos never fall into the add-movie FSM;
    # admin next so its FSM/command handlers win over the user catch-all.
    dp.include_router(restore.router)
    dp.include_router(admin.router)
    dp.include_router(user.router)

    # Global error handler for uncaught exceptions during update processing.
    dp.errors.register(on_error)

    logger.info("Starting polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
