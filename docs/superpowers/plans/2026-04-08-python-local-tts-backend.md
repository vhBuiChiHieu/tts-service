# Python Local TTS Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI backend that accepts long text, returns a `job_id`, processes TTS in a sequential background worker, and exposes job tracking from SQLite.

**Architecture:** A single-process monolith with FastAPI HTTP endpoints, SQLite as the source of truth for job lifecycle/progress, and one FIFO worker loop that processes exactly one queued job at a time. TTS synthesis is done through a Google Translate web RPC adapter with token caching and retry logic; chunk audio is merged into one mp3 output.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, SQLAlchemy + SQLite, Pydantic v2, requests, pydub + ffmpeg, pytest.

---

## File Structure (target)

- Create: `python-tts-backend/requirements.txt`
- Create: `python-tts-backend/.env.example`
- Create: `python-tts-backend/app/main.py`
- Create: `python-tts-backend/app/core/config.py`
- Create: `python-tts-backend/app/core/schemas.py`
- Create: `python-tts-backend/app/core/errors.py`
- Create: `python-tts-backend/app/core/logging.py`
- Create: `python-tts-backend/app/api/jobs.py`
- Create: `python-tts-backend/app/db/session.py`
- Create: `python-tts-backend/app/db/models.py`
- Create: `python-tts-backend/app/db/repo_jobs.py`
- Create: `python-tts-backend/app/tts/chunker.py`
- Create: `python-tts-backend/app/tts/token_manager.py`
- Create: `python-tts-backend/app/tts/google_adapter.py`
- Create: `python-tts-backend/app/audio/merger.py`
- Create: `python-tts-backend/app/worker/processor.py`
- Create: `python-tts-backend/app/worker/runner.py`
- Create: `python-tts-backend/tests/conftest.py`
- Create: `python-tts-backend/tests/test_health.py`
- Create: `python-tts-backend/tests/test_repo_jobs.py`
- Create: `python-tts-backend/tests/test_jobs_api.py`
- Create: `python-tts-backend/tests/test_chunker.py`
- Create: `python-tts-backend/tests/test_google_adapter.py`
- Create: `python-tts-backend/tests/test_processor.py`
- Create: `python-tts-backend/tests/test_runner_recovery.py`

---

### Task 1: Bootstrap project + app skeleton

**Files:**
- Create: `python-tts-backend/requirements.txt`
- Create: `python-tts-backend/.env.example`
- Create: `python-tts-backend/app/main.py`
- Create: `python-tts-backend/app/core/config.py`
- Create: `python-tts-backend/tests/test_health.py`

- [ ] **Step 1: Write the failing health test**

```python
# python-tts-backend/tests/test_health.py
from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest python-tts-backend/tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.main`.

- [ ] **Step 3: Add project dependencies and minimal app/config**

```text
# python-tts-backend/requirements.txt
fastapi==0.115.12
uvicorn==0.34.2
sqlalchemy==2.0.40
pydantic==2.11.3
pydantic-settings==2.8.1
requests==2.32.3
pydub==0.25.1
python-dotenv==1.1.0
pytest==8.3.5
```

```env
# python-tts-backend/.env.example
DB_PATH=./data/jobs.db
OUTPUT_DIR=./outputs
MAX_CHARS_PER_CHUNK=200
WORKER_POLL_INTERVAL_MS=500
REQUEST_TIMEOUT_SEC=20
CHUNK_RETRY_MAX=2
RANDOM_DELAY_MIN_SEC=0.5
RANDOM_DELAY_MAX_SEC=1.5
SILENT_BETWEEN_CHUNKS_MS=180
TOKEN_TTL_SEC=3600
HOST=127.0.0.1
PORT=8000
```

```python
# python-tts-backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_path: str = "./data/jobs.db"
    output_dir: str = "./outputs"
    max_chars_per_chunk: int = 200
    worker_poll_interval_ms: int = 500
    request_timeout_sec: int = 20
    chunk_retry_max: int = 2
    random_delay_min_sec: float = 0.5
    random_delay_max_sec: float = 1.5
    silent_between_chunks_ms: int = 180
    token_ttl_sec: int = 3600
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
```

```python
# python-tts-backend/app/main.py
from fastapi import FastAPI

app = FastAPI(title="Python Local TTS Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest python-tts-backend/tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/requirements.txt python-tts-backend/.env.example python-tts-backend/app/main.py python-tts-backend/app/core/config.py python-tts-backend/tests/test_health.py
git commit -m "chore: bootstrap local tts backend skeleton"
```

