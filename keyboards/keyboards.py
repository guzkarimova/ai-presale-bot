from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_start_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Начать", callback_data="start_survey"),
            InlineKeyboardButton(text="Что я получу?", callback_data="what_i_get"),
        ]
    ])
    return keyboard


def get_info_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать опрос", callback_data="start_survey")]
    ])
    return keyboard


def get_resume_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Продолжить", callback_data="continue_application"),
            InlineKeyboardButton(text="Начать заново", callback_data="restart_application"),
        ]
    ])
    return keyboard
