import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.main_menu import back_to_digest, deep_dive_keyboard
from bot.states.chat import BotStates
from bot.utils import send_long_message, parse_digest_response, format_digest_html
from services import db_service, llm_service

logger = logging.getLogger(__name__)
router = Router()


@router.message(BotStates.chat, F.text)
async def handle_followup(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    user_text = message.text.strip()

    status_msg = await message.answer("⏳ Ищу по статьям...")
    logger.info("ARTICLE_SEARCH user_id=%d", user_id)

    try:
        data = await state.get_data()
        all_articles = data.get("all_articles", [])
        model = await db_service.get_user_model(user_id)

        await db_service.save_chat_message(user_id, "user", user_text)

        response = await llm_service.search_articles(user_text, all_articles, model, user_id)

        parsed = parse_digest_response(response, all_articles)

        if parsed:
            text = format_digest_html(parsed)
            await state.update_data(digest_articles=parsed, digest_text=text)
            keyboard = deep_dive_keyboard(len(parsed))
            await status_msg.delete()
            await send_long_message(message, text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await status_msg.delete()
            await send_long_message(message, response, reply_markup=back_to_digest(), parse_mode=None)

    except Exception:
        logger.exception("ARTICLE_SEARCH_ERROR user_id=%d", user_id)
        await status_msg.edit_text("Произошла ошибка. Попробуйте позже.")
