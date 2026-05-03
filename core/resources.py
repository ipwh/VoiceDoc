"""
core/resources.py
@st.cache_resource 模型載入，確保 rerun / 切頁不重載模型。
支援 low_memory 模式（int8 + 限制執行緒），適合 8GB RAM 舊電腦。
"""
import os
import streamlit as st


@st.cache_resource(show_spinner=False)
def get_whisper_model(
    model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
    low_memory: bool = False,
):
    """
    載入 faster-whisper 模型。
    low_memory=True 時：強制 int8、限制 cpu_threads=2、num_workers=1。
    """
    from faster_whisper import WhisperModel
    from services.config import MODEL_CACHE
    if low_memory:
        compute_type = "int8"
    cpu_threads = min(2, os.cpu_count() or 2) if low_memory else (os.cpu_count() or 4)
    num_workers  = 1 if low_memory else 2
    return WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        download_root=os.path.join(MODEL_CACHE, "whisper"),
        cpu_threads=cpu_threads,
        num_workers=num_workers,
    )


@st.cache_resource(show_spinner=False)
def get_speechbrain_embedder():
    """載入 SpeechBrain ECAPA speaker embedding 模型，全程快取。"""
    from speechbrain.inference.speaker import EncoderClassifier
    from services.config import MODEL_CACHE
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=os.path.join(MODEL_CACHE, "speechbrain", "ecapa"),
        run_opts={"device": "cpu"},
    )
