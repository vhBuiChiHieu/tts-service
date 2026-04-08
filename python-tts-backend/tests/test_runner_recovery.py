from app.worker.runner import recover_running_jobs


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
