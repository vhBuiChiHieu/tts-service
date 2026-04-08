from app.tts.chunker import build_chunks


def test_build_chunks_with_offsets():
    text = "Xin chao. Day la cau thu hai!"
    chunks = build_chunks(text=text, max_chars=12)

    assert len(chunks) >= 2
    assert chunks[0]["chunk_index"] == 1
    assert chunks[0]["char_start"] == 0
    assert chunks[-1]["char_end"] <= len(text)


def test_build_chunks_empty_text_raises():
    try:
        build_chunks(text="   ", max_chars=200)
    except ValueError as exc:
        assert str(exc) == "text is empty"
    else:
        assert False, "expected ValueError"


def test_build_chunks_overflow_prefers_whitespace_not_midword_split():
    text = "abcde fghij"
    chunks = build_chunks(text=text, max_chars=7)

    assert chunks[0]["text"] == "abcde"
    assert chunks[1]["text"] == "fghij"


def test_build_chunks_overflow_prefers_punctuation_boundary():
    text = "xin chao, ban oi toi day"
    chunks = build_chunks(text=text, max_chars=12)

    assert chunks[0]["text"].endswith(",")
    assert chunks[0]["text"] == "xin chao,"
    assert chunks[1]["text"].startswith("ban")

    for chunk in chunks:
        assert len(chunk["text"]) <= 12
        assert chunk["text"]
