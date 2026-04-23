from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, Query, UploadFile
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
    CANCEL_JOB_DESCRIPTION,
    CANCEL_JOB_OPERATION_ID,
    CANCEL_JOB_RESPONSES,
    CANCEL_JOB_SUMMARY,
    CreateJobRequest,
    CreateJobResponse,
    JobErrorResponse,
    JobPositionResponse,
    JobProgressResponse,
    JobResultResponse,
    JobTrackingResponse,
    JobListResponse,
    DeleteAllJobsResponse,
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
    "/tts-file-txt",
    response_model=CreateJobResponse,
    status_code=202,
    summary="Create a TTS job from a TXT file",
    description="Queue a text-to-speech job by uploading a .txt file.",
    operation_id="create_tts_job_from_file",
)
def create_job_file_txt(
    file: UploadFile = File(...),
    speed: float = Query(1.0, ge=0.5, le=2.0, description="Playback speed applied during final audio export."),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are allowed")
    
    try:
        text = file.file.read().decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be utf-8 encoded")
    
    if not text.strip():
        raise HTTPException(status_code=422, detail="The provided txt file is empty")

    repo = JobRepo(db)
    job = repo.create_job(
        input_text=text,
        lang="vi",
        voice_hint=None,
        speed=speed,
        volume_gain_db=0.0,
        output_prefix=file.filename[:-4],
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
    speed: float = Query(1.0, ge=0.5, le=2.0, description="Playback speed applied during final audio export."),
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
        speed=speed,
        volume_gain_db=payload.volume_gain_db,
        output_prefix=output_prefix,
    )
    return CreateJobResponse(job_id=job.job_id, status=job.status, created_at=job.created_at)


def build_tracking_response(job) -> JobTrackingResponse:
    return JobTrackingResponse(
        job_id=job.job_id,
        status=job.status,
        progress=JobProgressResponse(
            total_chunks=job.total_chunks or 0,
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


@router.post(
    "/{job_id}/cancel",
    response_model=JobTrackingResponse,
    summary=CANCEL_JOB_SUMMARY,
    description=CANCEL_JOB_DESCRIPTION,
    operation_id=CANCEL_JOB_OPERATION_ID,
    responses=CANCEL_JOB_RESPONSES,
)
def cancel_job(
    job_id: str = Path(..., description=JOB_ID_DESCRIPTION, examples=[JOB_ID_EXAMPLE]),
    db: Session = Depends(get_db),
):
    repo = JobRepo(db)
    existing = repo.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="job not found")
    job = repo.request_cancel(job_id)
    if not job:
        raise HTTPException(status_code=409, detail="job cannot be cancelled from its current status")
    return build_tracking_response(job)


@router.post(
    "/retry/{job_id}",
    response_model=CreateJobResponse,
    status_code=202,
    summary="Retry a failed TTS job",
    description="Requeue a failed job on the same job ID so the worker can resume from its persisted partial audio.",
    operation_id="retry_job",
)
def retry_job(
    job_id: str = Path(..., description=JOB_ID_DESCRIPTION, examples=[JOB_ID_EXAMPLE]),
    db: Session = Depends(get_db),
):
    repo = JobRepo(db)
    job = repo.retry_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="retryable job not found")
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

    return build_tracking_response(job)


@router.get(
    "",
    response_model=JobListResponse,
    summary="List all jobs",
    description="Get a paginated list of all TTS jobs ordered by creation time descending.",
    operation_id="list_jobs",
)
def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db),
):
    repo = JobRepo(db)
    skip = (page - 1) * size
    jobs, total = repo.get_jobs(skip=skip, limit=size)
    pages = (total + size - 1) // size

    items = [build_tracking_response(job) for job in jobs]

    return JobListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@router.delete(
    "/all",
    response_model=DeleteAllJobsResponse,
    summary="Delete all jobs",
    description="Clear all job data from the database.",
    operation_id="delete_all_jobs",
)
def delete_all_jobs(
    db: Session = Depends(get_db),
):
    repo = JobRepo(db)
    deleted_count = repo.delete_all_jobs()
    return DeleteAllJobsResponse(deleted_count=deleted_count)
