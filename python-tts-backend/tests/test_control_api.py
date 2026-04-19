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
    assert "Local TTS Service" in response.text
    assert "/app-static/app.css" in response.text
    assert "/app-static/app.js" in response.text
    assert "Tạo job" in response.text
    assert "Danh sách job" in response.text
    assert "tracking-drawer" in response.text
    assert "page-size" in response.text
    assert "prev-page" in response.text
    assert "next-page" in response.text
    assert "Mở file output" in response.text


def test_app_ui_script_contains_tabs_and_pagination_logic():
    with TestClient(app) as client:
        response = client.get("/app-static/app.js")

    assert response.status_code == 200
    assert "activateTab" in response.text
    assert "updatePaginationControls" in response.text
    assert "pageSizeSelect" in response.text
    assert "prevPageButton" in response.text
    assert "nextPageButton" in response.text
    assert "trackingDrawer" in response.text


def test_app_ui_styles_contain_tabs_and_drawer_layout():
    with TestClient(app) as client:
        response = client.get("/app-static/app.css")

    assert response.status_code == 200
    assert ".tabs" in response.text
    assert ".tab-button" in response.text
    assert ".jobs-layout" in response.text
    assert ".tracking-drawer" in response.text
    assert ".pagination-bar" in response.text


def test_app_static_assets_are_served():
    with TestClient(app) as client:
        css_response = client.get("/app-static/app.css")
        js_response = client.get("/app-static/app.js")

    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
    assert ".jobs-list" in css_response.text
    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]
    assert "loadJobs" in js_response.text
    assert "statusFilter" in js_response.text


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
