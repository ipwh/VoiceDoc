"""
ui/layout.py — VoiceDoc AI v4.8
對應 page1 全自動科組詞庫閉環版

重點：
- 移除 sidebar「👥 說話人分離」
- sidebar 保留「🎤 語音轉錄設定」，只含：語言 / 降噪模式 / low memory
- Whisper model 不放 sidebar，應由 page1 步驟③前自行顯示
- 保留 AI 設定、會議資訊、補充指示、詞彙管理、重設狀態
- 保留 manual_terms / prev_vocab / context prompt 重建能力
"""

from __future__ import annotations

import os
import streamlit as st
from core.state import init_state, K_MEETING_INFO

WHISPER_MODEL_INFO = {
    "small": "⚡ Small — 速度最快，適合短會議（≤30 分鐘），記憶體少，準確度一般",
    "medium": "⚖️ Medium — 速度與準確度平衡，適合大多數會議（推薦）",
    "large-v3": "🎯 Large-v3 — 最準確，適合重要正式會議，需較長時間及較多記憶體",
}

APP_CSS = """
<style>
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}
div[data-testid="stMetricValue"] {
    font-weight: 700;
}
code {
    white-space: pre-wrap;
    word-break: break-word;
}
</style>
"""

_PAGE_CFG_KEY = "__page_config_done"


def configure_page():
    if _PAGE_CFG_KEY not in st.session_state:
        st.set_page_config(
            page_title="VoiceDoc AI",
            page_icon="🎙",
            layout="wide",
            initial_sidebar_state="expanded",
        )
        st.session_state[_PAGE_CFG_KEY] = True

    st.markdown(APP_CSS, unsafe_allow_html=True)


def render_header(title: str = "VoiceDoc AI", subtitle: str = ""):
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)


def _get_cfg() -> dict:
    ss = st.session_state
    if "_cfg" not in ss:
        from services.minutes_service import get_provider_names
        from services.config import DEFAULT_WHISPER_MODEL, DEFAULT_LANGUAGE
        from datetime import date

        providers = get_provider_names()

        ss["_cfg"] = {
            "provider": providers[0] if providers else "DeepSeek",
            "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
            "base_url": "",
            "custom_model": "",
            "whisper_model": DEFAULT_WHISPER_MODEL if DEFAULT_WHISPER_MODEL in ["small", "medium", "large-v3"] else "small",
            "language": DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in ["yue", "zh", "en", "auto"] else "yue",
            "noise_mode": "標準濾波（平衡）",
            "low_memory": False,
            "mtg_name": "",
            "mtg_date": date.today(),
            "mtg_venue": "",
            "mtg_attend": "",
            "mtg_type": "一般會議",
            "template": "formal_tc",
            "manual_terms": "",
            "detail_level": "標準",
            "custom_instr": "",
        }

    return ss["_cfg"]


def _normalize_manual_terms(raw: str) -> list[str]:
    terms = [t.strip() for t in str(raw or "").replace("，", ",").split(",") if t.strip()]
    if terms:
        return terms
    return [t.strip() for t in str(raw or "").splitlines() if t.strip()]


def _rebuild_prompts(ss):
    from core.pipeline_keywords import build_context_prompt

    all_terms = (
        ss.get("manual_terms", [])
        + ss.get("selected_vocab", [])
        + ss.get("prev_vocab", [])
    )
    extracted = ss.get("context_keywords", [])

    ss["initial_prompt"] = build_context_prompt(all_terms, extracted, 250)
    ss["llm_context_terms"] = build_context_prompt(all_terms, extracted, 800)


