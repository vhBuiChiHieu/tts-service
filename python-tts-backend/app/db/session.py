from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(f"sqlite:///{settings.db_path}", future=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _ensure_jobs_output_prefix_column() -> None:
    with engine.begin() as conn:
        columns = conn.execute(text("PRAGMA table_info(jobs)")).mappings().all()
        names = {row["name"] for row in columns}
        if "output_prefix" not in names:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN output_prefix VARCHAR"))


def init_db() -> None:
    from app.db.models import Job  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_jobs_output_prefix_column()
