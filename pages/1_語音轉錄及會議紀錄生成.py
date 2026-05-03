"""
pages/1_語音轉錄及會議紀錄生成.py

最終版：
- 已刪除說話人分離
- 修正轉錄進度條體感
- 補回詞庫管理區塊與推薦詞彙加入功能
- 刪除「切換至詳盡」建議按鈕
- 補回詳細程度滑桿
"""

from __future__ import annotations

import os
import re
import hashlib
import streamlit as st

from ui.layout import configure_page, render_sidebar, _read_file
from ui.widgets import (
    render_transcript_viewer,
    render_transcript_editor,
    render_export_transcript,
    step_hdr,
)
from ui.editors import render_minutes
from core.state import (
    init_state,
    mark_step,
    K_AUDIO_RESULT,
    K_TRANSCRIPT,
    K_MINUTES,
    K_MEETING_INFO,
    K_INITIAL_PROMPT,
    K_LLM_CONTEXT,
    K_MEETING_ID,
    K_HISTORY_FILE,
    K_TAB1_AGENDA,
    K_STEP_STATUS,
    K_TMP_MGR,
)
from core.pipeline_transcribe import run_transcribe
from core.pipeline_minutes import run_generate_minutes
from services.checkpoint_service import (
    new_meeting_id,
    save_checkpoint,
    detect_incomplete_jobs,
)
from services.audio_service import (
    TempAudioManager,
    convert_to_wav,
    get_audio_duration,
    estimate_duration,
    reduce_noise_basic,
    reduce_noise_deepfilter,
)

try:
    from services.vocab_manager import (
        extract_correction_pairs,
        bulk_save_correction_pairs,
        SUBJECTS,
        add_subject_terms,
    )
except Exception:
    extract_correction_pairs = None
    bulk_save_correction_pairs = None
    SUBJECTS = {"學校行政": "vocab_admin.txt"}

    def add_subject_terms(subject, terms):
        return 0


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def _files_digest(files) -> str:
    if not files:
        return ""
    parts = []
    for f in files:
        parts.append(f"{getattr(f, 'name', '')}:{getattr(f, 'size', '')}")
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def _extract_keywords_words(kws):
    out = []
    for k in kws or []:
        if isinstance(k, dict):
            w = str(k.get("word", "")).strip()
        else:
            w = str(k).strip()
        if w:
            out.append(w)
    return out


def _normalize_terms(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw)
    terms = [t.strip() for t in s.replace("，", ",").split(",") if t.strip()]
    if terms:
        return terms
    return [t.strip() for t in s.splitlines() if t.strip()]


def _dedupe_keep_order(items):
    seen = set()
    out = []
    for x in items:
        t = str(x).strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _filter_hallucination(transcript: dict) -> dict:
    import re as _re

    if not transcript or not isinstance(transcript, dict):
        return transcript

    bad_patterns = [
        _re.compile(r"[À-ɏ]{3,}"),
        _re.compile(r"[Ѐ-ӿ]{2,}"),
        _re.compile(r"[؀-ۿ]{2,}"),
        _re.compile(r"[぀-ヿ]{2,}"),
        _re.compile(r"[가-힯]{2,}"),
        _re.compile(r"(?i)(gracias|hola|merci|bonjour|danke|ciao|sauce|baoco)"),
    ]

    def _is_bad(text: str) -> bool:
        if not text or not text.strip():
            return True
        t = text.strip()
        if not _re.search(r"[一-鿿A-Za-z]", t):
            return True
        for pat in bad_patterns:
            if pat.search(t):
                return True
        return False

    segs = transcript.get("segments") or []
    clean_segs = [s for s in segs if not _is_bad(s.get("text", ""))]
    full_text = "\n".join(
        f"[{_fmt_ts(s.get('start', 0))}–{_fmt_ts(s.get('end', 0))}] {s['text'].strip()}"
        for s in clean_segs
    )
    removed = len(segs) - len(clean_segs)
    result = dict(transcript)
    result["segments"] = clean_segs
    result["full_text"] = full_text
    if removed > 0:
        result["coverage_warning"] = f"⚠️ 已自動移除 {removed} 個疑似亂碼片段（Whisper 幻覺）。"
    return result


