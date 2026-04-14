from pydantic import BaseModel, Field, model_validator


class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable error detail.")


class HealthResponse(BaseModel):
    status: str = Field(description="Service health status.", examples=["ok"])


class CreateJobRequest(BaseModel):
    text: str = Field(min_length=1, description="Input text to synthesize into a single MP3 output.")
    lang: str = Field(min_length=2, max_length=10, description="Target language code.", examples=["vi"])
    voice_hint: str | None = Field(default=None, description="Optional provider-specific voice hint.")
    metadata: dict = Field(default_factory=dict, description="Optional client metadata reserved for future use.")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Playback speed applied during final audio export.")
    volume_gain_db: float = Field(default=0.0, ge=-20.0, le=20.0, description="Volume gain in decibels applied before export.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "Xin chao. Day la ban test cho Swagger docs.",
                "lang": "vi",
                "voice_hint": None,
                "metadata": {"source": "demo"},
                "speed": 1.1,
                "volume_gain_db": 2.5,
            }
        }
    }


class SangTacVietRange(BaseModel):
    start: int = Field(description="First chapter number in the submitted range.", examples=[200])
    end: int = Field(description="Last chapter number in the submitted range.", examples=[202])

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.start > self.end:
            raise ValueError("range.start must be <= range.end")
        return self


class SangTacVietChapter(BaseModel):
    chapter_number: int | None = Field(default=None, description="Optional chapter number for client-side bookkeeping.", examples=[200])
    text: str = Field(min_length=1, description="Chapter text. All chapter texts are merged with a single space before enqueueing.")


class SangTacVietCreateJobRequest(BaseModel):
    book_id: str = Field(min_length=1, description="Sáng Tác Việt book identifier used to prefix the output file name.")
    range: SangTacVietRange
    chapters: list[SangTacVietChapter] = Field(min_length=1, description="Ordered chapter payloads to merge into one TTS job.")
    lang: str = Field(default="vi", min_length=2, max_length=10, description="Target language code.")
    voice_hint: str | None = Field(default=None, description="Optional provider-specific voice hint.")
    metadata: dict = Field(default_factory=dict, description="Optional client metadata reserved for future use.")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Playback speed applied during final audio export.")
    volume_gain_db: float = Field(default=0.0, ge=-20.0, le=20.0, description="Volume gain in decibels applied before export.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "book_id": "7577371088154266649",
                "range": {"start": 200, "end": 202},
                "chapters": [
                    {"chapter_number": 200, "text": "Doan 1"},
                    {"chapter_number": 201, "text": "Doan 2"},
                    {"chapter_number": 202, "text": "Doan 3"},
                ],
                "lang": "vi",
                "voice_hint": None,
                "metadata": {"source": "sangtacviet"},
                "speed": 1.0,
                "volume_gain_db": 0.0,
            }
        }
    }


class CreateJobResponse(BaseModel):
    job_id: str = Field(description="Unique identifier of the queued job.")
    status: str = Field(description="Initial job status.", examples=["QUEUED"])
    created_at: str = Field(description="Creation timestamp in ISO-8601 format.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "8a83b11c-3c0d-4fe4-a4f2-bf9c661251db",
                "status": "QUEUED",
                "created_at": "2026-04-15T08:30:00Z",
            }
        }
    }


class JobPositionResponse(BaseModel):
    current_chunk_index: int = Field(description="1-based index of the chunk currently being processed.")
    current_char_offset: int = Field(description="Character offset reached in the merged input text.")
    total_chars: int = Field(description="Total number of characters in the input text.")


class JobProgressResponse(BaseModel):
    total_chunks: int = Field(description="Total number of chunks created from the input text.")
    processed_chunks: int = Field(description="Number of chunks processed so far.")
    progress_pct: float = Field(description="Completion percentage from 0 to 100.")
    position: JobPositionResponse


class JobResultResponse(BaseModel):
    file_name: str | None = Field(default=None, description="Output MP3 file name when the job succeeds.")
    file_path: str | None = Field(default=None, description="Resolved output path when the job succeeds.")
    duration_ms: int | None = Field(default=None, description="Final audio duration in milliseconds.")


class JobErrorResponse(BaseModel):
    code: str | None = Field(default=None, description="Machine-readable failure code.")
    message: str | None = Field(default=None, description="Human-readable failure detail.")


