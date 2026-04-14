from fastapi.testclient import TestClient

from app.main import app


def test_control_status_returns_runtime_snapshot():
    with TestClient(app) as client:
        response = client.get("/v1/control/status")

    assert response.status_code == 200
    body = response.json()
    assert body["pid"] > 0
    assert body["worker_alive"] is True
    assert body["stop_requested"] is False
    assert body["queued"] >= 0
    assert body["running"] >= 0
    assert body["client_host"] == "testclient"


def test_control_shutdown_returns_stopping_and_sets_flag():
    with TestClient(app) as client:
        response = client.post("/v1/control/shutdown")
        status = client.get("/v1/control/status")

    assert response.status_code == 200
    assert response.json() == {"status": "stopping"}
    assert status.status_code == 200
    assert status.json()["stop_requested"] is True
