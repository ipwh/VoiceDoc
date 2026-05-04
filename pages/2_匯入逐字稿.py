"""
pages/2_匯入逐字稿.py
匯入既有逐字稿，直接生成會議紀錄

v2.3 callback 穩定版：
- 修正 StreamlitAPIException: widget key cannot be modified after instantiation
- 清除逐字稿 / 議程 / 情境文件均改用 callback
- 保留逐字稿、議程上傳後自動載入
- 調整詳細程度不會清除逐字稿
"""

from __future__ import annotations

import re
import hashlib
import streamlit as st

from ui.layout import configure_page, render_sidebar, _read_file
from ui.editors import render_minutes
from ui.widgets import step_hdr
from core.state import (
    init_state,
    mark_step,
    K_TRANSCRIPT,
    K_MINUTES,
    K_MEETING_INFO,
    K_LLM_CONTEXT,
    K_HISTORY_FILE,
)
from core.pipeline_minutes import run_generate_minutes


def _normalize_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


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


def _files_digest(files) -> str:
    if not files:
        return ""
    parts = []
    for f in files:
        parts.append(f"{getattr(f, 'name', '')}:{getattr(f, 'size', '')}")
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def _sync_transcript_back():
    st.session_state["tab2_transcript_text"] = _normalize_text(
        st.session_state.get("_tab2_transcript_editor", "")
    )


def _sync_agenda_back():
    st.session_state["tab2_agenda_text"] = st.session_state.get("_tab2_agenda_editor", "")


def _clear_tab2_transcript():
    ss = st.session_state
    ss["tab2_transcript_text"] = ""
    ss["_tab2_transcript_editor"] = ""
    ss["tab2_last_transcript_sig"] = ""
    ss[K_TRANSCRIPT] = None
    ss[K_MINUTES] = None
    ss["tab2_transcript_uploader_nonce"] += 1
    mark_step("transcript_import", "wait")
    mark_step("minutes", "wait")


def _clear_tab2_context():
    ss = st.session_state
    ss["tab2_context_text"] = ""
    ss["tab2_context_keywords"] = []
    ss["tab2_ctx_full_mode"] = False
    ss["tab2_effective_terms"] = []
    ss["tab2_initial_prompt"] = ""
    ss["tab2_last_ctx_sig"] = ""
    ss[K_LLM_CONTEXT] = ""
    ss["tab2_ctx_uploader_nonce"] += 1
    mark_step("context", "wait")


def _clear_tab2_agenda():
    ss = st.session_state
    ss["tab2_agenda_text"] = ""
    ss["_tab2_agenda_editor"] = ""
    ss["tab2_last_agenda_sig"] = ""
    ss["tab2_ag_uploader_nonce"] += 1


def _rebuild_tab2_context(ss):
    from core.pipeline_keywords import build_context_prompt

    manual_terms = _normalize_terms(ss.get("manual_terms", []))
    selected_vocab = _normalize_terms(ss.get("selected_vocab", []))
    prev_vocab = _normalize_terms(ss.get("prev_vocab", []))
    context_keywords = _extract_keywords_words(ss.get("tab2_context_keywords", []))

    merged_terms = _dedupe_keep_order(manual_terms + selected_vocab + prev_vocab + context_keywords)
    ss["tab2_effective_terms"] = merged_terms

    if ss.get("tab2_ctx_full_mode") and ss.get("tab2_context_text"):
        full_text = str(ss.get("tab2_context_text", ""))[:8000]
        prompt_prefix = build_context_prompt(merged_terms, [], 250)
        llm_prefix = build_context_prompt(merged_terms, [], 600)
        ss["tab2_initial_prompt"] = (prompt_prefix + "\n\n" + full_text)[:250]
        ss[K_LLM_CONTEXT] = (llm_prefix + "\n\n" + full_text)[:8000]
    else:
        pseudo_kws = [{"word": w, "score": 1.0} for w in context_keywords[:60]]
        ss["tab2_initial_prompt"] = build_context_prompt(merged_terms, pseudo_kws, 250)
        ss[K_LLM_CONTEXT] = build_context_prompt(merged_terms, pseudo_kws, 800)


configure_page()
init_state()
opts = render_sidebar()
ss = st.session_state

st.title("📄 匯入逐字稿生成會議紀錄")
st.caption("先匯入逐字稿，再按一下生成即可；情境文件與會議議程都是選填。")

