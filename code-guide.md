# Code Guide

## 1. Dự án này là gì?

Đây là backend TTS local viết bằng Python. Hệ thống nhận text qua HTTP API, đưa vào hàng đợi job trong SQLite, worker thread xử lý bất đồng bộ, gọi Google Translate batchexecute để lấy audio MP3 base64, ghép các chunk audio lại và xuất file MP3 ra thư mục output.

Luồng chính:

1. Client gọi API tạo job.
2. API ghi job vào DB với trạng thái `QUEUED`.
3. Worker polling job tiếp theo, chuyển sang `RUNNING`.
4. Processor chunk text, gọi provider, cập nhật progress.
5. Audio merger ghép audio và export MP3.
6. Job được cập nhật thành `SUCCEEDED` hoặc `FAILED`.

## 2. Tech stack

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Web API | FastAPI | Expose API tạo job, tracking job, control backend |
| ASGI server | Uvicorn | Chạy app FastAPI |
| Validation / settings | Pydantic, pydantic-settings | Validate request/response schema, đọc env config |
| Database | SQLite + SQLAlchemy | Lưu job queue, trạng thái, progress, kết quả |
| HTTP client | requests | Gọi endpoint nội bộ của Google Translate |
| Audio processing | pydub + ffmpeg/ffprobe | Ghép MP3 chunks, tăng/giảm volume, chỉnh tốc độ export |
| Desktop control | pystray + Pillow | Prototype tray app trên Windows |
| Testing | pytest | Test API, DB repo, worker, adapter, audio |

## 3. Cấu trúc thư mục

```text
.
├─ README.md
├─ PROJECT_CONTEXT.md
├─ docs/
├─ code-guide.md
└─ python-tts-backend/
   ├─ app/
   │  ├─ api/
   │  ├─ audio/
   │  ├─ core/
   │  ├─ db/
   │  ├─ tts/
   │  ├─ worker/
   │  ├─ runtime.py
   │  └─ main.py
   ├─ data/
   ├─ outputs/
   ├─ tests/
   ├─ requirements.txt
   ├─ pytest.ini
   ├─ run_backend.py
   └─ windows_tray.py
```

## 4. Kiến trúc tổng quan

Hệ thống đang theo kiểu monolith nhỏ, chia lớp khá rõ:

- **API layer**: nhận request, validate input, gọi repository tạo/truy vấn job.
- **Persistence layer**: lưu job vào SQLite qua SQLAlchemy.
- **Worker layer**: chạy thread nền, lấy job từ DB để xử lý.
- **TTS integration layer**: quản lý token và gọi Google Translate batchexecute.
- **Audio layer**: ghép audio chunks và export MP3.
- **Runtime/control layer**: quản lý lifecycle worker và shutdown local.

### Sơ đồ luồng

```text
Client
  -> FastAPI routes
  -> JobRepo
  -> SQLite (jobs)
  -> Worker thread polls queued jobs
  -> Processor
     -> Chunker
     -> GoogleTranslateAdapter
     -> AudioMerger
  -> output mp3 file
  -> JobRepo cập nhật progress / result / error
```

## 5. Entry points quan trọng

| File | Vai trò |
|---|---|
| `python-tts-backend/app/main.py` | FastAPI app chính, init DB, recover job dang dở, start/stop worker |
| `python-tts-backend/run_backend.py` | Chạy backend programmatically bằng uvicorn |
| `python-tts-backend/windows_tray.py` | Tray app Windows để start/stop backend local |
| `README.md` | Hướng dẫn chạy và dùng API ở mức tổng quan |

Điểm bắt đầu tốt nhất để hiểu hệ thống là:

1. `python-tts-backend/app/main.py`
2. `python-tts-backend/app/api/jobs.py`
3. `python-tts-backend/app/worker/runner.py`
4. `python-tts-backend/app/worker/processor.py`
5. `python-tts-backend/app/audio/merger.py`
6. `python-tts-backend/app/tts/google_adapter.py`

## 6. Các package/module và vai trò của chúng

### 6.1 `app/api/`

Chứa HTTP routes.

