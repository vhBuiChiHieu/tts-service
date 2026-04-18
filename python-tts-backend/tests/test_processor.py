import threading

from app.core.errors import JobErrorCode
from app.worker.processor import process_job


class DummyAdapter:
    def __init__(self):
        self.calls = []

    def synthesize_base64(self, text: str, lang: str, reqid: int, speed: float = 1.0) -> str:
        self.calls.append({"text": text, "lang": lang, "reqid": reqid, "speed": speed})
        return "SUQz"


class DummyMerger:
    def __init__(self):
        self.items = []
        self.loaded_paths = []
        self.exported_paths = []

    def load(self, path: str) -> None:
        self.loaded_paths.append(path)

    def append_base64_mp3(self, b64: str) -> None:
        self.items.append(b64)

    def export(self, path: str) -> int:
        self.exported_paths.append(path)
        return 1000


def test_process_job_marks_success(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="Xin chao. Day la test.",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=DummyAdapter(),
        merger=DummyMerger(),
        output_path="outputs/test.mp3",
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert saved.status == "SUCCEEDED"
    assert saved.progress_pct == 100.0


def test_process_job_uses_default_provider_speed(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="Xin chao. Day la test.",
        lang="vi",
        voice_hint=None,
        speed=1.4,
        volume_gain_db=2.0,
    )

    adapter = DummyAdapter()
    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=adapter,
        merger=DummyMerger(),
        output_path="outputs/test.mp3",
        max_chars=200,
    )

    assert adapter.calls[0]["speed"] == 1.0


def test_process_job_forces_provider_speed_to_1(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="Xin chao. Day la test.",
        lang="vi",
        voice_hint=None,
        speed=2.0,
        volume_gain_db=0.0,
    )

    adapter = DummyAdapter()
    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=adapter,
        merger=DummyMerger(),
        output_path="outputs/test.mp3",
        max_chars=200,
    )

    assert adapter.calls[0]["speed"] == 1.0


def test_process_job_marks_failed_when_shutdown_requested(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="Xin chao. Day la test.",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )

    stop_event = threading.Event()
    stop_event.set()
    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=DummyAdapter(),
        merger=DummyMerger(),
        output_path="outputs/test.mp3",
        max_chars=200,
        stop_event=stop_event,
    )

    saved = repo.get_job(job.job_id)
    assert saved.status == "FAILED"
    assert saved.error_code == JobErrorCode.BACKEND_SHUTDOWN
    assert saved.error_message == "backend is shutting down"


def test_process_job_stops_during_chunk_delay(db_session):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="Xin chao. Day la test.",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )

    stop_event = threading.Event()

    def chunker(text, max_chars):
        return [
            {"chunk_index": 1, "char_end": len(text) // 2, "text": text[: len(text) // 2]},
            {"chunk_index": 2, "char_end": len(text), "text": text[len(text) // 2 :]},
        ]

    original_min = __import__("app.worker.processor", fromlist=["settings"]).settings.random_delay_min_sec
    original_max = __import__("app.worker.processor", fromlist=["settings"]).settings.random_delay_max_sec
    processor_settings = __import__("app.worker.processor", fromlist=["settings"]).settings
    processor_settings.random_delay_min_sec = 0.2
    processor_settings.random_delay_max_sec = 0.2
    try:
        timer = threading.Timer(0.05, stop_event.set)
        timer.start()
        process_job(
            job_id=job.job_id,
            repo=repo,
            chunker=chunker,
            adapter=DummyAdapter(),
            merger=DummyMerger(),
            output_path="outputs/test.mp3",
            max_chars=200,
            stop_event=stop_event,
        )
        timer.cancel()
    finally:
        processor_settings.random_delay_min_sec = original_min
        processor_settings.random_delay_max_sec = original_max

    saved = repo.get_job(job.job_id)
    assert saved.status == "FAILED"
    assert saved.error_code == JobErrorCode.BACKEND_SHUTDOWN
    assert saved.processed_chunks == 1
    assert saved.progress_pct == 50.0
    assert saved.error_message == "backend is shutting down"


def test_process_job_resumes_from_processed_chunks(db_session, tmp_path):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="chunk-1 chunk-2 chunk-3",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )
    repo.update_progress(
        job_id=job.job_id,
        total_chunks=3,
        processed_chunks=1,
        current_chunk_index=1,
        current_char_offset=7,
        total_chars=len(job.input_text),
    )
    repo.mark_failed(job.job_id, JobErrorCode.UNEXPECTED_ERROR, "partial written")

    partial_output_path = tmp_path / "test.mp3.partial"
    partial_output_path.write_bytes(b"partial")

    adapter = DummyAdapter()
    merger = DummyMerger()
    chunks = [
        {"chunk_index": 1, "char_end": 7, "text": "chunk-1"},
        {"chunk_index": 2, "char_end": 15, "text": "chunk-2"},
        {"chunk_index": 3, "char_end": 23, "text": "chunk-3"},
    ]
    output_path = str(tmp_path / "test.mp3")

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: chunks,
        adapter=adapter,
        merger=merger,
        output_path=output_path,
        partial_output_path=str(partial_output_path),
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert [call["text"] for call in adapter.calls] == ["chunk-2", "chunk-3"]
    assert merger.loaded_paths == [str(partial_output_path)]
    assert merger.exported_paths == [str(partial_output_path), str(partial_output_path), output_path]
    assert not partial_output_path.exists()
    assert saved.status == "SUCCEEDED"
    assert saved.processed_chunks == 3
    assert saved.progress_pct == 100.0


def test_process_job_restarts_from_zero_when_partial_missing(db_session, tmp_path):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="chunk-1 chunk-2 chunk-3",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )
    repo.update_progress(
        job_id=job.job_id,
        total_chunks=3,
        processed_chunks=2,
        current_chunk_index=2,
        current_char_offset=15,
        total_chars=len(job.input_text),
    )
    repo.mark_failed(job.job_id, JobErrorCode.UNEXPECTED_ERROR, "partial missing")

    adapter = DummyAdapter()
    merger = DummyMerger()
    chunks = [
        {"chunk_index": 1, "char_end": 7, "text": "chunk-1"},
        {"chunk_index": 2, "char_end": 15, "text": "chunk-2"},
        {"chunk_index": 3, "char_end": 23, "text": "chunk-3"},
    ]
    output_path = str(tmp_path / "test.mp3")
    partial_output_path = str(tmp_path / "missing.mp3.partial")

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: chunks,
        adapter=adapter,
        merger=merger,
        output_path=output_path,
        partial_output_path=partial_output_path,
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert [call["text"] for call in adapter.calls] == ["chunk-1", "chunk-2", "chunk-3"]
    assert merger.loaded_paths == []
    assert saved.status == "SUCCEEDED"
    assert saved.processed_chunks == 3
    assert saved.progress_pct == 100.0


def test_process_job_marks_success_when_partial_cleanup_fails(db_session, tmp_path, monkeypatch):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="chunk-1",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )
    partial_output_path = tmp_path / "test.mp3.partial"
    partial_output_path.write_bytes(b"partial")
    output_path = str(tmp_path / "test.mp3")

    monkeypatch.setattr("app.worker.processor.os.remove", lambda path: (_ for _ in ()).throw(PermissionError("locked")))

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=DummyAdapter(),
        merger=DummyMerger(),
        output_path=output_path,
        partial_output_path=str(partial_output_path),
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert saved.status == "SUCCEEDED"
    assert partial_output_path.exists()
    assert saved.result_file_path == output_path.replace("\\", "/")
