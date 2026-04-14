from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.control import router as control_router
from app.api.jobs import router as jobs_router
from app.core.config import settings
from app.core.schemas import (
    API_CONTACT,
    API_DESCRIPTION,
    API_LICENSE,
    API_SERVERS,
    API_SUMMARY,
    API_TITLE,
    API_VERSION,
    HEALTH_DESCRIPTION,
    HEALTH_OPERATION_ID,
    HEALTH_RESPONSES,
    HEALTH_SUMMARY,
    HealthResponse,
    OPENAPI_TAGS,
)
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal, init_db
from app.worker.runner import recover_running_jobs, start_worker, stop_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        repo = JobRepo(db)
        recover_running_jobs(repo)

    app.state.runtime = start_worker()
    try:
        yield
    finally:
        runtime = getattr(app.state, "runtime", None)
        if runtime is not None:
            stop_worker(runtime, timeout=settings.control_shutdown_timeout_sec)


app = FastAPI(
    title=API_TITLE,
    summary=API_SUMMARY,
    description=API_DESCRIPTION,
    version=API_VERSION,
    contact=API_CONTACT,
    license_info=API_LICENSE,
    servers=API_SERVERS,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)
app.state.runtime = None
app.include_router(jobs_router)
app.include_router(control_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    summary=HEALTH_SUMMARY,
    description=HEALTH_DESCRIPTION,
    operation_id=HEALTH_OPERATION_ID,
    responses=HEALTH_RESPONSES,
    tags=["system"],
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
