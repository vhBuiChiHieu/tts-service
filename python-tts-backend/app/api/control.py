import threading
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal
from app.worker.runner import get_worker_status

router = APIRouter(prefix="/v1/control", tags=["control"])
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _get_client_host(request: Request) -> str:
    if request.client is None or request.client.host is None:
        return ""
    return request.client.host


def _require_loopback(request: Request) -> str:
    host = _get_client_host(request)
    if host not in _LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="control API is only available from localhost")
    return host


def _validate_token(token: str | None) -> None:
    if settings.control_token and token != settings.control_token:
        raise HTTPException(status_code=403, detail="invalid control token")


def _request_shutdown(app) -> None:
    runtime = getattr(app.state, "runtime", None)
    if runtime is not None:
        runtime.request_stop()

    server = getattr(app.state, "server", None)
    if server is not None:
        server.should_exit = True
        return

    def _delayed_exit() -> None:
        import os

        os._exit(0)

    threading.Timer(0.2, _delayed_exit).start()


@router.get("/status")
def control_status(request: Request) -> dict[str, Any]:
    host = _require_loopback(request)
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        return {
            "pid": None,
            "worker_alive": False,
            "stop_requested": False,
            "uptime_sec": 0.0,
            "queued": 0,
            "running": 0,
            "client_host": host,
        }

    with SessionLocal() as db:
        repo = JobRepo(db)
        payload = get_worker_status(runtime, repo)

    payload["client_host"] = host
    return payload


@router.post("/shutdown")
def control_shutdown(
    request: Request,
    x_control_token: str | None = Header(default=None),
) -> dict[str, str]:
    _require_loopback(request)
    _validate_token(x_control_token)
    _request_shutdown(request.app)
    return {"status": "stopping"}
