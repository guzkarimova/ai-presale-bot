from __future__ import annotations

from typing import Any

from database.database import SessionLocal
from sqlalchemy import update

from database.models import Application
from services.google_docs_service import GoogleDocsService


def get_application_by_user(user_id: int) -> Application | None:
    with SessionLocal() as session:
        return (
            session.query(Application)
            .filter(Application.telegram_user_id == str(user_id))
            .order_by(Application.created_at.desc())
            .first()
        )


def create_application(user_id: int, username: str | None) -> Application:
    with SessionLocal() as session:
        application = Application(
            telegram_user_id=str(user_id),
            username=username,
            status="new",
        )
        session.add(application)
        session.commit()
        session.refresh(application)

    GoogleDocsService.create_application_document(application)
    return application


def update_application_field(application_id: int, field_name: str, value: Any) -> Application:
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            raise ValueError(f"Application {application_id} not found")
        setattr(application, field_name, value)
        application.status = "interview"
        session.commit()
        session.refresh(application)
        return application


def update_application_status(application_id: int, status: str) -> Application:
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            raise ValueError(f"Application {application_id} not found")
        application.status = status
        session.commit()
        session.refresh(application)
        return application


def get_application(application_id: int) -> Application | None:
    with SessionLocal() as session:
        return session.get(Application, application_id)


def claim_presale_processing(application_id: int, message_id: int) -> bool:
    """Atomically claim a completed lead, preventing duplicate PDF/notifications."""
    with SessionLocal() as session:
        result = session.execute(
            update(Application)
            .where(
                Application.id == application_id,
                Application.status.in_(["ready", "QUALIFIED"]),
                Application.processing_message_id.is_(None),
            )
            .values(status="QUALIFIED", processing_message_id=str(message_id), analysis_error=None)
        )
        session.commit()
        return result.rowcount == 1


def save_presale_analysis(application_id: int, analysis_json: str, fields: dict[str, Any]) -> None:
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            return
        application.presale_analysis_json = analysis_json
        for field, value in fields.items():
            setattr(application, field, value)
        application.status = "AI_ANALYZED"
        application.analysis_error = None
        session.commit()


def save_proposal(application_id: int, proposal_path: str) -> None:
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            return
        application.proposal_path = proposal_path
        application.proposal_status = "GENERATED"
        application.proposal_needs_update = False
        application.status = "PROPOSAL_GENERATED"
        session.commit()


def save_pricing_result(application_id: int, pricing_json: str, fields: dict[str, Any]) -> None:
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            return
        application.pricing_result_json = pricing_json
        for field, value in fields.items():
            setattr(application, field, value)
        session.commit()


def mark_manager_notified(application_id: int) -> None:
    from datetime import datetime, timezone

    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            return
        application.status = "SENT_TO_MANAGER"
        application.proposal_status = "SENT_TO_MANAGER"
        application.manager_notified_at = datetime.now(timezone.utc)
        session.commit()


def mark_processing_error(application_id: int, error: str) -> None:
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            return
        application.analysis_error = error[:2000]
        application.status = "MANAGER_REVIEW"
        session.commit()


def mark_proposal_needs_update(application_id: int) -> None:
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None:
            return
        application.proposal_needs_update = True
        if application.status not in {"QUALIFIED", "AI_ANALYZED", "PROPOSAL_GENERATED"}:
            application.status = "MANAGER_REVIEW"
        session.commit()


def get_pending_presale_application_ids() -> list[int]:
    with SessionLocal() as session:
        return [
            item.id
            for item in session.query(Application).filter(
                Application.status.in_(["QUALIFIED", "AI_ANALYZED", "PROPOSAL_GENERATED", "MANAGER_REVIEW"]),
                Application.manager_notified_at.is_(None),
            ).all()
        ]
