import logging

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.keyboards.main_menu import main_menu
from config.settings import settings
from services import db_service

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я слежу за новостями об AI, LLM и Machine Learning.\n\nВыбери действие:",
        reply_markup=main_menu(),
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Контекст сброшен.", reply_markup=main_menu())


@router.callback_query(lambda c: c.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Выбери действие:", reply_markup=main_menu())
    await callback.answer()


# --- Admin commands ---

def _is_admin(user_id: int) -> bool:
    return user_id == settings.admin_user_id


@router.message(Command("add_user"))
async def cmd_add_user(message: Message, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        await message.answer("Использование: /add_user <user_id>")
        return

    target_id = int(parts[1])
    try:
        chat = await bot.get_chat(target_id)
        username = chat.username
    except Exception:
        username = None
    await db_service.add_to_whitelist(target_id, username, message.from_user.id)
    logger.info("WHITELIST_ADD admin=%d target=%d", message.from_user.id, target_id)
    await message.answer(f"Пользователь {target_id} добавлен в whitelist.")


@router.message(Command("remove_user"))
async def cmd_remove_user(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        await message.answer("Использование: /remove_user <user_id>")
        return

    target_id = int(parts[1])
    await db_service.remove_from_whitelist(target_id)
    logger.info("WHITELIST_REMOVE admin=%d target=%d", message.from_user.id, target_id)
    await message.answer(f"Пользователь {target_id} удалён из whitelist.")


@router.message(Command("list_users"))
async def cmd_list_users(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    users = await db_service.list_whitelist()
    if not users:
        await message.answer("Whitelist пуст.")
        return

    lines = [f"• {uid} ({uname or 'без username'})" for uid, uname in users]
    await message.answer("Whitelist:\n" + "\n".join(lines))


_ABOUT_TEXT = """\
<b>Что умеет этот бот</b>

<b>📰 Дайджест за неделю</b>
Бот собирает все статьи с HuggingFace Daily Papers за последние 7 дней и просит модель выбрать \
5–7 наиболее интересных — с кратким описанием каждой.

<b>🔍 Глубокий разбор статьи</b>
Под каждой статьёй в дайджесте есть кнопка 🔍N. Нажмите её — бот скачает полный текст статьи \
и попросит модель сделать структурированный анализ: проблема, метод, результаты, вклад авторов. \
После анализа можно задавать любые вопросы по статье — модель отвечает строго по тексту.

<b>💬 Поиск среди всех статей</b>
После дайджеста напишите запрос в чат — например, <i>«статьи по безопасности»</i> или \
<i>«что-то про reasoning»</i>. Модель просмотрит все статьи за неделю и найдёт подходящие. \
Если они есть — покажет мини-дайджест с кнопками для разбора.

<b>⚙️ Выбор модели</b>
Можно переключиться между доступными моделями через кнопку «Сменить модель».\
"""


@router.callback_query(lambda c: c.data == "about")
async def cb_about(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(_ABOUT_TEXT, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith("approve_"))
async def cb_approve_user(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    try:
        target_id = int(callback.data.split("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    try:
        chat = await bot.get_chat(target_id)
        username = chat.username
    except Exception:
        username = None
    await db_service.add_to_whitelist(target_id, username, callback.from_user.id)
    logger.info("WHITELIST_APPROVE admin=%d target=%d", callback.from_user.id, target_id)
    await callback.message.edit_text(f"✅ Пользователь {target_id} одобрен.")
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("deny_"))
async def cb_deny_user(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    try:
        target_id = int(callback.data.split("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    logger.info("WHITELIST_DENY admin=%d target=%d", callback.from_user.id, target_id)
    await callback.message.edit_text(f"❌ Пользователю {target_id} отказано.")
    await callback.answer()