ss.setdefault("tab2_transcript_text", "")
ss.setdefault("tab2_context_text", "")
ss.setdefault("tab2_context_keywords", [])
ss.setdefault("tab2_ctx_full_mode", False)
ss.setdefault("tab2_agenda_text", "")
ss.setdefault("tab2_effective_terms", [])
ss.setdefault("tab2_initial_prompt", "")
ss.setdefault("tab2_generating_minutes", False)
ss.setdefault("_minutes_error_tab2", None)
ss.setdefault("_cfg", {})

ss.setdefault("tab2_transcript_uploader_nonce", 0)
ss.setdefault("tab2_ctx_uploader_nonce", 0)
ss.setdefault("tab2_ag_uploader_nonce", 0)

ss.setdefault("tab2_last_transcript_sig", "")
ss.setdefault("tab2_last_ctx_sig", "")
ss.setdefault("tab2_last_ctx_mode", "📌 精選關鍵詞（較快）")
ss.setdefault("tab2_last_agenda_sig", "")

ss.setdefault("_tab2_transcript_editor", ss.get("tab2_transcript_text", ""))
ss.setdefault("_tab2_agenda_editor", ss.get("tab2_agenda_text", ""))

step_hdr("tab2_transcript_import", "步驟① 匯入逐字稿")

uploaded_transcript = st.file_uploader(
    "上傳逐字稿（TXT / DOCX / PDF）",
    type=["txt", "docx", "pdf"],
    key=f"tab2_transcript_file_{ss['tab2_transcript_uploader_nonce']}",
    help="上傳後會自動載入內容到下方文字框。",
)

if uploaded_transcript is not None:
    transcript_sig = f"{uploaded_transcript.name}:{getattr(uploaded_transcript, 'size', '')}"
    if ss.get("tab2_last_transcript_sig") != transcript_sig:
        loaded_text = _normalize_text(_read_file(uploaded_transcript))
        ss["tab2_transcript_text"] = loaded_text
        ss["_tab2_transcript_editor"] = loaded_text
        ss["tab2_last_transcript_sig"] = transcript_sig
        ss[K_TRANSCRIPT] = {
            "full_text": loaded_text,
            "segments": [],
            "language": "imported",
            "duration_sec": 0,
        }
        mark_step("transcript_import", "done")

st.text_area(
    "逐字稿內容",
    key="_tab2_transcript_editor",
    height=340,
    placeholder="可直接貼上逐字稿，或上傳 TXT / DOCX / PDF 文件。",
    on_change=_sync_transcript_back,
)

ss["tab2_transcript_text"] = _normalize_text(ss.get("_tab2_transcript_editor", ""))

t1, t2 = st.columns([3, 1])
with t1:
    if ss.get("tab2_transcript_text"):
        char_count = len(ss["tab2_transcript_text"])
        cjk_count = len(re.findall(r"[一-鿿]", ss["tab2_transcript_text"]))
        en_count = len(re.findall(r"[A-Za-z]+", ss["tab2_transcript_text"]))
        st.caption(f"📊 逐字稿統計：總字符 **{char_count:,}**　中文字 **{cjk_count:,}**　英文詞 **{en_count:,}**")
with t2:
    st.button("🗑 清除逐字稿", use_container_width=True, on_click=_clear_tab2_transcript)

st.divider()
step_hdr("tab2_optional_inputs", "步驟② 選填資料（可略過）")

