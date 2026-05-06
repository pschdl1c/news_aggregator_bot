import logging

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config.settings import MODEL_CATALOGUE
from services import db_service

logger = logging.getLogger(__name__)
router = Router()


def _model_keyboard(current_model: str) -> InlineKeyboardMarkup:
    rows = []
    for m in MODEL_CATALOGUE:
        check = " ✓" if m["id"] == current_model else ""
        label = (
            f"[{m['tier']}] {m['id']}"
            f" | in:{m['input_token_limit'] // 1024}K"
            f" | out:{m['output_token_limit'] // 1024}K"
            f"{check}"
        )
        rows.append([InlineKeyboardButton(text=label, callback_data=f"set_model:{m['id']}")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda c: c.data == "select_model")
async def cb_select_model(callback: CallbackQuery) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    current = await db_service.get_user_model(user_id)
    await callback.message.edit_text(
        "Выберите модель:\n\n"
        "<b>Tier S</b> — Gemma 4 31B (полный размер, лучшее качество)\n"
        "<b>Tier A</b> — Gemma 4 26B MoE (Mixture of Experts, быстрее)\n\n"
        "Контекст: 128K токенов у обеих моделей.",
        reply_markup=_model_keyboard(current),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith("set_model:"))
async def cb_set_model(callback: CallbackQuery) -> None:
    await callback.answer()
    model_id = callback.data.removeprefix("set_model:")
    valid_ids = {m["id"] for m in MODEL_CATALOGUE}
    if model_id not in valid_ids:
        await callback.answer("Неизвестная модель", show_alert=True)
        return
    user_id = callback.from_user.id
    await db_service.set_user_model(user_id, model_id)
    logger.info("MODEL_CHANGE user_id=%d model=%s", user_id, model_id)
    await callback.message.edit_reply_markup(reply_markup=_model_keyboard(model_id))
    await callback.answer(f"Модель: {model_id}", show_alert=False)
