import base64
from io import BytesIO

from pydub import AudioSegment
from pydub.generators import Sine

from app.audio.merger import AudioMerger


def _b64_from_segment(seg: AudioSegment) -> str:
    buf = BytesIO()
    seg.export(buf, format="mp3")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_export_speed_2_shorter_than_speed_1(tmp_path):
    tone = Sine(440).to_audio_segment(duration=3000)
    b64 = _b64_from_segment(tone)

    out_1 = tmp_path / "speed1.mp3"
    merger_1 = AudioMerger(silent_between_chunks_ms=0, volume_gain_db=0.0, speed=1.0)
    merger_1.append_base64_mp3(b64)
    duration_1 = merger_1.export(str(out_1))

    out_2 = tmp_path / "speed2.mp3"
    merger_2 = AudioMerger(silent_between_chunks_ms=0, volume_gain_db=0.0, speed=2.0)
    merger_2.append_base64_mp3(b64)
    duration_2 = merger_2.export(str(out_2))

    assert duration_2 < duration_1 * 0.9