| File | Vai trò |
|---|---|
| `app/api/jobs.py` | API tạo job thường, tạo job từ payload Sáng Tác Việt, lấy trạng thái job |
| `app/api/control.py` | API local-only để đọc trạng thái backend và shutdown graceful |

Khi muốn:
- thêm endpoint mới
- đổi request/response contract
- thêm validation ở mức API

thì bắt đầu ở `app/api/`.

### 6.2 `app/core/`

Chứa phần lõi dùng chung.

| File | Vai trò |
|---|---|
| `app/core/config.py` | Định nghĩa settings từ env |
| `app/core/schemas.py` | Pydantic schema cho request/response, metadata OpenAPI |
| `app/core/errors.py` | Mã lỗi nghiệp vụ |
| `app/core/logging.py` | Cấu hình/log helper nếu có |

Khi muốn:
- thêm biến môi trường mới
- sửa schema request/response
- chuẩn hóa error code

thì code ở `app/core/`.

### 6.3 `app/db/`

Chứa tầng truy cập dữ liệu.

| File | Vai trò |
|---|---|
| `app/db/session.py` | Engine, session factory, init DB, migration nhỏ cho SQLite hiện tại |
| `app/db/models.py` | SQLAlchemy model `Job` |
| `app/db/repo_jobs.py` | CRUD và state transition của job |

`Job` hiện lưu các nhóm dữ liệu chính:
- input: text, lang, voice_hint
- runtime params: speed, volume_gain_db, output_prefix
- tracking: total_chunks, processed_chunks, progress_pct, offsets
- result: file_name, file_path, duration_ms
- error: error_code, error_message
- timestamps: created, started, updated, finished

Khi muốn:
- thêm cột DB
- sửa logic queue/requeue
- đổi cách cập nhật trạng thái job

thì code ở `app/db/`.

### 6.4 `app/tts/`

Chứa tích hợp provider TTS.

| File | Vai trò |
|---|---|
| `app/tts/chunker.py` | Normalize text và cắt text thành chunks có metadata vị trí |
| `app/tts/token_manager.py` | Quản lý token cần để gọi Google Translate batchexecute |
| `app/tts/google_adapter.py` | Build payload RPC, gửi request, parse audio base64, fallback khi parse lỗi |

Khi muốn:
- đổi provider TTS
- sửa logic gọi batchexecute
- tinh chỉnh chunking text

thì code ở `app/tts/`.

Nếu sau này thêm provider mới, đây là vùng nên mở rộng đầu tiên.

### 6.5 `app/audio/`

Chứa xử lý audio sau khi provider trả về.

| File | Vai trò |
|---|---|
| `app/audio/merger.py` | Decode MP3 base64, ghép chunk, chèn silence, tăng/giảm volume, export file |

Đây là nơi cần sửa nếu muốn:
- đổi định dạng output
- chỉnh cách ghép audio
- chỉnh volume/speed hậu kỳ
- xử lý đặc thù Windows liên quan pydub/subprocess

### 6.6 `app/worker/`

Chứa logic xử lý nền.

| File | Vai trò |
|---|---|
| `app/worker/runner.py` | Start worker thread, polling queue, build adapter/merger, recover job RUNNING |
| `app/worker/processor.py` | Xử lý 1 job end-to-end, retry chunk, update progress, mark success/failure |

Khi muốn:
- thay đổi thứ tự xử lý queue
- thêm retry policy
- thêm stop behavior
- thay đổi orchestration end-to-end

thì code ở `app/worker/`.

### 6.7 `app/runtime.py`

Chứa runtime handle cho worker thread như thread object, stop event, pid/uptime helper. Đây là lớp hỗ trợ để control API và app lifecycle quản lý worker an toàn hơn.

## 7. End-to-end flow chi tiết

### 7.1 Tạo job thường

File chính: `python-tts-backend/app/api/jobs.py`

- `POST /v1/jobs` nhận `text`, `lang`, `voice_hint`, `speed`, `volume_gain_db`.
- API gọi `JobRepo.create_job(...)` để ghi DB.
- Response trả về `job_id`, `status`, `created_at`.

### 7.2 Tạo job từ payload Sáng Tác Việt

