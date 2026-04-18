from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.control import router as control_router
from app.api.jobs import router as jobs_router
from app.core.config import settings
from app.core.schemas import (
    API_CONTACT,
    API_DESCRIPTION,
    API_LICENSE,
    API_SERVERS,
    API_SUMMARY,
    API_TITLE,
    API_VERSION,
    HEALTH_DESCRIPTION,
    HEALTH_OPERATION_ID,
    HEALTH_RESPONSES,
    HEALTH_SUMMARY,
    HealthResponse,
    OPENAPI_TAGS,
)
from app.db.repo_jobs import JobRepo
from app.db.session import SessionLocal, init_db
from app.worker.runner import recover_running_jobs, start_worker, stop_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        repo = JobRepo(db)
        recover_running_jobs(repo)

    app.state.runtime = start_worker()
    try:
        yield
    finally:
        runtime = getattr(app.state, "runtime", None)
        if runtime is not None:
            stop_worker(runtime, timeout=settings.control_shutdown_timeout_sec)


app = FastAPI(
    title=API_TITLE,
    summary=API_SUMMARY,
    description=API_DESCRIPTION,
    version=API_VERSION,
    contact=API_CONTACT,
    license_info=API_LICENSE,
    servers=API_SERVERS,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)
app.state.runtime = None
app.include_router(jobs_router)
app.include_router(control_router)


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
def application_ui() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Giao diện ứng dụng</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px auto; max-width: 720px; line-height: 1.5; color: #1f2937; }
    h1 { margin-bottom: 24px; }
    form { display: grid; gap: 16px; padding: 20px; border: 1px solid #d1d5db; border-radius: 12px; }
    label { display: grid; gap: 8px; font-weight: 600; }
    input, button { font: inherit; }
    input[type="number"], input[type="file"] { padding: 10px; }
    button { width: fit-content; padding: 10px 18px; cursor: pointer; }
    :root { --progress-running: #16a34a; --progress-success: #2563eb; --progress-failed: #dc2626; }
    progress { width: 100%; height: 18px; accent-color: var(--progress-running); }
    progress.progress-state-running { accent-color: var(--progress-running); }
    progress.progress-state-succeeded { accent-color: var(--progress-success); }
    progress.progress-state-failed { accent-color: var(--progress-failed); }
    .panel { margin-top: 20px; padding: 20px; border: 1px solid #d1d5db; border-radius: 12px; }
    .muted { color: #6b7280; }
    .hidden { display: none; }
    .error { color: #b91c1c; }
    .success { color: #15803d; }
  </style>
</head>
<body>
  <h1>Giao diện ứng dụng</h1>
  <form id="tts-form">
    <label>
      File TXT
      <input id="file" name="file" type="file" accept=".txt,text/plain" required>
    </label>
    <label>
      Speed
      <input id="speed" name="speed" type="number" min="0.5" max="2" step="0.1" value="1.0" required>
    </label>
    <button id="submit" type="submit">Tạo job</button>
  </form>

  <div id="tracking" class="panel hidden">
    <div><strong>Job ID:</strong> <span id="job-id"></span></div>
    <div><strong>Trạng thái:</strong> <span id="status">-</span></div>
    <div style="margin-top: 12px;">
      <progress id="progress" value="0" max="100"></progress>
      <div id="progress-text" class="muted">0%</div>
    </div>
    <div id="result" class="muted" style="margin-top: 12px;"></div>
    <div id="error" class="error" style="margin-top: 12px;"></div>
  </div>

  <script>
    const form = document.getElementById('tts-form');
    const fileInput = document.getElementById('file');
    const speedInput = document.getElementById('speed');
    const submitButton = document.getElementById('submit');
    const tracking = document.getElementById('tracking');
    const jobIdText = document.getElementById('job-id');
    const statusText = document.getElementById('status');
    const progressBar = document.getElementById('progress');
    const progressText = document.getElementById('progress-text');
    const resultText = document.getElementById('result');
    const errorText = document.getElementById('error');

    let pollTimer = null;

    function stopPolling() {
      if (pollTimer !== null) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    function setProgressState(state) {
      progressBar.dataset.state = state;
      progressBar.classList.remove('progress-state-running', 'progress-state-succeeded', 'progress-state-failed');

      if (state === 'RUNNING') {
        progressBar.classList.add('progress-state-running');
      }

      if (state === 'SUCCEEDED') {
        progressBar.classList.add('progress-state-succeeded');
      }

      if (state === 'FAILED') {
        progressBar.classList.add('progress-state-failed');
      }
    }

    function updateTracking(job) {
      tracking.classList.remove('hidden');
      jobIdText.textContent = job.job_id;
      statusText.textContent = job.status;
      const progress = Math.max(0, Math.min(100, job.progress?.progress_pct ?? 0));
      progressBar.value = progress;
      progressText.textContent = `${progress}%`;
      progressBar.dataset.state = job.status;
      setProgressState(job.status);

      if (job.status === 'SUCCEEDED') {
        progressBar.dataset.state = 'SUCCEEDED';
        setProgressState('SUCCEEDED');
        resultText.textContent = job.result?.file_path ? `Hoàn thành: ${job.result.file_path}` : 'Hoàn thành';
        resultText.className = 'success';
        errorText.textContent = '';
        stopPolling();
        submitButton.disabled = false;
        return;
      }

      if (job.status === 'FAILED') {
        progressBar.dataset.state = 'FAILED';
        setProgressState('FAILED');
        errorText.textContent = job.error?.message || 'Job thất bại';
        resultText.textContent = '';
        stopPolling();
        submitButton.disabled = false;
        return;
      }

      if (job.status === 'RUNNING') {
        setProgressState('RUNNING');
      }

      resultText.textContent = '';
      errorText.textContent = '';
    }

    async function fetchJob(jobId) {
      const response = await fetch(`/v1/jobs/${jobId}`);
      if (!response.ok) {
        throw new Error('Không lấy được trạng thái job');
      }
      const job = await response.json();
      updateTracking(job);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      stopPolling();
      errorText.textContent = '';
      resultText.textContent = '';
      submitButton.disabled = true;

      const file = fileInput.files[0];
      const speed = speedInput.value;
      const formData = new FormData();
      formData.append('file', file);

      try {
        const response = await fetch(`/v1/jobs/tts-file-txt?speed=${encodeURIComponent(speed)}`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || 'Không tạo được job');
        }

        const created = await response.json();
        tracking.classList.remove('hidden');
        jobIdText.textContent = created.job_id;
        statusText.textContent = created.status;
        progressBar.value = 0;
        progressText.textContent = '0%';
        progressBar.dataset.state = 'QUEUED';
        setProgressState('QUEUED');
        pollTimer = setInterval(() => {
          fetchJob(created.job_id).catch((error) => {
            stopPolling();
            errorText.textContent = error.message;
            submitButton.disabled = false;
          });
        }, 1000);
        await fetchJob(created.job_id);
      } catch (error) {
        errorText.textContent = error.message;
        submitButton.disabled = false;
      }
    });
  </script>
</body>
</html>
        """.strip()
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary=HEALTH_SUMMARY,
    description=HEALTH_DESCRIPTION,
    operation_id=HEALTH_OPERATION_ID,
    responses=HEALTH_RESPONSES,
    tags=["system"],
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
