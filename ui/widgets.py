"""
ui/widgets.py
共用匯出按鈕、逐字稿顯示（分頁在下方）、逐字稿編輯器、步驟標頭。
"""
import streamlit as st


def render_export_transcript(transcript: dict, key_prefix: str = ""):
    from services.export_service import export_transcript_docx, export_srt
    c1, c2 = st.columns(2)
    c1.download_button(
        "📥 下載逐字稿 DOCX",
        export_transcript_docx(
            transcript.get("segments", []),
            transcript.get("full_text", ""),
        ),
        "逐字稿.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{key_prefix}_dl_tr_docx",
        use_container_width=True,
    )
    c2.download_button(
        "📥 下載 SRT 字幕",
        export_srt(transcript.get("segments", [])).encode("utf-8"),
        "字幕.srt",
        key=f"{key_prefix}_dl_tr_srt",
        use_container_width=True,
    )


def render_export_minutes(
    minutes: dict,
    meeting_info: dict,
    version_note: str = "",
    key_prefix: str = "",
):
    from services.export_service import export_minutes_docx
    from services.minutes_service import format_minutes_text
    mi           = meeting_info or {}
    meeting_name = mi.get("meeting_name", "會議紀錄")
    meeting_date = mi.get("date", "")
    c1, c2 = st.columns(2)
    c1.download_button(
        "📥 下載會議紀錄 DOCX",
        export_minutes_docx(minutes, meeting_info, version_note),
        f"{meeting_name}_{meeting_date}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{key_prefix}_dl_min_docx",
        use_container_width=True,
    )
    c2.download_button(
        "📥 下載會議紀錄 TXT",
        format_minutes_text(minutes, meeting_info).encode("utf-8"),
        f"{meeting_name}_{meeting_date}.txt",
        key=f"{key_prefix}_dl_min_txt",
        use_container_width=True,
    )


