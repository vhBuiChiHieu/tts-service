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


def test_retry_failed_job_requeues_without_resetting_progress(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    repo.update_progress(
        job_id=job.job_id,
        total_chunks=4,
        processed_chunks=2,
        current_chunk_index=2,
        current_char_offset=10,
        total_chars=20,
    )
    repo.mark_failed(job.job_id, "UNEXPECTED_ERROR", "boom")

    retried = repo.retry_failed_job(job.job_id)

    assert retried is not None
    saved = repo.get_job(job.job_id)
    assert saved.status == "QUEUED"
    assert saved.processed_chunks == 2
    assert saved.current_chunk_index == 2
    assert saved.current_char_offset == 10
    assert saved.error_code is None
    assert saved.error_message is None
    assert saved.finished_at is None


def test_retry_failed_job_returns_none_for_non_failed_job(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None, speed=1.0, volume_gain_db=0.0)

    assert repo.retry_failed_job(job.job_id) is None
    assert repo.retry_failed_job("missing") is None
