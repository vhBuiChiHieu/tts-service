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
            split_at = max_chars
            window = current[: max_chars + 1]
            punct_at = max(window.rfind("."), window.rfind("!"), window.rfind("?"), window.rfind(";"), window.rfind(","), window.rfind(":"))
            space_at = window.rfind(" ")

            if punct_at > 0:
                split_at = punct_at + 1
            elif space_at > 0:
                split_at = space_at

            head_raw = current[:split_at]
            tail_raw = current[split_at:]
            head = head_raw.rstrip()
            consumed = len(head_raw)

            if not head:
                head = current[:max_chars].rstrip()
                consumed = max_chars
                tail_raw = current[consumed:]

            current = head
            flush_chunk()

            next_current = tail_raw.lstrip()
            stripped = len(tail_raw) - len(next_current)
            current = next_current
            current_start += consumed + stripped

    flush_chunk()
    return chunks