def render_transcript_viewer(transcript: dict, key_prefix: str = ""):
    """
    逐字稿顯示（每頁 50 段）。
    分頁控制器放在文字區【下方】，符合閱讀習慣。
    """
    segs = transcript.get("segments", [])
    if not segs:
        st.info("逐字稿為空")
        return

    PAGE_SIZE   = 50
    total_pages = max(1, (len(segs) + PAGE_SIZE - 1) // PAGE_SIZE)

    # 讀取目前頁碼（預設第 1 頁）
    page_key = f"{key_prefix}_seg_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    page  = st.session_state[page_key] - 1
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, len(segs))

    st.caption(f"顯示第 {start + 1}–{end} 段（共 {len(segs)} 段）")

    # ── 逐字稿文字區 ──────────────────────────────────────────────────────────
    for seg in segs[start:end]:
        m1, s1 = divmod(int(seg["start"]), 60)
        m2, s2 = divmod(int(seg["end"]),   60)
        spk    = f'<b>[{seg["speaker"]}]</b> ' if seg.get("speaker") else ""
        time_tag = f"[{m1:02d}:{s1:02d}–{m2:02d}:{s2:02d}]"
        st.markdown(
            f'<div class="seg-block">'
            f'<span class="time-tag">{time_tag}</span> '
            f'{spk}{seg["text"]}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── 分頁控制器放在文字區【下方】 ──────────────────────────────────────────
    if total_pages > 1:
        st.markdown("---")
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("⬅ 上一頁", key=f"{key_prefix}_prev",
                         disabled=(st.session_state[page_key] <= 1),
                         use_container_width=True):
                st.session_state[page_key] -= 1
                st.rerun()
        with col_info:
            st.markdown(
                f"<div style='text-align:center;padding-top:.4rem'>"
                f"第 <b>{st.session_state[page_key]}</b> / {total_pages} 頁"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_next:
            if st.button("下一頁 ➡", key=f"{key_prefix}_next",
                         disabled=(st.session_state[page_key] >= total_pages),
                         use_container_width=True):
                st.session_state[page_key] += 1
                st.rerun()


def render_transcript_editor(transcript: dict, key_prefix: str = "") -> dict:
    """
    逐字稿編輯器：讓用戶在轉給 AI 前修正文字內容。
    回傳修改後的 transcript dict（含更新的 full_text 及 segments）。
    """
    ss = st.session_state
    edit_key = f"{key_prefix}_edited_segs"

    # 初始化編輯暫存
    if edit_key not in ss:
        ss[edit_key] = [
            {"start": s["start"], "end": s["end"],
             "text": s["text"], "speaker": s.get("speaker", "")}
            for s in transcript.get("segments", [])
        ]

    st.markdown("#### ✏️ 修正逐字稿")
    st.caption("可在此修正 AI 轉錄錯誤的詞語，修正後再生成會議紀錄，效果更準確。")

    PAGE_SIZE   = 20
    # Ensure segs is never None (handle cases where it might become None during rerun)
    if ss.get(edit_key) is None:
        ss[edit_key] = [
            {"start": s["start"], "end": s["end"],
             "text": s["text"], "speaker": s.get("speaker", "")}
            for s in (transcript.get("segments", []) if transcript else [])
        ]
    segs        = ss[edit_key]
    total_pages = max(1, (len(segs) + PAGE_SIZE - 1) // PAGE_SIZE)
    edit_page_key = f"{key_prefix}_edit_page"
    if edit_page_key not in ss:
        ss[edit_page_key] = 1

    page  = ss[edit_page_key] - 1
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, len(segs))

    # 每段文字編輯
    changed = False
    for i, seg in enumerate(segs[start:end], start=start):
        m1, s1 = divmod(int(seg["start"]), 60)
        col_time, col_text = st.columns([1, 5])
        col_time.markdown(
            f'<span class="time-tag">[{m1:02d}:{s1:02d}]</span>',
            unsafe_allow_html=True,
        )
        new_text = col_text.text_input(
            f"seg_{i}",
            value=seg["text"],
            label_visibility="collapsed",
            key=f"{key_prefix}_seg_{i}",
        )
        if new_text != seg["text"]:
            ss[edit_key][i]["text"] = new_text
            changed = True

    # 分頁（下方）
    if total_pages > 1:
        st.markdown("---")
        cp, ci, cn = st.columns([1, 2, 1])
        with cp:
            if st.button("⬅ 上一頁", key=f"{key_prefix}_ep",
                         disabled=(ss[edit_page_key] <= 1),
                         use_container_width=True):
                ss[edit_page_key] -= 1
                st.rerun()
        with ci:
            st.markdown(
                f"<div style='text-align:center;padding-top:.4rem'>"
                f"第 <b>{ss[edit_page_key]}</b> / {total_pages} 頁</div>",
                unsafe_allow_html=True,
            )
        with cn:
            if st.button("下一頁 ➡", key=f"{key_prefix}_en",
                         disabled=(ss[edit_page_key] >= total_pages),
                         use_container_width=True):
                ss[edit_page_key] += 1
                st.rerun()

    # 確認修改按鈕
    if st.button("✅ 確認修改，準備生成會議紀錄", type="primary",
                 use_container_width=True, key=f"{key_prefix}_confirm_edit"):
        updated_segs = ss[edit_key]
        updated_full = "\n".join(s["text"] for s in updated_segs)
        updated = dict(transcript, segments=updated_segs, full_text=updated_full)
        ss[f"{key_prefix}_final_transcript"] = updated
        st.success("✅ 修改已確認，請繼續生成會議紀錄")
        return updated

    # 回傳已確認版本（或原版本）
    return ss.get(f"{key_prefix}_final_transcript", transcript)


def step_hdr(step: str, label: str):
    """步驟標頭，顯示狀態圖示與顏色。"""
    ss     = st.session_state
    icons  = {"wait": "⬜", "active": "🔄", "done": "✅", "error": "❌"}
    cls    = {"wait": "step-wait", "active": "step-active",
              "done": "step-done", "error": "step-active"}
    status  = ss.get("step_status", {}).get(step, "wait")
    icon    = icons.get(status, "⬜")
    div_cls = cls.get(status, "step-wait")
    st.markdown(
        f'<div class="{div_cls}">{icon} {label}</div>',
        unsafe_allow_html=True,
    )
    err = ss.get("step_error", {}).get(step, "")
    if err:
        st.error(err)
