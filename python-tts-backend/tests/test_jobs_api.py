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
