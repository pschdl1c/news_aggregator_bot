from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    chat = State()
    deep_dive = State()
    waiting_model_name = State()