def _rebuild_tab1_context(ss):
    from core.pipeline_keywords import build_context_prompt

    manual_terms = _normalize_terms(ss.get("manual_terms", []))
    selected_vocab = _normalize_terms(ss.get("selected_vocab", []))
    prev_vocab = _normalize_terms(ss.get("prev_vocab", []))
    context_keywords = _extract_keywords_words(ss.get("tab1_context_keywords", []))
    subject_vocab = _normalize_terms(ss.get("tab1_subject_vocab", []))

    merged_terms = _dedupe_keep_order(
        manual_terms + selected_vocab + prev_vocab + subject_vocab + context_keywords
    )
    ss["tab1_effective_terms"] = merged_terms

    if ss.get("tab1_ctx_full_mode") and ss.get("tab1_context_text"):
        full_text = str(ss.get("tab1_context_text", ""))[:8000]
        ss[K_INITIAL_PROMPT] = full_text[:250]
        ss[K_LLM_CONTEXT] = full_text[:8000]
    else:
        pseudo_kws = [{"word": w, "score": 1.0} for w in context_keywords[:60]]
        ss[K_INITIAL_PROMPT] = build_context_prompt(merged_terms, pseudo_kws, 250)
        ss[K_LLM_CONTEXT] = build_context_prompt(merged_terms, pseudo_kws, 800)


