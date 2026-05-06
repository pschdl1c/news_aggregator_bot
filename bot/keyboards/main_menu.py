from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📰 Дайджест за неделю", callback_data="digest")],
            [InlineKeyboardButton(text="⚙️ Сменить модель", callback_data="select_model")],
            [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
        ]
    )


def back_to_digest() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ К дайджесту", callback_data="back_to_digest")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
        ]
    )


def deep_dive_keyboard(count: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=f"🔍 {i}", callback_data=f"deepdive_{i}")
        for i in range(1, count + 1)
    ]
    rows = [buttons[i:i+5] for i in range(0, len(buttons), 5)]
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
