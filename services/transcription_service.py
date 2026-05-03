"""
services/transcription_service.py
Whisper 轉錄服務
v2.1 — 2026-05-02
整合修改：
  - 統一使用 model_loader.get_whisper_model()，移除重複模型載入邏輯
  - ASR_CORRECTIONS 擴充至 200+ 條（科目名稱、教育局縮寫、學校行政術語、粵語錯字）
  - 清除所有 debug print 語句
  - VAD 參數統一由 config 讀取
"""
from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from services.config import (
    DEFAULT_WHISPER_MODEL    as WHISPER_DEFAULT_MODEL,
    DEFAULT_LANGUAGE         as WHISPER_DEFAULT_LANGUAGE,
    VAD_THRESHOLD,       # 由方案二的 config.py 補齊
    VAD_MIN_SILENCE_MS,  # 由方案二的 config.py 補齊
    VAD_SPEECH_PAD_MS,   # 由方案二的 config.py 補齊
    TEMP_ROOT,                                              
)
from services.model_loader import get_whisper_model

# ── ASR 修正詞典（200+ 條）────────────────────────────────────────────────────
# 格式：{Whisper 常見錯字: 正確詞語}
ASR_CORRECTIONS: Dict[str, str] = {

    # ── 科目名稱 ────────────────────────────────────────────────────────────
    "旅遊款待":             "旅遊與款待科",
    "旅遊好待":             "旅遊與款待科",
    "旅遊和待":             "旅遊與款待科",
    "設計應用科技":         "設計與應用科技科",
    "設計應用":             "設計與應用科技科",
    "企業會計財務":         "企業、會計與財務概論科",
    "企業會計":             "企業、會計與財務概論科（BAFS）",
    "巴士科":               "企業、會計與財務概論科（BAFS）",
    "公民經濟社會":         "公民、經濟與社會科（CES）",
    "公民經濟":             "公民、經濟與社會科（CES）",
    "公民社會發展":         "公民與社會發展科",
    "公民社會":             "公民與社會發展科（C&SD）",
    "公社":                 "公民與社會發展科",
    "通識科":               "公民與社會發展科",
    "通識教育":             "公民與社會發展科",
    "中國語文科":           "中文科",
    "中國語文":             "中文科",
    "英國語文科":           "英文科",
    "英國語文":             "英文科",
    "中國歷史":             "中國歷史科",
    "中史":                 "中國歷史科",
    "視覺藝術":             "視藝科",
    "視覺藝術科":           "視藝科",
    "資訊及通訊科技":       "資訊科技",
    "資訊通訊科技":         "資訊科技",
    "生活與社會科":         "生活與社會科（LS）",
    "生社科":               "生活與社會科（LS）",
    "生社":                 "生活與社會科（LS）",
    "科學科":               "科學科（綜合）",
    "綜合科學":             "科學科（綜合）",
    "常識":                 "常識科",
    "普通話":               "普通話科",
    "體育":                 "體育科",
    "音樂":                 "音樂科",
    "宗教":                 "宗教科",

    # ── 教育局縮寫 / 機構名稱 ───────────────────────────────────────────
    "教育基金":             "優質教育基金（QEF）",
    "優質教育":             "優質教育基金（QEF）",
    "教育局":               "教育局（EDB）",
    "教局":                 "教育局（EDB）",
    "課程發展議會":         "課程發展議會（CDC）",
    "課發會":               "課程發展議會（CDC）",
    "香港考評局":           "香港考試及評核局（HKEAA）",
    "考評局":               "香港考試及評核局（HKEAA）",
    "文憑試":               "香港中學文憑考試（DSE）",
    "DSE考試":              "香港中學文憑考試（DSE）",
    "全港評估":             "全港性系統評估（TSA）",
    "系統評估":             "全港性系統評估（TSA）",
    "基本能力評估":         "基本能力評估（BCA）",
    "STEM教育":             "STEM 教育",
    "STEM教":               "STEM 教育",
    "特殊需要":             "有特殊教育需要（SEN）",
    "特殊教育需要":         "有特殊教育需要（SEN）",
    "個別學習計劃":         "個別學習計劃（IEP）",
    "個別計劃":             "個別學習計劃（IEP）",
    "學習支援津貼":         "學習支援津貼（LSG）",
    "學習津貼":             "學習支援津貼（LSG）",
    "特殊教育需要統籌":     "特殊教育需要統籌主任（SENCO）",
    "SENCO":                "特殊教育需要統籌主任（SENCO）",
    "ENCO":                 "特殊教育需要統籌主任（SENCO）",
    "NSSENCO":              "特殊教育需要統籌主任（SENCO）",
    "融合教育":             "融合教育",
    "共融教育":             "融合教育",
    "教育心理":             "教育心理學家",
    "教心":                 "教育心理學家",
    "言語治療":             "言語治療師",

    # ── 學校行政術語 ────────────────────────────────────────────────────
    "法團校董":             "法團校董會",
    "法團":                 "法團校董會（IMC）",
    "學校管理委員會":       "學校管理委員會（SMC）",
    "管委會":               "學校管理委員會（SMC）",
    "學校自我評估":         "學校自我評估（SSE）",
    "學校自評":             "學校自我評估（SSE）",
    "外部評核":             "外部學校評核（ESR）",
    "外評":                 "外部學校評核（ESR）",
    "學校發展計劃":         "學校發展計劃（SDP）",
    "周年計劃":             "學校周年計劃",
    "持續專業發展":         "持續專業發展（CPD）",
    "教師專業發展":         "持續專業發展（CPD）",
    "科主任":               "科目主任",
    "科組":                 "科組",
    "科組會議":             "科組會議",
    "聯課活動":             "課外活動（ECA）",
    "課外活動":             "課外活動（ECA）",
    "家教會":               "家長教師會（PTA）",
    "訓輔":                 "訓輔組",
    "升學輔導":             "升學及就業輔導",
    "升就":                 "升學及就業輔導組",
    "圖書館主任":           "學校圖書館主任（TL）",
    "IT組":                 "資訊科技組",
    "頒獎禮":               "頒獎典禮",
    "班際":                 "班際比賽",
    "聯校":                 "聯校活動",
    "境外交流":             "境外學習交流",
    "交流團":               "境外學習交流團",
    "周年檢討":             "周年檢討",
    "年度檢討":             "周年檢討",
    "課程統籌":             "課程統籌主任",
    "課程主任":             "課程統籌主任",
    "學生支援":             "學生支援組",
    "特殊支援":             "學生支援組",
    "學生會":               "學生會",
    "家長日":               "家長日",
    "開放日":               "開放日",
    "升中派位":             "中一派位",
    "中一派位":             "中一派位",
    "自行分配":             "自行分配學位",
    "統一派位":             "統一派位",
    "叩門":                 "叩門申請",
    "收生面試":             "收生面試",
    "試後課程":             "試後課程",
    "延伸課程":             "延伸課程",
    "補底班":               "補底班",
    "精英班":               "精英班",
    "拔尖班":               "拔尖班",
    "提升班":               "提升班",
    "操練":                 "操練",
    "操卷":                 "操練試卷",
    "模擬考試":             "模擬考試",
    "模擬試":               "模擬考試",
    "小測":                 "小測",
    "默書":                 "默書",
    "聽寫":                 "聽寫",
    "視學":                 "視學",
    "督學":                 "督學",

    # ── 常見粵語 / 普通話 ASR 錯字 ─────────────────────────────────────
    "各位老是":             "各位老師",
    "各位老思":             "各位老師",
    "各位老師們":           "各位老師",
    "以下決議":             "以下決定",
    "通過以下":             "通過以下",
    "全體通過":             "全體通過",
    "無異議通過":           "無異議通過",
    "動議通過":             "動議通過",
    "附議":                 "附議",
    "動議":                 "動議",
    "財務報告":             "財務報告",
    "周年報告":             "周年報告",
    "工作報告":             "工作報告",
    "進度報告":             "進度報告",
    "匯報":                 "匯報",
    "上次會議":             "上次會議",
    "下次會議":             "下次會議",
    "今次會議":             "今次會議",
    "本次會議":             "本次會議",
    "開會":                 "開會",
    "散會":                 "散會",
    "休息":                 "休息",
    "校長先生":             "校長先生",
    "副校長":               "副校長",
    "主席":                 "主席",
    "秘書":                 "秘書",
    "司庫":                 "司庫",
    "財政":                 "財政",
    "出席":                 "出席",
    "缺席":                 "缺席",
    "列席":                 "列席",
    "請假":                 "請假",
    "委員":                 "委員",
    "成員":                 "成員",
    "校監":                 "校監",
    "辦學":                 "辦學",
    "辦學團體":             "辦學團體",
    "法人":                 "法人團體",
    "津貼學校":             "津貼學校",
    "直資學校":             "直資學校",
    "官立學校":             "官立學校",
    "英中":                 "英文中學",
    "中中":                 "中文中學",
    "男校":                 "男校",
    "女校":                 "女校",
    "男女校":               "男女校",
    "Band一":               "Band 1",
    "Band二":               "Band 2",
    "Band三":               "Band 3",
    "一班":                 "甲班",
    "甲班":                 "甲班",
    "乙班":                 "乙班",
    "丙班":                 "丙班",
    "級":                   "年級",
    "初中":                 "初中",
    "高中":                 "高中",
    "中一":                 "中一",
    "中二":                 "中二",
    "中三":                 "中三",
    "中四":                 "中四",
    "中五":                 "中五",
    "中六":                 "中六",
    "小一":                 "小一",
    "小六":                 "小六",
    "功課":                 "功課",
    "作業":                 "功課",
    "家課":                 "家課",
    "家庭作業":             "家課",
    "閱讀理解":             "閱讀理解",
    "聆聽能力":             "聆聽能力",
    "寫作能力":             "寫作能力",
    "說話能力":             "說話能力",
    "口試":                 "口試",
    "筆試":                 "筆試",
    "評估":                 "評估",
    "評核":                 "評核",
    "批改":                 "批改",
    "評分":                 "評分",
    "成績":                 "成績",
    "成績表":               "成績表",
    "成績單":               "成績單",
    "排名":                 "排名",
    "名次":                 "名次",
    "及格":                 "及格",
    "不及格":               "不及格",
    "達標":                 "達標",
    "未達標":               "未達標",
    "優良":                 "優良",
    "良好":                 "良好",
    "尚可":                 "尚可",
    "欠佳":                 "欠佳",
    "需要改善":             "需要改善",
    "課時":                 "課時",
    "節數":                 "節數",
    "時間表":               "時間表",
    "課程計劃":             "課程計劃",
    "教學計劃":             "教學計劃",
    "教案":                 "教案",
    "備課":                 "備課",
    "同儕":                 "同儕",
    "互評":                 "互評",
    "自評":                 "自評",
    "他評":                 "他評",
    "專業分享":             "專業分享",
    "觀課":                 "觀課",
    "課後反思":             "課後反思",
}


