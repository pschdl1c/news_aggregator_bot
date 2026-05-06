import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config.settings import settings
from services import db_service

logger = logging.getLogger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        user_id = user.id

        if user_id == settings.admin_user_id or await db_service.is_whitelisted(user_id):
            return await handler(event, data)

        logger.warning("AUTH_DENIED user_id=%d", user_id)

        bot: Bot = data["bot"]

        if isinstance(event, Message):
            await event.answer("Доступ закрыт. Обратитесь к администратору.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ закрыт.", show_alert=True)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"approve_{user_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"deny_{user_id}",
                ),
            ]
        ])

        username = f"@{user.username}" if user.username else str(user_id)
        await bot.send_message(
            settings.admin_user_id,
            f"Запрос доступа от пользователя {username} (id: {user_id})",
            reply_markup=keyboard,
        )

        return None
