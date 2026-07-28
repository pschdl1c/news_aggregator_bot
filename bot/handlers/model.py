import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards.main_menu import back_to_menu
from bot.states.chat import BotStates
from config.settings import settings, MODEL_CATALOGUE
from services import db_service, llm_service

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
    rows.append([InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="custom_model")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda c: c.data == "select_model")
async def cb_select_model(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    user_id = callback.from_user.id
    current = await db_service.get_user_model(user_id) or settings.default_model
    await callback.message.edit_text(
        "Выберите модель:\n\n"
        "<b>Tier G</b> — Gemini 3.5 Flash Lite (по умолчанию, контекст 1M токенов)\n"
        "<b>Tier S</b> — Gemma 4 31B (полный размер, лучшее качество, 128K)\n"
        "<b>Tier A</b> — Gemma 4 26B MoE (Mixture of Experts, быстрее, 128K)\n\n"
        f"Текущая модель: <code>{current}</code>",
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


@router.callback_query(lambda c: c.data == "custom_model")
async def cb_custom_model(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "Введите точное имя модели Google AI Studio (например: <code>gemini-3.5-flash-lite</code>).\n\n"
        "Я проверю, что она существует и реально отвечает, прежде чем сохранить.",
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await state.set_state(BotStates.waiting_model_name)


@router.message(BotStates.waiting_model_name, F.text)
async def handle_custom_model(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    model_id = message.text.strip().removeprefix("models/")

    status_msg = await message.answer(f"⏳ Проверяю модель «{model_id}»...")
    logger.info("MODEL_VERIFY_ATTEMPT user_id=%d model=%s", user_id, model_id)

    ok, detail = await llm_service.verify_model(model_id)

    if not ok:
        logger.info("MODEL_VERIFY_FAIL user_id=%d model=%s reason=%s", user_id, model_id, detail)
        await status_msg.edit_text(
            f"❌ Модель «{model_id}» недоступна:\n{detail}\n\n"
            "Проверьте имя и напишите ещё раз, либо вернитесь в меню.",
            reply_markup=back_to_menu(),
        )
        return

    await db_service.set_user_model(user_id, model_id)
    await state.clear()
    logger.info("MODEL_CHANGE user_id=%d model=%s (custom)", user_id, model_id)
    await status_msg.edit_text(
        f"✅ Модель установлена: <code>{model_id}</code>\nОтвет модели: {detail}",
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