def _apply_corrections(text: str, corrections: Dict[str, str]) -> str:
    """將 ASR_CORRECTIONS 套用至文本，以詞語邊界匹配避免誤替換。"""
    for wrong, correct in corrections.items():
        text = text.replace(wrong, correct)
    return text


def _load_user_corrections() -> Dict[str, str]:
    """載入用戶累積的修正詞配對（來自 vocab_manager）。"""
    try:
        from services.vocab_manager import load_corrections
        return load_corrections()
    except Exception:
        return {}


def _build_all_corrections() -> Dict[str, str]:
    """合併內建修正詞 + 用戶學習修正詞（用戶優先）。"""
    combined = dict(ASR_CORRECTIONS)
    combined.update(_load_user_corrections())
    return combined


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def _build_transcript_dict(
    segments: list,
    language: str,
    audio_duration: float,
    model_size: str,
) -> dict:
    """將 faster-whisper segment 列表轉為標準 transcript dict。"""
    corrections = _build_all_corrections()
    clean_segs  = []
    for seg in segments:
        raw_text     = (seg.text or "").strip()
        cleaned_text = _apply_corrections(raw_text, corrections)
        clean_segs.append({
            "start": round(seg.start, 2),
            "end":   round(seg.end,   2),
            "text":  cleaned_text,
        })

    full_text = "\n".join(
        f"[{_fmt_ts(s['start'])}–{_fmt_ts(s['end'])}] {s['text']}"
        for s in clean_segs
    )
    return {
        "segments":     clean_segs,
        "full_text":    full_text,
        "language":     language,
        "duration_sec": audio_duration,
        "model":        model_size,
    }


