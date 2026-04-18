import os
import random
import threading

from app.core.config import settings
from app.core.errors import JobErrorCode


def _raise_if_stopping(stop_event: threading.Event | None) -> None:
    if stop_event and stop_event.is_set():
        raise RuntimeError("backend is shutting down")


def process_job(job_id, repo, chunker, adapter, merger, output_path, partial_output_path=None, max_chars=200, stop_event=None):
    job = repo.get_job(job_id)
    if not job:
        return

    try:
        _raise_if_stopping(stop_event)
        repo.mark_running(job_id)
        chunks = chunker(job.input_text, max_chars)
        total_chunks = len(chunks)
        start_index = job.processed_chunks

        if partial_output_path and start_index > 0:
            if os.path.exists(partial_output_path):
                merger.load(partial_output_path)
            else:
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

        for idx, chunk in enumerate(chunks[start_index:], start=start_index + 1):
            _raise_if_stopping(stop_event)
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
            if partial_output_path:
                merger.export(partial_output_path)
            delay = random.uniform(settings.random_delay_min_sec, settings.random_delay_max_sec)
            if stop_event and stop_event.wait(delay):
                raise RuntimeError("backend is shutting down")

        _raise_if_stopping(stop_event)
        duration_ms = merger.export(output_path)
        repo.mark_success(job_id, output_path=output_path, duration_ms=duration_ms)
        if partial_output_path and os.path.exists(partial_output_path):
            try:
                os.remove(partial_output_path)
            except OSError:
                pass
    except ValueError as exc:
        repo.mark_failed(job_id, JobErrorCode.PROVIDER_RESPONSE_INVALID, str(exc))
    except RuntimeError as exc:
        repo.mark_failed(job_id, JobErrorCode.BACKEND_SHUTDOWN, str(exc))
    except Exception as exc:
        repo.mark_failed(job_id, JobErrorCode.UNEXPECTED_ERROR, str(exc))
