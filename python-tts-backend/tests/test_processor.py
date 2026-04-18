import os
import threading

from app.core.errors import JobErrorCode
from app.worker import processor as processor_module
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
        self.merged_chunk_paths = []
        self.chunk_dirs = []
        self.cleaned_dirs = []
        self.fail_cleanup = False

    def load(self, path: str) -> None:
        self.loaded_paths.append(path)

    def append_base64_mp3(self, b64: str) -> None:
        self.items.append(b64)

    def export(self, path: str) -> int:
        self.exported_paths.append(path)
        return 1000

    def export_chunk(self, b64: str, output_path: str) -> None:
        self.items.append(b64)
        self.exported_paths.append(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as chunk_file:
            chunk_file.write(b"chunk")

    def merge_files(self, input_paths, output_path: str) -> int:
        self.merged_chunk_paths.append(list(input_paths))
        self.exported_paths.append(output_path)
        with open(output_path, "wb") as output_file:
            output_file.write(b"merged")
        return 1000

    def chunk_path(self, chunk_dir: str, chunk_index: int) -> str:
        return os.path.join(chunk_dir, f"{chunk_index:04d}.mp3")

    def has_chunk(self, chunk_dir: str, chunk_index: int) -> bool:
        return os.path.exists(self.chunk_path(chunk_dir, chunk_index))

    def has_all_chunks(self, chunk_dir: str, processed_chunks: int) -> bool:
        return all(self.has_chunk(chunk_dir, idx) for idx in range(1, processed_chunks + 1))

    def chunk_paths_for_total(self, chunk_dir: str, total_chunks: int):
        return [self.chunk_path(chunk_dir, idx) for idx in range(1, total_chunks + 1)]

    def ensure_chunk_dir(self, chunk_dir: str) -> None:
        self.chunk_dirs.append(chunk_dir)
        os.makedirs(chunk_dir, exist_ok=True)

    def cleanup_chunk_dir(self, chunk_dir: str) -> None:
        self.cleaned_dirs.append(chunk_dir)
        if self.fail_cleanup:
            raise OSError("locked")
        for file_name in os.listdir(chunk_dir):
            os.remove(os.path.join(chunk_dir, file_name))
        os.rmdir(chunk_dir)


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

    original_min = processor_module.settings.random_delay_min_sec
    original_max = processor_module.settings.random_delay_max_sec
    processor_module.settings.random_delay_min_sec = 0.2
    processor_module.settings.random_delay_max_sec = 0.2
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
        processor_module.settings.random_delay_min_sec = original_min
        processor_module.settings.random_delay_max_sec = original_max

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

    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    first_chunk_path = chunk_dir / "0001.mp3"
    first_chunk_path.write_bytes(b"chunk-1")

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
        partial_output_path=str(chunk_dir),
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert [call["text"] for call in adapter.calls] == ["chunk-2", "chunk-3"]
    assert merger.loaded_paths == []
    assert merger.merged_chunk_paths == [[
        str(first_chunk_path),
        str(chunk_dir / "0002.mp3"),
        str(chunk_dir / "0003.mp3"),
    ]]
    assert merger.exported_paths == [
        str(chunk_dir / "0002.mp3"),
        str(chunk_dir / "0003.mp3"),
        output_path,
    ]
    assert not chunk_dir.exists()
    assert saved.status == "SUCCEEDED"
    assert saved.processed_chunks == 3
    assert saved.progress_pct == 100.0


def test_process_job_writes_each_chunk_before_final_merge(db_session, tmp_path):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="chunk-1 chunk-2",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )

    merger = DummyMerger()
    chunk_dir = tmp_path / "chunks"
    output_path = str(tmp_path / "test.mp3")
    chunks = [
        {"chunk_index": 1, "char_end": 7, "text": "chunk-1"},
        {"chunk_index": 2, "char_end": 15, "text": "chunk-2"},
    ]

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: chunks,
        adapter=DummyAdapter(),
        merger=merger,
        output_path=output_path,
        partial_output_path=str(chunk_dir),
        max_chars=200,
    )

    assert merger.exported_paths == [
        str(chunk_dir / "0001.mp3"),
        str(chunk_dir / "0002.mp3"),
        output_path,
    ]
    assert merger.merged_chunk_paths == [[
        str(chunk_dir / "0001.mp3"),
        str(chunk_dir / "0002.mp3"),
    ]]
    assert not chunk_dir.exists()
    saved = repo.get_job(job.job_id)
    assert saved.status == "SUCCEEDED"
    assert saved.progress_pct == 100.0


def test_process_job_restarts_from_zero_when_chunk_files_missing(db_session, tmp_path):
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
    repo.mark_failed(job.job_id, JobErrorCode.UNEXPECTED_ERROR, "chunks missing")

    adapter = DummyAdapter()
    merger = DummyMerger()
    chunks = [
        {"chunk_index": 1, "char_end": 7, "text": "chunk-1"},
        {"chunk_index": 2, "char_end": 15, "text": "chunk-2"},
        {"chunk_index": 3, "char_end": 23, "text": "chunk-3"},
    ]
    output_path = str(tmp_path / "test.mp3")
    chunk_dir = str(tmp_path / "missing-chunks")

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: chunks,
        adapter=adapter,
        merger=merger,
        output_path=output_path,
        partial_output_path=chunk_dir,
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert [call["text"] for call in adapter.calls] == ["chunk-1", "chunk-2", "chunk-3"]
    assert merger.loaded_paths == []
    assert saved.status == "SUCCEEDED"
    assert saved.processed_chunks == 3
    assert saved.progress_pct == 100.0


def test_process_job_marks_success_when_chunk_cleanup_fails(db_session, tmp_path):
    from app.db.repo_jobs import JobRepo

    repo = JobRepo(db_session)
    job = repo.create_job(
        input_text="chunk-1",
        lang="vi",
        voice_hint=None,
        speed=1.0,
        volume_gain_db=0.0,
    )
    chunk_dir = tmp_path / "chunks"
    output_path = str(tmp_path / "test.mp3")
    merger = DummyMerger()
    merger.fail_cleanup = True

    process_job(
        job_id=job.job_id,
        repo=repo,
        chunker=lambda text, max_chars: [{"chunk_index": 1, "char_end": len(text), "text": text}],
        adapter=DummyAdapter(),
        merger=merger,
        output_path=output_path,
        partial_output_path=str(chunk_dir),
        max_chars=200,
    )

    saved = repo.get_job(job.job_id)
    assert saved.status == "SUCCEEDED"
    assert chunk_dir.exists()
    assert saved.result_file_path == output_path.replace("\\", "/")
