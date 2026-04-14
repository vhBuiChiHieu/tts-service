import base64
import subprocess
import sys
from io import BytesIO

import pydub.audio_segment
import pydub.utils
from pydub import AudioSegment


def _patch_pydub_subprocess_for_windows() -> None:
    if sys.platform != "win32":
        return
    if getattr(_patch_pydub_subprocess_for_windows, "_patched", False):
        return

    original_popen = subprocess.Popen
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def hidden_popen(*args, **kwargs):
        startupinfo = kwargs.get("startupinfo")
        if startupinfo is None:
            startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | create_no_window
        return original_popen(*args, **kwargs)

    pydub.audio_segment.subprocess.Popen = hidden_popen
    pydub.utils.Popen = hidden_popen
    _patch_pydub_subprocess_for_windows._patched = True


_patch_pydub_subprocess_for_windows()


class AudioMerger:
    def __init__(self, silent_between_chunks_ms: int, volume_gain_db: float = 0.0, speed: float = 1.0) -> None:
        self.buffer = AudioSegment.empty()
        self.silence = AudioSegment.silent(duration=silent_between_chunks_ms)
        self.volume_gain_db = volume_gain_db
        self.speed = speed

    def append_base64_mp3(self, b64: str) -> None:
        raw = base64.b64decode(b64)
        seg = AudioSegment.from_file(BytesIO(raw), format="mp3")
        if self.volume_gain_db != 0.0:
            seg = seg + self.volume_gain_db
        self.buffer += seg + self.silence

    def export(self, output_path: str) -> int:
        if self.speed == 1.0:
            self.buffer.export(output_path, format="mp3")
        else:
            if self.speed < 0.5 or self.speed > 2.0:
                raise ValueError(f"invalid speed for post-process: {self.speed}")
            self.buffer.export(
                output_path,
                format="mp3",
                parameters=["-filter:a", f"atempo={self.speed}"],
            )
        exported = AudioSegment.from_file(output_path, format="mp3")
        return len(exported)
