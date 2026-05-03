"""
services/model_loader.py
VoiceDoc AI — Whisper model loader

功能：
1. 統一管理 faster-whisper 模型載入
2. 模型快取與下載位置固定到本機使用者資料夾
3. 提供 get_model() 給 pipeline_transcribe.py 使用
4. 提供 preload_model() 供首頁背景預載模型
"""

from __future__ import annotations

import os
import logging
import threading
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: Dict[Tuple[str, bool], object] = {}


def _default_model_dir() -> str:
    return str(Path.home() / "VoiceDoc_env" / "whisper_models")


def get_model_dir() -> str:
    model_dir = (
        os.environ.get("VOICEDOC_MODEL_DIR")
        or os.environ.get("WHISPER_MODEL_DIR")
        or os.environ.get("HF_HOME")
        or _default_model_dir()
    )
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    return model_dir


def _resolve_device(low_memory: bool = False) -> tuple[str, str]:
    """
    回傳 (device, compute_type)
    優先使用 CPU，避免不同學校電腦因 CUDA / DLL 差異導致不穩。
    如日後要開 GPU，可再擴充此邏輯。
    """
    force_cpu = os.environ.get("VOICEDOC_FORCE_CPU", "true").strip().lower()
    if force_cpu in {"1", "true", "yes", "y"}:
        return "cpu", "int8" if low_memory else "int8"

    try:
        import torch
        if torch.cuda.is_available() and not low_memory:
            return "cuda", "float16"
    except Exception:
        pass

    return "cpu", "int8" if low_memory else "int8"


def get_model(model_size: str = "medium", low_memory: bool = False):
    """
    載入並快取 faster-whisper 模型。

    Args:
        model_size: small / medium / large-v3
        low_memory: 是否使用低記憶體模式

    Returns:
        WhisperModel instance
    """
    key = (model_size, bool(low_memory))

    with _MODEL_LOCK:
        if key in _MODEL_CACHE:
            return _MODEL_CACHE[key]

        from faster_whisper import WhisperModel

        model_dir = get_model_dir()
        device, compute_type = _resolve_device(low_memory=low_memory)

        logger.info(
            "載入 Whisper 模型：model=%s, low_memory=%s, device=%s, compute_type=%s, download_root=%s",
            model_size,
            low_memory,
            device,
            compute_type,
            model_dir,
        )

        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=model_dir,
        )

        _MODEL_CACHE[key] = model
        return model


def preload_model(model_size: str = "medium", low_memory: bool = False) -> None:
    """
    背景預載模型，不拋出例外，適合首頁啟動時使用。
    """
    try:
        get_model(model_size=model_size, low_memory=low_memory)
        logger.info("Whisper 模型預載完成：%s", model_size)
    except Exception as e:
        logger.warning("Whisper 模型預載失敗：%s", e)


def clear_model_cache() -> None:
    """
    清除記憶體中的模型快取。
    注意：不會刪除硬碟上的模型檔案。
    """
    global _MODEL_CACHE
    with _MODEL_LOCK:
        _MODEL_CACHE = {}
        logger.info("Whisper 模型快取已清除")