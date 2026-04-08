# Workthrough: Implement `speed` / `volume` for Python Local TTS Backend

Mục tiêu: thêm khả năng điều chỉnh tốc độ đọc và âm lượng cho mỗi job, nhưng vẫn giữ backward-compatible với flow hiện tại.

---

## 1) Current state (baseline)

Hiện tại request TTS đang gọi payload cứng:
- `python-tts-backend/app/tts/google_adapter.py:36`
  - `json.dumps([text, lang, None])`

API hiện có `voice_hint` nhưng chưa dùng khi gọi provider:
- `python-tts-backend/app/core/schemas.py:7`
- `python-tts-backend/app/api/jobs.py:22`
- `python-tts-backend/app/db/models.py:21`
- `python-tts-backend/app/db/repo_jobs.py:17`

Kết luận: chưa có field speed/volume ở API + DB + pipeline.

---

## 2) Design đề xuất (safe-first)

### 2.1 API contract
Thêm field optional vào `CreateJobRequest`:
- `speed: float | None = None` (gợi ý range `0.5 -> 2.0`)
- `volume_gain_db: float | None = None` (gợi ý range `-20 -> 20`)

Nếu không truyền thì dùng mặc định:
- `speed = 1.0`
- `volume_gain_db = 0.0`

### 2.2 Persistence
Lưu cấu hình per-job trong bảng `jobs`:
- `speed REAL NOT NULL DEFAULT 1.0`
- `volume_gain_db REAL NOT NULL DEFAULT 0.0`

Cập nhật:
- model
- repo create_job
- response tracking (nếu muốn hiển thị cấu hình đã dùng)

### 2.3 Processing strategy
Áp dụng theo thứ tự:
1. **Speed**: truyền vào provider payload (nếu provider hỗ trợ). Nếu provider reject -> fallback 1.0.
2. **Volume**: xử lý hậu kỳ ở audio layer bằng `pydub` (ổn định hơn):
   - `segment = segment + volume_gain_db`

---

## 3) Implementation steps

## Step A — Add tests first (TDD)

### A1. API validation test
File: `python-tts-backend/tests/test_jobs_api.py`
- case accepted: speed=1.2, volume_gain_db=3
- case invalid: speed=0.1 hoặc volume_gain_db=100 => 422

### A2. Repo persistence test
File: `python-tts-backend/tests/test_repo_jobs.py`
- create job với speed/volume custom
- assert đọc ra đúng giá trị

### A3. Processor/audio behavior test
File: `python-tts-backend/tests/test_processor.py`
- verify processor truyền `speed` vào adapter call
- verify merger apply volume (có thể dùng fake merger để assert argument)

### A4. Adapter fallback test
File mới: `python-tts-backend/tests/test_google_adapter_speed.py`
- khi gọi với speed != 1.0 mà provider parse fail -> retry với speed=1.0
- đảm bảo không fail toàn job chỉ vì speed unsupported

---

## Step B — Schema and DB

### B1. Update request schema
File: `python-tts-backend/app/core/schemas.py`
- thêm field:
  - `speed: float | None = Field(default=1.0, ge=0.5, le=2.0)`
  - `volume_gain_db: float | None = Field(default=0.0, ge=-20.0, le=20.0)`

### B2. Update model
File: `python-tts-backend/app/db/models.py`
- thêm cột:
  - `speed`
  - `volume_gain_db`

### B3. Migration note
Hiện chưa có migration tool.
- Cách nhanh local: xóa DB cũ (`python-tts-backend/data/jobs.db`) rồi `init_db()` tạo lại.
- Nếu muốn giữ data: cần migration script `ALTER TABLE`.

### B4. Update repository
File: `python-tts-backend/app/db/repo_jobs.py`
- `create_job(...)` nhận thêm speed/volume và persist.

---

## Step C — API layer

File: `python-tts-backend/app/api/jobs.py`
- map payload.speed / payload.volume_gain_db vào `repo.create_job(...)`.

Optional: trả config trong response tracking để debug:
- thêm vào `JobTrackingResponse` hoặc `metadata` section.

---

## Step D — Adapter (speed)

File: `python-tts-backend/app/tts/google_adapter.py`

### D1. Signature
Đổi:
- `synthesize_base64(self, text, lang, reqid)`
Thành:
- `synthesize_base64(self, text, lang, reqid, speed=1.0)`

### D2. Payload experimentation
Hiện payload đang `[text, lang, None]`.
Tạo helper build payload theo speed:
- baseline: `[text, lang, None]`
- thử variant có speed (điều tra theo docs/trace thực tế).

### D3. Fallback logic
Nếu parse/provider fail ở variant custom speed:
- retry 1 lần với baseline payload (speed=1.0)
- nếu vẫn fail thì raise như hiện tại.

> Gợi ý: giữ logic fallback trong adapter để processor không phình.

---

## Step E — Audio volume

File: `python-tts-backend/app/audio/merger.py`

### E1. Extend class
- `AudioMerger(..., volume_gain_db: float = 0.0)`
- lưu `self.volume_gain_db`

### E2. Apply gain per chunk
Trong `append_base64_mp3`:
- decode mp3 -> `seg`
- nếu `volume_gain_db != 0`: `seg = seg + volume_gain_db`
- merge như cũ.

---

## Step F — Processor/runner wiring

File: `python-tts-backend/app/worker/processor.py`
- truyền `job.speed` vào `adapter.synthesize_base64(..., speed=job.speed)`

File: `python-tts-backend/app/worker/runner.py`
- khi tạo merger, truyền `volume_gain_db=job.volume_gain_db`.

---

## 4) Error handling policy

- Invalid input speed/volume -> trả `422` tại API boundary.
- Provider không nhận speed custom -> fallback speed=1.0 (không fail ngay).
- Nếu cả custom + fallback cùng fail -> giữ error mapping hiện có (`PROVIDER_RESPONSE_INVALID` / `UNEXPECTED_ERROR`).

---

## 5) Verification checklist

1. Unit tests pass toàn bộ:
```bash
pytest python-tts-backend/tests -v
```

2. Manual API:
- tạo job speed=1.3 volume=5
- tracking phải `SUCCEEDED`
- file mp3 có tồn tại

3. Quick audio sanity:
- so sánh 2 job cùng text:
  - default vs speed>1 (duration ngắn hơn)
  - default vs volume>0 (RMS lớn hơn / nghe to hơn)

---

## 6) Suggested rollout strategy

- Phase 1: implement `volume_gain_db` trước (chắc chắn, local control).
- Phase 2: implement `speed` với adapter fallback (do provider undocumented).
- Phase 3: nếu speed provider không ổn định, cân nhắc speed bằng ffmpeg filter hậu kỳ.

---

## 7) Notes for future

- `voice_hint` hiện chưa sử dụng; có thể map thành preset (`male_soft`, `female_clear`, ...) rồi translate thành speed/volume defaults.
- Nếu cần reproducible hơn, ghi lại `effective_speed` và `effective_volume_gain_db` trong job result.
