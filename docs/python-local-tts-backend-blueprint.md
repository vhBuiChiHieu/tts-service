# Blueprint chi tiết — Python Local TTS Backend (Monolith FastAPI + SQLite + Worker tuần tự)

## 1) Mục tiêu

Xây dựng backend local bằng Python để:
- Nhận text dài, tạo job TTS.
- Trả về **`job_id`** ngay sau request.
- Xử lý tổng hợp audio ở background (không streaming).
- Cung cấp API tracking theo `job_id` gồm:
  - trạng thái job,
  - tiến độ,
  - vị trí xử lý hiện tại,
  - tên file kết quả.

Ràng buộc đã chốt:
- Kiến trúc: **Monolith FastAPI + SQLite + 1 worker tuần tự**.
- Không phát audio trực tiếp trong lúc xử lý.
- Ưu tiên ổn định/rate-limit safety hơn throughput.

---

## 2) Non-goals (không làm ở phase này)

- Không hỗ trợ xử lý nhiều job song song.
- Không dùng Redis/Celery/RabbitMQ.
- Không xây UI web riêng cho dashboard.
- Không đảm bảo API Google Translate undocumented luôn ổn định vĩnh viễn.

---

## 3) Kiến trúc tổng thể

## 3.1 Thành phần chính

1. **FastAPI App (HTTP layer)**
   - Validate input.
   - Tạo job record trong SQLite.
   - Đưa job vào hàng đợi nội bộ.
   - Trả `job_id`.
   - Cung cấp endpoint tracking/query file metadata.

2. **SQLite (state store)**
   - Lưu lifecycle job, tiến độ, vị trí, lỗi, output file.
   - Nguồn sự thật duy nhất cho tracking.

3. **Sequential Worker (background thread/process trong cùng app)**
   - Poll job `QUEUED` theo FIFO.
   - Xử lý 1 job tại 1 thời điểm.
   - Chunk text -> gọi Google RPC từng chunk -> decode/ghép audio -> export mp3.
   - Cập nhật progress liên tục.

4. **Google Translate Web TTS Client (undocumented adapter)**
   - Lấy/cached WIZ tokens (`f.sid`, `bl`, `at`) TTL 1h.
   - Gọi `batchexecute` với payload đúng format.
   - Parse response nhiều lớp để lấy base64 MP3.

5. **Audio Processor**
   - Decode từng chunk mp3.
   - Ghép bằng `pydub` + `ffmpeg`.
   - Chèn khoảng lặng tùy cấu hình.
   - Xuất 1 file mp3 kết quả chuẩn.

## 3.2 Luồng high-level

1. Client gọi `POST /v1/jobs` với text/lang.
2. API tạo `job_id`, lưu `QUEUED`, trả ngay `job_id`.
3. Worker lấy job FIFO -> set `RUNNING`.
4. Worker chunk text, xử lý lần lượt từng chunk.
5. Sau mỗi chunk: cập nhật `processed_chunks`, `progress_pct`, `current_position`.
6. Xong toàn bộ: export mp3, set `SUCCEEDED`, lưu `result_file_name` + `result_file_path`.
7. Client poll `GET /v1/jobs/{job_id}` để theo dõi trạng thái và lấy metadata file.

---

## 4) API contract đề xuất

## 4.1 Tạo job

**POST** `/v1/jobs`

Request:
```json
{
  "text": "<very long text>",
  "lang": "vi",
  "voice_hint": null,
  "metadata": {
    "source": "novel-chapter-12"
  }
}
```

Response `202 Accepted`:
```json
{
  "job_id": "a7f5c2f4-8e2f-4f64-9c7f-5e07f1f6f2a1",
  "status": "QUEUED",
  "created_at": "2026-04-08T10:15:00Z"
}
```

Ghi chú:
- Không trả audio/data URL ở endpoint này.
- Chỉ trả định danh để tracking.

## 4.2 Tracking job

**GET** `/v1/jobs/{job_id}`

