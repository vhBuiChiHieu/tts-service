import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String, nullable=False, default="QUEUED")
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(String, nullable=False)
    voice_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    volume_gain_db: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    total_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_char_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    result_file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    result_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    result_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
