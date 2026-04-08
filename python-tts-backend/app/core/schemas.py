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
