from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]
DB_DIR = BASE_DIR / "data"
DB_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_DIR / 'applications.db'}"


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_applications_table()


def _migrate_applications_table() -> None:
    """Add new nullable columns to existing SQLite databases without data loss."""
    expected_columns = {
        "presale_analysis_json": "TEXT",
        "selected_solution": "TEXT",
        "selected_services_json": "TEXT",
        "analyzed_integrations_json": "TEXT",
        "complexity": "VARCHAR(32)",
        "estimated_timeline_json": "TEXT",
        "estimated_price_json": "TEXT",
        "clarifications_json": "TEXT",
        "proposal_path": "VARCHAR(512)",
        "proposal_needs_update": "BOOLEAN NOT NULL DEFAULT 0",
        "processing_message_id": "VARCHAR(64)",
        "manager_notified_at": "DATETIME",
        "analysis_error": "TEXT",
        "pricing_result_json": "TEXT",
        "calculated_price": "INTEGER",
        "final_price": "INTEGER",
        "project_level": "VARCHAR(32)",
        "pricing_timeline": "VARCHAR(128)",
        "pricing_manual_check": "BOOLEAN NOT NULL DEFAULT 0",
        "pricing_manual_reasons_json": "TEXT",
        "proposal_status": "VARCHAR(32)",
    }
    existing = {column["name"] for column in inspect(engine).get_columns("applications")}
    with engine.begin() as connection:
        for name, sql_type in expected_columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE applications ADD COLUMN {name} {sql_type}"))
