"""
pages/3_歷史記錄.py — 瀏覽、還原、匯出歷史會議紀錄
修正：清理暫存時同步重置語音相關狀態及 file_uploader
"""
import streamlit as st
from ui.layout import configure_page, render_sidebar
from core.state import (
    init_state, mark_step,
    K_TRANSCRIPT, K_MINUTES, K_IMPORT_MINUTES,
    K_AUDIO_RESULT, K_MEETING_INFO, K_HISTORY_FILE, K_HISTORY_TAB,
    K_TMP_MGR,
)
from services.audio_service import purge_old_temps
from services.checkpoint_service import cleanup_old_checkpoints

configure_page()
init_state()
render_sidebar()
ss = st.session_state

st.title("🗂️ 歷史記錄")

col_clean, _ = st.columns([1, 3])
with col_clean:
    if st.button("🗑 一鍵清理暫存檔", use_container_width=True):
        # 1. 清理實體檔案
        purge_old_temps(force=True)
        cleanup_old_checkpoints()
        # 2. 同步重置語音相關 session_state
        tmgr = ss.get(K_TMP_MGR)
        if tmgr and hasattr(tmgr, "cleanup"):
            tmgr.cleanup()
        ss[K_TMP_MGR]                  = None
        ss[K_AUDIO_RESULT]             = None
        ss[K_TRANSCRIPT]               = None
        ss[K_MINUTES]                  = None
        ss["transcribing"]             = False
        ss["generating_minutes"]       = False
        ss["tab1_edited_segs"]         = None
        ss["tab1_final_transcript"]    = None
        # 3. 遞增 upload_counter → 語音轉錄頁的 file_uploader 強制重置
        ss["upload_counter"]           = ss.get("upload_counter", 0) + 1
        mark_step("audio",      "wait")
        mark_step("transcript", "wait")
        mark_step("minutes",    "wait")
        st.success("✅ 暫存已清空，語音轉錄頁已重置，可重新上傳語音檔")

st.divider()

from services.history_service import (
    list_history, load_history, get_active_minutes,
    set_active_version, delete_history, add_version,
)
from services.export_service import export_minutes_docx

records = list_history(limit=30)
if not records:
    st.info("尚未有任何儲存的會議紀錄。")
else:
    for rec in records:
        has_m = rec.get("has_minutes", False)
        label = f"{'✅' if has_m else '📝'} {rec.get('meeting_name','（未命名）')}　{rec.get('date','')}"
        with st.expander(label, expanded=False):
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.caption(f"儲存時間：{rec.get('saved_at','')[:16]}")
            c2.caption(f"版本數：{rec.get('version_count', 1)}")
            if c3.button("🗑 刪除", key=f"del_{rec['filename']}"):
                delete_history(rec["filename"])
                st.rerun()
            if not has_m:
                continue

            full     = load_history(rec["filename"])
            versions = full.get("minutes_versions", [])
            active_vid = full.get("active_version_id")

            if len(versions) > 1:
                st.markdown("**版本管理**")
                ver_labels = [
                    f"v{i+1}　{v.get('timestamp','')[:16]}　{v.get('note','')}"
                    for i, v in enumerate(versions)
                ]
                active_idx = next(
                    (i for i, v in enumerate(versions) if v["version_id"] == active_vid),
                    len(versions) - 1,
                )
                sel_idx = st.selectbox(
                    "選擇版本",
                    range(len(versions)),
                    format_func=lambda i: ver_labels[i],
                    index=active_idx,
                    key=f"ver_sel_{rec['filename']}",
                )
                if sel_idx != active_idx:
                    if st.button("🔄 還原此版本", key=f"restore_{rec['filename']}"):
                        set_active_version(rec["filename"], versions[sel_idx]["version_id"])
                        st.success("✅ 已還原")
                        st.rerun()

            coll, cole = st.columns(2)
            if coll.button("📂 載入此會議紀錄", key=f"load_{rec['filename']}", use_container_width=True):
                m  = get_active_minutes(full)
                tr = full.get("transcript")
                if tr and tr.get("segments"):
                    ss[K_TRANSCRIPT] = tr
                    ss[K_MINUTES]    = m
                    ss[K_HISTORY_TAB] = "main"
                    mark_step("transcript", "done")
                    mark_step("minutes",    "done")
                else:
                    ss[K_IMPORT_MINUTES] = m
                    ss[K_HISTORY_TAB]    = "import"
                ss[K_MEETING_INFO] = full.get("meeting_info", {})
                ss[K_HISTORY_FILE] = rec["filename"]
                st.success(
                    f"✅ 已載入，請前往"
                    f"{'語音轉錄' if ss[K_HISTORY_TAB]=='main' else '匯入逐字稿'}"
                    f"頁面查看"
                )
            if cole.button("📥 下載 DOCX", key=f"exp_{rec['filename']}", use_container_width=True):
                m     = get_active_minutes(full)
                docx_ = export_minutes_docx(m, full.get("meeting_info", {}))
                st.download_button(
                    "⬇ 確認下載",
                    docx_,
                    f"{rec.get('meeting_name','會議紀錄')}_{rec.get('date','')}.docx",
                    key=f"dl_{rec['filename']}",
                )
