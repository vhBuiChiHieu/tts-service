import sys
import types

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


def test_app_ui_page_is_served():
    with TestClient(app) as client:
        response = client.get("/app")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Giao diện ứng dụng" in response.text
    assert "/v1/jobs/tts-file-txt" in response.text
    assert "/v1/jobs/" in response.text
    assert "--progress-running: #16a34a;" in response.text
    assert "--progress-success: #2563eb;" in response.text
    assert "--progress-failed: #dc2626;" in response.text
    assert "progressBar.dataset.state = job.status;" in response.text
    assert "progressBar.dataset.state = 'QUEUED';" in response.text
    assert "progressBar.dataset.state = 'FAILED';" in response.text
    assert "progressBar.dataset.state = 'SUCCEEDED';" in response.text
    assert "progress-state-running" in response.text
    assert "progress-state-succeeded" in response.text
    assert "progress-state-failed" in response.text
    assert "job.status === 'RUNNING'" in response.text
    assert "job.status === 'FAILED'" in response.text
    assert "job.status === 'SUCCEEDED'" in response.text


def test_tray_menu_contains_application_ui_item(monkeypatch):
    pystray_stub = types.SimpleNamespace()
    pystray_stub.Menu = lambda *items: items
    pystray_stub.Menu.SEPARATOR = object()
    pystray_stub.Icon = object
    pystray_stub.MenuItem = lambda *args, **kwargs: (args, kwargs)
    monkeypatch.setitem(sys.modules, "pystray", pystray_stub)

    class DummyRequestException(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "requests",
        types.SimpleNamespace(
            get=lambda *args, **kwargs: (_ for _ in ()).throw(DummyRequestException()),
            post=lambda *args, **kwargs: (_ for _ in ()).throw(DummyRequestException()),
            RequestException=DummyRequestException,
        ),
    )

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self.target = kwargs.get("target")

        def start(self):
            return None

        def join(self, timeout=None):
            return None

    monkeypatch.setattr("threading.Thread", DummyThread)

    class DummyImage:
        pass

    class DummyImageModule:
        Image = DummyImage

        @staticmethod
        def new(*args, **kwargs):
            return DummyImage()

    class DummyDrawModule:
        @staticmethod
        def Draw(image):
            return types.SimpleNamespace(rounded_rectangle=lambda *a, **k: None, rectangle=lambda *a, **k: None)

    pil_module = types.ModuleType("PIL")
    pil_module.Image = DummyImageModule
    pil_module.ImageDraw = DummyDrawModule
    monkeypatch.setitem(sys.modules, "PIL", pil_module)
    monkeypatch.setitem(sys.modules, "PIL.Image", DummyImageModule)
    monkeypatch.setitem(sys.modules, "PIL.ImageDraw", DummyDrawModule)

    from windows_tray import TrayController

    controller = TrayController()
    labels = [item[0][0] for item in controller._build_menu() if item is not pystray_stub.Menu.SEPARATOR]

    assert "Giao diện ứng dụng" in labels
    controller._poll_thread.join(timeout=0)
    controller._poll_thread = None
