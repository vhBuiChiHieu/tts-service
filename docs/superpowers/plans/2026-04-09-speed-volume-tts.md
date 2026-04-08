# Speed + Volume Per-Job TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-job `speed` and `volume_gain_db` controls to the Python TTS backend with safe defaults, API validation, DB persistence, volume post-processing, and provider-speed fallback.

**Architecture:** Extend request + DB job model to store `speed` and `volume_gain_db` on each job. Apply `volume_gain_db` in `AudioMerger` (post-processing, deterministic). Pass `speed` into Google adapter and keep job resilient by retrying once with baseline payload (`speed=1.0`) if custom speed payload fails.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy + SQLite, requests, pydub, pytest.

---

## File Structure (target)

- Modify: `python-tts-backend/app/core/schemas.py`
- Modify: `python-tts-backend/app/api/jobs.py`
- Modify: `python-tts-backend/app/db/models.py`
- Modify: `python-tts-backend/app/db/repo_jobs.py`
- Modify: `python-tts-backend/app/audio/merger.py`
- Modify: `python-tts-backend/app/worker/processor.py`
- Modify: `python-tts-backend/app/worker/runner.py`
- Modify: `python-tts-backend/app/tts/google_adapter.py`
- Modify: `python-tts-backend/tests/test_jobs_api.py`
- Modify: `python-tts-backend/tests/test_repo_jobs.py`
- Modify: `python-tts-backend/tests/test_processor.py`
- Create: `python-tts-backend/tests/test_google_adapter_speed.py`

> Note: user chose local reset strategy for DB. After model change, remove `python-tts-backend/data/jobs.db` so schema is recreated by `init_db()`.

---

### Task 1: Add API contract validation for speed/volume

**Files:**
- Modify: `python-tts-backend/tests/test_jobs_api.py`
- Modify: `python-tts-backend/app/core/schemas.py`

- [ ] **Step 1: Write failing API tests for accepted + invalid values**

```python
# python-tts-backend/tests/test_jobs_api.py
from fastapi.testclient import TestClient

from app.main import app


def test_post_jobs_accepts_speed_and_volume():
    client = TestClient(app)
    response = client.post(
        "/v1/jobs",
        json={
            "text": "xin chao",
            "lang": "vi",
            "voice_hint": None,
            "metadata": {},
            "speed": 1.2,
            "volume_gain_db": 3.0,
        },
    )
    assert response.status_code == 202


def test_post_jobs_rejects_invalid_speed():
    client = TestClient(app)
    response = client.post(
        "/v1/jobs",
        json={
            "text": "xin chao",
            "lang": "vi",
            "voice_hint": None,
            "metadata": {},
            "speed": 0.1,
            "volume_gain_db": 0.0,
        },
    )
    assert response.status_code == 422


def test_post_jobs_rejects_invalid_volume_gain_db():
    client = TestClient(app)
    response = client.post(
        "/v1/jobs",
        json={
            "text": "xin chao",
            "lang": "vi",
            "voice_hint": None,
            "metadata": {},
            "speed": 1.0,
            "volume_gain_db": 100.0,
        },
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run: `pytest python-tts-backend/tests/test_jobs_api.py -v`
Expected: FAIL because schema does not include/range-check `speed` and `volume_gain_db`.

- [ ] **Step 3: Add fields + validation with safe defaults**

```python
# python-tts-backend/app/core/schemas.py
from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    text: str = Field(min_length=1)
    lang: str = Field(min_length=2, max_length=10)
    voice_hint: str | None = None
    metadata: dict = Field(default_factory=dict)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    volume_gain_db: float = Field(default=0.0, ge=-20.0, le=20.0)


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

- [ ] **Step 4: Re-run tests and verify pass**

Run: `pytest python-tts-backend/tests/test_jobs_api.py -v`
Expected: PASS for new validation tests.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/tests/test_jobs_api.py python-tts-backend/app/core/schemas.py
git commit -m "feat: validate speed and volume in job request"
```

---

### Task 2: Persist speed/volume in DB model + repository + API mapping

**Files:**
- Modify: `python-tts-backend/tests/test_repo_jobs.py`
- Modify: `python-tts-backend/app/db/models.py`
- Modify: `python-tts-backend/app/db/repo_jobs.py`
- Modify: `python-tts-backend/app/api/jobs.py`

- [ ] **Step 1: Write failing repository persistence test**

```python
# append to python-tts-backend/tests/test_repo_jobs.py

def test_create_job_persists_speed_and_volume(db_session):
    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="xin chao",
        lang="vi",
        voice_hint=None,
        speed=1.3,
        volume_gain_db=5.0,
    )

    saved = repo.get_job(job.job_id)
    assert saved.speed == 1.3
    assert saved.volume_gain_db == 5.0
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run: `pytest python-tts-backend/tests/test_repo_jobs.py -v`
Expected: FAIL because `create_job` signature/model does not include new fields.

- [ ] **Step 3: Add model columns + repo create_job args + API mapping**

