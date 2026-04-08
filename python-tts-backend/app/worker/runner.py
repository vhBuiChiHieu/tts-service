import os
import threading
import time

from app.audio.merger import AudioMerger
from app.core.config import settings
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal
from app.tts.chunker import build_chunks
from app.tts.google_adapter import GoogleTranslateAdapter
from app.tts.token_manager import TokenManager
from app.worker.processor import process_job


def recover_running_jobs(repo: JobRepo) -> None:
    repo.requeue_running_jobs()


def start_worker() -> threading.Thread:
    def loop() -> None:
        token_manager = TokenManager(ttl_sec=settings.token_ttl_sec, user_agent="Mozilla/5.0")
        adapter = GoogleTranslateAdapter(
            token_manager=token_manager,
            request_timeout_sec=settings.request_timeout_sec,
            user_agent="Mozilla/5.0",
        )

        while True:
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
                    output_path = f"{settings.output_dir}/{job.job_id}.mp3"
                    process_job(
                        job_id=job.job_id,
                        repo=repo,
                        chunker=build_chunks,
                        adapter=adapter,
                        merger=merger,
                        output_path=output_path,
                        max_chars=settings.max_chars_per_chunk,
                    )
            time.sleep(settings.worker_poll_interval_ms / 1000)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t