def _load_subject_vocab(subject: str):
    try:
        from services.vocab_manager import get_subject_vocab_path
        p = get_subject_vocab_path(subject)
        if not p.exists():
            return []
        with p.open(encoding="utf-8") as f:
            return [
                line.strip().split()[0]
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
    except Exception:
        return []


def _clear_tab1_context():
    ss = st.session_state
    ss["tab1_context_text"] = ""
    ss["tab1_context_keywords"] = []
    ss["tab1_ctx_full_mode"] = False
    ss["tab1_effective_terms"] = _dedupe_keep_order(
        _normalize_terms(ss.get("manual_terms", []))
        + _normalize_terms(ss.get("selected_vocab", []))
        + _normalize_terms(ss.get("prev_vocab", []))
        + _normalize_terms(ss.get("tab1_subject_vocab", []))
    )
    ss["tab1_last_ctx_sig"] = ""
    ss["tab1_last_ctx_mode"] = "📌 精選關鍵詞（較快）"
    ss["tab1_ctx_uploader_nonce"] += 1
    _rebuild_tab1_context(ss)
    mark_step("context", "wait")


def _clear_tab1_agenda():
    ss = st.session_state
    ss[K_TAB1_AGENDA] = ""
    ss["_tab1_agenda_editor"] = ""
    ss["tab1_last_agenda_sig"] = ""
    ss["tab1_ag_uploader_nonce"] += 1


def _sync_tab1_agenda_back():
    st.session_state[K_TAB1_AGENDA] = st.session_state.get("_tab1_agenda_editor", "")


def _clear_audio_and_downstream():
    ss = st.session_state
    old_mid = ss.get(K_MEETING_ID, "default")
    for pfx in ["_pii_", "_vrec_"]:
        for sfx in ["_done", "_findings", "_recs"]:
            ss.pop(f"{pfx}{old_mid}{sfx}", None)

    for k in ["_pii_show_detail"]:
        ss.pop(k, None)

    ss[K_MEETING_ID] = new_meeting_id()
    ss[K_AUDIO_RESULT] = None
    ss[K_TRANSCRIPT] = None
    ss[K_MINUTES] = None
    ss["transcribing"] = False
    ss["generating_minutes"] = False
    ss["tab1_edited_segs"] = None
    ss["tab1_final_transcript"] = None
    ss["show_audio_player"] = False
    ss["tab1_vocab_recs"] = []
    ss["upload_counter"] += 1
    mark_step("audio", "wait")
    mark_step("transcript", "wait")
    mark_step("minutes", "wait")


try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

configure_page()
init_state()
opts = render_sidebar()
ss = st.session_state

st.title("🎙️ 語音轉錄及會議紀錄生成")
st.caption("先上傳語音，再按一下開始轉錄；情境文件與議程都是選填。")

ss.setdefault("upload_counter", 0)
ss.setdefault("transcribing", False)
ss.setdefault("generating_minutes", False)
ss.setdefault("_minutes_error", None)

ss.setdefault("tab1_context_text", "")
ss.setdefault("tab1_context_keywords", [])
ss.setdefault("tab1_ctx_full_mode", False)
ss.setdefault("tab1_effective_terms", [])
ss.setdefault("tab1_ctx_uploader_nonce", 0)
ss.setdefault("tab1_last_ctx_sig", "")
ss.setdefault("tab1_last_ctx_mode", "📌 精選關鍵詞（較快）")

ss.setdefault("tab1_ag_uploader_nonce", 0)
ss.setdefault("tab1_last_agenda_sig", "")
ss.setdefault("_tab1_agenda_editor", ss.get(K_TAB1_AGENDA, ""))

ss.setdefault("tab1_subject", list(SUBJECTS.keys())[0] if SUBJECTS else "學校行政")
ss.setdefault("tab1_subject_vocab", _load_subject_vocab(ss["tab1_subject"]))
ss.setdefault("tab1_vocab_recs", [])
ss.setdefault("tab1_quick_add_terms", "")

if ss.get(K_TMP_MGR) is None:
    ss[K_TMP_MGR] = TempAudioManager()
if not ss.get(K_MEETING_ID):
    ss[K_MEETING_ID] = new_meeting_id()

show_recovery = st.query_params.get("recover", "0") == "1"
if show_recovery and not ss.get("recovery_dismissed") and not ss.get(K_AUDIO_RESULT):
    incomplete = detect_incomplete_jobs()
    if incomplete:
        job = incomplete[0]
        with st.warning(
            f"偵測到未完成的任務（{job.get('meeting_id','')[:8]}，{job.get('updated_at','')[:16]}）"
        ):
            cr, cd = st.columns(2)
            if cr.button("🔄 恢復任務", use_container_width=True):
                from services.checkpoint_service import load_checkpoint
                ckpt = load_checkpoint(job["meeting_id"])
                if ckpt and ckpt.get("transcription"):
                    ss[K_TRANSCRIPT] = ckpt["transcription"]["transcript"]
                    ss[K_AUDIO_RESULT] = ckpt["transcription"].get("audio_result")
                    ss[K_MEETING_ID] = job["meeting_id"]
                    mark_step("transcript", "done")
                    mark_step("context", "done")
                    st.rerun()
            if cd.button("❌ 忽略", use_container_width=True):
                ss["recovery_dismissed"] = True
                st.rerun()

step_hdr("audio", "步驟① 上傳語音")

up_key = f"audio_up_{ss['upload_counter']}"
audio_file = st.file_uploader(
    "支援 MP3 / MP4 / WAV / M4A / OGG / FLAC",
    type=["mp3", "mp4", "wav", "m4a", "ogg", "flac"],
    key=up_key,
)

if audio_file and ss[K_STEP_STATUS].get("audio") != "done":
    tmp = ss[K_TMP_MGR].get_dir()
    src = os.path.join(tmp, audio_file.name)
    with open(src, "wb") as fh:
        fh.write(audio_file.read())

    wav = os.path.join(tmp, "raw.wav")

    with st.spinner("轉換格式中…"):
        convert_to_wav(src, wav)

    dur = get_audio_duration(wav)
    est = estimate_duration(dur, opts["whisper_model"])
    st.info(f"📁 {audio_file.name}　時長：{int(dur//60):02d}:{int(dur%60):02d}　預計轉錄：{est}")

    noise_map = {
        "快速降噪（速度優先）": "light",
        "標準濾波（平衡）": "standard",
        "強效濾波（品質優先）": "strong",
    }
    noise_key = opts.get("noise_mode", "標準濾波（平衡）")

    with st.spinner("降噪處理中…"):
        if "DeepFilterNet" in noise_key:
            clean, note = reduce_noise_deepfilter(wav)
        else:
            clean, note = reduce_noise_basic(wav, noise_map.get(noise_key, "standard"))

    ss[K_AUDIO_RESULT] = {"clean_wav": clean, "duration": dur}
    mark_step("audio", "done")
    save_checkpoint(ss[K_MEETING_ID], "audio", {"clean_wav": clean, "duration": dur})
    st.success(f"✅ 語音就緒（{note}）")
    st.rerun()

if ss.get(K_AUDIO_RESULT):
    dur = ss[K_AUDIO_RESULT]["duration"]
    st.success(f"✅ 語音已就緒　時長：{int(dur//60):02d}:{int(dur%60):02d}")
    ca, cb = st.columns(2)
    if ca.button("▶ 試聽", use_container_width=True, key="btn_play"):
        st.audio(ss[K_AUDIO_RESULT]["clean_wav"])
    cb.button("🗑 重新上傳語音", use_container_width=True, key="btn_reup", on_click=_clear_audio_and_downstream)

st.divider()
with st.expander("步驟② 情境設定（選填）", expanded=False):
    st.caption("可加入情境文件、議程及科組詞庫，提升轉錄與會議紀錄準確度。")

    ctx_col, agenda_col = st.columns(2)

    with ctx_col:
        st.markdown("#### 📚 上傳情境文件")
        ctx_mode = st.radio(
            "載入模式",
            ["📌 精選關鍵詞（較快）", "📄 完整文件內容（最全面）"],
            key="tab1_ctx_mode",
            horizontal=True,
        )

        docs = st.file_uploader(
            "PDF / DOCX / TXT",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key=f"tab1_ctx_docs_{ss['tab1_ctx_uploader_nonce']}",
        )

        if docs:
            if len(docs) > 10:
                st.warning("最多支援 10 個文件，已取前 10 個")
                docs = docs[:10]

            doc_sig = _files_digest(docs)
            if ss.get("tab1_last_ctx_sig") != doc_sig or ss.get("tab1_last_ctx_mode") != ctx_mode:
                from core.pipeline_keywords import extract_from_docs

                texts = [_read_file(d) for d in docs]
                texts = [t for t in texts if t]

                with st.spinner("載入情境文件中…"):
                    if "完整" in ctx_mode:
                        full_text = "\n\n".join(texts)[:8000]
                        ss["tab1_context_text"] = full_text
                        ss["tab1_context_keywords"] = []
                        ss["tab1_ctx_full_mode"] = True
                    else:
                        kws = extract_from_docs(texts, top_k=60)
                        ss["tab1_context_keywords"] = kws
                        ss["tab1_context_text"] = "\n\n".join(texts)[:8000]
                        ss["tab1_ctx_full_mode"] = False

                    ss["tab1_last_ctx_sig"] = doc_sig
                    ss["tab1_last_ctx_mode"] = ctx_mode
                    _rebuild_tab1_context(ss)
                    mark_step("context", "done")
                    st.rerun()

        st.button("🗑 清除情境文件", use_container_width=True, on_click=_clear_tab1_context)

        if ss.get("tab1_context_text"):
            preview_label = "情境文件內容預覽" if ss.get("tab1_ctx_full_mode") else "情境文件內容預覽（已抽取關鍵詞）"
            st.text_area(
                preview_label,
                value=ss.get("tab1_context_text", ""),
                height=180,
                key=f"tab1_ctx_preview_{ss['tab1_ctx_uploader_nonce']}",
                disabled=True,
            )

        if not ss.get("tab1_ctx_full_mode"):
            kws = _extract_keywords_words(ss.get("tab1_context_keywords", []))
            if kws:
                with st.expander("查看情境詞", expanded=False):
                    st.write("、".join(kws[:80]))
        else:
            if ss.get("tab1_context_text"):
                st.caption(f"已載入完整文件內容：{len(ss.get('tab1_context_text', '')):,} 字")

    with agenda_col:
        st.markdown("#### 📋 會議議程")
        from data.agenda_templates import AGENDA_TEMPLATES

        tpl_choice = st.selectbox(
            "快速載入範本",
            list(AGENDA_TEMPLATES.keys()),
            key="tab1_ag_tpl",
        )

        if st.button("📋 載入議程範本", key="tab1_load_tpl", use_container_width=True):
            if tpl_choice != "空白":
                loaded = AGENDA_TEMPLATES[tpl_choice]
                ss[K_TAB1_AGENDA] = loaded
                ss["_tab1_agenda_editor"] = loaded
                st.rerun()

        ag_file = st.file_uploader(
            "或上傳議程（TXT / DOCX / PDF）",
            type=["txt", "docx", "pdf"],
            key=f"tab1_ag_file_{ss['tab1_ag_uploader_nonce']}",
        )

        if ag_file is not None:
            agenda_sig = f"{ag_file.name}:{getattr(ag_file, 'size', '')}"
            if ss.get("tab1_last_agenda_sig") != agenda_sig:
                loaded_agenda = _read_file(ag_file)
                ss[K_TAB1_AGENDA] = loaded_agenda
                ss["_tab1_agenda_editor"] = loaded_agenda
                ss["tab1_last_agenda_sig"] = agenda_sig

        st.text_area(
            "議程內容",
            key="_tab1_agenda_editor",
            height=180,
            placeholder="可直接貼上議程，或上傳議程文件。",
            on_change=_sync_tab1_agenda_back,
        )
        ss[K_TAB1_AGENDA] = ss.get("_tab1_agenda_editor", "")

        st.button("🗑 清除議程", key="cl_ag", use_container_width=True, on_click=_clear_tab1_agenda)

    st.markdown("#### 🧠 詞庫管理")
    sv1, sv2 = st.columns([2, 1])
    with sv1:
        picked_subject = st.selectbox("選擇科組", list(SUBJECTS.keys()), key="tab1_subject_pick")
        if picked_subject != ss.get("tab1_subject"):
            ss["tab1_subject"] = picked_subject
            ss["tab1_subject_vocab"] = _load_subject_vocab(picked_subject)
            _rebuild_tab1_context(ss)
            st.rerun()

    with sv2:
        st.caption(f"目前科組詞庫：{len(ss.get('tab1_subject_vocab', []))} 個詞彙")

    with st.expander("查看目前科組詞庫", expanded=False):
        vocab_words = ss.get("tab1_subject_vocab", [])
        st.write("、".join(vocab_words[:300]) if vocab_words else "（尚未載入詞彙）")

    quick_terms = st.text_area(
        "手動加入詞彙（換行或逗號分隔）",
        value=ss.get("tab1_quick_add_terms", ""),
        height=100,
        key="tab1_quick_add_terms",
        placeholder="例如：DSE、跨課程閱讀、學與教、觀課",
    )
    if st.button("➕ 加入到目前科組詞庫", use_container_width=True, key="btn_tab1_quick_add"):
        terms = _normalize_terms(quick_terms)
        if not terms:
            st.warning("請先輸入詞彙。")
        else:
            added = add_subject_terms(ss.get("tab1_subject", "學校行政"), terms)
            ss["tab1_subject_vocab"] = _load_subject_vocab(ss.get("tab1_subject", "學校行政"))
            _rebuild_tab1_context(ss)
            st.success(f"✅ 已新增 {added} 個詞彙到「{ss.get('tab1_subject')}」")
            st.rerun()

    st.markdown("#### 🧩 本次實際生效詞彙")
    st.caption("以下詞彙會一併用於轉錄提示及會議紀錄生成。")
    _rebuild_tab1_context(ss)
    effective_terms = ss.get("tab1_effective_terms", [])
    if effective_terms:
        st.text_area(
            "本次實際生效詞彙",
            value="、".join(effective_terms[:300]),
            height=120,
            key="tab1_effective_terms_view",
            disabled=True,
        )
        st.caption(f"共 {len(effective_terms)} 個詞彙")
    else:
        st.info("目前未載入額外詞彙；仍可直接轉錄。")

    if ss.get(K_INITIAL_PROMPT):
        st.caption(f"ASR Prompt：{len(ss[K_INITIAL_PROMPT])} 字符")

st.divider()
step_hdr("transcript", "步驟③ 語音轉錄")

if not ss.get(K_AUDIO_RESULT):
    st.info("請先完成步驟①上傳語音。")
elif ss.get(K_TRANSCRIPT):
    seg_count = len(ss[K_TRANSCRIPT].get("segments", []))
    dur_s = ss[K_TRANSCRIPT].get("duration_sec", 0)
    st.success(
        f"✅ 轉錄完成　{int(dur_s//60):02d}:{int(dur_s%60):02d}　{seg_count} 段　語言：{ss[K_TRANSCRIPT].get('language','—')}"
    )
    cw = ss[K_TRANSCRIPT].get("coverage_warning", "")
    if cw:
        st.warning(cw)
else:
    st.markdown("### 🎛 語音轉錄設定")
    model_info = {
        "small": "⚡ Small — 速度最快，適合短會議",
        "medium": "⚖️ Medium — 速度與準確度平衡（推薦）",
        "large-v3": "🎯 Large-v3 — 最準確，耗時較長",
    }
    curr_model = ss["_cfg"].get("whisper_model", opts.get("whisper_model", "small"))
    picked_model = st.selectbox(
        "Whisper 模型",
        ["small", "medium", "large-v3"],
        index=["small", "medium", "large-v3"].index(curr_model) if curr_model in ["small", "medium", "large-v3"] else 0,
        format_func=lambda x: model_info.get(x, x),
        key="tab1_whisper_model",
    )
    ss["_cfg"]["whisper_model"] = picked_model
    opts["whisper_model"] = picked_model

    is_transcribing = ss.get("transcribing", False)
    low_mem = opts.get("low_memory", False)

    if is_transcribing:
        st.button("⏳ 轉錄中，請稍候…", disabled=True, type="primary", use_container_width=True)
        st.warning("⚠️ 轉錄進行中，請勿關閉視窗或重新整理頁面")

        prog_bar = st.progress(0.0, text="準備中…")

        last_shown = {"v": 0.0}
        def cb(pct, msg):
            try:
                raw = float(pct or 0.0)
            except Exception:
                raw = 0.0
            raw = max(0.0, min(1.0, raw))
            shown = max(last_shown["v"], raw)
            last_shown["v"] = shown
            prog_bar.progress(shown, text=msg)

        try:
            mark_step("transcript", "active")
            wav_path = ss[K_AUDIO_RESULT]["clean_wav"]

            if not os.path.exists(wav_path):
                st.error(f"⚠️ 音頻暫存檔案已遺失，請重新上載語音檔案。\n（路徑：`{wav_path}`）")
                ss[K_AUDIO_RESULT] = None
                ss["transcribing"] = False
                mark_step("transcript", "error", "音頻檔案遺失")
                st.rerun()

            result = run_transcribe(
                wav_path,
                language=opts["lang_code"],
                initial_prompt=ss.get(K_INITIAL_PROMPT, ""),
                model_size=opts["whisper_model"],
                progress_callback=cb,
                low_memory=low_mem,
                audio_duration_sec=ss[K_AUDIO_RESULT].get("duration", 0),
            )
            result = _filter_hallucination(result)

            try:
                from services.vocab_manager import apply_corrections_to_transcript
                result = apply_corrections_to_transcript(result, record_counts=True)
            except Exception:
                pass

            try:
                from services.vocab_recommender import recommend_vocab
                wc = len(result.get("full_text", ""))
                min_freq = 2 if wc < 4000 else 3
                recs = recommend_vocab(
                    text=result.get("full_text", ""),
                    existing_vocab=ss.get("tab1_subject_vocab", []),
                    min_freq=min_freq,
                    top_n=20,
                )
                ss["tab1_vocab_recs"] = recs
            except Exception:
                ss["tab1_vocab_recs"] = []

            ss[K_TRANSCRIPT] = result
            ss["transcribing"] = False
            mark_step("transcript", "done")
            save_checkpoint(
                ss[K_MEETING_ID],
                "transcription",
                {"transcript": result, "audio_result": ss[K_AUDIO_RESULT]},
            )
            st.rerun()

        except Exception as e:
            ss["transcribing"] = False
            mark_step("transcript", "error", str(e))
            st.error(f"❌ 轉錄失敗：{e}")
            st.rerun()
    else:
        if low_mem:
            st.info("🐌 低記憶體模式已啟用（int8 量化，限制執行緒）")
        if st.button("🚀 開始轉錄", type="primary", use_container_width=True):
            ss["transcribing"] = True
            st.rerun()

if ss.get(K_TRANSCRIPT):
    pii_key = f"_pii_{ss.get(K_MEETING_ID, 'default')}"
    if not ss.get(pii_key + "_done"):
        try:
            from services.privacy_guard import detect_pii, pii_summary
            full_text = ss[K_TRANSCRIPT].get("full_text", "")
            findings = detect_pii(full_text)
            ss[pii_key + "_findings"] = findings
            ss[pii_key + "_done"] = True
        except Exception:
            ss[pii_key + "_findings"] = []
            ss[pii_key + "_done"] = True
            findings = []
    else:
        from services.privacy_guard import pii_summary
        findings = ss.get(pii_key + "_findings", [])

    if findings:
        summary = pii_summary(findings)
        c1, c2, c3 = st.columns([6, 2, 2])
        c1.warning(f"🔒 私隱提醒：逐字稿中偵測到疑似個人資料（{summary}）。請確認傳送至 AI 前已符合學校私隱政策。")
        if c2.button("🔍 查看詳情", key="btn_pii_detail", use_container_width=True):
            ss["_pii_show_detail"] = not ss.get("_pii_show_detail", False)
        if c3.button("✅ 已確認知悉", key="btn_pii_ack", use_container_width=True):
            ss[pii_key + "_findings"] = []
            ss["_pii_show_detail"] = False
            st.rerun()

        if ss.get("_pii_show_detail"):
            with st.expander("⚠️ 偵測到的個人資料詳情", expanded=True):
                for fi in findings:
                    a, b, c = st.columns([2, 3, 2])
                    a.markdown(f"**{fi['label']}**")
                    b.code(fi["value"])
                    c.markdown(f"{'🔴' if fi['confidence']=='high' else '🟡'} {fi['confidence']}")
    if not findings and ss.get(pii_key + "_done"):
        st.caption("🔒 私隱掃描完成：未偵測到個人資料（HKID、電話、電郵、學號）。")

    with st.expander("📄 查看逐字稿", expanded=True):
        render_transcript_viewer(ss[K_TRANSCRIPT], key_prefix="tab1")
        render_export_transcript(ss[K_TRANSCRIPT], key_prefix="tab1")

        ft = ss[K_TRANSCRIPT].get("full_text", "")
        char_count = len(ft)
        word_count_cjk = len(re.findall(r"[一-鿿]", ft))
        word_count_en = len(re.findall(r"[a-zA-Z]+", ft))
        st.caption(f"📊 逐字稿統計：總字符 **{char_count:,}**　中文字 **{word_count_cjk:,}**　英文詞 **{word_count_en:,}**")

    with st.expander("📚 詞庫推薦與加入", expanded=False):
        st.caption("轉錄完成後，系統會根據逐字稿推薦可加入科組詞庫的詞彙。每個詞可分別指定加入組別。")
        recs = ss.get("tab1_vocab_recs", [])
    if not recs:
        st.info("本次未找到適合新增的推薦詞彙。")
    else:
        all_subjects = list(SUBJECTS.keys())
        default_subject = ss.get("tab1_subject", "學校行政")
        if default_subject not in all_subjects and all_subjects:
            default_subject = all_subjects[0]

        for i, item in enumerate(recs[:20]):
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                word, freq = item[0], item[1]
            else:
                word, freq = str(item), 0

            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"- **{word}**（出現 {freq} 次）")
            target_subject = c2.selectbox(
                "加入至",
                all_subjects,
                index=all_subjects.index(default_subject) if default_subject in all_subjects else 0,
                key=f"vocab_target_subject_{i}",
                label_visibility="collapsed",
            )
            if c3.button("加入", key=f"add_vocab_rec_{i}", use_container_width=True):
                try:
                    from services.vocab_manager import add_vocab_word
                    add_vocab_word(word, target_subject)
                    if target_subject == ss.get("tab1_subject"):
                        ss["tab1_subject_vocab"] = _load_subject_vocab(target_subject)
                        _rebuild_tab1_context(ss)
                    st.success(f"✅ 已加入「{word}」到「{target_subject}」")
                    st.rerun()
                except Exception as e:
                    st.error(f"加入詞庫失敗：{e}")