Cũng ở `python-tts-backend/app/api/jobs.py`.

- Endpoint: `POST /v1/jobs/sangtacviet`
- Nhận `book_id`, `range`, `chapters[]`
- Merge toàn bộ chapter text bằng một dấu cách
- Tạo `output_prefix={book_id}-{start}-{end}`
- Tạo job như job thường

### 7.3 Worker lấy job và xử lý

File chính: `python-tts-backend/app/worker/runner.py`

- Worker loop mở `SessionLocal()` theo từng vòng polling
- Lấy job `QUEUED` sớm nhất
- Tạo `AudioMerger`
- Tính `output_path`
- Gọi `process_job(...)`

### 7.4 Processor xử lý job

File chính: `python-tts-backend/app/worker/processor.py`

- Đánh dấu job `RUNNING`
- Chunk text qua `build_chunks(...)`
- Với từng chunk:
  - gọi adapter lấy MP3 base64
  - append vào merger
  - update progress vào DB
  - sleep random theo config
- Sau cùng export file và mark success
- Nếu lỗi thì mark failed với error code phù hợp

### 7.5 Adapter gọi Google Translate

File chính: `python-tts-backend/app/tts/google_adapter.py`

- Build payload RPC `jQ1olc`
- Gọi endpoint `batchexecute`
- Parse response để lấy audio base64
- Nếu parse fail với speed custom thì fallback gọi lại với `speed=1.0`

### 7.6 Audio export

File chính: `python-tts-backend/app/audio/merger.py`

- Decode base64 thành `AudioSegment`
- Áp `volume_gain_db` từng chunk nếu cần
- Nối chunks với khoảng lặng giữa các đoạn
- Export MP3
- Nếu `speed != 1.0` thì áp hậu kỳ bằng ffmpeg filter `atempo`

## 8. Muốn code tính năng gì thì code vào đâu?

| Nhu cầu | Nên sửa ở đâu |
|---|---|
| Thêm endpoint API mới | `app/api/` + `app/core/schemas.py` |
| Thêm field request/response | `app/core/schemas.py`, có thể kèm `app/api/` |
| Thêm config env mới | `app/core/config.py` |
| Thêm cột hoặc state mới cho job | `app/db/models.py`, `app/db/repo_jobs.py`, có thể kèm `app/db/session.py` |
| Đổi logic xếp hàng/polling/recovery | `app/worker/runner.py`, `app/db/repo_jobs.py` |
| Đổi logic xử lý 1 job | `app/worker/processor.py` |
| Đổi cách cắt text | `app/tts/chunker.py` |
| Đổi provider TTS hoặc request sang provider | `app/tts/google_adapter.py`, `app/tts/token_manager.py` |
| Đổi cách ghép MP3 / volume / speed | `app/audio/merger.py` |
| Thêm control/tray behavior | `app/api/control.py`, `app/runtime.py`, `windows_tray.py` |
| Thêm test | `python-tts-backend/tests/` |

## 9. Các file nên đọc trước khi sửa code

### Nếu bạn làm API
- `python-tts-backend/app/main.py`
- `python-tts-backend/app/api/jobs.py`
- `python-tts-backend/app/core/schemas.py`
- `python-tts-backend/app/db/repo_jobs.py`

### Nếu bạn làm worker / processing
- `python-tts-backend/app/worker/runner.py`
- `python-tts-backend/app/worker/processor.py`
- `python-tts-backend/app/db/repo_jobs.py`
- `python-tts-backend/app/audio/merger.py`
- `python-tts-backend/app/tts/chunker.py`
- `python-tts-backend/app/tts/google_adapter.py`

### Nếu bạn làm data / DB
- `python-tts-backend/app/db/models.py`
- `python-tts-backend/app/db/repo_jobs.py`
- `python-tts-backend/app/db/session.py`

### Nếu bạn làm desktop/tray/control
- `python-tts-backend/app/api/control.py`
- `python-tts-backend/app/runtime.py`
- `python-tts-backend/run_backend.py`
- `python-tts-backend/windows_tray.py`

## 10. Package/dependency có vai trò gì?