```python
# python-tts-backend/app/db/models.py (inside class Job)
speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
volume_gain_db: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
```

```python
# python-tts-backend/app/db/repo_jobs.py
class JobRepo:
    ...
    def create_job(
        self,
        input_text: str,
        lang: str,
        voice_hint: str | None,
        speed: float,
        volume_gain_db: float,
    ) -> Job:
        job = Job(
            input_text=input_text,
            lang=lang,
            voice_hint=voice_hint,
            speed=speed,
            volume_gain_db=volume_gain_db,
            total_chars=len(input_text),
            status="QUEUED",
            updated_at=now_iso(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job
```

```python
# python-tts-backend/app/api/jobs.py (inside create_job)
job = repo.create_job(
    input_text=payload.text,
    lang=payload.lang,
    voice_hint=payload.voice_hint,
    speed=payload.speed,
    volume_gain_db=payload.volume_gain_db,
)
```

Also update existing repo tests/call sites to pass defaults explicitly where needed:

```python
job = repo.create_job(
    input_text="xin chao",
    lang="vi",
    voice_hint=None,
    speed=1.0,
    volume_gain_db=0.0,
)
```

- [ ] **Step 4: Reset local SQLite DB to apply new schema**

Run: `rm -f python-tts-backend/data/jobs.db`
Expected: DB file removed; next app/test init recreates schema including new columns.

- [ ] **Step 5: Re-run tests and verify pass**

Run: `pytest python-tts-backend/tests/test_repo_jobs.py python-tts-backend/tests/test_jobs_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python-tts-backend/app/db/models.py python-tts-backend/app/db/repo_jobs.py python-tts-backend/app/api/jobs.py python-tts-backend/tests/test_repo_jobs.py python-tts-backend/tests/test_jobs_api.py
git commit -m "feat: persist per-job speed and volume settings"
```

---

### Task 3: Apply volume in audio merger and wire processor/runner

**Files:**
- Modify: `python-tts-backend/tests/test_processor.py`
- Modify: `python-tts-backend/app/audio/merger.py`
- Modify: `python-tts-backend/app/worker/processor.py`
- Modify: `python-tts-backend/app/worker/runner.py`

- [ ] **Step 1: Write failing processor test to assert speed forwarding and merger gain wiring**

```python
# python-tts-backend/tests/test_processor.py
from app.worker.processor import process_job


class DummyAdapter:
    def __init__(self):
        self.calls = []

    def synthesize_base64(self, text: str, lang: str, reqid: int, speed: float = 1.0) -> str:
        self.calls.append({"text": text, "lang": lang, "reqid": reqid, "speed": speed})
        return "SUQz"


class DummyMerger:
    def __init__(self):
        self.items = []

    def append_base64_mp3(self, b64: str) -> None:
        self.items.append(b64)

    def export(self, path: str) -> int:
        return 1000


def test_process_job_passes_speed_to_adapter(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="Xin chao. Day la test.",
        lang="vi",
        voice_hint=None,
        speed=1.4,
        volume_gain_db=2.0,
    )

    adapter = DummyAdapter()
    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=adapter,
        merger=DummyMerger(),
        output_path="outputs/test.mp3",
        max_chars=200,
    )

    assert adapter.calls[0]["speed"] == 1.4
```

- [ ] **Step 2: Run targeted test and verify failure**

Run: `pytest python-tts-backend/tests/test_processor.py -v`
Expected: FAIL because processor/adapter call path does not accept speed yet.

- [ ] **Step 3: Implement volume in merger + wire job speed and volume usage**

```python
# python-tts-backend/app/audio/merger.py
import base64
from io import BytesIO

from pydub import AudioSegment


class AudioMerger:
    def __init__(self, silent_between_chunks_ms: int, volume_gain_db: float = 0.0) -> None:
        self.buffer = AudioSegment.empty()
        self.silence = AudioSegment.silent(duration=silent_between_chunks_ms)
        self.volume_gain_db = volume_gain_db

    def append_base64_mp3(self, b64: str) -> None:
        raw = base64.b64decode(b64)
        seg = AudioSegment.from_file(BytesIO(raw), format="mp3")
        if self.volume_gain_db != 0.0:
            seg = seg + self.volume_gain_db
        self.buffer += seg + self.silence

    def export(self, output_path: str) -> int:
        self.buffer.export(output_path, format="mp3")
        return len(self.buffer)
```

```python
# python-tts-backend/app/worker/processor.py (inside chunk loop)
b64 = adapter.synthesize_base64(chunk["text"], job.lang, reqid=10000 + idx, speed=job.speed)
```

```python
# python-tts-backend/app/worker/runner.py (when creating merger)
merger = AudioMerger(
    silent_between_chunks_ms=settings.silent_between_chunks_ms,
    volume_gain_db=job.volume_gain_db,
)
```

- [ ] **Step 4: Re-run targeted tests and verify pass**

