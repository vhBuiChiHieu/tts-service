from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.repo_jobs import JobRepo


def test_create_job_defaults(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="xin chao",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )

    assert job.job_id
    assert job.status == "QUEUED"
    assert job.processed_chunks == 0
    assert job.progress_pct == 0.0
    assert job.speed == 1.0
    assert job.volume_gain_db == 0.0


def test_create_job_sets_retry_resume_defaults(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    saved = repo.get_job(job.job_id)
    assert saved.next_chunk_index == 0
    assert saved.attempt_count == 0
    assert saved.last_error_retryable is None


def test_create_job_persists_speed_and_volume(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="xin chao",
        lang="vi",
        voice_hint=None,
        speed=1.3,
        volume_gain_db=5.0,
    )

    saved = repo.get_job(job.job_id)
    assert saved.speed == 1.3
    assert saved.volume_gain_db == 5.0


def test_get_next_queued_job_fifo(db_session):
    repo = JobRepo(db_session)
    a = repo.create_job(input_text="a", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)
    repo.create_job(input_text="b", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    next_job = repo.get_next_queued_job()
    assert next_job.job_id == a.job_id


def test_update_progress(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    repo.mark_running(job.job_id)
    repo.update_progress(
        job_id=job.job_id,
        total_chunks=10,
        processed_chunks=3,
        current_chunk_index=3,
        current_char_offset=120,
        total_chars=400,
    )

    saved = repo.get_job(job.job_id)
    assert saved.status == "RUNNING"
    assert saved.total_chunks == 10
    assert saved.processed_chunks == 3
    assert saved.progress_pct == 30.0


def test_update_progress_persists_next_chunk_index(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abcdef", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    repo.mark_running(job.job_id)
    repo.update_progress(
        job_id=job.job_id,
        total_chunks=6,
        processed_chunks=4,
        current_chunk_index=4,
        current_char_offset=4,
        total_chars=6,
    )

    saved = repo.get_job(job.job_id)
    assert saved.next_chunk_index == 4


def test_retry_failed_job_requeues_and_clears_error(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    repo.mark_running(job.job_id)
    repo.update_progress(
        job_id=job.job_id,
        total_chunks=10,
        processed_chunks=3,
        current_chunk_index=3,
        current_char_offset=120,
        total_chars=400,
    )
    repo.mark_failed(job.job_id, "UPSTREAM_TIMEOUT", "provider timeout", retryable=True)

    ok = repo.retry_failed_job(job.job_id)
    saved = repo.get_job(job.job_id)

    assert ok is True
    assert saved.status == "QUEUED"
    assert saved.error_code is None
    assert saved.error_message is None
    assert saved.finished_at is None
    assert saved.last_error_retryable == 1


def test_retry_failed_job_rejects_non_failed_status(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    ok = repo.retry_failed_job(job.job_id)
    saved = repo.get_job(job.job_id)

    assert ok is False
    assert saved.status == "QUEUED"


def test_create_job_persists_output_prefix(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="xin chao",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
        output_prefix="7577371088154266649-200-202",
    )

    saved = repo.get_job(job.job_id)
    assert saved.output_prefix == "7577371088154266649-200-202"


def test_init_db_migrates_retry_resume_columns(tmp_path, monkeypatch):
    db_file = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE jobs (
                    job_id VARCHAR PRIMARY KEY,
                    status VARCHAR NOT NULL,
                    input_text TEXT NOT NULL,
                    lang VARCHAR NOT NULL,
                    voice_hint VARCHAR,
                    speed FLOAT NOT NULL,
                    volume_gain_db FLOAT NOT NULL,
                    output_prefix VARCHAR,
                    total_chars INTEGER NOT NULL,
                    total_chunks INTEGER,
                    processed_chunks INTEGER NOT NULL,
                    progress_pct FLOAT NOT NULL,
                    current_chunk_index INTEGER NOT NULL,
                    current_char_offset INTEGER NOT NULL,
                    result_file_name VARCHAR,
                    result_file_path VARCHAR,
                    result_duration_ms INTEGER,
                    error_code VARCHAR,
                    error_message TEXT,
                    created_at VARCHAR NOT NULL,
                    started_at VARCHAR,
                    updated_at VARCHAR NOT NULL,
                    finished_at VARCHAR
                )
                """
            )
        )

    from app.db import session as db_session_module

    test_engine = create_engine(f"sqlite:///{db_file}", future=True)
    test_sessionmaker = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)
    monkeypatch.setattr(db_session_module, "engine", test_engine)
    monkeypatch.setattr(db_session_module, "SessionLocal", test_sessionmaker)

    db_session_module.init_db()

    cols = {col["name"] for col in inspect(test_engine).get_columns("jobs")}
    assert "next_chunk_index" in cols
    assert "attempt_count" in cols
    assert "last_error_retryable" in cols

    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO jobs (
                    job_id, status, input_text, lang, voice_hint, speed, volume_gain_db, output_prefix,
                    total_chars, total_chunks, processed_chunks, progress_pct,
                    current_chunk_index, current_char_offset,
                    result_file_name, result_file_path, result_duration_ms,
                    error_code, error_message,
                    created_at, started_at, updated_at, finished_at
                ) VALUES (
                    'legacy-job', 'QUEUED', 'abc', 'vi', NULL, 1.0, 0.0, NULL,
                    3, NULL, 0, 0.0,
                    0, 0,
                    NULL, NULL, NULL,
                    NULL, NULL,
                    '2026-01-01T00:00:00+00:00', NULL, '2026-01-01T00:00:00+00:00', NULL
                )
                """
            )
        )

    with test_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT next_chunk_index, attempt_count, last_error_retryable "
                "FROM jobs WHERE job_id='legacy-job'"
            )
        ).first()

    assert row is not None
    assert row[0] == 0
    assert row[1] == 0
    assert row[2] is None

    test_engine.dispose()
    engine.dispose()
    db_session_module.engine.dispose()
