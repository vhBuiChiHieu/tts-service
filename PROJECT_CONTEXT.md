# Project Context – Python Local TTS Backend

## 1. Mục tiêu dự án
Dự án này cung cấp backend TTS local bằng Python, xử lý bất đồng bộ theo mô hình job queue.

Mục tiêu chính:
- Nhận text từ API.
- Tách text thành chunks.
- Gọi Google Translate batchexecute để lấy audio base64.
- Ghép audio chunks thành 1 file MP3.
- Trả trạng thái tiến độ/ket quả qua endpoint tracking.

## 2. Kiến trúc tổng quan
Thư mục chính: `python-tts-backend/`

Các module chính:
- `app/main.py`: khởi tạo FastAPI app, lifespan startup/shutdown, init DB, recover job RUNNING, khởi động worker, mount jobs API + control API.
- `app/api/jobs.py`: API tạo job và theo dõi job (`/v1/jobs`, `/v1/jobs/sangtacviet`, `/v1/jobs/{job_id}`).
- `app/api/control.py`: API local-only cho tray/backend control (`/v1/control/status`, `/v1/control/shutdown`).
- `app/db/`: SQLAlchemy session/model/repository cho bảng jobs.
- `app/tts/`: token manager, Google adapter, chunker.
- `app/audio/merger.py`: decode base64 MP3, áp `volume_gain_db`, áp speed hậu kỳ toàn file (`atempo`), rồi export file.
- `app/worker/`: worker loop và processor xử lý từng job; hiện đã có cooperative shutdown qua `stop_event`.
- `app/runtime.py`: runtime handle cho worker thread (`thread`, `stop_event`, uptime/pid helper).
- `run_backend.py`: entrypoint chạy backend theo kiểu programmatic uvicorn.
- `windows_tray.py`: prototype tray app Windows để start/stop backend detached.
- `tests/`: test cho health/api/repo/chunker/google adapter/processor/recovery/control.

Ngoài ra project hiện có thêm prototype chạy nền:
- backend có thể chạy detached khỏi terminal qua `run_backend.py` hoặc qua tray app.
- tray app hiện dùng `pystray` + `Pillow`, phù hợp cho desktop session Windows.
- control API có thể dùng để đọc status backend và shutdown graceful từ localhost.
- nếu shutdown trong lúc job đang chạy, job hiện sẽ bị đánh `FAILED` với `error_code=BACKEND_SHUTDOWN`.
- đây vẫn là prototype local, chưa phải Windows Service.

Các dependency mới cho prototype:
- `pystray`
- `Pillow`
- config mới: `CONTROL_TOKEN`, `CONTROL_SHUTDOWN_TIMEOUT_SEC`

Các endpoint bổ sung:
- `GET /v1/control/status`
- `POST /v1/control/shutdown`

Luồng chạy prototype mới:
1. User có thể chạy `python python-tts-backend/run_backend.py` để start backend trực tiếp.
2. Hoặc chạy `python python-tts-backend/windows_tray.py` để mở icon tray.
3. Tray sẽ start backend dạng detached bằng subprocess nếu backend chưa chạy.
4. Tray gọi `GET /v1/control/status` để hiển thị trạng thái.
5. Khi user chọn stop, tray gọi `POST /v1/control/shutdown` để backend dừng graceful.
6. Worker dừng cooperative thay vì bị cắt đột ngột.
7. Nếu đang xử lý giữa chừng lúc shutdown, job bị đánh FAILED với mã `BACKEND_SHUTDOWN`.

Smoke test đã xác nhận:
- `GET /v1/control/status` trả đúng runtime snapshot.
- `POST /v1/control/shutdown` hoạt động.
- test suite targeted mới pass.

Tình trạng phụ thuộc local:
- dependencies cho tray prototype đã được cài trong môi trường Python hiện tại.
- để thấy icon tray thật cần chạy trong Windows desktop session có system tray khả dụng.

Tests hiện đã bổ sung:
- shutdown/control API
- worker runtime stop/join
- processor fail đúng khi backend shutdown

Tổng số test targeted đã verify trong lần cập nhật này: 25 pass.