if ss.get(K_TRANSCRIPT):
    st.divider()
    with st.expander("✏️ 修正逐字稿（選填，修正後生成會議紀錄效果更好）", expanded=False):
        orig_text = ss[K_TRANSCRIPT].get("full_text", "")
        segs = ss[K_TRANSCRIPT].get("segments") or []
        edited = render_transcript_editor(ss[K_TRANSCRIPT], key_prefix="tab1") if len(segs) > 0 else ss[K_TRANSCRIPT]

        if len(segs) == 0:
            st.info("逐字稿尚未包含分段資料，無法使用修正功能。")

        if edited is not ss[K_TRANSCRIPT]:
            new_text = edited.get("full_text", "")
            if orig_text != new_text and extract_correction_pairs and bulk_save_correction_pairs:
                try:
                    pairs = extract_correction_pairs(orig_text, new_text)
                    if pairs:
                        saved = bulk_save_correction_pairs(pairs)
                        if saved > 0:
                            st.toast(f"✅ 已學習 {saved} 個修正詞，下次轉錄自動套用", icon="🧠")
                except Exception:
                    pass
            ss[K_TRANSCRIPT] = edited

        if st.button("🗑 重新轉錄", use_container_width=True):
            ss[K_TRANSCRIPT] = None
            ss["transcribing"] = False
            ss["tab1_edited_segs"] = None
            ss["tab1_final_transcript"] = None
            mark_step("transcript", "wait")
            st.rerun()