Response mẫu khi đang chạy:
```json
{
  "job_id": "a7f5c2f4-8e2f-4f64-9c7f-5e07f1f6f2a1",
  "status": "RUNNING",
  "progress": {
    "total_chunks": 120,
    "processed_chunks": 37,
    "progress_pct": 30.83,
    "position": {
      "current_chunk_index": 37,
      "current_char_offset": 7420,
      "total_chars": 24180
    }
  },
  "result": {
    "file_name": null,
    "file_path": null,
    "duration_ms": null
  },
  "error": null,
  "created_at": "2026-04-08T10:15:00Z",
  "started_at": "2026-04-08T10:15:02Z",
  "updated_at": "2026-04-08T10:17:40Z",
  "finished_at": null
}
```

Response mẫu khi hoàn tất:
```json
{
  "job_id": "a7f5c2f4-8e2f-4f64-9c7f-5e07f1f6f2a1",
  "status": "SUCCEEDED",
  "progress": {
    "total_chunks": 120,
    "processed_chunks": 120,
    "progress_pct": 100.0,
    "position": {
      "current_chunk_index": 120,
      "current_char_offset": 24180,
      "total_chars": 24180
    }
  },
  "result": {
    "file_name": "a7f5c2f4-8e2f-4f64-9c7f-5e07f1f6f2a1.mp3",
    "file_path": "outputs/2026-04-08/a7f5c2f4-8e2f-4f64-9c7f-5e07f1f6f2a1.mp3",
    "duration_ms": 1834021
  },
  "error": null,
  "created_at": "2026-04-08T10:15:00Z",
  "started_at": "2026-04-08T10:15:02Z",
  "updated_at": "2026-04-08T10:25:13Z",
  "finished_at": "2026-04-08T10:25:13Z"
}
```

## 4.3 (Tuỳ chọn nhưng nên có) Lấy danh sách job gần đây

**GET** `/v1/jobs?status=RUNNING&limit=20`

Mục đích:
- Quan sát hệ thống local.
- Hữu ích khi client bị mất `job_id` tạm thời.

---

## 5) Job state machine

Trạng thái chuẩn:
- `QUEUED`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `CANCELED` (optional phase 2)

Transition:
- `QUEUED -> RUNNING`
- `RUNNING -> SUCCEEDED | FAILED`
- `QUEUED/RUNNING -> CANCELED` (nếu triển khai cancel)

Nguyên tắc:
- Chỉ worker được phép chuyển trạng thái runtime.
- API tracking chỉ đọc, không sửa trạng thái.

---

## 6) Thiết kế dữ liệu SQLite

## 6.1 Bảng `jobs`

Các cột đề xuất:
- `job_id TEXT PRIMARY KEY`
- `status TEXT NOT NULL`
- `input_text TEXT NOT NULL`
- `lang TEXT NOT NULL`
- `voice_hint TEXT NULL`
- `total_chars INTEGER NOT NULL`
- `total_chunks INTEGER NULL`
- `processed_chunks INTEGER NOT NULL DEFAULT 0`
- `progress_pct REAL NOT NULL DEFAULT 0`
- `current_chunk_index INTEGER NOT NULL DEFAULT 0`
- `current_char_offset INTEGER NOT NULL DEFAULT 0`
- `result_file_name TEXT NULL`
- `result_file_path TEXT NULL`
- `result_duration_ms INTEGER NULL`
- `error_code TEXT NULL`
- `error_message TEXT NULL`
- `retry_count INTEGER NOT NULL DEFAULT 0`
- `created_at TEXT NOT NULL`
- `started_at TEXT NULL`
- `updated_at TEXT NOT NULL`
- `finished_at TEXT NULL`

Index:
- `idx_jobs_status_created_at(status, created_at)`
- `idx_jobs_updated_at(updated_at)`

## 6.2 Bảng `job_chunks` (khuyến nghị)

Mục tiêu: debug/khôi phục tốt hơn.

