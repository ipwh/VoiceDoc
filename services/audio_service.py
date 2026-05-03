from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

# ── config import (兼容 root / services) ──────────────────────────────────
try:
    from services.config import TEMP_ROOT, TEMP_MAX_AGE_HOURS
except Exception:
    from config import TEMP_ROOT, TEMP_MAX_AGE_HOURS


# ──────────────────────────────────────────────────────────────────────────────
# FFmpeg helpers
# ──────────────────────────────────────────────────────────────────────────────
def ensure_ffmpeg() -> None:
    """確保 ffmpeg 可用（Windows 必須 PATH 有 ffmpeg.exe）。"""
    if not shutil.which("ffmpeg"):
        raise EnvironmentError(
            "❌ 系統中找不到 ffmpeg。\n\n"
            "🔧 Windows 建議安裝方式：\n"
            "1) 使用 winget：winget install Gyan.FFmpeg\n"
            "或 2) 下載 Windows builds → 解壓後把 <ffmpeg>\\bin 加入 PATH\n\n"
            "驗證：在 cmd 執行 ffmpeg -version"
        )


def _run_ffmpeg(cmd: list, timeout_sec: int = 600) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    if p.returncode != 0:
        tail = (p.stderr or p.stdout or "")[-2000:]
        raise RuntimeError(f"ffmpeg 失敗（code={p.returncode}）\n{tail}")


# ──────────────────────────────────────────────────────────────────────────────
# Temp manager
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class TempAudioManager:
    """
    為每個 session 建一個獨立 temp folder，避免互相覆蓋/被清理。
    TEMP_ROOT 已在 config.py 指向 LOCALAPPDATA\\VoiceDoc\\tmp（Windows）
    """
    _dir: Optional[str] = None

    def __post_init__(self):
        atexit.register(self.cleanup)

    def get_dir(self) -> str:
        if self._dir and os.path.isdir(self._dir):
            return self._dir

        os.makedirs(TEMP_ROOT, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._dir = os.path.join(TEMP_ROOT, f"session_{os.getpid()}_{stamp}")
        os.makedirs(self._dir, exist_ok=True)
        return self._dir

    def cleanup(self):
        # 不強制刪除（避免 Streamlit rerun 還用緊），只清舊的由 purge_old_temps 處理
        pass

    def delete_audio_files(self):
        """可選：轉錄完成後手動釋放 audio 檔案。"""
        if not self._dir or not os.path.isdir(self._dir):
            return
        for fn in os.listdir(self._dir):
            if fn.lower().endswith((".wav", ".mp3", ".m4a", ".mp4", ".mkv", ".mov", ".webm", ".ogg", ".flac")):
                try:
                    os.remove(os.path.join(self._dir, fn))
                except Exception:
                    pass


def purge_old_temps(force: bool = False, protect_dirs: Optional[list] = None) -> None:
    """清理 TEMP_ROOT 舊資料夾。"""
    if not os.path.isdir(TEMP_ROOT):
        return

    protect = set([d for d in (protect_dirs or []) if d])
    cutoff = datetime.min if force else (datetime.now() - timedelta(hours=max(int(TEMP_MAX_AGE_HOURS), 2)))

    for name in os.listdir(TEMP_ROOT):
        full = os.path.join(TEMP_ROOT, name)
        if full in protect:
            continue
        if os.path.isdir(full):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(full))
                if force or mtime < cutoff:
                    shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Conversion / extraction
# ──────────────────────────────────────────────────────────────────────────────
def convert_to_wav(input_path: str, output_wav: str) -> str:
    """
    任意音訊 → 16kHz mono PCM WAV
    """
    ensure_ffmpeg()
    os.makedirs(os.path.dirname(output_wav), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        output_wav
    ]
    _run_ffmpeg(cmd, timeout_sec=900)

    if not os.path.exists(output_wav) or os.path.getsize(output_wav) <= 0:
        raise RuntimeError("轉換後 WAV 檔案不存在或為 0 bytes")
    return output_wav


