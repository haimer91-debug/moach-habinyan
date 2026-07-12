import gc
import os
import shutil
import tempfile
import time
from pathlib import Path

import speech_recognition as sr


def _find_ffmpeg() -> str | None:
    import glob
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        r"C:\Program Files\FFmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        # winget install path
        os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
        ),
    ]
    # Also glob for any winget ffmpeg version
    winget_glob = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\bin\ffmpeg.exe"
    )
    candidates += glob.glob(winget_glob, recursive=True)
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _safe_delete(path: str | Path) -> None:
    """Delete a file safely — on Windows, retry a few times if file is locked."""
    p = Path(path)
    for _ in range(5):
        try:
            if p.exists():
                p.unlink()
            return
        except PermissionError:
            time.sleep(0.2)


def _to_wav(audio_bytes: bytes, original_suffix: str) -> bytes:
    """Convert any audio format to WAV bytes using pydub + ffmpeg."""
    from pydub import AudioSegment

    ffmpeg_path = _find_ffmpeg()
    if ffmpeg_path:
        AudioSegment.converter = ffmpeg_path

    # Write source file
    src_fd, src_path = tempfile.mkstemp(suffix=original_suffix)
    os.close(src_fd)
    Path(src_path).write_bytes(audio_bytes)

    wav_path = src_path + ".wav"
    wav_bytes = b""
    seg = None
    try:
        seg = AudioSegment.from_file(src_path)
        seg.export(wav_path, format="wav")
        wav_bytes = Path(wav_path).read_bytes()
    finally:
        # Release pydub object before deleting files (important on Windows)
        del seg
        gc.collect()
        time.sleep(0.3)
        _safe_delete(src_path)
        _safe_delete(wav_path)

    return wav_bytes


def transcribe(audio_bytes: bytes, filename: str = "recording.wav") -> str:
    """
    Transcribe audio to Hebrew text.
    Supports: .wav (direct), .ogg / .opus / .m4a / .mp3 (via ffmpeg).
    Returns the transcribed text, or an error string starting with '('.
    """
    suffix = Path(filename).suffix.lower() or ".wav"

    # Convert non-WAV formats first
    if suffix != ".wav":
        try:
            audio_bytes = _to_wav(audio_bytes, suffix)
            suffix = ".wav"
        except Exception as e:
            return f"(לא ניתן להמיר את הקובץ: {e})"

    # Write WAV to temp file
    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    Path(wav_path).write_bytes(audio_bytes)

    recognizer = sr.Recognizer()
    audio_data = None
    try:
        with sr.AudioFile(wav_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(audio_data, language="he-IL")
        return text

    except sr.UnknownValueError:
        return "(לא זוהה דיבור — נסה הקלטה ברורה יותר)"
    except sr.RequestError as e:
        return f"(שגיאת חיבור לאינטרנט: {e})"
    except Exception as e:
        return f"(שגיאה בתמלול: {e})"
    finally:
        del audio_data
        gc.collect()
        time.sleep(0.2)
        _safe_delete(wav_path)