Cột:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `job_id TEXT NOT NULL`
- `chunk_index INTEGER NOT NULL`
- `chunk_text TEXT NOT NULL`
- `char_start INTEGER NOT NULL`
- `char_end INTEGER NOT NULL`
- `status TEXT NOT NULL` (`PENDING|DONE|FAILED`)
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `error_message TEXT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Unique:
- `(job_id, chunk_index)`

---

## 7) Xử lý text/chunking

Pipeline:
1. Normalize text:
   - trim, collapse whitespace,
   - thay chuỗi ký tự vô nghĩa phổ biến,
   - giữ dấu câu cần cho ngữ điệu.
2. Sentence split (ưu tiên theo câu).
3. Ghép câu thành chunk <= `MAX_CHARS_PER_CHUNK` (mặc định 200).
4. Fallback nếu câu đơn quá dài: cắt mềm theo từ/ký tự.

Output chunk phải giữ metadata:
- `chunk_index`
- `char_start`, `char_end`
- `text`

Các metadata này dùng cho endpoint tracking vị trí.

---

## 8) Google RPC adapter (undocumented)

## 8.1 Token manager

- Endpoint scrape: `https://translate.google.com/`
- Regex key:
  - `f.sid` qua `"FdrFJe":"(.*?)"`
  - `bl` qua `"cfb2h":"(.*?)"`
  - `at` qua `"SNlM0e":"(.*?)"`
- Cache in-memory TTL 1h.
- Khi request lỗi auth/parse token: invalidate cache -> scrape lại 1 lần.

## 8.2 Synthesize 1 chunk

- POST `/_/TranslateWebserverUi/data/batchexecute`
- Query params gồm `rpcids=jQ1olc`, `f.sid`, `bl`, `_reqid`, ...
- Body form-urlencoded:
  - `f.req=<nested JSON payload>`
  - `at=<token>`
- Header bắt buộc:
  - `Content-Type: application/x-www-form-urlencoded;charset=utf-8`
  - `User-Agent: browser-like UA`

## 8.3 Parse response

- Tách envelope theo format batchexecute.
- Parse lớp JSON ngoài -> lấy `envelopes[0][2]`.
- Parse tiếp payload -> lấy base64 mp3 tại `payload[0]`.

---

## 9) Worker tuần tự và hàng đợi

Thiết kế worker:
- Một vòng lặp duy nhất (singleton worker).
- Poll `jobs WHERE status='QUEUED' ORDER BY created_at ASC LIMIT 1`.
- Nếu không có job: sleep ngắn (vd 500ms).
- Nếu có job:
  1. `RUNNING`, set `started_at`.
  2. chunk input + persist `job_chunks`.
  3. synthesize tuần tự từng chunk.
  4. cập nhật tiến độ sau mỗi chunk.
  5. merge/export mp3.
  6. set `SUCCEEDED` + metadata file.

Retry policy khuyến nghị:
- Mỗi chunk retry tối đa 2 lần khi lỗi tạm thời (`429`, timeout, 5xx).
- Backoff: `1s -> 2s` + jitter.
- Nếu vẫn fail: đánh `FAILED` toàn job, lưu `error_code/error_message`.

---

## 10) Audio merge/output

Đề xuất chuẩn:
- Decode base64 -> bytes.
- Dùng `pydub.AudioSegment.from_file(BytesIO(...), format='mp3')`.
- Cộng dồn segment + `silent_blip_ms` giữa chunk (vd 120–250ms).
- Export mp3 final bằng ffmpeg.

Quy ước lưu file:
- Root: `outputs/YYYY-MM-DD/`
- Tên file: `<job_id>.mp3`

Lý do:
- Dễ truy vết theo ngày và theo job.
- Tránh xung đột tên file.

---

## 11) Cấu hình hệ thống

Biến cấu hình chính:
- `DB_PATH=./data/jobs.db`
- `OUTPUT_DIR=./outputs`
- `MAX_CHARS_PER_CHUNK=200`
- `WORKER_POLL_INTERVAL_MS=500`
- `REQUEST_TIMEOUT_SEC=20`
- `CHUNK_RETRY_MAX=2`
- `RANDOM_DELAY_MIN_SEC=0.5`
- `RANDOM_DELAY_MAX_SEC=1.5`
- `SILENT_BETWEEN_CHUNKS_MS=180`
- `TOKEN_TTL_SEC=3600`

Nguyên tắc:
- Có default hợp lý.
- Cho override qua `.env`.

---

## 12) Error handling & observability

Phân loại lỗi:
1. **Input errors**: text rỗng, lang invalid -> `400`.
2. **Provider transient**: timeout/429/5xx -> retry theo policy.
3. **Provider hard fail**: parse response fail liên tiếp, token invalid liên tiếp -> fail job.
4. **Internal errors**: sqlite lock, ffmpeg missing, disk full -> fail job.

