import json
import logging
from datetime import datetime, timezone

from aiogram.types import Message, User

from database.database import SessionLocal
from database.models import Application
from services.google_docs_service import GoogleDocsService


def _user_data(user: User | None) -> dict:
    if user is None:
        return {}
    return {
        "telegram_user_id": str(user.id),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "language_code": user.language_code,
        "is_premium": user.is_premium,
        "is_bot": user.is_bot,
    }


def record_chat_event(
    application_id: int,
    message: Message,
    sender: str,
    text: str,
    event_type: str = "message",
    interview_step: str = "",
    user: User | None = None,
) -> bool:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sender": sender,
        "event_type": event_type,
        "interview_step": interview_step,
        "text": text,
        "message_id": message.message_id,
        "chat_id": str(message.chat.id),
        "chat_type": str(message.chat.type),
        "chat_title": message.chat.title or "",
        **_user_data(user or message.from_user),
    }

    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            return False
        transcript = []
        if application.additional_answers_json:
            try:
                transcript = json.loads(application.additional_answers_json)
            except (json.JSONDecodeError, TypeError):
                transcript = []
        if any(
            item.get("message_id") == event["message_id"] and item.get("sender") == event["sender"]
            for item in transcript
        ):
            logging.info("Duplicate chat event ignored: application=%s message=%s sender=%s", application_id, event["message_id"], event["sender"])
            return False
        transcript.append(event)
        application.additional_answers_json = json.dumps(transcript, ensure_ascii=False)
        session.commit()
        session.refresh(application)
        GoogleDocsService.append_chat_event(application, event)
        return True