---

### Task 2: Implement SQLite schema + repository for jobs

**Files:**
- Create: `python-tts-backend/app/db/session.py`
- Create: `python-tts-backend/app/db/models.py`
- Create: `python-tts-backend/app/db/repo_jobs.py`
- Create: `python-tts-backend/tests/conftest.py`
- Create: `python-tts-backend/tests/test_repo_jobs.py`

- [ ] **Step 1: Write failing repository tests**

```python
# python-tts-backend/tests/test_repo_jobs.py
from app.db.repo_jobs import JobRepo


def test_create_job_defaults(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="xin chao", lang="vi", voice_hint=None)

    assert job.job_id
    assert job.status == "QUEUED"
    assert job.processed_chunks == 0
    assert job.progress_pct == 0.0


def test_get_next_queued_job_fifo(db_session):
    repo = JobRepo(db_session)
    a = repo.create_job(input_text="a", lang="vi", voice_hint=None)
    b = repo.create_job(input_text="b", lang="vi", voice_hint=None)

    next_job = repo.get_next_queued_job()
    assert next_job.job_id == a.job_id


def test_update_progress(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None)

    repo.mark_running(job.job_id)
    repo.update_progress(
        job_id=job.job_id,
        total_chunks=10,
        processed_chunks=3,
        current_chunk_index=3,
        current_char_offset=120,
        total_chars=400,
    )

    saved = repo.get_job(job.job_id)
    assert saved.status == "RUNNING"
    assert saved.total_chunks == 10
    assert saved.processed_chunks == 3
    assert saved.progress_pct == 30.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest python-tts-backend/tests/test_repo_jobs.py -v`
Expected: FAIL with missing DB modules.

- [ ] **Step 3: Implement SQLAlchemy session/models/repo (minimal)**

```python
# python-tts-backend/app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(f"sqlite:///{settings.db_path}", future=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db() -> None:
    from app.db.models import Job  # noqa: F401
    Base.metadata.create_all(bind=engine)
```

```python
# python-tts-backend/app/db/models.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String, nullable=False, default="QUEUED")
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(String, nullable=False)
    voice_hint: Mapped[str | None] = mapped_column(String, nullable=True)

    total_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_char_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    result_file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    result_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    result_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
```

```python
# python-tts-backend/app/db/repo_jobs.py
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRepo:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_job(self, input_text: str, lang: str, voice_hint: str | None) -> Job:
        job = Job(
            input_text=input_text,
            lang=lang,
            voice_hint=voice_hint,
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
        job.current_chunk_index = current_chunk_index
        job.current_char_offset = current_char_offset
        job.total_chars = total_chars
        job.progress_pct = pct
        job.updated_at = now_iso()
        self.db.commit()
```

```python
# python-tts-backend/tests/conftest.py
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base


@pytest.fixture()
def db_session(tmp_path) -> Session:
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    TestingSession = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest python-tts-backend/tests/test_repo_jobs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/app/db/session.py python-tts-backend/app/db/models.py python-tts-backend/app/db/repo_jobs.py python-tts-backend/tests/conftest.py python-tts-backend/tests/test_repo_jobs.py
git commit -m "feat: add sqlite job repository and schema"
```

---

### Task 3: Implement job API (`POST /v1/jobs`, `GET /v1/jobs/{job_id}`)

**Files:**
- Create: `python-tts-backend/app/core/schemas.py`
- Create: `python-tts-backend/app/api/jobs.py`
- Modify: `python-tts-backend/app/main.py`
- Create: `python-tts-backend/tests/test_jobs_api.py`

- [ ] **Step 1: Write failing API tests**

```python
# python-tts-backend/tests/test_jobs_api.py
from fastapi.testclient import TestClient

from app.main import app


def test_post_jobs_returns_job_id(monkeypatch):
    client = TestClient(app)

    payload = {"text": "xin chao", "lang": "vi", "voice_hint": None, "metadata": {"source": "chapter-1"}}
    response = client.post("/v1/jobs", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert "job_id" in body
    assert body["status"] == "QUEUED"


def test_get_job_not_found():
    client = TestClient(app)
    response = client.get("/v1/jobs/not-found")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest python-tts-backend/tests/test_jobs_api.py -v`
Expected: FAIL because `/v1/jobs` route is missing.