Chuẩn hóa mã lỗi job (`error_code`):
- `INPUT_INVALID`
- `TOKEN_SCRAPE_FAILED`
- `PROVIDER_RATE_LIMITED`
- `PROVIDER_RESPONSE_INVALID`
- `AUDIO_MERGE_FAILED`
- `STORAGE_WRITE_FAILED`
- `UNEXPECTED_ERROR`

Logging:
- Log structured theo `job_id`, `chunk_index`, `event`.
- Tối thiểu log các sự kiện: job accepted/start/progress/success/fail.

---

## 13) Bảo mật & vận hành local

- Service mặc định bind `127.0.0.1` (không mở public).
- Giới hạn body size cho `POST /v1/jobs`.
- Sanitize metadata hiển thị ra response/log.
- Không ghi raw token WIZ vào log.
- Dọn file output cũ theo policy (phase 2).

Lưu ý pháp lý/kỹ thuật:
- API này là undocumented, có thể đổi bất kỳ lúc nào.
- Cần cơ chế graceful failure và thông báo rõ cho client.

---

## 14) Cấu trúc thư mục đề xuất

```text
python-tts-backend/
  app/
    main.py                 # FastAPI bootstrap + routes registration
    api/
      jobs.py               # POST/GET jobs endpoints
    db/
      models.py             # ORM models (jobs, job_chunks)
      session.py            # SQLite engine/session factory
      repo_jobs.py          # query/update helper
    worker/
      runner.py             # sequential worker loop
      processor.py          # process single job pipeline
    tts/
      google_adapter.py     # batchexecute client + parser
      token_manager.py      # WIZ scrape/cache
      chunker.py            # normalize + sentence/chunk logic
    audio/
      merger.py             # pydub merge/export
    core/
      config.py             # settings from env
      schemas.py            # pydantic request/response
      errors.py             # error codes / exception mapping
      logging.py            # structured logging helpers
  data/
    jobs.db
  outputs/
  requirements.txt
  .env.example
```

---

## 15) Trình tự thực thi 1 job (chi tiết)

1. API tạo bản ghi `jobs(status=QUEUED)`.
2. Worker pick job sớm nhất.
3. `RUNNING` + `started_at`.
4. Generate chunks + `total_chunks`.
5. For each chunk:
   - gọi adapter synthesize,
   - nhận base64 mp3,
   - decode thành segment,
   - append vào buffer merge,
   - update `processed_chunks`, `progress_pct`, `current_chunk_index`, `current_char_offset`,
   - sleep random delay.
6. Export file mp3 final.
7. Update `result_file_name/result_file_path/result_duration_ms`.
8. Set `SUCCEEDED` + `finished_at`.
9. Nếu fail ở bất kỳ bước nào: set `FAILED` + `error_code/error_message` + `finished_at`.

---

## 16) Test strategy (tối thiểu)

1. **Unit tests**
   - chunker: câu ngắn/dài/ký tự đặc biệt.
   - response parser: format batchexecute mẫu.
   - progress calculator: % và position đúng.

2. **Integration tests (local)**
   - POST job -> GET tracking chuyển trạng thái đúng.
   - Job thành công tạo file mp3 thật.
   - Lỗi provider -> trạng thái FAILED + error_code chuẩn.

3. **Resilience checks**
   - restart app giữa chừng: job `RUNNING` cũ cần quy ước xử lý (đề xuất: reset về `QUEUED` khi startup).
   - ffmpeg thiếu: fail rõ ràng `AUDIO_MERGE_FAILED`.

---

## 17) Roadmap phase tiếp theo (sau bản đầu)

- Cancel job endpoint.
- Download endpoint có auth local token.
- Resume từ chunk gần nhất sau crash.
- Giới hạn số job backlog.
- Multi-worker configurable (khi cần throughput).

---

## 18) Definition of Done (phase hiện tại)

Hoàn thành khi:
- `POST /v1/jobs` trả `job_id` ổn định.
- `GET /v1/jobs/{job_id}` phản ánh tiến độ + vị trí + tên file chính xác.
- Mỗi lần chỉ chạy đúng 1 job.
- Job thành công tạo MP3 hợp lệ.
- Job lỗi có `error_code` rõ ràng.
- Dữ liệu tracking còn sau khi restart app (SQLite persistence).
