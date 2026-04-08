# Python Local TTS Backend

Backend TTS local bằng FastAPI + SQLite + worker thread, tạo MP3 từ text qua Google Translate batchexecute.

## Features
- Tạo job TTS qua API.
- Theo dõi tiến độ xử lý job theo thời gian thực.
- Xử lý chunk + retry + random delay.
- Ghép audio và xuất ra file MP3.
- Recover job `RUNNING` về `QUEUED` khi restart.

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
```bash
PYTHONPATH="python-tts-backend" \
DB_PATH="python-tts-backend/data/jobs.db" \
OUTPUT_DIR="python-tts-backend/outputs" \
uvicorn "app.main:app" --host 127.0.0.1 --port 8000
```

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
    "metadata":{"source":"demo"}
  }'
```

Response mẫu:
```json
{
  "job_id": "<uuid>",
  "status": "QUEUED",
  "created_at": "..."
}
```

### 3) Track job
```bash
curl -s "http://127.0.0.1:8000/v1/jobs/<job_id>"
```

Khi thành công:
- `status = SUCCEEDED`
- `result.file_path = python-tts-backend/outputs/<job_id>.mp3`

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
- Thử lại job; kiểm tra kết nối mạng.

### 4) Không thấy file output
- Kiểm tra `OUTPUT_DIR`.
- Kiểm tra trạng thái job qua endpoint tracking.
