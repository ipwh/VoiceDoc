"""
core/pipeline_transcribe.py
v2.3 — 2026-05-03

修正：
1. 使用 services.model_loader.get_model()
2. initial_prompt 改為 build_whisper_prompt() 風格描述句
3. 修正 progress_callback：
   - 改用音訊總時長 audio_duration_sec 作為真實進度基準
   - 避免一開始衝到大半、長時間停在同一時間點
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def build_whisper_prompt(
    context_terms: str = "",
    manual_terms: list = None,
    meeting_type: str = "一般學校會議",
    subject: str = "",
    lang_code: str = "yue",
) -> str:
    """建立 Whisper initial_prompt 風格描述句（≤200 字元）。"""
    lang_desc = {
        "yue": "粵語為主，間有英語及普通話術語",
        "zh": "普通話為主，間有英語及粵語術語",
        "en": "英語為主，間有粵語及中文術語",
    }.get(lang_code, "粵語為主，間有英語")

    subj_part = f"，科目：{subject}" if subject else ""

    all_terms: list = []
    if manual_terms:
        all_terms += [t.strip() for t in manual_terms if t and t.strip()]
    if context_terms:
        extracted = re.findall(r"[\w\u4e00-\u9fff\-]+", context_terms)
        all_terms += [t for t in extracted if len(t) >= 2]

    seen: set = set()
    unique_terms: list = []
    for t in all_terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
        if len(unique_terms) >= 8:
            break

    base = (
        f"以下是香港中學{meeting_type}錄音，{lang_desc}{subj_part}。"
        f"說話人為教師，內容涉及教學、評估及學校行政。"
    )

    if unique_terms:
        terms_str = "、".join(unique_terms[:6])
        prompt = base + f"常用術語包括：{terms_str}。"
    else:
        prompt = base

    return prompt[:200]


def run_transcribe(
    wav_path: str,
    language: str = "yue",
    initial_prompt: str = "",
    model_size: str = "medium",
    progress_callback: Optional[Callable] = None,
    low_memory: bool = False,
    audio_duration_sec: Optional[float] = None,
) -> dict:
    """
    執行 Whisper 語音轉錄。

    initial_prompt 處理：
    - 若傳入純詞語列表（無句號/逗號且詞數 > 5），自動轉換為風格描述句
    - 否則直接使用（相容舊版呼叫）
    """
    _prompt = initial_prompt.strip()
    if _prompt:
        is_word_list = (
            len(re.findall(r"[。，！？,.]", _prompt)) == 0
            and len(_prompt.split()) > 5
        )
        if is_word_list:
            logger.info("initial_prompt 疑為詞語列表，自動轉為風格描述句")
            _prompt = build_whisper_prompt(
                context_terms=_prompt,
                lang_code=language,
            )

    def emit(pct: float, msg: str) -> None:
        if progress_callback:
            progress_callback(max(0.0, min(1.0, float(pct))), msg)

    try:
        emit(0.02, f"🎙️ 準備轉錄（{model_size} 模型）…")

        from services.model_loader import get_model
        model = get_model(model_size, low_memory=low_memory)

        emit(0.08, f"🧠 模型已就緒（{model_size}）")

        _lang = language if language != "yue" else "zh"

        segs_raw, info = model.transcribe(
            wav_path,
            language=_lang,
            task="transcribe",
            initial_prompt=_prompt or None,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            word_timestamps=False,
            condition_on_previous_text=True,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
        )

        emit(0.12, "⏱️ 開始語音轉錄…")

        segments: list = []
        total_dur = 0.0
        real_total = float(audio_duration_sec or 0.0)
        last_emit_pct = 0.12
        last_emit_sec = -1.0

        for i, seg in enumerate(segs_raw, start=1):
            start_sec = float(getattr(seg, "start", 0.0) or 0.0)
            end_sec = float(getattr(seg, "end", 0.0) or 0.0)
            text = (getattr(seg, "text", "") or "").strip()

            segments.append({
                "id": i - 1,
                "start": round(start_sec, 2),
                "end": round(end_sec, 2),
                "text": text,
            })
            total_dur = max(total_dur, end_sec)

            if real_total > 1:
                ratio = min(1.0, max(0.0, end_sec / real_total))
                pct = 0.12 + ratio * 0.80
            else:
                pct = min(0.92, 0.12 + i * 0.01)

            should_emit = (
                end_sec - last_emit_sec >= 8
                or pct - last_emit_pct >= 0.02
                or i <= 3
            )
            if should_emit:
                m, s = int(end_sec // 60), int(end_sec % 60)
                emit(pct, f"⏱️ 轉錄中… 已處理至 {m:02d}:{s:02d}")
                last_emit_pct = pct
                last_emit_sec = end_sec

        emit(0.97, "🧾 整理逐字稿中…")

        nl = "\n"
        dash = "\u2013"
        lines = []
        for s in segments:
            ts = (
                f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}"
                f"{dash}"
                f"{int(s['end']//60):02d}:{int(s['end']%60):02d}]"
            )
            lines.append(f"{ts} {s['text']}")
        full_text = nl.join(lines)

        emit(1.00, "✅ 轉錄完成")

        logger.info(
            "轉錄完成：%d segments，時長 %.1f s，語言=%s",
            len(segments), total_dur, getattr(info, "language", language),
        )

        return {
            "segments": segments,
            "full_text": full_text,
            "language": getattr(info, "language", language),
            "duration_sec": round(total_dur, 1),
            "model_size": model_size,
            "initial_prompt": _prompt,
        }

    except Exception as e:
        logger.error("run_transcribe() 失敗：%s", e, exc_info=True)
        raise RuntimeError(f"轉錄失敗：{e}") from e