- [ ] **Step 3: Implement schemas + routes + route registration**

```python
# python-tts-backend/app/core/schemas.py
from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    text: str = Field(min_length=1)
    lang: str = Field(min_length=2, max_length=10)
    voice_hint: str | None = None
    metadata: dict = Field(default_factory=dict)


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str


class JobTrackingResponse(BaseModel):
    job_id: str
    status: str
    progress: dict
    result: dict
    error: dict | None
    created_at: str
    started_at: str | None
    updated_at: str
    finished_at: str | None
```

```python
# python-tts-backend/app/api/jobs.py
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
    job = repo.create_job(input_text=payload.text, lang=payload.lang, voice_hint=payload.voice_hint)
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
```

```python
# python-tts-backend/app/main.py
from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.db.session import init_db

app = FastAPI(title="Python Local TTS Backend")
init_db()
app.include_router(jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run API tests to verify pass**

Run: `pytest python-tts-backend/tests/test_jobs_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/app/core/schemas.py python-tts-backend/app/api/jobs.py python-tts-backend/app/main.py python-tts-backend/tests/test_jobs_api.py
git commit -m "feat: add job create and tracking endpoints"
```

---

### Task 4: Implement text chunker with position metadata

**Files:**
- Create: `python-tts-backend/app/tts/chunker.py`
- Create: `python-tts-backend/tests/test_chunker.py`

- [ ] **Step 1: Write failing chunker tests**

```python
# python-tts-backend/tests/test_chunker.py
from app.tts.chunker import build_chunks


def test_build_chunks_with_offsets():
    text = "Xin chao. Day la cau thu hai!"
    chunks = build_chunks(text=text, max_chars=12)

    assert len(chunks) >= 2
    assert chunks[0]["chunk_index"] == 1
    assert chunks[0]["char_start"] == 0
    assert chunks[-1]["char_end"] <= len(text)


def test_build_chunks_empty_text_raises():
    try:
        build_chunks(text="   ", max_chars=200)
    except ValueError as exc:
        assert str(exc) == "text is empty"
    else:
        assert False, "expected ValueError"
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest python-tts-backend/tests/test_chunker.py -v`
Expected: FAIL because chunker module does not exist.

- [ ] **Step 3: Implement chunker**

```python
# python-tts-backend/app/tts/chunker.py
import re


def normalize_text(text: str) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    return value


def build_chunks(text: str, max_chars: int) -> list[dict]:
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("text is empty")

    sentences = re.split(r"(?<=[.!?;])\s+", normalized)
    chunks: list[dict] = []

    current = ""
    current_start = 0
    cursor = 0

    def flush_chunk() -> None:
        nonlocal current, current_start
        if not current:
            return
        chunk_index = len(chunks) + 1
        chunks.append(
            {
                "chunk_index": chunk_index,
                "char_start": current_start,
                "char_end": current_start + len(current),
                "text": current,
            }
        )
        current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_len = len(sentence)
        if not current:
            current = sentence
            current_start = cursor
        elif len(current) + 1 + sentence_len <= max_chars:
            current = f"{current} {sentence}"
        else:
            flush_chunk()
            current = sentence
            current_start = cursor

        cursor += sentence_len + 1

        while len(current) > max_chars:
            overflow = current[max_chars:]
            current = current[:max_chars].rstrip()
            flush_chunk()
            current = overflow.lstrip()
            current_start += max_chars

    flush_chunk()
    return chunks
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest python-tts-backend/tests/test_chunker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/app/tts/chunker.py python-tts-backend/tests/test_chunker.py
git commit -m "feat: add chunker with chunk position metadata"
```

---

### Task 5: Implement Google token manager + response parser + synthesize adapter

**Files:**
- Create: `python-tts-backend/app/tts/token_manager.py`
- Create: `python-tts-backend/app/tts/google_adapter.py`
- Create: `python-tts-backend/tests/test_google_adapter.py`

- [ ] **Step 1: Write failing adapter tests (token parse + payload parse)**

```python
# python-tts-backend/tests/test_google_adapter.py
from app.tts.google_adapter import parse_batchexecute_audio_base64
from app.tts.token_manager import parse_tokens


def test_parse_tokens_from_html():
    html = '"FdrFJe":"fsid123","cfb2h":"bl123","SNlM0e":"at123"'
    tokens = parse_tokens(html)
    assert tokens["f.sid"] == "fsid123"
    assert tokens["bl"] == "bl123"
    assert tokens["at"] == "at123"