## 3. Luồng xử lý end-to-end
1. Client gọi `POST /v1/jobs` với `text`, `lang`, `voice_hint`, `metadata`, `speed`, `volume_gain_db` **hoặc** gọi `POST /v1/jobs/sangtacviet` với `book_id`, `range`, `chapters[]`.
2. API validate request: `speed` (0.5-2.0), `volume_gain_db` (-20.0 đến 20.0); với endpoint Sáng Tác Việt kiểm tra thêm `range.start <= range.end`, `chapters` không rỗng, chapter text không rỗng.
3. Với endpoint Sáng Tác Việt: gom toàn bộ `chapters[].text` bằng 1 dấu cách và tạo `output_prefix={book_id}-{start}-{end}`.
4. API tạo bản ghi job `QUEUED` trong SQLite (persist thêm `output_prefix` nếu có).
5. Worker polling định kỳ lấy job `QUEUED` đầu tiên (FIFO), chuyển `RUNNING`.
6. Processor tách text thành chunks (có offset), gọi provider TTS cho từng chunk với `speed=1.0` để ổn định provider response.
7. Sau mỗi chunk, cập nhật progress (`processed_chunks`, `progress_pct`, vị trí char).
8. Merger áp `volume_gain_db` lên từng chunk audio trước khi ghép.
9. Khi export, Merger áp speed hậu kỳ trên toàn file bằng ffmpeg `atempo` theo `job.speed`; tên file là `outputs/{output_prefix}-{job_id}.mp3` nếu có prefix, ngược lại `outputs/{job_id}.mp3`.
10. Google adapter vẫn giữ fallback an toàn về `speed=1.0` và log raw response khi parse fail.
11. Thành công: `SUCCEEDED` + thông tin file/duration.
12. Thất bại: `FAILED` + `error_code`/`error_message`.

## 4. Dữ liệu job tracking
Thông tin tracking gồm:
- `status`: `QUEUED | RUNNING | SUCCEEDED | FAILED`
- `progress`: total/processed/progress_pct/position
- `result`: file_name/file_path/duration_ms
- `error`: code/message
- mốc thời gian: created/started/updated/finished

## 5. Cấu hình runtime quan trọng
Nguồn config: `app/core/config.py`.

Giá trị mặc định hiện tại (chạy từ repo root):
- `DB_PATH=./python-tts-backend/data/jobs.db`
- `OUTPUT_DIR=./python-tts-backend/outputs`
- `MAX_CHARS_PER_CHUNK=200`
- `WORKER_POLL_INTERVAL_MS=500`
- `REQUEST_TIMEOUT_SEC=20`
- `CHUNK_RETRY_MAX=2`
- `RANDOM_DELAY_MIN_SEC=0.5`
- `RANDOM_DELAY_MAX_SEC=1.5`
- `SILENT_BETWEEN_CHUNKS_MS=180`
- `TOKEN_TTL_SEC=3600`
- `HOST=127.0.0.1`, `PORT=8000`

## 6. Trạng thái hiện tại
- API tạo job và tracking hoạt động.
- Worker xử lý bất đồng bộ hoạt động.
- Đã hỗ trợ per-job `speed` + `volume_gain_db`, có validate input ở API.
- DB đã persist `speed` và `volume_gain_db` theo từng job.
- Speed hiện được xử lý hậu kỳ ở bước export audio (ffmpeg `atempo`) để chủ động và ổn định hơn provider speed.
- Processor hiện gọi provider với `speed=1.0` để tránh lỗi response khi speed custom.
- Google adapter có fallback an toàn về `speed=1.0` nếu parse lỗi, đồng thời có log raw response để debug.
- Đã fix parser token cho trường hợp Google không trả key `SNlM0e`.
- End-to-end đã tạo thành công file MP3 (khi có ffmpeg/ffprobe).
- Đã thêm endpoint `POST /v1/jobs/sangtacviet` cho payload chapter list (gom text bằng dấu cách).
- Đã hỗ trợ `output_prefix` theo dạng `{book_id}-{start}-{end}` để đặt tên output file.
- DB jobs đã có thêm cột nullable `output_prefix` và có bước tự thêm cột khi init DB với SQLite cũ.
- Test suite hiện có: 35 pass, 1 skipped.

## 7. Giới hạn hiện tại
- Phụ thuộc vào endpoint nội bộ Google Translate (có thể thay đổi format bất kỳ lúc nào).
- Metadata request hiện nhận vào nhưng chưa persist vào DB.
- Chưa có auth/rate-limit/cleanup chính sách cho output files.
- Worker chạy in-process (thread), chưa tách thành service riêng.
