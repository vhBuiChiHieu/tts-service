import re


def normalize_text(text: str) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    return value


def build_chunks(text: str, max_chars: int) -> list[dict]:
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("text is empty")

    sentences = re.split(r"(?<=[.!?;])\s+", normalized)
    chunks: list[dict] = []

    current = ""
    current_start = 0
    cursor = 0

    def flush_chunk() -> None:
        nonlocal current, current_start
        if not current:
            return
        chunk_index = len(chunks) + 1
        chunks.append(
            {
                "chunk_index": chunk_index,
                "char_start": current_start,
                "char_end": current_start + len(current),
                "text": current,
            }
        )
        current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_len = len(sentence)
        if not current:
            current = sentence
            current_start = cursor
        elif len(current) + 1 + sentence_len <= max_chars:
            current = f"{current} {sentence}"
        else:
            flush_chunk()
            current = sentence
            current_start = cursor

        cursor += sentence_len + 1

        while len(current) > max_chars:
            overflow = current[max_chars:]
            current = current[:max_chars].rstrip()
            flush_chunk()
            current = overflow.lstrip()
            current_start += max_chars

    flush_chunk()
    return chunks
