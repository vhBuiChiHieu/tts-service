import random
import time

from app.core.config import settings
from app.core.errors import JobErrorCode


def process_job(job_id, repo, chunker, adapter, merger, output_path, max_chars):
    job = repo.get_job(job_id)
    if not job:
        return

    try:
        repo.mark_running(job_id)
        chunks = chunker(job.input_text, max_chars)
        total_chunks = len(chunks)

        for idx, chunk in enumerate(chunks, start=1):
            last_error = None
            for _ in range(settings.chunk_retry_max + 1):
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
            time.sleep(random.uniform(settings.random_delay_min_sec, settings.random_delay_max_sec))

        duration_ms = merger.export(output_path)
        repo.mark_success(job_id, output_path=output_path, duration_ms=duration_ms)
    except ValueError as exc:
        repo.mark_failed(job_id, JobErrorCode.PROVIDER_RESPONSE_INVALID, str(exc))
    except Exception as exc:
        repo.mark_failed(job_id, JobErrorCode.UNEXPECTED_ERROR, str(exc))
