from fastapi.testclient import TestClient

from app.main import app


def test_post_jobs_returns_job_id():
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


def test_post_jobs_rejects_empty_text():
    client = TestClient(app)
    response = client.post(
        "/v1/jobs",
        json={"text": "", "lang": "vi", "voice_hint": None, "metadata": {}},
    )
    assert response.status_code == 422
