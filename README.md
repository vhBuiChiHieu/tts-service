# Python Local TTS Backend

Backend TTS local bằng FastAPI + SQLite + worker thread, tạo MP3 từ text qua Google Translate batchexecute.

## Features
- Tạo job TTS qua API (`/v1/jobs`).
- Tạo job từ payload chapter Sáng Tác Việt (`/v1/jobs/sangtacviet`).
- Hỗ trợ per-job `speed` và `volume_gain_db` với default an toàn.
- Theo dõi tiến độ xử lý job theo thời gian thực.
- Xử lý chunk + retry + random delay.
- Ghép audio, áp gain volume, và xuất ra file MP3.
- Recover job `RUNNING` về `QUEUED` khi restart.
- Có control API local-only để đọc trạng thái backend và shutdown graceful.
- Có prototype tray app Windows để start/stop backend dạng detached.

## Background + tray prototype
Prototype hiện tại thêm 2 entrypoint mới:

- `python-tts-backend/run_backend.py`: chạy backend bằng uvicorn theo kiểu programmatic.
- `python-tts-backend/windows_tray.py`: mở icon ở system tray để điều khiển backend local.

Control API mới:

- `GET /v1/control/status`
- `POST /v1/control/shutdown`

Lưu ý:
- Đây là **prototype local**, chưa phải Windows Service thật.
- Control API chỉ intended cho localhost.
- Khi shutdown giữa lúc đang xử lý job, job sẽ bị đánh `FAILED` với `error.code = BACKEND_SHUTDOWN`.
- Tray dùng `pystray` + `Pillow`; cần desktop session Windows để hiện icon.

### Chạy backend detached qua tray
Từ repo root:

```bash
pip install -r python-tts-backend/requirements.txt
python python-tts-backend/windows_tray.py
```

Tray menu hiện có:
- Start backend
- Stop backend
- Open API
- Open outputs
- Refresh status
- Exit tray
- Exit and stop backend

### Chạy backend trực tiếp không qua tray
```bash
python python-tts-backend/run_backend.py
```

### Control API usage
```bash
curl -s "http://127.0.0.1:8000/v1/control/status"
curl -s -X POST "http://127.0.0.1:8000/v1/control/shutdown"
```

Nếu muốn khóa shutdown endpoint bằng token, set thêm biến môi trường:

```env
CONTROL_TOKEN=your-secret-token
CONTROL_SHUTDOWN_TIMEOUT_SEC=10
```

Khi dùng token, tray sẽ tự gửi `X-Control-Token` từ config hiện tại.

### Build thành exe sau này
Prototype này phù hợp để build tiếp bằng `PyInstaller --noconsole` cho:
- backend runner
- tray app

Nhưng phần đó chưa được cấu hình sẵn trong repo ở bước hiện tại.

---


## Project structure
```text
python-tts-backend/
  app/
    api/jobs.py
    audio/merger.py
    core/{config.py,schemas.py,errors.py}
    db/{session.py,models.py,repo_jobs.py}
    tts/{token_manager.py,google_adapter.py,chunker.py}
    worker/{runner.py,processor.py}
    main.py
  tests/
  data/
  outputs/
  requirements.txt
```

## Prerequisites
- Python 3.10+
- ffmpeg + ffprobe (bắt buộc để xử lý MP3)

Kiểm tra:
```bash
ffmpeg -version
ffprobe -version
```

## Setup
Từ thư mục repo root:

```bash
pip install -r python-tts-backend/requirements.txt
```

(Tùy chọn) tạo `.env` tại repo root hoặc trong `python-tts-backend/` với các biến bên dưới.

## Environment variables
Giá trị nên dùng khi chạy từ repo root:

```env
DB_PATH=./python-tts-backend/data/jobs.db
OUTPUT_DIR=./python-tts-backend/outputs
MAX_CHARS_PER_CHUNK=200
WORKER_POLL_INTERVAL_MS=500
REQUEST_TIMEOUT_SEC=20
CHUNK_RETRY_MAX=2
RANDOM_DELAY_MIN_SEC=0.5
RANDOM_DELAY_MAX_SEC=1.5
SILENT_BETWEEN_CHUNKS_MS=180
TOKEN_TTL_SEC=3600
HOST=127.0.0.1
PORT=8000
```

## Run server
### macOS/Linux (bash)
Từ repo root:
```bash
PYTHONPATH="python-tts-backend" \
DB_PATH="python-tts-backend/data/jobs.db" \
OUTPUT_DIR="python-tts-backend/outputs" \
uvicorn "app.main:app" --host 127.0.0.1 --port 8000
```