with st.expander("📚 情境文件（選填）", expanded=False):
    st.caption("可加入背景資料、術語或過往文件，提升會議紀錄準確度。")

    ctx_mode = st.radio(
        "載入模式",
        ["📌 精選關鍵詞（較快）", "📄 完整文件內容（最全面）"],
        horizontal=True,
        key="tab2_ctx_mode",
        help="精選模式會抽取關鍵詞；完整模式會把文件全文（最多 8,000 字）傳入 AI。",
    )

    ctx_docs = st.file_uploader(
        "上傳情境文件（PDF / DOCX / TXT）",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key=f"tab2_ctx_docs_{ss['tab2_ctx_uploader_nonce']}",
        help="上傳後會自動處理。",
    )

    if ctx_docs:
        limited_docs = ctx_docs[:10]
        ctx_sig = _files_digest(limited_docs)

        if ss.get("tab2_last_ctx_sig") != ctx_sig or ss.get("tab2_last_ctx_mode") != ctx_mode:
            texts = [_read_file(f) for f in limited_docs]
            texts = [t for t in texts if t.strip()]

            with st.spinner("處理情境文件中…"):
                if "完整" in ctx_mode:
                    ss["tab2_context_text"] = "\n\n".join(texts)[:8000]
                    ss["tab2_context_keywords"] = []
                    ss["tab2_ctx_full_mode"] = True
                else:
                    from core.pipeline_keywords import extract_from_docs
                    kws = extract_from_docs(texts, top_k=60)
                    ss["tab2_context_text"] = "\n\n".join(texts)[:8000]
                    ss["tab2_context_keywords"] = kws
                    ss["tab2_ctx_full_mode"] = False

                ss["tab2_last_ctx_sig"] = ctx_sig
                ss["tab2_last_ctx_mode"] = ctx_mode
                _rebuild_tab2_context(ss)
                mark_step("context", "done")

    c1, c2 = st.columns(2)
    with c1:
        st.button("🗑 清除情境文件", use_container_width=True, on_click=_clear_tab2_context)

    if ss.get("tab2_context_text"):
        label = "情境文件內容預覽" if ss.get("tab2_ctx_full_mode") else "情境文件內容預覽（已抽取關鍵詞）"
        st.text_area(
            label,
            value=ss.get("tab2_context_text", ""),
            height=180,
            key=f"tab2_ctx_preview_{ss['tab2_ctx_uploader_nonce']}",
            disabled=True,
        )

    if not ss.get("tab2_ctx_full_mode"):
        kws = _extract_keywords_words(ss.get("tab2_context_keywords", []))
        if kws:
            st.caption(f"已抽取情境詞：{len(kws)} 個")
            with st.expander("查看情境詞", expanded=False):
                st.write("、".join(kws[:80]))
    else:
        if ss.get("tab2_context_text"):
            st.caption(f"已載入完整文件內容：{len(ss.get('tab2_context_text', '')):,} 字")

with st.expander("📋 會議議程（選填）", expanded=False):
    st.caption("有議程時，AI 較容易按議項整理會議紀錄。")

    ag_left, ag_right = st.columns(2)

    with ag_left:
        from data.agenda_templates import AGENDA_TEMPLATES

        tpl_choice = st.selectbox(
            "快速載入範本",
            list(AGENDA_TEMPLATES.keys()),
            key="tab2_ag_tpl",
        )

        if st.button("📋 載入議程範本", use_container_width=True):
            if tpl_choice != "空白":
                loaded = AGENDA_TEMPLATES[tpl_choice]
                ss["tab2_agenda_text"] = loaded
                ss["_tab2_agenda_editor"] = loaded
                st.rerun()

    with ag_right:
        ag_file = st.file_uploader(
            "上傳議程文件（TXT / DOCX / PDF）",
            type=["txt", "docx", "pdf"],
            key=f"tab2_ag_file_{ss['tab2_ag_uploader_nonce']}",
            help="上傳後會自動載入內容。",
        )

        if ag_file is not None:
            agenda_sig = f"{ag_file.name}:{getattr(ag_file, 'size', '')}"
            if ss.get("tab2_last_agenda_sig") != agenda_sig:
                loaded_agenda = _read_file(ag_file)
                ss["tab2_agenda_text"] = loaded_agenda
                ss["_tab2_agenda_editor"] = loaded_agenda
                ss["tab2_last_agenda_sig"] = agenda_sig

    st.text_area(
        "議程內容",
        key="_tab2_agenda_editor",
        height=180,
        placeholder="可直接貼上議程，或上傳議程文件。",
        on_change=_sync_agenda_back,
    )

    ss["tab2_agenda_text"] = ss.get("_tab2_agenda_editor", "")

    st.button("🗑 清除議程", use_container_width=True, on_click=_clear_tab2_agenda)

st.divider()
has_transcript = bool(ss.get("tab2_transcript_text"))
has_context = bool(ss.get("tab2_context_text"))
has_agenda = bool(ss.get("tab2_agenda_text"))

# 先取得並設定詳細程度，再顯示 metrics
detail_options = ["簡略", "標準", "詳盡"]
current_detail = ss.get("_cfg", {}).get("detail_level", "標準")

c1, c2, c3, c4 = st.columns(4)
c1.metric("逐字稿", "已載入" if has_transcript else "未載入")
c2.metric("情境文件", "已加入" if has_context else "未加入")
c3.metric("會議議程", "已加入" if has_agenda else "未加入")
c4.metric("詳盡程度", current_detail)

st.divider()
step_hdr("tab2_generate", "步驟③ AI 生成會議紀錄")

def _update_detail_level():
    ss["_cfg"]["detail_level"] = ss.get("tab2_detail_slider", "標準")

