from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.schemas import CreateJobRequest, CreateJobResponse, JobTrackingResponse
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=CreateJobResponse, status_code=202)
def create_job(payload: CreateJobRequest, db: Session = Depends(get_db)):
    repo = JobRepo(db)
    job = repo.create_job(
        input_text=payload.text,
        lang=payload.lang,
        voice_hint=payload.voice_hint,
        speed=payload.speed,
        volume_gain_db=payload.volume_gain_db,
    )
    return CreateJobResponse(job_id=job.job_id, status=job.status, created_at=job.created_at)


@router.get("/{job_id}", response_model=JobTrackingResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    repo = JobRepo(db)
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    return JobTrackingResponse(
        job_id=job.job_id,
        status=job.status,
        progress={
            "total_chunks": job.total_chunks,
            "processed_chunks": job.processed_chunks,
            "progress_pct": job.progress_pct,
            "position": {
                "current_chunk_index": job.current_chunk_index,
                "current_char_offset": job.current_char_offset,
                "total_chars": job.total_chars,
            },
        },
        result={
            "file_name": job.result_file_name,
            "file_path": job.result_file_path,
            "duration_ms": job.result_duration_ms,
        },
        error=(
            {"code": job.error_code, "message": job.error_message}
            if job.error_code or job.error_message
            else None
        ),
        created_at=job.created_at,
        started_at=job.started_at,
        updated_at=job.updated_at,
        finished_at=job.finished_at,
    )
