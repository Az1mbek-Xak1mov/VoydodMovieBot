from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.config import settings


class AdminAuthMiddleware(BaseMiddleware):
    """Gate handlers so only ADMIN_IDS users pass; others are dropped."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.id not in settings.admin_ids:
            return None
        return await handler(event, data)