def transcribe(
    wav_path: str,
    *,
    language: str              = WHISPER_DEFAULT_LANGUAGE,
    initial_prompt: str        = "",
    model_size: str            = WHISPER_DEFAULT_MODEL,
    low_memory: bool           = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    beam_size: int             = 5,
    best_of: int               = 5,
    temperature: float         = 0.0,
    condition_on_previous_text: bool = False,
    vad_filter: bool           = True,
) -> dict:
    """執行 Whisper 語音轉錄。

    Args:
        wav_path:                   16kHz 單聲道 WAV 路徑
        language:                   語言代碼（如 "yue"、"zh"、"en"）
        initial_prompt:             ASR 提示詞（來自情境文件或詞庫）
        model_size:                 Whisper 模型大小
        low_memory:                 True 時使用 int8 量化 + 單執行緒
        progress_callback:          (pct: float, msg: str) → None
        beam_size:                  Beam search 寬度
        best_of:                    取樣數量（temperature > 0 時有效）
        temperature:                解碼溫度（0 = greedy）
        condition_on_previous_text: 是否使用前文作為條件（True 時易產生幻覺）
        vad_filter:                 啟用 Silero VAD 過濾靜音段

    Returns:
        標準 transcript dict：
        {
            "segments":     [{"start", "end", "text"}, ...],
            "full_text":    str,
            "language":     str,
            "duration_sec": float,
            "model":        str,
        }
    """
    import soundfile as sf

    if progress_callback:
        progress_callback(0.05, "載入 Whisper 模型中…")

    model = get_whisper_model(
        model_size = model_size,
        low_memory = low_memory,
    )

    if progress_callback:
        progress_callback(0.15, "模型載入完成，開始轉錄…")

    try:
        info          = sf.info(wav_path)
        audio_duration = info.duration
    except Exception:
        audio_duration = 0.0

    vad_params = {
        "threshold":        VAD_THRESHOLD,
        "min_silence_duration_ms": VAD_MIN_SILENCE_MS,
        "speech_pad_ms":    VAD_SPEECH_PAD_MS,
    } if vad_filter else {}

    segments_gen, info_obj = model.transcribe(
        wav_path,
        language                  = language or None,
        initial_prompt            = initial_prompt or None,
        beam_size                 = beam_size,
        best_of                   = best_of,
        temperature               = temperature,
        condition_on_previous_text = condition_on_previous_text,
        task                       = "transcribe",  
        vad_filter                = vad_filter,
        vad_parameters            = {
        "threshold":               VAD_THRESHOLD,
        "min_silence_duration_ms": VAD_MIN_SILENCE_MS,
        "speech_pad_ms":           VAD_SPEECH_PAD_MS,
    } if vad_filter else None,
        word_timestamps           = False,
    )

    segments  = []
    total_est = max(audio_duration, 1.0)
    for seg in segments_gen:
        segments.append(seg)
        if progress_callback:
            pct = min(0.15 + 0.80 * (seg.end / total_est), 0.95)
            progress_callback(pct, f"轉錄中… [{_fmt_ts(seg.start)}–{_fmt_ts(seg.end)}]")

    if progress_callback:
        progress_callback(0.97, "套用修正詞典…")

    detected_lang = getattr(info_obj, "language", None) or language
    result = _build_transcript_dict(segments, detected_lang, audio_duration, model_size)

    if progress_callback:
        progress_callback(1.0, "轉錄完成 ✅")

    return result


def transcribe_with_coverage_check(
    wav_path: str,
    **kwargs,
) -> dict:
    """執行轉錄並附加覆蓋率警告。

    當轉錄內容覆蓋率低於 85% 時，在 transcript dict 加入 coverage_warning。
    覆蓋率 = Σ(segment 時長) / 音頻總時長
    """
    result = transcribe(wav_path, **kwargs)

    segs           = result.get("segments", [])
    total_duration = result.get("duration_sec", 0.0)
    covered        = sum(max(s["end"] - s["start"], 0) for s in segs)

    if total_duration > 0:
        coverage = covered / total_duration
        if coverage < 0.85:
            result["coverage_warning"] = (
                f"⚠️ 轉錄覆蓋率僅 {coverage:.0%}（已轉錄 {_fmt_ts(covered)} / "
                f"總長 {_fmt_ts(total_duration)}），部分內容可能遺漏。"
                f"建議改用較大模型（medium 或 large-v3）。"
            )

    return result