from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.schemas import (
    CREATE_JOB_DESCRIPTION,
    CREATE_JOB_OPERATION_ID,
    CREATE_JOB_SUMMARY,
    JOB_BODY_EXAMPLES,
    JOB_CREATE_RESPONSES,
    JOB_ID_DESCRIPTION,
    JOB_ID_EXAMPLE,
    JOB_TRACKING_RESPONSES,
    SANGTACVIET_BODY_EXAMPLES,
    SANGTACVIET_DESCRIPTION,
    SANGTACVIET_OPERATION_ID,
    SANGTACVIET_RESPONSES,
    SANGTACVIET_SUMMARY,
    TRACK_JOB_DESCRIPTION,
    TRACK_JOB_OPERATION_ID,
    TRACK_JOB_SUMMARY,
    CreateJobRequest,
    CreateJobResponse,
    JobErrorResponse,
    JobPositionResponse,
    JobProgressResponse,
    JobResultResponse,
    JobTrackingResponse,
    SangTacVietCreateJobRequest,
)
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "",
    response_model=CreateJobResponse,
    status_code=202,
    summary=CREATE_JOB_SUMMARY,
    description=CREATE_JOB_DESCRIPTION,
    operation_id=CREATE_JOB_OPERATION_ID,
    responses=JOB_CREATE_RESPONSES,
)
def create_job(
    payload: CreateJobRequest = Body(openapi_examples=JOB_BODY_EXAMPLES),
    db: Session = Depends(get_db),
):
    repo = JobRepo(db)
    job = repo.create_job(
        input_text=payload.text,
        lang=payload.lang,
        voice_hint=payload.voice_hint,
        speed=payload.speed,
        volume_gain_db=payload.volume_gain_db,
    )
    return CreateJobResponse(job_id=job.job_id, status=job.status, created_at=job.created_at)


@router.post(
    "/sangtacviet",
    response_model=CreateJobResponse,
    status_code=202,
    summary=SANGTACVIET_SUMMARY,
    description=SANGTACVIET_DESCRIPTION,
    operation_id=SANGTACVIET_OPERATION_ID,
    responses=SANGTACVIET_RESPONSES,
)
def create_job_sangtacviet(
    payload: SangTacVietCreateJobRequest = Body(openapi_examples=SANGTACVIET_BODY_EXAMPLES),
    db: Session = Depends(get_db),
):
    repo = JobRepo(db)

    chapter_texts = [chapter.text.strip() for chapter in payload.chapters]
    if any(not text for text in chapter_texts):
        raise HTTPException(status_code=422, detail="chapter text must be non-empty")

    merged_text = " ".join(chapter_texts).strip()
    if not merged_text:
        raise HTTPException(status_code=422, detail="merged chapter text is empty")

    output_prefix = f"{payload.book_id}-{payload.range.start}-{payload.range.end}"

    job = repo.create_job(
        input_text=merged_text,
        lang=payload.lang,
        voice_hint=payload.voice_hint,
        speed=payload.speed,
        volume_gain_db=payload.volume_gain_db,
        output_prefix=output_prefix,
    )
    return CreateJobResponse(job_id=job.job_id, status=job.status, created_at=job.created_at)


@router.get(
    "/{job_id}",
    response_model=JobTrackingResponse,
    summary=TRACK_JOB_SUMMARY,
    description=TRACK_JOB_DESCRIPTION,
    operation_id=TRACK_JOB_OPERATION_ID,
    responses=JOB_TRACKING_RESPONSES,
)
def get_job(
    job_id: str = Path(..., description=JOB_ID_DESCRIPTION, examples=[JOB_ID_EXAMPLE]),
    db: Session = Depends(get_db),
):
    repo = JobRepo(db)
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    return JobTrackingResponse(
        job_id=job.job_id,
        status=job.status,
        progress=JobProgressResponse(
            total_chunks=job.total_chunks,
            processed_chunks=job.processed_chunks,
            progress_pct=job.progress_pct,
            position=JobPositionResponse(
                current_chunk_index=job.current_chunk_index,
                current_char_offset=job.current_char_offset,
                total_chars=job.total_chars,
            ),
        ),
        result=JobResultResponse(
            file_name=job.result_file_name,
            file_path=job.result_file_path,
            duration_ms=job.result_duration_ms,
        ),
        error=(
            JobErrorResponse(code=job.error_code, message=job.error_message)
            if job.error_code or job.error_message
            else None
        ),
        created_at=job.created_at,
        started_at=job.started_at,
        updated_at=job.updated_at,
        finished_at=job.finished_at,
    )
