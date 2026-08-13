import asyncio

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from handlers.interview import InterviewState, QUESTION_TEXT
from keyboards.keyboards import get_info_keyboard, get_resume_keyboard, get_start_keyboard
from services.application_service import create_application, get_application_by_user
from services.application_service import update_application_status
from services.chat_log_service import record_chat_event

router = Router()


@router.message(CommandStart())
async def command_start(message: Message) -> None:
    existing = get_application_by_user(message.from_user.id)
    if existing is None or existing.status not in {"new", "interview"}:
        existing = await asyncio.to_thread(create_application, message.from_user.id, message.from_user.username)
    text = (
        "Здравствуйте! 👋\n\n"
        "Я задам несколько вопросов о вашей задаче, чтобы наша команда могла подготовить для вас "
        "подходящее решение и коммерческое предложение.\n\n"
        "Отвечайте в свободной форме. Это займёт около 5–10 минут."
    )

    await asyncio.to_thread(record_chat_event, existing.id, message, "user", message.text or "/start", "command")

    if existing.status == "interview":
        sent = await message.answer(text)
        await asyncio.to_thread(record_chat_event, existing.id, sent, "bot", text, "message", user=message.from_user)
        prompt = "Вы уже начали отвечать на вопросы. Продолжим с того места, где остановились?"
        sent = await message.answer(prompt, reply_markup=get_resume_keyboard())
        await asyncio.to_thread(record_chat_event, existing.id, sent, "bot", prompt, "message", user=message.from_user)
        return

    sent = await message.answer(text, reply_markup=get_start_keyboard())
    await asyncio.to_thread(record_chat_event, existing.id, sent, "bot", text, "message", user=message.from_user)


@router.callback_query(F.data == "what_i_get")
async def what_i_get(callback: CallbackQuery) -> None:
    text = (
        "По итогам вы получите документ, в котором будут:\n"
        "— описание задачи;\n"
        "— текущий процесс;\n"
        "— предлагаемый вариант автоматизации;\n"
        "— функции будущего решения;\n"
        "— необходимые интеграции;\n"
        "— необходимые материалы и данные;\n"
        "— ограничения;\n"
        "— этапы реализации;\n"
        "— ожидаемый результат."
    )
    await callback.message.answer(text, reply_markup=get_info_keyboard())
    await callback.answer()


@router.callback_query(F.data == "start_survey")
async def start_survey(callback: CallbackQuery, state: FSMContext) -> None:
    existing = get_application_by_user(callback.from_user.id)
    if existing and existing.status == "interview":
        await callback.message.answer("У вас уже есть активная заявка. Продолжим её.", reply_markup=get_resume_keyboard())
        await callback.answer()
        return

    if existing is None or existing.status != "new":
        existing = await asyncio.to_thread(create_application, callback.from_user.id, callback.from_user.username)
    await state.set_state(InterviewState.company_and_task)
    sent = await callback.message.answer(QUESTION_TEXT["company_and_task"])
    await asyncio.to_thread(
        record_chat_event, existing.id, sent, "bot", QUESTION_TEXT["company_and_task"], "question", "company_and_task", callback.from_user
    )
    await callback.answer()


@router.callback_query(F.data == "continue_application")
async def continue_application(callback: CallbackQuery, state: FSMContext) -> None:
    existing = get_application_by_user(callback.from_user.id)
    if existing is None:
        await callback.message.answer("Незавершённая заявка не найдена. Начнём заново.")
        await start_survey(callback, state)
        return

    current_step = await state.get_state()
    if current_step is None:
        await state.set_state(InterviewState.company_and_task)
        await callback.message.answer(QUESTION_TEXT["company_and_task"])
    else:
        current_key = current_step.split(":")[-1]
        if current_key == "company_and_task":
            await callback.message.answer(QUESTION_TEXT["company_and_task"])
        elif current_key == "current_process":
            await callback.message.answer(QUESTION_TEXT["current_process"])
        elif current_key == "channels_and_integrations":
            await callback.message.answer(QUESTION_TEXT["channels_and_integrations"])
        elif current_key == "ai_scope":
            await callback.message.answer(QUESTION_TEXT["ai_scope"])
        else:
            await callback.message.answer(QUESTION_TEXT["expected_result"])
    await callback.answer()


@router.callback_query(F.data == "restart_application")
async def restart_application(callback: CallbackQuery, state: FSMContext) -> None:
    existing = get_application_by_user(callback.from_user.id)
    if existing and existing.status in {"new", "interview"}:
        await asyncio.to_thread(update_application_status, existing.id, "cancelled")
    await state.clear()
    await start_survey(callback, state)
