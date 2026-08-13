import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from services.application_service import (
    claim_presale_processing,
    create_application,
    get_application_by_user,
    mark_proposal_needs_update,
    update_application_field,
    update_application_status,
)
from services.chat_log_service import record_chat_event
from services.manager_notifier import ManagerNotifier, additional_message_affects_proposal
from services.presale_pipeline import schedule_presale_processing
from services.google_docs_service import GoogleDocsService

router = Router()


class InterviewState(StatesGroup):
    company_and_task = State()
    current_process = State()
    channels_and_integrations = State()
    ai_scope = State()
    expected_result = State()


QUESTION_TEXT = {
    "company_and_task": (
        "<b>1️⃣ Чем занимается ваша компания и какую задачу вы хотите решить с помощью AI?</b>\n"
        "Ответьте коротко, в 2–3 предложениях."
    ),
    "current_process": (
        "<b>2️⃣ Как эта задача решается сейчас?</b>\n"
        "Опишите текущий процесс: кто выполняет работу и что приходится делать вручную."
    ),
    "channels_and_integrations": (
        "<b>3️⃣ Где должно работать решение и с какими сервисами его нужно связать?</b>\n"
        "Например: Telegram, MAX, сайт, CRM, 1С, Google Таблицы, маркетплейсы или другие сервисы."
    ),
    "ai_scope": (
        "<b>4️⃣ Что должен уметь AI-ассистент?</b>\n"
        "Опишите, какие действия он должен выполнять самостоятельно. Если у вас есть инструкции, документы, "
        "FAQ, таблицы или другие материалы для его работы — укажите это."
    ),
    "expected_result": (
        "<b>5️⃣ Какой результат вы хотите получить после внедрения?</b>\n"
        "Например: сократить ручную работу, быстрее обрабатывать обращения, снизить количество ошибок, "
        "автоматизировать процессы или увеличить продажи."
    ),
}

STATE_TO_FIELD = {
    "company_and_task": "business_task",
    "current_process": "current_process",
    "channels_and_integrations": "integrations",
    "ai_scope": "ai_actions",
    "expected_result": "expected_result",
}

STEP_ORDER = [
    "company_and_task",
    "current_process",
    "channels_and_integrations",
    "ai_scope",
    "expected_result",
]

MANAGER_PENDING_TEXT = (
    "✅ Ваш запрос уже передан менеджеру и находится в работе. "
    "Я добавлю ваше сообщение к заявке, чтобы менеджер учёл его при подготовке предложения."
)

COMPLETED_STATUSES = {
    "ready", "QUALIFIED", "AI_ANALYZED", "PROPOSAL_GENERATED", "SENT_TO_MANAGER", "MANAGER_REVIEW", "DONE"
}

STATE_LOOKUP = {
    InterviewState.company_and_task: "company_and_task",
    InterviewState.current_process: "current_process",
    InterviewState.channels_and_integrations: "channels_and_integrations",
    InterviewState.ai_scope: "ai_scope",
    InterviewState.expected_result: "expected_result",
}


async def _ask_next_question(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await state.set_state(InterviewState.company_and_task)
        await message.answer(QUESTION_TEXT["company_and_task"])
        return

    current_key = STATE_LOOKUP.get(current)
    if current_key is None:
        await state.set_state(InterviewState.company_and_task)
        await message.answer(QUESTION_TEXT["company_and_task"])
        return

    next_index = STEP_ORDER.index(current_key) + 1
    if next_index >= len(STEP_ORDER):
        await state.clear()
        await message.answer(
            "Спасибо! Я передал все ваши ответы менеджеру. Он изучит информацию и свяжется с вами уже с готовым коммерческим предложением."
        )
        return

    next_key = STEP_ORDER[next_index]
    await state.set_state(getattr(InterviewState, next_key))
    await message.answer(QUESTION_TEXT[next_key])


@router.message(F.text)
async def handle_interview_message(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        application = get_application_by_user(message.from_user.id)
        if application is not None and application.status in COMPLETED_STATUSES:
            sent = await message.answer(MANAGER_PENDING_TEXT)
            is_new = await asyncio.to_thread(
                record_chat_event,
                application.id,
                message,
                "user",
                message.text,
                "message",
                user=message.from_user,
            )
            if not is_new:
                return
            affects_proposal = additional_message_affects_proposal(message.text)
            if affects_proposal:
                await asyncio.to_thread(mark_proposal_needs_update, application.id)
                await asyncio.to_thread(GoogleDocsService.mark_proposal_needs_update, application)
            await asyncio.to_thread(
                record_chat_event,
                application.id,
                sent,
                "bot",
                MANAGER_PENDING_TEXT,
                "message",
                user=message.from_user,
            )
            try:
                await ManagerNotifier().send_additional_message(
                    message.bot, application, message.text, affects_proposal
                )
            except Exception:
                import logging

                logging.exception("Failed to notify manager about additional message for application %s", application.id)
        return

    current_key = STATE_LOOKUP.get(current)
    if current_key is None:
        return

    application = get_application_by_user(message.from_user.id)
    if application is None:
        application = create_application(message.from_user.id, message.from_user.username)

    value = message.text.strip()
    if not value:
        await message.answer("Пожалуйста, напишите ответ одним сообщением.")
        return

    field_name = STATE_TO_FIELD[current_key]
    update_application_field(application.id, field_name, value)

    if current_key == "expected_result":
        update_application_status(application.id, "ready")
        text = (
            "Спасибо! Я передал все ваши ответы менеджеру. "
            "Он изучит информацию и свяжется с вами уже с готовым коммерческим предложением."
        )
        sent = await message.answer(text)
        await asyncio.to_thread(
            record_chat_event, application.id, message, "user", value, "answer", current_key, message.from_user
        )
        await asyncio.to_thread(record_chat_event, application.id, sent, "bot", text, "message", current_key, message.from_user)
        await state.clear()
        if await asyncio.to_thread(claim_presale_processing, application.id, message.message_id):
            schedule_presale_processing(message.bot, application.id)
        return

    next_index = STEP_ORDER.index(current_key) + 1
    next_key = STEP_ORDER[next_index]
    await state.set_state(getattr(InterviewState, next_key))
    sent = await message.answer(QUESTION_TEXT[next_key])
    await asyncio.to_thread(
        record_chat_event, application.id, message, "user", value, "answer", current_key, message.from_user
    )
    await asyncio.to_thread(
        record_chat_event, application.id, sent, "bot", QUESTION_TEXT[next_key], "question", next_key, message.from_user
    )