def render_sidebar() -> dict:
    init_state()
    cfg = _get_cfg()
    ss = st.session_state

    with st.sidebar:
        st.markdown("### 🎙 VoiceDoc AI")
        st.caption("v4.8 · 香港學校會議紀錄")
        st.divider()

        with st.expander("🤖 AI 設定", expanded=False):
            from services.minutes_service import LLM_PROVIDERS, get_provider_names

            providers = get_provider_names()
            prov_idx = providers.index(cfg["provider"]) if cfg["provider"] in providers else 0
            cfg["provider"] = st.selectbox("▶ AI 供應商", providers, index=prov_idx, key="_sb_provider")

            provider_meta = LLM_PROVIDERS.get(cfg["provider"], {})
            local_providers = {"本地 Ollama", "自定義 (OpenAI 相容)"}

            if cfg["provider"] in local_providers:
                st.success("🔒 本地模式：資料不離開本機，符合私隱要求", icon=None)
            else:
                st.warning(
                    "⚠️ 會議內容將傳送至第三方 LLM API。請確保符合學校個人資料私隱政策及《私隱條例》。",
                    icon=None,
                )

            api_stored = cfg.get("api_key", "")
            if not api_stored:
                try:
                    from services.key_manager import get_api_key
                    saved_key = get_api_key(cfg["provider"])
                    if saved_key:
                        cfg["api_key"] = saved_key
                        api_stored = saved_key
                except Exception:
                    pass

            if api_stored:
                try:
                    from services.key_manager import mask_key_display
                    masked = mask_key_display(api_stored)
                except Exception:
                    masked = api_stored[:3] + "***...***" + api_stored[-4:]
                st.caption(f"🔑 API Key 已儲存：`{masked}`")

            new_key = st.text_input(
                "API Key（輸入後按 Enter 更新）",
                type="password",
                placeholder=provider_meta.get("placeholder", ""),
                key="_sb_api_input",
            )

            if new_key and new_key != api_stored:
                cfg["api_key"] = new_key
                try:
                    from services.key_manager import store_api_key
                    if store_api_key(cfg["provider"], new_key):
                        st.success("✅ API Key 已更新並加密儲存")
                    else:
                        st.success("✅ API Key 已更新（session）")
                except Exception:
                    st.success("✅ API Key 已更新")
                st.rerun()

            if cfg["provider"] == "自定義 (OpenAI 相容)":
                cfg["base_url"] = st.text_input("Base URL", value=cfg.get("base_url", ""), key="_sb_base_url")
                cfg["custom_model"] = st.text_input("Model Name", value=cfg.get("custom_model", ""), key="_sb_model")

        with st.expander("🎤 語音轉錄設定", expanded=False):
            lang_options = {
                "粵語": "yue",
                "中文": "zh",
                "英文": "en",
                "自動偵測": "auto",
            }
            reverse_lang = {v: k for k, v in lang_options.items()}
            current_lang_label = reverse_lang.get(cfg.get("language", "yue"), "粵語")

            picked_lang_label = st.selectbox(
                "語言",
                list(lang_options.keys()),
                index=list(lang_options.keys()).index(current_lang_label),
                key="_sb_lang",
            )
            cfg["language"] = lang_options[picked_lang_label]

            noise_options = [
                "快速降噪（速度優先）",
                "標準濾波（平衡）",
                "強效濾波（品質優先）",
                "AI 降噪 (DeepFilterNet)",
            ]
            noise_idx = noise_options.index(cfg["noise_mode"]) if cfg["noise_mode"] in noise_options else 1
            cfg["noise_mode"] = st.selectbox(
                "降噪模式",
                noise_options,
                index=noise_idx,
                key="_sb_noise_mode",
            )

            cfg["low_memory"] = st.checkbox(
                "低記憶體模式",
                value=bool(cfg.get("low_memory", False)),
                key="_sb_low_memory",
                help="使用較省記憶體的轉錄方式，適合 RAM 較少或長音檔情況，但速度可能較慢。",
            )

            st.caption("Whisper model 已改為在「語音轉錄及會議紀錄生成」頁面步驟③前設定。")

        with st.expander("📋 會議資訊", expanded=False):
            cfg["mtg_name"] = st.text_input("會議名稱", value=cfg.get("mtg_name", ""), key="_sb_mname")
            cfg["mtg_date"] = st.date_input("會議日期", value=cfg.get("mtg_date"), key="_sb_mdate")
            cfg["mtg_venue"] = st.text_input("地點", value=cfg.get("mtg_venue", ""), key="_sb_mvenue")
            cfg["mtg_attend"] = st.text_area("出席人員", value=cfg.get("mtg_attend", ""), height=55, key="_sb_mattend")

            meeting_types = [
                "一般會議",
                "常務委員會",
                "學務委員會",
                "訓導委員會",
                "科組會議",
                "家長教師會",
                "輔導委員會",
            ]
            mt_idx = meeting_types.index(cfg["mtg_type"]) if cfg["mtg_type"] in meeting_types else 0
            cfg["mtg_type"] = st.selectbox("會議類型", meeting_types, index=mt_idx, key="_sb_mtype")

            templates = ["formal_tc", "english"]
            tp_idx = templates.index(cfg["template"]) if cfg["template"] in templates else 0
            cfg["template"] = st.selectbox(
                "會議紀錄格式",
                templates,
                index=tp_idx,
                key="_sb_tpl",
                format_func=lambda x: "繁體中文（正式）" if x == "formal_tc" else "English",
            )

            ss[K_MEETING_INFO] = {
                "meeting_name": cfg["mtg_name"],
                "date": str(cfg["mtg_date"]),
                "venue": cfg["mtg_venue"],
                "attendees": cfg["mtg_attend"],
                "meeting_type": cfg["mtg_type"],
            }

        with st.expander("💬 補充指示（選填）", expanded=False):
            cfg["custom_instr"] = st.text_area(
                "對 AI 的額外要求",
                value=cfg.get("custom_instr", ""),
                height=90,
                placeholder="例如：請特別詳細記錄財務討論部分\n例如：用點列式而非段落式\n例如：按議程逐項整理，列明負責人及跟進事項",
                key="_sb_custom_instr",
            )

        with st.expander("📚 詞彙管理", expanded=False):
            cfg["manual_terms"] = st.text_area(
                "手動詞彙（換行或逗號分隔）",
                value=cfg.get("manual_terms", ""),
                height=80,
                placeholder="STEM教育, 跨課程閱讀, DSE...",
                key="_sb_mterms",
            )

            if st.button("✅ 套用詞彙", key="_sb_apply_terms"):
                terms = _normalize_manual_terms(cfg.get("manual_terms", ""))
                ss["manual_terms"] = terms
                _rebuild_prompts(ss)
                st.success(f"已套用 {len(terms)} 個詞彙")

            prev_files = st.file_uploader(
                "上傳上年度會議紀錄（DOCX / TXT / PDF）",
                type=["docx", "txt", "pdf"],
                accept_multiple_files=True,
                key="_sb_prev_files",
            )

            if prev_files:
                if len(prev_files) > 10:
                    prev_files = prev_files[:10]

                if st.button("📖 建立詞庫", key="_sb_build_vocab"):
                    from core.pipeline_keywords import build_prev_vocab
                    texts = [_read_file(fi) for fi in prev_files]
                    vocab = build_prev_vocab([t for t in texts if t], top_k=80)
                    ss["prev_vocab"] = vocab
                    _rebuild_prompts(ss)
                    st.success(f"詞庫建立完成：{len(vocab)} 個詞彙")

        st.divider()

        if st.button("🗑 重設所有狀態", use_container_width=True):
            saved_cfg = dict(ss.get("_cfg", {}))
            from core.state import reset_all
            reset_all()
            ss["_cfg"] = saved_cfg
            st.rerun()

    noise_map = {
        "快速降噪（速度優先）": "light",
        "標準濾波（平衡）": "standard",
        "強效濾波（品質優先）": "strong",
        "AI 降噪 (DeepFilterNet)": "deepfilter",
    }

    return dict(
        selected_provider=cfg["provider"],
        minutes_api_key=cfg.get("api_key", ""),
        custom_base_url=cfg.get("base_url", ""),
        custom_model=cfg.get("custom_model", ""),
        whisper_model=cfg["whisper_model"],
        lang_code=cfg["language"],
        noise_mode=cfg["noise_mode"],
        noise_mode_key=noise_map.get(cfg["noise_mode"], "standard"),
        low_memory=cfg.get("low_memory", False),
        meeting_type=cfg["mtg_type"],
        template_code=cfg["template"],
        detail_level=cfg.get("detail_level", "標準"),
        custom_instr=cfg.get("custom_instr", ""),
    )


def _read_file(f) -> str:
    if f is None:
        return ""

    name = f.name.lower()
    raw = f.read()

    if name.endswith(".txt"):
        for enc in ["utf-8", "utf-16", "big5", "gb2312"]:
            try:
                return raw.decode(enc)
            except Exception:
                pass
        return raw.decode("utf-8", errors="ignore")

    if name.endswith(".docx"):
        import io
        import docx
        return "\n".join(
            p.text for p in docx.Document(io.BytesIO(raw)).paragraphs if p.text.strip()
        )

    if name.endswith(".pdf"):
        import io
        from pypdf import PdfReader
        return "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages
        )

    return ""