### Windows (PowerShell)
**Cách 1: chạy từ repo root (`tts-service`)**
```powershell
$env:PYTHONPATH = "python-tts-backend"
$env:DB_PATH = "python-tts-backend/data/jobs.db"
$env:OUTPUT_DIR = "python-tts-backend/outputs"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Cách 2: chạy trong thư mục `python-tts-backend`**
```powershell
$env:PYTHONPATH = "."
$env:DB_PATH = "./data/jobs.db"
$env:OUTPUT_DIR = "./outputs"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Lưu ý: PowerShell không dùng cú pháp `VAR=value command` như bash.
```powershell
# Sai trong PowerShell
PYTHONPATH="python-tts-backend" uvicorn app.main:app
```
Dùng `$env:...` như ví dụ ở trên.

Nếu vừa cài ffmpeg bằng winget, mở PowerShell mới rồi kiểm tra:
```powershell
Get-Command ffmpeg
Get-Command ffprobe
```
Nếu chưa thấy, thêm thư mục `ffmpeg\bin` vào PATH và mở terminal lại.


## API usage
### 1) Health check
```bash
curl -s "http://127.0.0.1:8000/health"
```

### 2) Create TTS job
```bash
curl -s -X POST "http://127.0.0.1:8000/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Xin chao. Day la ban test.",
    "lang":"vi",
    "voice_hint":null,
    "metadata":{"source":"demo"},
    "speed": 1.2,
    "volume_gain_db": 3.0
  }'
```

Ràng buộc request:
- `speed`: `0.5 -> 2.0` (default `1.0`)
- `volume_gain_db`: `-20.0 -> 20.0` (default `0.0`)

Lưu ý:
- `speed != 1.0` sẽ gửi payload speed tới Google adapter.
- Nếu provider không parse được response với speed custom, hệ thống fallback 1 lần về `speed=1.0`.

Response mẫu:
```json
{
  "job_id": "<uuid>",
  "status": "QUEUED",
  "created_at": "..."
}
```

### 3) Create TTS job từ payload Sáng Tác Việt
```bash
curl -s -X POST "http://127.0.0.1:8000/v1/jobs/sangtacviet" \
  -H "Content-Type: application/json" \
  -d '{
    "book_id": "7577371088154266649",
    "range": {"start": 200, "end": 202},
    "chapters": [
      {"chapter_number": 200, "text": "Doan 1"},
      {"chapter_number": 201, "text": "Doan 2"},
      {"chapter_number": 202, "text": "Doan 3"}
    ],
    "lang": "vi",
    "voice_hint": null,
    "metadata": {"source": "sangtacviet"},
    "speed": 1.2,
    "volume_gain_db": 3.0
  }'
```

Ràng buộc bổ sung cho endpoint này:
- `book_id`: bắt buộc, non-empty
- `range.start <= range.end`
- `chapters`: không rỗng
- mỗi `chapters[i].text`: non-empty (sau trim)

Behavior:
- Hệ thống gom toàn bộ `chapters[].text` bằng **1 dấu cách** rồi enqueue như job thường.
- Tên file output sẽ có prefix: `{book_id}-{start}-{end}-{job_id}.mp3`.

### 4) Track job
```bash
curl -s "http://127.0.0.1:8000/v1/jobs/<job_id>"
```

Khi thành công:
- `status = SUCCEEDED`
- Với job thường: `result.file_path = python-tts-backend/outputs/<job_id>.mp3`
- Với job Sáng Tác Việt: `result.file_path = python-tts-backend/outputs/<book_id>-<start>-<end>-<job_id>.mp3`

Khi lỗi:
- `status = FAILED`
- kiểm tra `error.code` và `error.message`

## Run tests
```bash
pytest python-tts-backend/tests -v
```

## Troubleshooting
### 1) `ModuleNotFoundError: No module named 'app'`
- Chạy lệnh với `PYTHONPATH="python-tts-backend"`.

### 2) `[WinError 2] The system cannot find the file specified`
- Thiếu ffmpeg/ffprobe hoặc chưa vào PATH.

### 3) Job fail với `PROVIDER_RESPONSE_INVALID`
- Google response thay đổi hoặc token parse lỗi tạm thời.
- Với `speed` custom, hệ thống đã thử fallback về `speed=1.0` một lần.
- Thử lại job; kiểm tra kết nối mạng.

### 4) Không thấy file output
- Kiểm tra `OUTPUT_DIR`.
- Kiểm tra trạng thái job qua endpoint tracking.
