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
  <title>Local TTS Studio</title>
  <style>
    :root {
      --bg: #f4f7fb;
      --surface: rgba(255, 255, 255, 0.94);
      --surface-strong: #ffffff;
      --surface-soft: #f8fbff;
      --border: #dbe4f0;
      --border-strong: #c7d7ea;
      --text: #0f172a;
      --muted: #64748b;
      --primary: #2563eb;
      --primary-soft: #dbeafe;
      --primary-strong: #1d4ed8;
      --success: #15803d;
      --success-soft: #dcfce7;
      --danger: #dc2626;
      --danger-soft: #fee2e2;
      --warning: #b45309;
      --warning-soft: #ffedd5;
      --shadow: 0 24px 60px rgba(15, 23, 42, 0.10);
      --shadow-soft: 0 10px 30px rgba(37, 99, 235, 0.10);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
      line-height: 1.5;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.10), transparent 34%),
        radial-gradient(circle at top right, rgba(14, 165, 233, 0.10), transparent 28%),
        linear-gradient(180deg, #f8fbff 0%, var(--bg) 100%);
    }

    .shell {
      width: min(1080px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0 56px;
    }

    .hero {
      display: flex;
      flex-direction: column;
      gap: 14px;
      margin-bottom: 24px;
      padding: 28px 32px;
      background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(239,246,255,0.92));
      border: 1px solid rgba(219, 228, 240, 0.95);
      border-radius: 28px;
      box-shadow: var(--shadow-soft);
    }

    .eyebrow {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--primary-soft);
      color: var(--primary-strong);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(32px, 4vw, 46px);
      line-height: 1.08;
      letter-spacing: -0.03em;
    }

    .hero p {
      margin: 0;
      max-width: 700px;
      color: var(--muted);
      font-size: 16px;
    }

    .hero-stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 8px;
    }

    .stat {
      padding: 16px 18px;
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid rgba(219, 228, 240, 0.9);
      border-radius: 20px;
    }

    .stat strong {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 4px;
    }

    .stat span {
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
    }

    .content {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
      gap: 20px;
      align-items: stretch;
    }

    .panel {
      display: flex;
      flex-direction: column;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
      min-height: 100%;
    }

    .panel-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 20px;
    }

    .panel-header h2 {
      margin: 0 0 6px;
      font-size: 22px;
      letter-spacing: -0.02em;
    }

    .panel-header p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--surface-soft);
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      white-space: nowrap;
    }

    .badge::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: #94a3b8;
      box-shadow: 0 0 0 4px rgba(148, 163, 184, 0.15);
    }

    .badge.status-running {
      color: var(--success);
      background: var(--success-soft);
      border-color: rgba(34, 197, 94, 0.18);
    }

    .badge.status-running::before {
      background: var(--success);
      box-shadow: 0 0 0 4px rgba(21, 128, 61, 0.16);
    }

    .badge.status-succeeded {
      color: var(--primary-strong);
      background: var(--primary-soft);
      border-color: rgba(37, 99, 235, 0.16);
    }

    .badge.status-succeeded::before {
      background: var(--primary);
      box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14);
    }

    .badge.status-failed {
      color: var(--danger);
      background: var(--danger-soft);
      border-color: rgba(220, 38, 38, 0.16);
    }

    .badge.status-failed::before {
      background: var(--danger);
      box-shadow: 0 0 0 4px rgba(220, 38, 38, 0.14);
    }

    .badge.status-queued {
      color: var(--warning);
      background: var(--warning-soft);
      border-color: rgba(245, 158, 11, 0.18);
    }

    .badge.status-queued::before {
      background: var(--warning);
      box-shadow: 0 0 0 4px rgba(180, 83, 9, 0.14);
    }

    form {
      display: grid;
      gap: 18px;
      flex: 1;
      align-content: start;
    }

    .field {
      display: grid;
      gap: 8px;
    }

    .field-label {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      font-weight: 700;
      font-size: 14px;
    }

    .field-hint {
      font-size: 12px;
      color: var(--muted);
      font-weight: 500;
    }

    input, button {
      font: inherit;
    }

    input[type="number"],
    input[type="file"] {
      width: 100%;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid var(--border-strong);
      background: var(--surface-strong);
      color: var(--text);
      transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
    }

    input[type="number"]:focus,
    input[type="file"]:focus {
      outline: none;
      border-color: rgba(37, 99, 235, 0.55);
      box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.12);
      transform: translateY(-1px);
    }

    .actions {
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      margin-top: 6px;
    }

    button {
      appearance: none;
      border: none;
      border-radius: 16px;
      padding: 14px 20px;
      min-width: 160px;
      font-weight: 700;
      cursor: pointer;
      color: #ffffff;
      background: linear-gradient(135deg, var(--primary), #3b82f6);
      box-shadow: 0 16px 30px rgba(37, 99, 235, 0.24);
      transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
    }

    button:hover:not(:disabled) {
      transform: translateY(-1px);
      box-shadow: 0 18px 34px rgba(37, 99, 235, 0.28);
    }

    button:disabled {
      cursor: wait;
      opacity: 0.7;
      box-shadow: none;
    }

    .helper {
      color: var(--muted);
      font-size: 13px;
    }

    .tracking-grid {
      display: grid;
      gap: 16px;
      flex: 1;
      align-content: start;
    }

    #tracking {
      justify-content: space-between;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .meta-card {
      padding: 16px 18px;
      border-radius: 18px;
      border: 1px solid var(--border);
      background: var(--surface-soft);
    }

    .meta-card strong {
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .meta-card span {
      font-size: 15px;
      font-weight: 700;
      color: var(--text);
      word-break: break-word;
    }

    .progress-card {
      padding: 18px;
      border-radius: 20px;
      border: 1px solid var(--border);
      background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      margin-top: auto;
    }

    .progress-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
    }

    .progress-head strong {
      font-size: 15px;
    }

    .progress-meter {
      width: 100%;
      height: 12px;
      border-radius: 999px;
      overflow: hidden;
      background: #e2e8f0;
      box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.08);
    }

    .progress-fill {
      height: 100%;
      width: 0%;
      border-radius: inherit;
      background: linear-gradient(90deg, #f59e0b 0%, #fbbf24 100%);
      transition: width 0.35s ease, background 0.35s ease;
    }

    .progress-fill.progress-state-running {
      background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
    }

    .progress-fill.progress-state-succeeded {
      background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
    }

    .progress-fill.progress-state-failed {
      background: linear-gradient(90deg, #f87171 0%, #dc2626 100%);
    }

    .message {
      min-height: 22px;
      font-size: 14px;
      margin: 0;
    }

    .muted { color: var(--muted); }
    .hidden { display: none; }
    .error { color: var(--danger); font-weight: 600; }
    .success { color: var(--success); font-weight: 600; }

    @media (max-width: 860px) {
      .content,
      .hero-stats,
      .meta-grid {
        grid-template-columns: 1fr;
      }

      .shell {
        width: min(100% - 20px, 1080px);
        padding-top: 20px;
        padding-bottom: 28px;
      }

      .hero,
      .panel {
        padding: 20px;
        border-radius: 22px;
      }

      .panel-header,
      .progress-head,
      .field-label {
        flex-direction: column;
        align-items: flex-start;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <span class="eyebrow">Local TTS Service</span>
      <h1>Tạo file MP3 từ TXT với giao diện gọn, sáng và dễ theo dõi.</h1>
      <p>Upload nội dung văn bản, điều chỉnh tốc độ đọc và theo dõi tiến độ job ngay trên local backend của repo này.</p>
      <div class="hero-stats">
        <div class="stat">
          <strong>Input</strong>
          <span>TXT upload trực tiếp</span>
        </div>
        <div class="stat">
          <strong>Processing</strong>
          <span>Job queue bất đồng bộ</span>
        </div>
        <div class="stat">
          <strong>Output</strong>
          <span>MP3 hoàn tất theo dõi realtime</span>
        </div>
      </div>
    </section>

    <section class="content">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>Tạo job TTS</h2>
            <p>Giữ nguyên flow hiện tại, tối ưu lại trình bày để thao tác nhanh và rõ ràng hơn.</p>
          </div>
          <span class="badge status-queued">Sẵn sàng</span>
        </div>

        <form id="tts-form">
          <label class="field">
            <span class="field-label">
              <span>File TXT</span>
              <span class="field-hint">Chấp nhận .txt hoặc text/plain</span>
            </span>
            <input id="file" name="file" type="file" accept=".txt,text/plain" required>
          </label>

          <label class="field">
            <span class="field-label">
              <span>Speed</span>
              <span class="field-hint">Khoảng hợp lệ 0.5 đến 2.0</span>
            </span>
            <input id="speed" name="speed" type="number" min="0.5" max="2" step="0.1" value="1.0" required>
          </label>

          <div class="actions">
            <button id="submit" type="submit">Tạo job</button>
            <span class="helper">Sau khi tạo, hệ thống sẽ polling trạng thái job mỗi giây.</span>
          </div>
        </form>
      </div>

      <div id="tracking" class="panel hidden">
        <div class="panel-header">
          <div>
            <h2>Theo dõi tiến độ</h2>
            <p>Trạng thái job được cập nhật realtime để dễ kiểm soát quá trình xử lý.</p>
          </div>
          <span id="status-badge" class="badge status-queued">QUEUED</span>
        </div>

        <div class="tracking-grid">
          <div class="meta-grid">
            <div class="meta-card">
              <strong>Job ID</strong>
              <span id="job-id">-</span>
            </div>
            <div class="meta-card">
              <strong>Trạng thái</strong>
              <span id="status">-</span>
            </div>
          </div>

          <div class="progress-card">
            <div class="progress-head">
              <strong>Tiến độ xử lý</strong>
              <span id="progress-text" class="muted">0%</span>
            </div>
            <div class="progress-meter" aria-hidden="true">
              <div id="progress" class="progress-fill"></div>
            </div>
          </div>

          <p id="result" class="message muted"></p>
          <p id="error" class="message error"></p>
        </div>
      </div>
    </section>
  </main>

  <script>
    const form = document.getElementById('tts-form');
    const fileInput = document.getElementById('file');
    const speedInput = document.getElementById('speed');
    const submitButton = document.getElementById('submit');
    const tracking = document.getElementById('tracking');
    const jobIdText = document.getElementById('job-id');
    const statusText = document.getElementById('status');
    const statusBadge = document.getElementById('status-badge');
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

    function setStatusBadge(state) {
      const normalizedState = state || 'QUEUED';
      statusBadge.textContent = normalizedState;
      statusBadge.className = 'badge';

      if (normalizedState === 'RUNNING') {
        statusBadge.classList.add('status-running');
        return;
      }

      if (normalizedState === 'SUCCEEDED') {
        statusBadge.classList.add('status-succeeded');
        return;
      }

      if (normalizedState === 'FAILED') {
        statusBadge.classList.add('status-failed');
        return;
      }

      statusBadge.classList.add('status-queued');
    }

    function setProgressState(state) {
      progressBar.classList.remove('progress-state-running', 'progress-state-succeeded', 'progress-state-failed');

      if (state === 'RUNNING') {
        progressBar.classList.add('progress-state-running');
        return;
      }

      if (state === 'SUCCEEDED') {
        progressBar.classList.add('progress-state-succeeded');
        return;
      }

      if (state === 'FAILED') {
        progressBar.classList.add('progress-state-failed');
      }
    }

    function updateTracking(job) {
      tracking.classList.remove('hidden');
      jobIdText.textContent = job.job_id;
      statusText.textContent = job.status;
      setStatusBadge(job.status);

      const progress = Math.max(0, Math.min(100, job.progress?.progress_pct ?? 0));
      progressBar.style.width = `${progress}%`;
      progressText.textContent = `${progress}%`;
      setProgressState(job.status);

      if (job.status === 'SUCCEEDED') {
        setProgressState('SUCCEEDED');
        resultText.textContent = job.result?.file_path ? `Hoàn thành: ${job.result.file_path}` : 'Hoàn thành';
        resultText.className = 'message success';
        errorText.textContent = '';
        stopPolling();
        submitButton.disabled = false;
        submitButton.textContent = 'Tạo job';
        return;
      }

      if (job.status === 'FAILED') {
        setProgressState('FAILED');
        errorText.textContent = job.error?.message || 'Job thất bại';
        resultText.textContent = '';
        resultText.className = 'message muted';
        stopPolling();
        submitButton.disabled = false;
        submitButton.textContent = 'Tạo job';
        return;
      }

      if (job.status === 'RUNNING') {
        setProgressState('RUNNING');
      }

      resultText.textContent = '';
      resultText.className = 'message muted';
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
      resultText.className = 'message muted';
      submitButton.disabled = true;
      submitButton.textContent = 'Đang tạo job...';

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
        setStatusBadge(created.status);
        progressBar.style.width = '0%';
        progressText.textContent = '0%';
        setProgressState('QUEUED');
        pollTimer = setInterval(() => {
          fetchJob(created.job_id).catch((error) => {
            stopPolling();
            errorText.textContent = error.message;
            submitButton.disabled = false;
            submitButton.textContent = 'Tạo job';
          });
        }, 1000);
        await fetchJob(created.job_id);
      } catch (error) {
        errorText.textContent = error.message;
        submitButton.disabled = false;
        submitButton.textContent = 'Tạo job';
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
