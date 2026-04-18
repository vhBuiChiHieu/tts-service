import os
import threading
import time

from sqlalchemy import func, select

from app.audio.merger import AudioMerger
from app.core.config import settings
from app.db.models import Job
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal
from app.runtime import WorkerRuntime
from app.tts.chunker import build_chunks
from app.tts.google_adapter import GoogleTranslateAdapter
from app.tts.token_manager import TokenManager
from app.worker.processor import process_job


def recover_running_jobs(repo: JobRepo) -> None:
    repo.requeue_running_jobs()


def build_output_path(output_dir: str, job_id: str, output_prefix: str | None) -> str:
    file_name = f"{job_id}.mp3" if not output_prefix else f"{output_prefix}-{job_id}.mp3"
    return f"{output_dir}/{file_name}"


def build_partial_output_path(output_dir: str, job_id: str, output_prefix: str | None) -> str:
    return f"{build_output_path(output_dir, job_id, output_prefix)}.partial"


def start_worker() -> WorkerRuntime:
    stop_event = threading.Event()

    def loop() -> None:
        token_manager = TokenManager(ttl_sec=settings.token_ttl_sec, user_agent="Mozilla/5.0")
        adapter = GoogleTranslateAdapter(
            token_manager=token_manager,
            request_timeout_sec=settings.request_timeout_sec,
            user_agent="Mozilla/5.0",
        )

        while not stop_event.is_set():
            with SessionLocal() as db:
                repo = JobRepo(db)
                job = repo.get_next_queued_job()
                if job:
                    os.makedirs(settings.output_dir, exist_ok=True)
                    merger = AudioMerger(
                        silent_between_chunks_ms=settings.silent_between_chunks_ms,
                        volume_gain_db=job.volume_gain_db,
                        speed=job.speed,
                    )
                    output_path = build_output_path(settings.output_dir, job.job_id, job.output_prefix)
                    partial_output_path = build_partial_output_path(settings.output_dir, job.job_id, job.output_prefix)
                    process_job(
                        job_id=job.job_id,
                        repo=repo,
                        chunker=build_chunks,
                        adapter=adapter,
                        merger=merger,
                        output_path=output_path,
                        partial_output_path=partial_output_path,
                        max_chars=settings.max_chars_per_chunk,
                        stop_event=stop_event,
                    )
            stop_event.wait(settings.worker_poll_interval_ms / 1000)

    thread = threading.Thread(target=loop, daemon=True, name="tts-worker")
    thread.start()
    return WorkerRuntime(thread=thread, stop_event=stop_event)


def stop_worker(runtime: WorkerRuntime, timeout: float | None = None) -> None:
    runtime.request_stop()
    runtime.join(timeout=timeout)


def get_runtime_status(runtime: WorkerRuntime) -> dict[str, object]:
    return {
        "pid": runtime.pid,
        "worker_alive": runtime.worker_alive,
        "stop_requested": runtime.stop_requested,
        "uptime_sec": round(max(0.0, time.time() - runtime.started_at), 2),
    }


def count_jobs(repo: JobRepo) -> dict[str, int]:
    statuses = {}
    for status in ("QUEUED", "RUNNING"):
        stmt = select(func.count()).select_from(Job).where(Job.status == status)
        statuses[status.lower()] = repo.db.execute(stmt).scalar_one()
    return statuses


def get_worker_status(runtime: WorkerRuntime, repo: JobRepo) -> dict[str, object]:
    return {
        **get_runtime_status(runtime),
        **count_jobs(repo),
    }
