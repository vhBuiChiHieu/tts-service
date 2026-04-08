from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal, init_db
from app.worker.runner import recover_running_jobs, start_worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        repo = JobRepo(db)
        recover_running_jobs(repo)
    start_worker()
    yield


app = FastAPI(title="Python Local TTS Backend", lifespan=lifespan)
app.include_router(jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