picked_detail = st.select_slider(
    "AI 生成會議紀錄詳細程度",
    options=detail_options,
    value=current_detail if current_detail in detail_options else "標準",
    key="tab2_detail_slider",
    on_change=_update_detail_level,
    help="簡略：重點摘要；標準：一般會議建議；詳盡：較完整記錄討論內容與跟進事項。",
)
ss["_cfg"]["detail_level"] = picked_detail

transcript_text = _normalize_text(ss.get("tab2_transcript_text", ""))

if not transcript_text:
    st.info("請先在步驟①匯入或貼上逐字稿。")
else:
    provider = opts.get("selected_provider", "")
    api_key = opts.get("minutes_api_key", "")
    is_local = provider in {"本地 Ollama", "自定義 (OpenAI 相容)"}
    no_key = not is_local and not api_key

    detail_level = ss.get("_cfg", {}).get("detail_level", "標準")
    word_count = len(transcript_text)

    st.caption(
        "　｜　".join(
            [f"逐字稿：{word_count:,} 字"]
            + (["已加入情境文件"] if has_context else [])
            + (["已加入會議議程"] if has_agenda else [])
            + [f"供應商：{provider or '未選擇'}"]
        )
    )

    if ss.get(K_MINUTES):
        render_minutes(ss[K_MINUTES], ss.get(K_MEETING_INFO, {}), "tab2")
        c_save, c_regen = st.columns(2)

        if c_save.button("💾 儲存至歷史記錄", use_container_width=True, key="tab2_save_history"):
            from services.history_service import save_session

            pseudo_transcript = {
                "full_text": transcript_text,
                "segments": [],
                "language": "imported",
                "duration_sec": 0,
            }
            fname = save_session(ss.get(K_MEETING_INFO, {}), pseudo_transcript, ss[K_MINUTES])
            ss[K_HISTORY_FILE] = fname
            st.success(f"✅ 已儲存：{fname}")

        if c_regen.button("🗑 重新生成", use_container_width=True, key="tab2_regen"):
            ss[K_MINUTES] = None
            ss["_minutes_error_tab2"] = None
            mark_step("minutes", "wait")
            st.rerun()
    else:
        if ss.get("_minutes_error_tab2"):
            st.error(f"❌ 上次生成失敗：{ss['_minutes_error_tab2']}")

        generating = ss.get("tab2_generating_minutes", False)

        if generating:
            st.button("⏳ 生成中，請稍候…", disabled=True, type="primary", use_container_width=True)
            time_hint = {"簡略": "10–20", "標準": "20–40", "詳盡": "40–90"}.get(detail_level, "20–60")
            st.warning(f"⚠️ AI 生成中（約 {time_hint} 秒），請勿關閉視窗")

            try:
                mark_step("minutes", "active")
                mi = ss.get(K_MEETING_INFO, {})

                if ss.get("tab2_context_text") or ss.get("tab2_context_keywords"):
                    _rebuild_tab2_context(ss)
                else:
                    ss[K_LLM_CONTEXT] = ""

                m = run_generate_minutes(
                    transcript_text,
                    agenda_text=ss.get("tab2_agenda_text", ""),
                    opts={**opts, "detail_level": detail_level, "llm_context_terms": ss.get(K_LLM_CONTEXT, "")},
                    meeting_date_str=str(mi.get("date", "")),
                    detail_level=detail_level,
                    custom_instructions=opts.get("custom_instr", ""),
                    progress_callback=lambda p, t: None,
                )

                ss[K_TRANSCRIPT] = {
                    "full_text": transcript_text,
                    "segments": [],
                    "language": "imported",
                    "duration_sec": 0,
                }
                ss[K_MINUTES] = m
                ss["tab2_generating_minutes"] = False
                ss["_minutes_error_tab2"] = None
                mark_step("minutes", "done")
                st.rerun()

            except Exception as e:
                ss["tab2_generating_minutes"] = False
                ss["_minutes_error_tab2"] = str(e)
                mark_step("minutes", "error", str(e))
                st.error(f"❌ 生成失敗：{e}")
        else:
            if no_key:
                st.warning("⚠️ 請先在左側側欄填入 API Key，再生成會議紀錄。")

            if st.button(
                "🤖 開始生成會議紀錄",
                type="primary",
                use_container_width=True,
                disabled=no_key,
                key="tab2_generate_minutes",
            ):
                ss["tab2_generating_minutes"] = True
                ss["_minutes_error_tab2"] = None
                st.rerun()