st.divider()
step_hdr("minutes", "步驟④ AI 生成會議紀錄")

detail_options = ["簡略", "標準", "詳盡"]
current_detail = ss.get("_cfg", {}).get("detail_level", "標準")
picked_detail = st.select_slider(
    "AI 生成會議紀錄詳細程度",
    options=detail_options,
    value=current_detail if current_detail in detail_options else "標準",
    key="tab1_detail_slider",
    help="簡略：重點摘要；標準：一般會議建議；詳盡：較完整記錄討論內容與跟進事項。",
)
ss["_cfg"]["detail_level"] = picked_detail
opts["detail_level"] = picked_detail

if not ss.get(K_TRANSCRIPT):
    st.info("請先完成步驟③轉錄。")
else:
    provider = opts.get("selected_provider", "")
    api_key = opts.get("minutes_api_key", "")
    is_local = provider in {"本地 Ollama", "自定義 (OpenAI 相容)"}
    no_key = not is_local and not api_key

    word_count = len(ss[K_TRANSCRIPT].get("full_text", ""))
    curr_level = opts.get("detail_level", "標準")
    suggest = None

    if word_count < 800 and curr_level == "詳盡":
        suggest = ("⚡", "簡略", f"逐字稿僅 {word_count} 字，使用「詳盡」模式可能過度生成，建議改用「簡略」。")
    elif 800 <= word_count <= 3000 and curr_level not in ("標準", "詳盡"):
        suggest = ("⚖️", "標準", f"逐字稿 {word_count} 字，建議使用「標準」模式。")

    if suggest:
        icon, level, msg = suggest
        sc, sb = st.columns([5, 1])
        sc.info(f"{icon} **詳盡度建議：** {msg}")
        if sb.button(f"切換至{level}", key="btn_switch_detail"):
            ss["_cfg"]["detail_level"] = level
            opts["detail_level"] = level
            st.rerun()

    if ss.get(K_TAB1_AGENDA):
        n_items = len([l for l in ss[K_TAB1_AGENDA].split("\n") if l.strip()])
        st.info(f"📋 將使用議程模式（{n_items} 個議項）")

    if ss.get(K_LLM_CONTEXT):
        st.caption(f"已加入情境內容／詞彙；LLM Context 長度：{len(ss.get(K_LLM_CONTEXT, ''))} 字符")

    if ss.get(K_MINUTES):
        render_minutes(ss[K_MINUTES], ss.get(K_MEETING_INFO, {}), "main")

        c_save, c_regen = st.columns(2)
        if c_save.button("💾 儲存至歷史記錄", use_container_width=True, key="save_main"):
            from services.history_service import save_session
            fname = save_session(ss.get(K_MEETING_INFO, {}), ss[K_TRANSCRIPT], ss[K_MINUTES])
            ss[K_HISTORY_FILE] = fname
            save_checkpoint(ss[K_MEETING_ID], "minutes", {"minutes": ss[K_MINUTES]})
            st.success(f"✅ 已儲存：{fname}")

        if c_regen.button("🗑 重新生成", use_container_width=True):
            ss[K_MINUTES] = None
            ss["_minutes_error"] = None
            mark_step("minutes", "wait")
            st.rerun()
    else:
        if ss.get("_minutes_error"):
            st.error(f"❌ 上次生成失敗：{ss['_minutes_error']}")

        is_generating = ss.get("generating_minutes", False)
        if is_generating:
            st.button("⏳ 生成中，請稍候…", disabled=True, type="primary", use_container_width=True)
            dl = opts.get("detail_level", "標準")
            time_hint = {"簡略": "10–20", "標準": "20–40", "詳盡": "40–90"}.get(dl, "20–60")
            two_stage_hint = "　🔬 已啟用兩階段深度生成" if dl == "詳盡" else ""
            st.warning(f"⚠️ AI 生成中（約 {time_hint} 秒），請勿關閉視窗{two_stage_hint}")

            with st.spinner("AI 思考中…"):
                try:
                    mi = ss.get(K_MEETING_INFO, {})
                    m = run_generate_minutes(
                        ss[K_TRANSCRIPT]["full_text"],
                        agenda_text=ss.get(K_TAB1_AGENDA, ""),
                        opts={**opts, "llm_context_terms": ss.get(K_LLM_CONTEXT, "")},
                        meeting_date_str=str(mi.get("date", "")),
                        detail_level=opts.get("detail_level", "標準"),
                        custom_instructions=opts.get("custom_instr", ""),
                        progress_callback=lambda p, t: None,
                    )
                    ss[K_MINUTES] = m
                    ss["generating_minutes"] = False
                    ss["_minutes_error"] = None
                    mark_step("minutes", "done")
                    try:
                        save_checkpoint(ss[K_MEETING_ID], "minutes", {"minutes": m})
                    except Exception:
                        pass
                    st.rerun()
                except Exception as e:
                    ss["generating_minutes"] = False
                    ss["_minutes_error"] = str(e)
                    mark_step("minutes", "error", str(e))
                    st.error(f"❌ 生成失敗：{e}")
        else:
            if no_key:
                st.warning("⚠️ 請先在左側側欄填入 API Key，再生成會議紀錄。")

            st.caption(f"逐字稿長度：{word_count:,} 字　·　供應商：{provider or '未選擇'}")
            if st.button("🤖 開始生成會議紀錄", type="primary", use_container_width=True, disabled=no_key):
                ss["generating_minutes"] = True
                ss["_minutes_error"] = None
                st.rerun()