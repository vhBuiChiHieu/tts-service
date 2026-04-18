from fastapi.testclient import TestClient

from app.main import app
from app.db.session import init_db


def test_post_jobs_returns_job_id():
    init_db()
    client = TestClient(app)

    payload = {"text": "xin chao", "lang": "vi", "voice_hint": None, "metadata": {"source": "chapter-1"}}
    response = client.post("/v1/jobs", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert "job_id" in body
    assert body["status"] == "QUEUED"


def test_get_job_not_found():
    init_db()
    client = TestClient(app)
    response = client.get("/v1/jobs/not-found")
    assert response.status_code == 404


def test_get_job_returns_tracking_payload():
    from app.db.repo_jobs import JobRepo
    from app.db.session import SessionLocal

    init_db()
    with SessionLocal() as db:
        repo = JobRepo(db)
        job = repo.create_job(
            input_text="xin chao",
            lang="vi",
            voice_hint=None,
            speed=1.0,
            volume_gain_db=0.0,
        )

    client = TestClient(app)
    response = client.get(f"/v1/jobs/{job.job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job.job_id
    assert body["status"] == "QUEUED"
    assert body["progress"]["processed_chunks"] == 0


def test_post_jobs_retry_requeues_failed_job():
    from app.db.repo_jobs import JobRepo
    from app.db.session import SessionLocal

    init_db()
    with SessionLocal() as db:
        repo = JobRepo(db)
        job = repo.create_job(
            input_text="xin chao",
            lang="vi",
            voice_hint=None,
            speed=1.0,
            volume_gain_db=0.0,
        )
        repo.update_progress(
            job_id=job.job_id,
            total_chunks=3,
            processed_chunks=1,
            current_chunk_index=1,
            current_char_offset=3,
            total_chars=len(job.input_text),
        )
        repo.mark_failed(job.job_id, "UNEXPECTED_ERROR", "partial exists")

    client = TestClient(app)
    response = client.post(f"/v1/jobs/retry/{job.job_id}")

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == job.job_id
    assert body["status"] == "QUEUED"

    with SessionLocal() as db:
        repo = JobRepo(db)
        saved = repo.get_job(job.job_id)

    assert saved.status == "QUEUED"
    assert saved.processed_chunks == 1
    assert saved.error_code is None
    assert saved.error_message is None
    assert saved.finished_at is None


def test_post_jobs_rejects_empty_text():
    init_db()
    client = TestClient(app)
    response = client.post(
        "/v1/jobs",
        json={"text": "", "lang": "vi", "voice_hint": None, "metadata": {}},
    )
    assert response.status_code == 422


def test_post_jobs_accepts_speed_and_volume():
    init_db()
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
    init_db()
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
    init_db()
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


def test_post_jobs_sangtacviet_returns_job_id():
    init_db()
    client = TestClient(app)

    payload = {
        "book_id": "7577371088154266649",
        "range": {"start": 200, "end": 202},
        "lang": "vi",
        "voice_hint": None,
        "metadata": {},
        "speed": 1.2,
        "volume_gain_db": 3.0,
        "chapters": [
            {"chapter_number": 200, "text": "A"},
            {"chapter_number": 201, "text": "B"},
            {"chapter_number": 202, "text": "C"},
        ],
    }

    response = client.post("/v1/jobs/sangtacviet", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert "job_id" in body
    assert body["status"] == "QUEUED"


def test_post_jobs_sangtacviet_rejects_invalid_range():
    init_db()
    client = TestClient(app)
    response = client.post(
        "/v1/jobs/sangtacviet",
        json={
            "book_id": "1",
            "range": {"start": 202, "end": 200},
            "chapters": [{"text": "x"}],
            "lang": "vi",
        },
    )
    assert response.status_code == 422


def test_post_jobs_sangtacviet_rejects_empty_chapters():
    init_db()
    client = TestClient(app)
    response = client.post(
        "/v1/jobs/sangtacviet",
        json={
            "book_id": "1",
            "range": {"start": 200, "end": 202},
            "chapters": [],
            "lang": "vi",
        },
    )
    assert response.status_code == 422


def test_post_jobs_sangtacviet_rejects_blank_chapter_text():
    init_db()
    client = TestClient(app)
    response = client.post(
        "/v1/jobs/sangtacviet",
        json={
            "book_id": "1",
            "range": {"start": 200, "end": 202},
            "chapters": [{"text": "   "}],
            "lang": "vi",
        },
    )
    assert response.status_code == 422


def test_post_jobs_sangtacviet_persists_joined_text_and_output_prefix():
    from app.db.repo_jobs import JobRepo
    from app.db.session import SessionLocal

    init_db()
    client = TestClient(app)

    payload = {
        "book_id": "7577371088154266649",
        "range": {"start": 200, "end": 202},
        "chapters": [{"text": "A"}, {"text": "B"}, {"text": "C"}],
        "lang": "vi",
    }
    response = client.post("/v1/jobs/sangtacviet", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    with SessionLocal() as db:
        repo = JobRepo(db)
        job = repo.get_job(job_id)

    assert job.input_text == "A B C"
    assert job.output_prefix == "7577371088154266649-200-202"
