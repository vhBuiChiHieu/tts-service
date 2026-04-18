import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
import requests
from PIL import Image, ImageDraw
from pystray import MenuItem as Item

from app.core.config import settings

BASE_URL = f"http://{settings.host}:{settings.port}"
DOCS_URL = f"{BASE_URL}/docs"
APP_URL = f"{BASE_URL}/app"
HEALTH_URL = f"{BASE_URL}/health"
STATUS_URL = f"{BASE_URL}/v1/control/status"
SHUTDOWN_URL = f"{BASE_URL}/v1/control/shutdown"
ROOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROOT_DIR.parent
RUN_BACKEND = ROOT_DIR / "run_backend.py"
OUTPUT_DIR = Path(settings.output_dir).resolve()
BACKEND_LOG = ROOT_DIR / "backend.log"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
STARTUP_TIMEOUT_SEC = 8.0
STARTUP_POLL_INTERVAL_SEC = 0.25


class TrayController:
    def __init__(self) -> None:
        self.icon: pystray.Icon | None = None
        self.status_text = "Stopped"
        self._poll_thread = threading.Thread(target=self._poll_status_loop, daemon=True)
        self._poll_thread.start()

    def _headers(self) -> dict[str, str]:
        if not settings.control_token:
            return {}
        return {"X-Control-Token": settings.control_token}

    def _pythonw(self) -> str:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
        return sys.executable

    def _backend_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)
        env["DB_PATH"] = str((REPO_ROOT / "python-tts-backend" / "data" / "jobs.db").resolve())
        env["OUTPUT_DIR"] = str((REPO_ROOT / "python-tts-backend" / "outputs").resolve())
        if settings.control_token:
            env.setdefault("CONTROL_TOKEN", settings.control_token)
        return env

    def _status_request(self) -> dict | None:
        try:
            response = requests.get(STATUS_URL, timeout=1.5)
            if response.ok:
                return response.json()
        except requests.RequestException:
            return None
        return None

    def _healthcheck(self) -> bool:
        try:
            response = requests.get(HEALTH_URL, timeout=1.5)
            return response.ok
        except requests.RequestException:
            return False

    def _is_backend_running(self) -> bool:
        payload = self._status_request()
        if payload is not None:
            return payload.get("worker_alive") is True
        return self._healthcheck()

    def _wait_for_backend_start(self) -> bool:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SEC
        while time.monotonic() < deadline:
            if self._is_backend_running():
                return True
            time.sleep(STARTUP_POLL_INTERVAL_SEC)
        return False

    def _set_status_text(self, value: str) -> None:
        self.status_text = value
        if self.icon is not None:
            self.icon.title = f"TTS Backend - {self.status_text}"
            self.icon.update_menu()

    def _write_launch_error(self, message: str) -> None:
        BACKEND_LOG.parent.mkdir(parents=True, exist_ok=True)
        BACKEND_LOG.write_text(message, encoding="utf-8")

    def _log_handle(self):
        BACKEND_LOG.parent.mkdir(parents=True, exist_ok=True)
        return BACKEND_LOG.open("ab")

    def _launch_backend(self) -> None:
        env = self._backend_env()
        with self._log_handle() as log_file:
            log_file.write(f"\n=== Tray launch {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode("utf-8"))
            log_file.write(f"python={self._pythonw()}\n".encode("utf-8"))
            log_file.write(f"cwd={ROOT_DIR}\n".encode("utf-8"))
            log_file.write(f"PYTHONPATH={env['PYTHONPATH']}\n".encode("utf-8"))
            log_file.write(f"DB_PATH={env['DB_PATH']}\n".encode("utf-8"))
            log_file.write(f"OUTPUT_DIR={env['OUTPUT_DIR']}\n".encode("utf-8"))
            log_file.flush()
            subprocess.Popen(
                [self._pythonw(), str(RUN_BACKEND)],
                cwd=str(ROOT_DIR),
                env=env,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

    def _start_backend_sync(self) -> None:
        if self._is_backend_running():
            self.refresh_status()
            return

        self._set_status_text("Starting...")
        try:
            self._launch_backend()
        except OSError as exc:
            self._write_launch_error(f"Failed to start backend: {exc}\n")
            self._set_status_text("Start failed")
            return

        if self._wait_for_backend_start():
            self.refresh_status()
            return

        self._set_status_text(f"Start failed (see {BACKEND_LOG.name})")

    def _start_backend_async(self) -> None:
        threading.Thread(target=self._start_backend_sync, daemon=True).start()

    def _open_in_browser(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            self._set_status_text("Open browser failed")
            raise

    def _open_log(self) -> None:
        if BACKEND_LOG.exists():
            os.startfile(str(BACKEND_LOG))

    def _open_api_sync(self) -> None:
        if not self._is_backend_running():
            self._set_status_text("Backend not running")
            self._open_log()
            return
        self._open_in_browser(BASE_URL)

    # Mở giao diện local đơn giản để upload TXT và theo dõi job vừa tạo.
    def _open_app_sync(self) -> None:
        if not self._is_backend_running():
            self._set_status_text("Backend not running")
            self._open_log()
            return
        self._open_in_browser(APP_URL)

    def _open_docs_sync(self) -> None:
        if not self._is_backend_running():
            self._set_status_text("Backend not running")
            self._open_log()
            return
        self._open_in_browser(DOCS_URL)

    def _stop_backend_async(self) -> None:
        threading.Thread(target=self.stop_backend, daemon=True).start()

    def _open_api_async(self) -> None:
        threading.Thread(target=self._open_api_sync, daemon=True).start()

    def _open_app_async(self) -> None:
        threading.Thread(target=self._open_app_sync, daemon=True).start()

    def _open_docs_async(self) -> None:
        threading.Thread(target=self._open_docs_sync, daemon=True).start()

    def _open_outputs_async(self) -> None:
        threading.Thread(target=self.open_outputs, daemon=True).start()

    def _refresh_status_async(self) -> None:
        threading.Thread(target=self.refresh_status, daemon=True).start()

    def _status_item_label(self, item) -> str:
        return f"Status: {self.status_text}"

    def _log_item_label(self, item) -> str:
        return f"Open log ({BACKEND_LOG.name})"

    def _has_log(self, item) -> bool:
        return BACKEND_LOG.exists()

    def _on_menu_error(self, func):
        def wrapper(icon: pystray.Icon | None = None, item=None) -> None:
            try:
                func(icon, item)
            except Exception as exc:
                self._write_launch_error(f"Tray action failed: {exc}\n")
                self._set_status_text("Action failed")

        return wrapper

    def _menu_start(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._start_backend_async()

    def _menu_stop(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._stop_backend_async()

    def _menu_open_api(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._open_api_async()

    def _menu_open_app(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._open_app_async()

    def _menu_open_docs(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._open_docs_async()

    def _menu_open_outputs(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._open_outputs_async()

    def _menu_open_log(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._open_log()

    def _menu_refresh(self, icon: pystray.Icon | None = None, item=None) -> None:
        self._refresh_status_async()

    def _menu_exit(self, icon: pystray.Icon | None = None, item=None) -> None:
        self.exit_tray()

    def _menu_exit_and_stop(self, icon: pystray.Icon | None = None, item=None) -> None:
        self.exit_and_stop()

    def _safe_enabled(self, predicate):
        def wrapper(item) -> bool:
            try:
                return predicate(item)
            except Exception:
                return False

        return wrapper

    def _safe_label(self, label_func):
        def wrapper(item) -> str:
            try:
                return label_func(item)
            except Exception:
                return "Status: unknown"

        return wrapper

    def _safe_default(self, func, fallback: str):
        def wrapper(item) -> str:
            try:
                return func(item)
            except Exception:
                return fallback

        return wrapper

    def _status_menu_item(self):
        return Item(self._safe_default(self._status_item_label, "Status: unknown"), lambda icon, item: None, enabled=False)

    def _log_menu_item(self):
        return Item(
            self._safe_default(self._log_item_label, "Open log"),
            self._on_menu_error(self._menu_open_log),
            enabled=self._safe_enabled(self._has_log),
        )

    def _action_item(self, title: str, callback):
        return Item(title, self._on_menu_error(callback))

    def _separator(self):
        return pystray.Menu.SEPARATOR

    def _build_menu(self):
        return pystray.Menu(
            self._status_menu_item(),
            self._action_item("Start backend", self._menu_start),
            self._action_item("Stop backend", self._menu_stop),
            self._action_item("Open API", self._menu_open_api),
            self._action_item("Giao diện ứng dụng", self._menu_open_app),
            self._action_item("Open Swagger Docs", self._menu_open_docs),
            self._action_item("Open outputs", self._menu_open_outputs),
            self._log_menu_item(),
            self._action_item("Refresh status", self._menu_refresh),
            self._separator(),
            self._action_item("Exit tray", self._menu_exit),
            self._action_item("Exit and stop backend", self._menu_exit_and_stop),
        )

    def _poll_status_loop(self) -> None:
        while True:
            self.refresh_status()
            threading.Event().wait(3)

    def refresh_status(self) -> None:
        payload = self._status_request()
        if payload is not None:
            queued = payload.get("queued", 0)
            running = payload.get("running", 0)
            self._set_status_text(f"Running | queued={queued} running={running}")
            return

        if self._healthcheck():
            self._set_status_text("Running")
            return

        self._set_status_text("Stopped")

    def stop_backend(self, icon: pystray.Icon | None = None, item=None) -> None:
        try:
            requests.post(SHUTDOWN_URL, headers=self._headers(), timeout=2)
        except requests.RequestException:
            pass
        self.refresh_status()

    def open_outputs(self, icon: pystray.Icon | None = None, item=None) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(OUTPUT_DIR))

    def exit_tray(self, icon: pystray.Icon | None = None, item=None) -> None:
        if self.icon is not None:
            self.icon.stop()

    def exit_and_stop(self, icon: pystray.Icon | None = None, item=None) -> None:
        self.stop_backend()
        self.exit_tray()

    def run(self) -> None:
        image = create_icon_image()
        self.icon = pystray.Icon(
            "tts-backend",
            image,
            "TTS Backend",
            menu=self._build_menu(),
        )
        self.refresh_status()
        self.icon.run()


def create_icon_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (32, 32, 32, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(41, 128, 185, 255))
    draw.rectangle((18, 18, 46, 46), fill=(255, 255, 255, 255))
    draw.rectangle((24, 14, 40, 20), fill=(255, 255, 255, 255))
    return image


if __name__ == "__main__":
    TrayController().run()
