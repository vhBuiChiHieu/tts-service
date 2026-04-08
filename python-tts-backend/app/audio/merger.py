import base64
from io import BytesIO

from pydub import AudioSegment


class AudioMerger:
    def __init__(self, silent_between_chunks_ms: int, volume_gain_db: float = 0.0) -> None:
        self.buffer = AudioSegment.empty()
        self.silence = AudioSegment.silent(duration=silent_between_chunks_ms)
        self.volume_gain_db = volume_gain_db

    def append_base64_mp3(self, b64: str) -> None:
        raw = base64.b64decode(b64)
        seg = AudioSegment.from_file(BytesIO(raw), format="mp3")
        if self.volume_gain_db != 0.0:
            seg = seg + self.volume_gain_db
        self.buffer += seg + self.silence

    def export(self, output_path: str) -> int:
        self.buffer.export(output_path, format="mp3")
        return len(self.buffer)
