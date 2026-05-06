import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main_menu import back_to_menu, back_to_digest, deep_dive_keyboard
from bot.states.chat import BotStates
from bot.utils import send_long_message
from services import db_service, llm_service, scraper

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(lambda c: c.data and c.data.startswith("deepdive_"))
async def cb_deep_dive(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user_id = callback.from_user.id

    data = await state.get_data()
    articles = data.get("digest_articles", [])

    try:
        num = int(callback.data.removeprefix("deepdive_"))
    except ValueError:
        num = None
    article = next((a for a in articles if a["display_num"] == num), None) if num is not None else None

    if not article:
        await callback.message.answer("Статья не найдена. Попробуйте запросить дайджест заново.")
        return

    status_msg = await callback.message.answer("⏳ Читаю статью...")
    logger.info("DEEP_DIVE user_id=%d article=%s", user_id, article["url"])

    try:
        model = await db_service.get_user_model(user_id)

        content = await scraper.fetch_article_text(article["url"])
        if not content:
            content = article.get("description") or article["title"]
            logger.info("DEEP_DIVE_FALLBACK user_id=%d", user_id)

        summary = await llm_service.deep_dive_summary(article, content, model, user_id=user_id)

        await state.update_data(
            deep_dive_article=article,
            deep_dive_content=content,
        )

        header = f'📰 <a href="{article["url"]}">{article["title"]}</a>\n\n'
        await status_msg.delete()
        await send_long_message(
            callback.message,
            header + summary,
            reply_markup=back_to_digest(),
            parse_mode="HTML",
        )
        await state.set_state(BotStates.deep_dive)

    except Exception:
        logger.exception("DEEP_DIVE_ERROR user_id=%d", user_id)
        await status_msg.edit_text("Произошла ошибка. Попробуйте позже.")


@router.message(BotStates.deep_dive, F.text)
async def handle_deep_dive_chat(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    user_text = message.text.strip()

    status_msg = await message.answer("⏳ Думаю...")
    logger.info("DEEP_DIVE_CHAT user_id=%d", user_id)

    try:
        data = await state.get_data()
        article = data.get("deep_dive_article", {})
        content = data.get("deep_dive_content", "")
        model = await db_service.get_user_model(user_id)

        await db_service.save_chat_message(user_id, "user", user_text)

        response = await llm_service.deep_dive_followup(
            user_message=user_text,
            article=article,
            article_content=content,
            model=model,
            user_id=user_id,
        )

        await status_msg.delete()
        await send_long_message(message, response, reply_markup=back_to_digest(), parse_mode=None)

    except Exception:
        logger.exception("DEEP_DIVE_CHAT_ERROR user_id=%d", user_id)
        await status_msg.edit_text("Произошла ошибка. Попробуйте позже.")


@router.callback_query(lambda c: c.data == "back_to_digest")
async def cb_back_to_digest(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    digest_text = data.get("digest_text")
    digest_articles = data.get("digest_articles", [])

    if not digest_text or not digest_articles:
        await callback.message.answer("Дайджест не найден. Запросите его заново.", reply_markup=back_to_menu())
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await send_long_message(
        callback.message,
        digest_text,
        reply_markup=deep_dive_keyboard(len(digest_articles)),
        parse_mode="HTML",
    )
    await state.set_state(BotStates.chat)
