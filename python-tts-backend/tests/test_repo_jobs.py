from app.db.repo_jobs import JobRepo


def test_create_job_defaults(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="xin chao", lang="vi", voice_hint=None)

    assert job.job_id
    assert job.status == "QUEUED"
    assert job.processed_chunks == 0
    assert job.progress_pct == 0.0


def test_get_next_queued_job_fifo(db_session):
    repo = JobRepo(db_session)
    a = repo.create_job(input_text="a", lang="vi", voice_hint=None)
    repo.create_job(input_text="b", lang="vi", voice_hint=None)

    next_job = repo.get_next_queued_job()
    assert next_job.job_id == a.job_id


def test_update_progress(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None)

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
