import base64
import os
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
        self.crossfade_ms = 25
        self.target_peak_dbfs = -1.0
        self.target_sample_rate = 44100
        self.export_quality = "2"

    def _prepare_segment(self, seg: AudioSegment) -> AudioSegment:
        prepared = seg.set_frame_rate(self.target_sample_rate).set_sample_width(2)
        if self.volume_gain_db != 0.0:
            prepared = prepared + self.volume_gain_db
        if prepared.max_dBFS != float("-inf") and prepared.max_dBFS > self.target_peak_dbfs:
            prepared = prepared.apply_gain(self.target_peak_dbfs - prepared.max_dBFS)
        return prepared

    def _append_with_crossfade(self, base: AudioSegment, addition: AudioSegment) -> AudioSegment:
        if len(base) == 0:
            return addition
        effective_crossfade = min(self.crossfade_ms, len(base), len(addition))
        if effective_crossfade <= 0:
            return base + addition
        return base.append(addition, crossfade=effective_crossfade)

    def _export(self, audio: AudioSegment, output_path: str) -> int:
        export_parameters = ["-q:a", self.export_quality]
        if self.speed != 1.0:
            if self.speed < 0.5 or self.speed > 2.0:
                raise ValueError(f"invalid speed for post-process: {self.speed}")
            export_parameters.extend(["-filter:a", f"atempo={self.speed}"])
        audio.export(output_path, format="mp3", parameters=export_parameters)
        exported = AudioSegment.from_file(output_path, format="mp3")
        return len(exported)

    def load(self, input_path: str) -> None:
        self.buffer = self._prepare_segment(AudioSegment.from_file(input_path, format="mp3"))

    def append_base64_mp3(self, b64: str) -> None:
        raw = base64.b64decode(b64)
        seg = self._prepare_segment(AudioSegment.from_file(BytesIO(raw), format="mp3"))
        self.buffer = self._append_with_crossfade(self.buffer, seg)
        if len(self.silence) > 0:
            self.buffer += self.silence

    def reset(self) -> None:
        self.buffer = AudioSegment.empty()

    def export(self, output_path: str) -> int:
        return self._export(self.buffer, output_path)

    def export_chunk(self, b64: str, output_path: str) -> None:
        raw = base64.b64decode(b64)
        seg = self._prepare_segment(AudioSegment.from_file(BytesIO(raw), format="mp3"))
        self._export(seg, output_path)

    def merge_files(self, input_paths: list[str], output_path: str) -> int:
        merged = AudioSegment.empty()
        for input_path in input_paths:
            seg = self._prepare_segment(AudioSegment.from_file(input_path, format="mp3"))
            merged = self._append_with_crossfade(merged, seg)
        return self._export(merged, output_path)

    def chunk_path(self, chunk_dir: str, chunk_index: int) -> str:
        return os.path.join(chunk_dir, f"{chunk_index:04d}.mp3")

    def has_chunk(self, chunk_dir: str, chunk_index: int) -> bool:
        return os.path.exists(self.chunk_path(chunk_dir, chunk_index))

    def has_all_chunks(self, chunk_dir: str, processed_chunks: int) -> bool:
        return all(self.has_chunk(chunk_dir, idx) for idx in range(1, processed_chunks + 1))

    def chunk_paths_for_total(self, chunk_dir: str, total_chunks: int) -> list[str]:
        return [self.chunk_path(chunk_dir, idx) for idx in range(1, total_chunks + 1)]

    def ensure_chunk_dir(self, chunk_dir: str) -> None:
        os.makedirs(chunk_dir, exist_ok=True)

    def cleanup_chunk_dir(self, chunk_dir: str) -> None:
        if not os.path.isdir(chunk_dir):
            return
        for file_name in sorted(os.listdir(chunk_dir)):
            if file_name.endswith(".mp3"):
                os.remove(os.path.join(chunk_dir, file_name))
        os.rmdir(chunk_dir)
