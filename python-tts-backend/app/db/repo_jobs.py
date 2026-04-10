from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRepo:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_job(
        self,
        input_text: str,
        lang: str,
        voice_hint: str | None,
        speed: float,
        volume_gain_db: float,
        output_prefix: str | None = None,
    ) -> Job:
        job = Job(
            input_text=input_text,
            lang=lang,
            voice_hint=voice_hint,
            speed=speed,
            volume_gain_db=volume_gain_db,
            output_prefix=output_prefix,
            total_chars=len(input_text),
            status="QUEUED",
            updated_at=now_iso(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def get_next_queued_job(self) -> Job | None:
        stmt = select(Job).where(Job.status == "QUEUED").order_by(Job.created_at.asc()).limit(1)
        return self.db.execute(stmt).scalars().first()

    def mark_running(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        job.status = "RUNNING"
        job.started_at = now_iso()
        job.updated_at = now_iso()
        self.db.commit()

    def update_progress(
        self,
        job_id: str,
        total_chunks: int,
        processed_chunks: int,
        current_chunk_index: int,
        current_char_offset: int,
        total_chars: int,
    ) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        pct = 0.0 if total_chunks == 0 else round((processed_chunks / total_chunks) * 100.0, 2)
        job.total_chunks = total_chunks
        job.processed_chunks = processed_chunks
        job.next_chunk_index = processed_chunks
        job.current_chunk_index = current_chunk_index
        job.current_char_offset = current_char_offset
        job.total_chars = total_chars
        job.progress_pct = pct
        job.updated_at = now_iso()
        self.db.commit()

    def mark_success(self, job_id: str, output_path: str, duration_ms: int) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        file_name = output_path.replace("\\", "/").split("/")[-1]
        job.status = "SUCCEEDED"
        job.result_file_name = file_name
        job.result_file_path = output_path.replace("\\", "/")
        job.result_duration_ms = duration_ms
        job.progress_pct = 100.0
        job.finished_at = now_iso()
        job.updated_at = now_iso()
        self.db.commit()

    def mark_failed(self, job_id: str, error_code: str, error_message: str, retryable: bool = False) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        job.status = "FAILED"
        job.error_code = error_code
        job.error_message = error_message
        job.last_error_retryable = 1 if retryable else 0
        job.finished_at = now_iso()
        job.updated_at = now_iso()
        self.db.commit()

    def mark_retryable_failure(self, job_id: str, error_code: str, error_message: str) -> None:
        self.mark_failed(job_id, error_code, error_message, retryable=True)

    def retry_failed_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if not job or job.status != "FAILED":
            return False
        job.status = "QUEUED"
        job.error_code = None
        job.error_message = None
        job.finished_at = None
        job.attempt_count += 1
        job.updated_at = now_iso()
        self.db.commit()
        return True

    def requeue_running_jobs(self) -> None:
        stmt = select(Job).where(Job.status == "RUNNING")
        rows = self.db.execute(stmt).scalars().all()
        for job in rows:
            job.status = "QUEUED"
            job.updated_at = now_iso()
        self.db.commit()
