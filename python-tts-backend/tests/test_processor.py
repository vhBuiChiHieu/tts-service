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

    def append_base64_mp3(self, b64: str) -> None:
        self.items.append(b64)

    def export(self, path: str) -> int:
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