def test_parse_batchexecute_payload():
    body = '123\n[["wrb.fr","jQ1olc","[\"BASE64_AUDIO\"]"]]'
    assert parse_batchexecute_audio_base64(body) == "BASE64_AUDIO"
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest python-tts-backend/tests/test_google_adapter.py -v`
Expected: FAIL because adapter modules are missing.

- [ ] **Step 3: Implement token parser + cached token manager + adapter parser**

```python
# python-tts-backend/app/tts/token_manager.py
import re
import time
from dataclasses import dataclass

import requests


def parse_tokens(html: str) -> dict[str, str]:
    fsid = re.search(r'"FdrFJe":"(.*?)"', html)
    bl = re.search(r'"cfb2h":"(.*?)"', html)
    at = re.search(r'"SNlM0e":"(.*?)"', html)
    if not fsid or not bl or not at:
        raise ValueError("cannot parse tokens")
    return {"f.sid": fsid.group(1), "bl": bl.group(1), "at": at.group(1)}


@dataclass
class TokenCache:
    tokens: dict[str, str] | None = None
    expires_at: float = 0.0


class TokenManager:
    def __init__(self, ttl_sec: int, user_agent: str) -> None:
        self.ttl_sec = ttl_sec
        self.user_agent = user_agent
        self.cache = TokenCache()

    def get_tokens(self) -> dict[str, str]:
        now = time.time()
        if self.cache.tokens and now < self.cache.expires_at:
            return self.cache.tokens

        response = requests.get(
            "https://translate.google.com/",
            headers={"User-Agent": self.user_agent},
            timeout=15,
        )
        response.raise_for_status()

        tokens = parse_tokens(response.text)
        self.cache.tokens = tokens
        self.cache.expires_at = now + self.ttl_sec
        return tokens

    def invalidate(self) -> None:
        self.cache = TokenCache()
```

```python
# python-tts-backend/app/tts/google_adapter.py
import json
from urllib.parse import urlencode

import requests


def parse_batchexecute_audio_base64(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("[[") and "jQ1olc" in line:
            outer = json.loads(line)
            payload = outer[0][2]
            inner = json.loads(payload)
            return inner[0]
    raise ValueError("cannot parse batchexecute response")


class GoogleTranslateAdapter:
    def __init__(self, token_manager, request_timeout_sec: int, user_agent: str) -> None:
        self.token_manager = token_manager
        self.request_timeout_sec = request_timeout_sec
        self.user_agent = user_agent

    def synthesize_base64(self, text: str, lang: str, reqid: int) -> str:
        tokens = self.token_manager.get_tokens()
        query = {
            "rpcids": "jQ1olc",
            "f.sid": tokens["f.sid"],
            "bl": tokens["bl"],
            "hl": "en",
            "soc-app": "1",
            "soc-platform": "1",
            "soc-device": "1",
            "_reqid": str(reqid),
            "rt": "c",
        }
        f_req = json.dumps([[ ["jQ1olc", json.dumps([text, lang, None]), None, "generic"] ]])
        body = urlencode({"f.req": f_req, "at": tokens["at"]})

        response = requests.post(
            f"https://translate.google.com/_/TranslateWebserverUi/data/batchexecute?{urlencode(query)}",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "User-Agent": self.user_agent,
            },
            timeout=self.request_timeout_sec,
        )
        response.raise_for_status()
        return parse_batchexecute_audio_base64(response.text)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest python-tts-backend/tests/test_google_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/app/tts/token_manager.py python-tts-backend/app/tts/google_adapter.py python-tts-backend/tests/test_google_adapter.py
git commit -m "feat: add google translate token and synth adapter"
```

---

### Task 6: Implement audio merger and processor pipeline

**Files:**
- Create: `python-tts-backend/app/audio/merger.py`
- Create: `python-tts-backend/app/core/errors.py`
- Create: `python-tts-backend/app/worker/processor.py`
- Create: `python-tts-backend/tests/test_processor.py`

- [ ] **Step 1: Write failing processor tests (progress + success/fail state)**

```python
# python-tts-backend/tests/test_processor.py
from app.worker.processor import process_job


class DummyAdapter:
    def __init__(self):
        self.calls = 0

    def synthesize_base64(self, text: str, lang: str, reqid: int) -> str:
        self.calls += 1
        return "SUQz"  # base64 of small mp3 header bytes placeholder for pipeline test


