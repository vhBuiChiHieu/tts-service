import threading
import time

from app.runtime import WorkerRuntime
from app.worker.runner import build_output_path, get_runtime_status, recover_running_jobs, stop_worker


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


def test_stop_worker_sets_stop_event_and_joins_thread():
    stop_event = threading.Event()
    thread = threading.Thread(target=lambda: stop_event.wait(2), daemon=True)
    thread.start()
    runtime = WorkerRuntime(thread=thread, stop_event=stop_event)

    stop_worker(runtime, timeout=1)

    assert stop_event.is_set() is True
    assert thread.is_alive() is False


def test_get_runtime_status_reports_runtime_fields():
    stop_event = threading.Event()
    thread = threading.Thread(target=lambda: stop_event.wait(0.05), daemon=True)
    thread.start()
    runtime = WorkerRuntime(thread=thread, stop_event=stop_event)

    status = get_runtime_status(runtime)
    stop_event.set()
    thread.join(timeout=1)

    assert status["pid"] > 0
    assert status["worker_alive"] is True
    assert status["stop_requested"] is False
    assert status["uptime_sec"] >= 0.0


def test_worker_runtime_stop_requested_reflects_event():
    stop_event = threading.Event()
    thread = threading.Thread(target=lambda: stop_event.wait(0.05), daemon=True)
    thread.start()
    runtime = WorkerRuntime(thread=thread, stop_event=stop_event)

    stop_event.set()
    time.sleep(0.01)
    status = get_runtime_status(runtime)
    thread.join(timeout=1)
    final_status = get_runtime_status(runtime)

    assert status["stop_requested"] is True
    assert status["pid"] == runtime.pid
    assert status["uptime_sec"] >= 0.0
    assert final_status["worker_alive"] is False
    assert final_status["stop_requested"] is True
    assert final_status["pid"] == runtime.pid
    assert final_status["uptime_sec"] >= status["uptime_sec"]
    assert runtime.stop_requested is True
    assert runtime.worker_alive is False
    assert runtime.thread is thread
    assert runtime.stop_event is stop_event