class JobTrackingResponse(BaseModel):
    job_id: str = Field(description="Unique identifier of the job.")
    status: str = Field(description="Current job status.", examples=["RUNNING"])
    progress: JobProgressResponse
    result: JobResultResponse
    error: JobErrorResponse | None = Field(default=None, description="Failure payload when the job does not succeed.")
    created_at: str = Field(description="Creation timestamp in ISO-8601 format.")
    started_at: str | None = Field(default=None, description="Processing start timestamp in ISO-8601 format.")
    updated_at: str = Field(description="Last update timestamp in ISO-8601 format.")
    finished_at: str | None = Field(default=None, description="Completion timestamp in ISO-8601 format.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "8a83b11c-3c0d-4fe4-a4f2-bf9c661251db",
                "status": "SUCCEEDED",
                "progress": {
                    "total_chunks": 3,
                    "processed_chunks": 3,
                    "progress_pct": 100.0,
                    "position": {
                        "current_chunk_index": 3,
                        "current_char_offset": 128,
                        "total_chars": 128,
                    },
                },
                "result": {
                    "file_name": "8a83b11c-3c0d-4fe4-a4f2-bf9c661251db.mp3",
                    "file_path": "python-tts-backend/outputs/8a83b11c-3c0d-4fe4-a4f2-bf9c661251db.mp3",
                    "duration_ms": 5120,
                },
                "error": None,
                "created_at": "2026-04-15T08:30:00Z",
                "started_at": "2026-04-15T08:30:02Z",
                "updated_at": "2026-04-15T08:30:07Z",
                "finished_at": "2026-04-15T08:30:07Z",
            }
        }
    }


class ControlStatusResponse(BaseModel):
    pid: int | None = Field(description="Backend process ID.")
    worker_alive: bool = Field(description="Whether the background worker thread is alive.")
    stop_requested: bool = Field(description="Whether a graceful shutdown has been requested.")
    uptime_sec: float = Field(description="Backend uptime in seconds.")
    queued: int = Field(description="Number of queued jobs.")
    running: int = Field(description="Number of currently running jobs.")
    client_host: str = Field(description="Detected caller host used for loopback validation.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "pid": 17244,
                "worker_alive": True,
                "stop_requested": False,
                "uptime_sec": 42.17,
                "queued": 1,
                "running": 0,
                "client_host": "127.0.0.1",
            }
        }
    }


class ControlShutdownResponse(BaseModel):
    status: str = Field(description="Shutdown request status.", examples=["stopping"])

    model_config = {"json_schema_extra": {"example": {"status": "stopping"}}}


class LocalhostOnlyErrorResponse(BaseModel):
    detail: str = Field(description="Control API access error.", examples=["control API is only available from localhost"])


class InvalidControlTokenErrorResponse(BaseModel):
    detail: str = Field(description="Invalid control token error.", examples=["invalid control token"])


class JobNotFoundErrorResponse(BaseModel):
    detail: str = Field(description="Job lookup error.", examples=["job not found"])


class ValidationErrorResponse(BaseModel):
    detail: str | list[dict] = Field(description="Validation or domain error returned by FastAPI.")

    model_config = {"json_schema_extra": {"example": {"detail": "chapter text must be non-empty"}}}


OPENAPI_TAGS = [
    {"name": "jobs", "description": "Create text-to-speech jobs and track asynchronous processing state."},
    {"name": "control", "description": "Local-only control endpoints used by the Windows tray app to inspect status and request graceful shutdown."},
    {"name": "system", "description": "Basic service health endpoints."},
]

API_TITLE = "Python Local TTS Backend"
API_SUMMARY = "Asynchronous local TTS backend with queue-based job processing and Windows tray control support."
API_DESCRIPTION = """
Local TTS backend built with FastAPI, SQLite, and an in-process worker thread.

Workflow:
1. Submit a job with `POST /v1/jobs` or `POST /v1/jobs/sangtacviet`.
2. Poll `GET /v1/jobs/{job_id}` for progress and output details.
3. Use the local-only control API for tray integration and graceful shutdown.
""".strip()
API_VERSION = "0.1.0"
API_CONTACT = {"name": "Local TTS Backend", "url": "https://github.com/vhBuiChiHieu/tts-service"}
API_LICENSE = {"name": "MIT"}
API_SERVERS = [{"url": "http://127.0.0.1:8000", "description": "Default local development server"}]

JOB_ID_EXAMPLE = "8a83b11c-3c0d-4fe4-a4f2-bf9c661251db"
JOB_ID_DESCRIPTION = "Unique job identifier returned by the create-job endpoints."
CONTROL_TOKEN_DESCRIPTION = "Optional control token. Required only when the backend is configured with CONTROL_TOKEN."