Run: `pytest python-tts-backend/tests/test_processor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/tests/test_processor.py python-tts-backend/app/audio/merger.py python-tts-backend/app/worker/processor.py python-tts-backend/app/worker/runner.py
git commit -m "feat: apply volume gain and pass speed through processor"
```

---

### Task 4: Implement Google adapter speed payload + fallback policy

**Files:**
- Create: `python-tts-backend/tests/test_google_adapter_speed.py`
- Modify: `python-tts-backend/app/tts/google_adapter.py`

- [ ] **Step 1: Write failing adapter fallback test**

```python
# python-tts-backend/tests/test_google_adapter_speed.py
import json

from app.tts.google_adapter import GoogleTranslateAdapter


class DummyTokenManager:
    def get_tokens(self):
        return {"f.sid": "fsid", "bl": "bl", "at": "at"}


def test_adapter_fallbacks_to_default_speed_when_custom_payload_invalid(monkeypatch):
    adapter = GoogleTranslateAdapter(token_manager=DummyTokenManager(), request_timeout_sec=20, user_agent="ua")

    calls = {"count": 0}

    class DummyResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            # first response cannot be parsed -> should trigger fallback
            return DummyResponse("not-parseable")
        return DummyResponse('123\n[["wrb.fr","jQ1olc","[\\"BASE64_AUDIO\\"]"]]')

    monkeypatch.setattr("app.tts.google_adapter.requests.post", fake_post)

    audio = adapter.synthesize_base64("xin chao", "vi", reqid=10001, speed=1.3)
    assert audio == "BASE64_AUDIO"
    assert calls["count"] == 2
```

- [ ] **Step 2: Run targeted test and verify failure**

Run: `pytest python-tts-backend/tests/test_google_adapter_speed.py -v`
Expected: FAIL because adapter has no `speed` parameter/fallback logic.

- [ ] **Step 3: Implement speed-aware request + one-time fallback to baseline**

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

    def _build_rpc_payload(self, text: str, lang: str, speed: float) -> str:
        # Custom-speed variant first; baseline remains [text, lang, None]
        if speed == 1.0:
            inner = [text, lang, None]
        else:
            inner = [text, lang, None, speed]
        return json.dumps([[["jQ1olc", json.dumps(inner), None, "generic"]]])

    def _post_batchexecute(self, f_req: str, reqid: int) -> str:
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
        return response.text

    def synthesize_base64(self, text: str, lang: str, reqid: int, speed: float = 1.0) -> str:
        # Attempt custom speed first; fallback to baseline only when parse fails.
        f_req = self._build_rpc_payload(text, lang, speed)
        response_text = self._post_batchexecute(f_req=f_req, reqid=reqid)
        try:
            return parse_batchexecute_audio_base64(response_text)
        except ValueError:
            if speed == 1.0:
                raise

        fallback_f_req = self._build_rpc_payload(text, lang, 1.0)
        fallback_response = self._post_batchexecute(f_req=fallback_f_req, reqid=reqid)
        return parse_batchexecute_audio_base64(fallback_response)
```

- [ ] **Step 4: Run adapter tests and verify pass**

Run: `pytest python-tts-backend/tests/test_google_adapter.py python-tts-backend/tests/test_google_adapter_speed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-tts-backend/tests/test_google_adapter_speed.py python-tts-backend/app/tts/google_adapter.py
git commit -m "feat: add speed payload with safe adapter fallback"
```

---

### Task 5: Full verification + manual sanity check

**Files:**
- No code changes expected unless verification fails

- [ ] **Step 1: Run full backend test suite**

Run: `pytest python-tts-backend/tests -v`
Expected: PASS for all tests.

- [ ] **Step 2: Start app and create sample job (speed+volume)**

Run:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir python-tts-backend
```
In another shell run:
```bash
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"text":"Xin chao day la ban thu nghiem","lang":"vi","speed":1.3,"volume_gain_db":5.0,"metadata":{}}'
```
Expected: `202` and `{"status":"QUEUED", ...}`.

- [ ] **Step 3: Verify tracking and output file**

Run:
```bash
curl http://127.0.0.1:8000/v1/jobs/<job_id>
```
Expected: status transitions to `SUCCEEDED`; file exists at `python-tts-backend/outputs/<job_id>.mp3`.

- [ ] **Step 4: Quick audio sanity comparison**

- Create two jobs same text:
  - A: defaults (`speed=1.0`, `volume_gain_db=0.0`)
  - B: modified (`speed>1.0`, `volume_gain_db>0.0`)
- Verify B is shorter duration (or fallback to baseline if provider rejects custom speed) and sounds louder.

- [ ] **Step 5: Final commit (if any verification-driven fix applied)**

```bash
git add <changed-files>
git commit -m "test: finalize verification for speed and volume controls"
```

(If no code changes were required during verification, skip this commit.)

---

## Self-Review Notes

- Spec coverage: API validation, DB persistence, volume processing, adapter speed fallback, verification checklist are all covered.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: `speed: float`, `volume_gain_db: float`, adapter signature includes `speed` in all relevant call paths.