def extract_audio_to_wav(src_path: str, output_wav: str) -> str:
    """
    視訊（mp4/mov/mkv/webm）→ 抽音成 16kHz mono PCM WAV
    """
    ensure_ffmpeg()
    os.makedirs(os.path.dirname(output_wav), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", src_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        output_wav
    ]
    _run_ffmpeg(cmd, timeout_sec=1200)

    if not os.path.exists(output_wav) or os.path.getsize(output_wav) <= 0:
        raise RuntimeError("抽音後 WAV 檔案不存在或為 0 bytes")
    return output_wav


def get_audio_duration(wav_path: str) -> float:
    """
    取得 wav 時長（秒）。優先用 soundfile，否則用 wave。
    """
    try:
        import soundfile as sf
        info = sf.info(wav_path)
        return float(info.duration)
    except Exception:
        try:
            import wave
            with wave.open(wav_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
            return frames / float(rate)
        except Exception:
            return 0.0


def estimate_duration(duration_sec: float, model_size: str = "small") -> str:
    """粗略估算轉錄時間。"""
    ratios = {"small": 0.15, "medium": 0.35, "large-v3": 0.7}
    r = ratios.get(model_size, 0.2)
    est = max(1.0, duration_sec * r)
    if est < 60:
        return f"約 {int(est)} 秒"
    return f"約 {int(est // 60)} 分 {int(est % 60)} 秒"


# ──────────────────────────────────────────────────────────────────────────────
# Noise reduction (safe fallback)
# ──────────────────────────────────────────────────────────────────────────────
def reduce_noise_basic(wav_path: str, mode: str = "standard") -> Tuple[str, str]:
    """
    三檔降噪：
    - light: 高通 120Hz + 正規化
    - standard: 高通 120Hz + 低通 7000Hz + 正規化
    - strong: 高通 80Hz + 低通 8000Hz + 正規化（較重）
    若缺 numpy/soundfile/scipy → 直接返回原檔（不崩）
    """
    mode = (mode or "standard").lower()
    out_path = wav_path.replace(".wav", f"_{mode}.wav")

    try:
        import numpy as np
        import soundfile as sf
        from scipy.signal import butter, sosfilt

        x, sr = sf.read(wav_path)
        if x is None or len(x) == 0:
            return wav_path, "降噪略過（空音訊）"

        if x.ndim > 1:
            x = x.mean(axis=1)

        def _hp(sig, cutoff):
            sos = butter(4, cutoff / (sr / 2), btype="highpass", output="sos")
            return sosfilt(sos, sig)

        def _lp(sig, cutoff):
            sos = butter(4, cutoff / (sr / 2), btype="lowpass", output="sos")
            return sosfilt(sos, sig)

        if mode == "light":
            y = _hp(x, 120)
        elif mode == "strong":
            y = _lp(_hp(x, 80), 8000)
        else:
            y = _lp(_hp(x, 120), 7000)

        # normalize
        peak = float(np.max(np.abs(y)) + 1e-9)
        y = y / peak * 0.98

        sf.write(out_path, y, sr)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path, f"降噪（{mode}）"
        return wav_path, f"降噪（{mode}）輸出失敗，已回退"

    except Exception:
        return wav_path, "降噪模組缺失/失敗，已略過"


def reduce_noise_deepfilter(wav_path: str) -> Tuple[str, str]:
    """AI 降噪（DeepFilterNet），若未安裝則回退原檔。"""
    try:
        try:
            from services.deepfilter_service import deepfilter_denoise
        except Exception:
            from deepfilter_service import deepfilter_denoise

        out_path = wav_path.replace(".wav", "_deepfilter.wav")
        deepfilter_denoise(wav_path, out_path)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path, "AI 降噪 (DeepFilterNet)"
        return wav_path, "DeepFilterNet 輸出失敗，已回退"
    except Exception:
        return wav_path, "DeepFilterNet 未安裝/失敗，已略過"