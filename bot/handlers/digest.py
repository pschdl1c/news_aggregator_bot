import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import back_to_menu, deep_dive_keyboard
from bot.states.chat import BotStates
from bot.utils import send_long_message, parse_digest_response, format_digest_html
from services import db_service, llm_service
from services.llm_service import NoArticlesError

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(lambda c: c.data == "digest")
async def cb_digest(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    status_msg = await callback.message.answer("⏳ Собираю новости...")
    logger.info("DIGEST user_id=%d", user_id)

    try:
        model = await db_service.get_user_model(user_id)
        raw_response, articles = await llm_service.get_digest(user_id, model)

        parsed = parse_digest_response(raw_response, articles)

        if parsed:
            digest_html = format_digest_html(parsed)
            text = (
                f"📊 Статей за 7 дней: <b>{len(articles)}</b>\n\n"
                f"Наиболее интересные и релевантные:\n\n"
                f"{digest_html}\n\n"
                f"──────────\n"
                f"💬 Напишите запрос — и я найду подходящие статьи среди всех {len(articles)}. "
                f"Например: <i>«статьи по безопасности»</i>, <i>«что-то про multimodal»</i> "
                f"или <i>«новости об агентах»</i>."
            )
            await state.update_data(
                all_articles=articles,
                digest_articles=parsed,
                digest_text=text,
            )
            keyboard = deep_dive_keyboard(len(parsed))
        else:
            # LLM не вернул нужный формат — показываем как есть
            text = raw_response
            await state.update_data(all_articles=articles, digest_articles=[])
            keyboard = back_to_menu()

        await db_service.save_chat_message(user_id, "assistant", text)
        await status_msg.delete()
        await send_long_message(callback.message, text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(BotStates.chat)

    except NoArticlesError:
        await status_msg.edit_text("Статьи за последние 7 дней не найдены. Попробуйте позже.")
    except Exception:
        logger.exception("DIGEST_ERROR user_id=%d", user_id)
        await status_msg.edit_text("Произошла ошибка. Попробуйте позже.")
