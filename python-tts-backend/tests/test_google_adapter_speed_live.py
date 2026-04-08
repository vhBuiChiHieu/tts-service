import base64
from io import BytesIO

import pytest
from pydub import AudioSegment

from app.tts.google_adapter import GoogleTranslateAdapter
from app.tts.token_manager import TokenManager


def _duration_ms_from_b64_mp3(b64_audio: str) -> int:
    raw = base64.b64decode(b64_audio)
    seg = AudioSegment.from_file(BytesIO(raw), format="mp3")
    return len(seg)


@pytest.mark.skip(reason="Provider custom speed is unreliable; speed is now controlled in post-processing")
def test_live_google_speed_2_is_shorter_than_speed_1():
    token_manager = TokenManager(ttl_sec=3600, user_agent="Mozilla/5.0")
    adapter = GoogleTranslateAdapter(
        token_manager=token_manager,
        request_timeout_sec=20,
        user_agent="Mozilla/5.0",
    )

    text = "Xin chao ban, day la bai kiem tra toc do doc cua Google TTS tren cung mot noi dung ngan."

    b64_speed_1 = adapter.synthesize_base64(text=text, lang="vi", reqid=30001, speed=1.0)
    b64_speed_2 = adapter.synthesize_base64(text=text, lang="vi", reqid=30002, speed=2.0)

    duration_1 = _duration_ms_from_b64_mp3(b64_speed_1)
    duration_2 = _duration_ms_from_b64_mp3(b64_speed_2)

    assert duration_2 < duration_1 * 0.9, (
        f"Expected speed=2.0 to be clearly shorter than speed=1.0, got duration_1={duration_1}ms, duration_2={duration_2}ms"
    )