| Package | Vai trò thực tế trong repo |
|---|---|
| `fastapi` | Route declaration, dependency injection, response model |
| `uvicorn` | Chạy web server cho FastAPI |
| `sqlalchemy` | ORM và session với SQLite |
| `pydantic` | Schema request/response |
| `pydantic-settings` | Map env sang settings object |
| `requests` | Gửi HTTP request tới Google Translate |
| `pydub` | Làm việc với audio segment và export MP3 |
| `python-dotenv` | Hỗ trợ load `.env` |
| `pytest` | Chạy test |
| `pystray` | System tray icon cho Windows prototype |
| `Pillow` | Hỗ trợ icon/image cho tray app |

## 11. Các ràng buộc và lưu ý kỹ thuật

### 11.1 Provider TTS không ổn định tuyệt đối
Project đang dùng endpoint nội bộ của Google Translate, nên format response có thể thay đổi bất kỳ lúc nào. Khi gặp lỗi parse response, hãy kiểm tra trước ở `app/tts/google_adapter.py`.

### 11.2 Worker đang là in-process thread
Worker không tách sang process/service riêng. Vì vậy mọi logic xử lý nền hiện gắn chặt với vòng đời của app FastAPI.

### 11.3 DB migration hiện rất nhẹ
Hiện `app/db/session.py` chỉ tự thêm cột `output_prefix` nếu SQLite cũ chưa có. Chưa có migration framework chính thức như Alembic.

### 11.4 Cần ffmpeg/ffprobe để audio chạy đúng
`pydub` phụ thuộc `ffmpeg` và `ffprobe` có trong PATH. Nếu backend chạy nhưng không export được MP3, đây là chỗ kiểm tra đầu tiên.

### 11.5 Control API chỉ intended cho localhost
`app/api/control.py` chặn request không đến từ loopback. Nếu sửa phần này cần rất cẩn thận vì nó liên quan khả năng shutdown backend.

## 12. Cách chạy project

Từ root repo:

```bash
pip install -r python-tts-backend/requirements.txt
python python-tts-backend/run_backend.py
```

Hoặc chạy trực tiếp uvicorn nếu tự set env đúng.

Swagger mặc định:
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

## 13. Cách chạy test

```bash
pytest python-tts-backend/tests -v
```

Nhóm test hiện có:
- health
- jobs API
- control API
- repo_jobs
- chunker
- google adapter
- audio merger
- processor
- runner recovery

Nếu sửa logic ở đâu, hãy ưu tiên chạy đúng nhóm test gần nhất với vùng code đó trước.

## 14. Quy ước làm việc thực tế cho dev mới

1. Bắt đầu đọc từ `app/main.py` để hiểu lifecycle app.
2. Muốn hiểu request đi đâu, đọc `app/api/jobs.py` rồi xuống `app/db/repo_jobs.py` và `app/worker/runner.py`.
3. Muốn hiểu audio ra file thế nào, đọc `app/worker/processor.py` rồi `app/audio/merger.py`.
4. Muốn debug provider, đọc `app/tts/google_adapter.py` và `app/tts/token_manager.py`.
5. Muốn thêm feature mới, cố giữ đúng ranh giới lớp hiện có thay vì nhồi mọi thứ vào route hoặc worker.

## 15. Gợi ý định hướng mở rộng sau này

Các hướng mở rộng hợp lý nếu dự án lớn hơn:
- tách provider interface để hỗ trợ nhiều TTS backend
- thêm migration framework chính thức
- persist metadata đầy đủ vào DB
- thêm auth/rate limit nếu expose ra môi trường rộng hơn
- tách worker thành process/service riêng nếu queue phức tạp hơn

---

## TL;DR cho dev mới

- Đây là **FastAPI + SQLite + worker thread**.
- API chỉ tạo và track job; xử lý thật diễn ra ở worker.
- TTS provider logic nằm trong `app/tts/`.
- Ghép và export audio nằm trong `app/audio/`.
- State/job queue nằm trong `app/db/`.
- Muốn sửa đúng chỗ, hãy xác định trước bạn đang sửa **API**, **DB**, **worker orchestration**, **provider integration**, hay **audio processing**.