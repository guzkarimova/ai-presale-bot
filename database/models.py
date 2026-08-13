from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)

    company_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_task: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_process: Mapped[str | None] = mapped_column(Text, nullable=True)
    users: Mapped[str | None] = mapped_column(Text, nullable=True)
    channels: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_sources: Mapped[str | None] = mapped_column(Text, nullable=True)
    integrations: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_handoff: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    additional_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_spec_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    presale_analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_services_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_integrations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    estimated_timeline_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_price_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarifications_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    proposal_needs_update: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manager_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculated_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pricing_timeline: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pricing_manual_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pricing_manual_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