class DummyMerger:
    def __init__(self):
        self.items = []

    def append_base64_mp3(self, b64: str) -> None:
        self.items.append(b64)

    def export(self, path: str) -> int:
        return 1000


def test_process_job_marks_success(db_session, monkeypatch):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(input_text="Xin chao. Day la test.", lang="vi", voice_hint=None)

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=DummyAdapter(),
        merger=DummyMerger(),
        output_path="outputs/test.mp3",
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert saved.status == "SUCCEEDED"
    assert saved.progress_pct == 100.0
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest python-tts-backend/tests/test_processor.py -v`
Expected: FAIL because processor modules are missing.

- [ ] **Step 3: Implement merger + error codes + processor**

```python
# python-tts-backend/app/core/errors.py
class JobErrorCode:
    INPUT_INVALID = "INPUT_INVALID"
    TOKEN_SCRAPE_FAILED = "TOKEN_SCRAPE_FAILED"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"
    AUDIO_MERGE_FAILED = "AUDIO_MERGE_FAILED"
    STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
```

```python
# python-tts-backend/app/audio/merger.py
import base64
from io import BytesIO

from pydub import AudioSegment


class AudioMerger:
    def __init__(self, silent_between_chunks_ms: int) -> None:
        self.buffer = AudioSegment.empty()
        self.silence = AudioSegment.silent(duration=silent_between_chunks_ms)

    def append_base64_mp3(self, b64: str) -> None:
        raw = base64.b64decode(b64)
        seg = AudioSegment.from_file(BytesIO(raw), format="mp3")
        self.buffer += seg + self.silence

    def export(self, output_path: str) -> int:
        self.buffer.export(output_path, format="mp3")
        return len(self.buffer)
```

```python
# python-tts-backend/app/worker/processor.py
from datetime import datetime, timezone


def process_job(job_id, repo, chunker, adapter, merger, output_path, max_chars):
    job = repo.get_job(job_id)
    if not job:
        return

    repo.mark_running(job_id)
    chunks = chunker(job.input_text, max_chars)
    total_chunks = len(chunks)

    for idx, chunk in enumerate(chunks, start=1):
        b64 = adapter.synthesize_base64(chunk["text"], job.lang, reqid=10000 + idx)
        merger.append_base64_mp3(b64)
        repo.update_progress(
            job_id=job_id,
            total_chunks=total_chunks,
            processed_chunks=idx,
            current_chunk_index=idx,
            current_char_offset=chunk["char_end"],
            total_chars=len(job.input_text),
        )

    duration_ms = merger.export(output_path)
    repo.mark_success(job_id, output_path=output_path, duration_ms=duration_ms)
```

Also add missing methods to `JobRepo`:

```python
# in python-tts-backend/app/db/repo_jobs.py
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

    def mark_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        job.status = "FAILED"
        job.error_code = error_code
        job.error_message = error_message
        job.finished_at = now_iso()
        job.updated_at = now_iso()
        self.db.commit()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest python-tts-backend/tests/test_processor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/app/core/errors.py python-tts-backend/app/audio/merger.py python-tts-backend/app/worker/processor.py python-tts-backend/app/db/repo_jobs.py python-tts-backend/tests/test_processor.py
git commit -m "feat: add job processing pipeline and audio merge"
```

---

### Task 7: Implement sequential worker runner + startup recovery

**Files:**
- Create: `python-tts-backend/app/worker/runner.py`
- Modify: `python-tts-backend/app/main.py`
- Create: `python-tts-backend/tests/test_runner_recovery.py`

- [ ] **Step 1: Write failing recovery test**

```python
# python-tts-backend/tests/test_runner_recovery.py
from app.worker.runner import recover_running_jobs


