from app.worker.runner import build_output_path, recover_running_jobs


def test_recover_running_jobs_to_queued(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="abc",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )
    repo.mark_running(job.job_id)

    recover_running_jobs(repo)

    saved = repo.get_job(job.job_id)
    assert saved.status == "QUEUED"


def test_build_output_path_uses_job_id_without_prefix():
    output_path = build_output_path("python-tts-backend/outputs", "job-123", None)
    assert output_path == "python-tts-backend/outputs/job-123.mp3"


def test_build_output_path_uses_prefix_when_present():
    output_path = build_output_path(
        "python-tts-backend/outputs",
        "job-123",
        "7577371088154266649-200-202",
    )
    assert output_path == "python-tts-backend/outputs/7577371088154266649-200-202-job-123.mp3"