CREATE_JOB_SUMMARY = "Create a TTS job"
CREATE_JOB_DESCRIPTION = "Queue a standard text-to-speech job. Text is chunked internally, synthesized asynchronously, and merged into one MP3 output file."
SANGTACVIET_SUMMARY = "Create a Sáng Tác Việt batch job"
SANGTACVIET_DESCRIPTION = "Submit a merged Sáng Tác Việt chapter batch as one asynchronous TTS job. Chapter texts are merged with a single space before queueing, and the output filename is prefixed with `{book_id}-{start}-{end}`."
TRACK_JOB_SUMMARY = "Get job status"
TRACK_JOB_DESCRIPTION = "Poll the current state of a queued, running, succeeded, or failed job."
CONTROL_STATUS_SUMMARY = "Get backend control status"
CONTROL_STATUS_DESCRIPTION = "Return a runtime snapshot for the backend process and worker queue. Available only from localhost (`127.0.0.1`, `::1`, `localhost`)."
CONTROL_SHUTDOWN_SUMMARY = "Request backend shutdown"
CONTROL_SHUTDOWN_DESCRIPTION = "Request a graceful shutdown of the backend worker and process. Available only from localhost and may require `X-Control-Token` when `CONTROL_TOKEN` is configured."
HEALTH_SUMMARY = "Health check"
HEALTH_DESCRIPTION = "Returns a simple liveness response for local health checks and service monitoring."

CREATE_JOB_OPERATION_ID = "create_tts_job"
SANGTACVIET_OPERATION_ID = "create_sangtacviet_job"
TRACK_JOB_OPERATION_ID = "get_job_status"
CONTROL_STATUS_OPERATION_ID = "get_control_status"
CONTROL_SHUTDOWN_OPERATION_ID = "request_backend_shutdown"
HEALTH_OPERATION_ID = "get_health_status"

JOB_BODY_EXAMPLES = {
    "basic": {
        "summary": "Basic TTS job",
        "description": "Queue one text payload and let the worker build a single MP3 file.",
        "value": CreateJobRequest.model_config["json_schema_extra"]["example"],
    }
}

SANGTACVIET_BODY_EXAMPLES = {
    "chapter_batch": {
        "summary": "Merged chapter batch",
        "description": "Chapter texts are merged with a single space before the job is queued.",
        "value": SangTacVietCreateJobRequest.model_config["json_schema_extra"]["example"],
    }
}

JOB_CREATE_RESPONSES = {
    202: {
        "description": "Job accepted and queued for asynchronous processing.",
        "content": {"application/json": {"example": CreateJobResponse.model_config["json_schema_extra"]["example"]}},
    },
    422: {
        "model": ValidationErrorResponse,
        "description": "Request validation failed.",
        "content": {"application/json": {"example": {"detail": "chapter text must be non-empty"}}},
    },
}

SANGTACVIET_RESPONSES = {
    202: {
        "description": "Merged chapter payload accepted and queued for asynchronous processing.",
        "content": {"application/json": {"example": CreateJobResponse.model_config["json_schema_extra"]["example"]}},
    },
    422: {
        "model": ValidationErrorResponse,
        "description": "Chapter payload failed validation or merged text was empty.",
        "content": {"application/json": {"example": {"detail": "merged chapter text is empty"}}},
    },
}

JOB_TRACKING_RESPONSES = {
    200: {
        "description": "Current tracking snapshot for the requested job.",
        "content": {"application/json": {"example": JobTrackingResponse.model_config["json_schema_extra"]["example"]}},
    },
    404: {
        "model": JobNotFoundErrorResponse,
        "description": "Job ID was not found.",
        "content": {"application/json": {"example": {"detail": "job not found"}}},
    },
}

CONTROL_STATUS_RESPONSES = {
    200: {
        "description": "Runtime snapshot for the backend process and worker queue.",
        "content": {"application/json": {"example": ControlStatusResponse.model_config["json_schema_extra"]["example"]}},
    },
    403: {
        "model": LocalhostOnlyErrorResponse,
        "description": "The control API only accepts loopback requests.",
        "content": {"application/json": {"example": {"detail": "control API is only available from localhost"}}},
    },
}

CONTROL_SHUTDOWN_RESPONSES = {
    200: {
        "description": "Graceful shutdown has been requested.",
        "content": {"application/json": {"example": ControlShutdownResponse.model_config["json_schema_extra"]["example"]}},
    },
    403: {
        "description": "Caller is not localhost or the control token is invalid.",
        "content": {
            "application/json": {
                "examples": {
                    "localhost_only": {"summary": "Non-loopback caller", "value": {"detail": "control API is only available from localhost"}},
                    "invalid_token": {"summary": "Invalid control token", "value": {"detail": "invalid control token"}},
                }
            }
        },
    },
}

HEALTH_RESPONSES = {
    200: {
        "description": "Backend health status.",
        "content": {"application/json": {"example": {"status": "ok"}}},
    }
}