def test_recover_running_jobs_to_queued(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(input_text="abc", lang="vi", voice_hint=None)
    repo.mark_running(job.job_id)

    recover_running_jobs(repo)

    saved = repo.get_job(job.job_id)
    assert saved.status == "QUEUED"
```

- [ ] **Step 2: Run test to verify fail**

Run: `pytest python-tts-backend/tests/test_runner_recovery.py -v`
Expected: FAIL because runner does not exist.

- [ ] **Step 3: Implement runner loop and app startup wiring**

```python
# python-tts-backend/app/worker/runner.py
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
                    merger = AudioMerger(silent_between_chunks_ms=settings.silent_between_chunks_ms)
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
```

Add `requeue_running_jobs` to repo:

```python
# in python-tts-backend/app/db/repo_jobs.py
from sqlalchemy import select

    def requeue_running_jobs(self) -> None:
        stmt = select(Job).where(Job.status == "RUNNING")
        rows = self.db.execute(stmt).scalars().all()
        for job in rows:
            job.status = "QUEUED"
            job.updated_at = now_iso()
        self.db.commit()
```

Wire startup in app:

```python
# python-tts-backend/app/main.py
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
```

- [ ] **Step 4: Run recovery test to verify pass**

Run: `pytest python-tts-backend/tests/test_runner_recovery.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/app/worker/runner.py python-tts-backend/app/main.py python-tts-backend/app/db/repo_jobs.py python-tts-backend/tests/test_runner_recovery.py
git commit -m "feat: add sequential worker runner and startup recovery"
```

---

### Task 8: Add validation, error mapping, and final end-to-end checks

**Files:**
- Create: `python-tts-backend/app/core/logging.py`
- Modify: `python-tts-backend/app/api/jobs.py`
- Modify: `python-tts-backend/app/worker/processor.py`
- Modify: `python-tts-backend/tests/test_jobs_api.py`

- [ ] **Step 1: Write failing tests for input validation and failed job shape**

```python
# add in python-tts-backend/tests/test_jobs_api.py

def test_post_jobs_rejects_empty_text():
    client = TestClient(app)
    response = client.post("/v1/jobs", json={"text": "", "lang": "vi", "voice_hint": None, "metadata": {}})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify fail (if current schema allows empty)**

Run: `pytest python-tts-backend/tests/test_jobs_api.py -v`
Expected: FAIL for empty input case.

- [ ] **Step 3: Implement final validation/logging/error behavior**

```python
# python-tts-backend/app/core/logging.py
import logging


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger(name)
```

```python
# patch in python-tts-backend/app/worker/processor.py
from app.core.errors import JobErrorCode


def process_job(...):
    try:
        ...
    except ValueError as exc:
        repo.mark_failed(job_id, JobErrorCode.PROVIDER_RESPONSE_INVALID, str(exc))
    except Exception as exc:
        repo.mark_failed(job_id, JobErrorCode.UNEXPECTED_ERROR, str(exc))
```

```python
# patch in python-tts-backend/app/api/jobs.py
# keep CreateJobRequest.text min_length=1 so FastAPI returns 422 for empty text
```

- [ ] **Step 4: Run full test suite**

Run: `pytest python-tts-backend/tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/app/core/logging.py python-tts-backend/app/api/jobs.py python-tts-backend/app/worker/processor.py python-tts-backend/tests/test_jobs_api.py
git commit -m "feat: finalize validation error mapping and test coverage"
```

---

### Task 9: Manual verification checklist (non-test)

**Files:**
- Modify: none

- [ ] **Step 1: Start API**

Run: `uvicorn python-tts-backend.app.main:app --host 127.0.0.1 --port 8000 --reload`
Expected: server starts, worker thread starts once.

- [ ] **Step 2: Create one job**

Run:
```bash
curl -X POST http://127.0.0.1:8000/v1/jobs -H "Content-Type: application/json" -d '{"text":"Xin chao. Day la ban test.","lang":"vi","voice_hint":null,"metadata":{"source":"manual"}}'
```
Expected: `202` with `job_id`.

- [ ] **Step 3: Poll tracking**

Run:
```bash
curl http://127.0.0.1:8000/v1/jobs/<job_id>
```
Expected: transitions `QUEUED -> RUNNING -> SUCCEEDED`, includes `progress.position` and `result.file_name`.

- [ ] **Step 4: Verify output file exists**

Run: `ls python-tts-backend/outputs`
Expected: file `<job_id>.mp3` exists (or under date folder if implemented in code).

- [ ] **Step 5: Commit if any manual-fix changes were made**

```bash
git add <changed-files>
git commit -m "fix: align runtime behavior after manual verification"
```

---

## Self-Review Notes

- **Spec coverage:** Covered API create/track, SQLite persistence, sequential single worker, chunking with position metadata, token cache, adapter parse, retry/error mapping hooks, output file metadata, startup recovery.
- **Placeholder scan:** No TODO/TBD placeholders left.
- **Type consistency:** `job_id`, status enums, progress fields, and repo method names are consistent across tasks.
