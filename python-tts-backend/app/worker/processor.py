import random
import threading

from app.core.config import settings
from app.core.errors import JobErrorCode


class JobCancelled(Exception):
    pass


def _raise_if_cancel_requested(repo, job_id: str) -> None:
    if repo.is_cancel_requested(job_id):
        raise JobCancelled("job cancellation requested")


def _raise_if_stopping(stop_event: threading.Event | None) -> None:
    if stop_event and stop_event.is_set():
        raise RuntimeError("backend is shutting down")


def process_job(job_id, repo, chunker, adapter, merger, output_path, partial_output_path=None, max_chars=200, stop_event=None):
    job = repo.get_job(job_id)
    if not job:
        return

    try:
        repo.mark_running(job_id)
        _raise_if_cancel_requested(repo, job_id)
        _raise_if_stopping(stop_event)
        chunks = chunker(job.input_text, max_chars)
        total_chunks = len(chunks)
        chunk_dir = partial_output_path
        start_index = job.processed_chunks

        if chunk_dir and start_index > 0 and not merger.has_all_chunks(chunk_dir, start_index):
            # Nếu metadata progress còn nhưng file chunk tạm đã mất thì phải chạy lại từ đầu để tránh thiếu audio đầu file.
            start_index = 0
            repo.update_progress(
                job_id=job_id,
                total_chunks=total_chunks,
                processed_chunks=0,
                current_chunk_index=0,
                current_char_offset=0,
                total_chars=len(job.input_text),
            )
            job = repo.get_job(job_id)
            if not job:
                return

        if chunk_dir:
            merger.ensure_chunk_dir(chunk_dir)

        for idx, chunk in enumerate(chunks[start_index:], start=start_index + 1):
            _raise_if_stopping(stop_event)
            _raise_if_cancel_requested(repo, job_id)
            last_error = None
            for _ in range(settings.chunk_retry_max + 1):
                _raise_if_stopping(stop_event)
                try:
                    b64 = adapter.synthesize_base64(
                        chunk["text"],
                        job.lang,
                        reqid=10000 + idx,
                        speed=1.0,
                    )
                    if chunk_dir:
                        merger.export_chunk(b64, merger.chunk_path(chunk_dir, idx))
                    else:
                        merger.append_base64_mp3(b64)
                    break
                except ValueError as exc:
                    last_error = exc
                    continue
            else:
                raise ValueError(str(last_error) if last_error else "provider response invalid")

            repo.update_progress(
                job_id=job_id,
                total_chunks=total_chunks,
                processed_chunks=idx,
                current_chunk_index=idx,
                current_char_offset=chunk["char_end"],
                total_chars=len(job.input_text),
            )
            _raise_if_cancel_requested(repo, job_id)
            delay = random.uniform(settings.random_delay_min_sec, settings.random_delay_max_sec)
            if stop_event and stop_event.wait(delay):
                raise RuntimeError("backend is shutting down")

        _raise_if_stopping(stop_event)
        _raise_if_cancel_requested(repo, job_id)
        if chunk_dir:
            duration_ms = merger.merge_files(merger.chunk_paths_for_total(chunk_dir, total_chunks), output_path)
        else:
            duration_ms = merger.export(output_path)
        _raise_if_cancel_requested(repo, job_id)
        repo.mark_success(job_id, output_path=output_path, duration_ms=duration_ms)
        if chunk_dir:
            try:
                merger.cleanup_chunk_dir(chunk_dir)
            except OSError:
                pass
    except ValueError as exc:
        repo.mark_failed(job_id, JobErrorCode.PROVIDER_RESPONSE_INVALID, str(exc))
    except JobCancelled:
        repo.mark_cancelled(job_id)
    except RuntimeError as exc:
        repo.mark_failed(job_id, JobErrorCode.BACKEND_SHUTDOWN, str(exc))
    except Exception as exc:
        repo.mark_failed(job_id, JobErrorCode.UNEXPECTED_ERROR, str(exc))
