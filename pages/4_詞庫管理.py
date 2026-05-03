"""
pages/4_詞庫管理.py — v2
新增：旅遊與款待科 + 詞庫匯出/匯入（JSON / TXT）
"""
import json
import os
import streamlit as st
from ui.layout import configure_page, render_sidebar
from services.vocab_manager import (
    SUBJECTS, load_all_vocab, list_subject_vocabs,
    add_subject_terms, get_subject_vocab_path,
    load_corrections, bulk_save_correction_pairs,
    get_corrections_count, get_correction_stats,
    save_correction_pair, invalidate_vocab_cache,
)
from core.pipeline_keywords import extract_from_documents

configure_page()
render_sidebar()

st.title("📚 詞庫管理")
st.caption("管理科組專屬詞庫及自動學習修正詞，提升語音辨識準確度。")

# ── 確保「旅遊與款待科」已在 SUBJECTS 中 ─────────────────────────────────────
_TOURISM = "旅遊與款待科"
if _TOURISM not in SUBJECTS:
    SUBJECTS[_TOURISM] = "tourism_hospitality"

tab_vocab, tab_io, tab_learn, tab_stats = st.tabs(
    ["🏫 科組詞庫", "📤 匯出 / 匯入", "🧠 自動學習修正詞", "📊 修正頻率統計"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1：科組詞庫管理
# ══════════════════════════════════════════════════════════════════════════════
with tab_vocab:
    st.markdown("### 科組詞庫管理")
    st.info(
        "上傳各科課程大綱、通告或教材，系統自動提取詞語加入該科組詞庫，"
        "提升對應科組會議的辨識準確度。"
    )

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.markdown("#### 選擇科組")
        subject    = st.selectbox("科組", list(SUBJECTS.keys()), key="sel_subject")
        vocab_path = get_subject_vocab_path(subject)
        counts     = list_subject_vocabs()
        st.metric("現有詞語數", counts.get(subject, 0))

        if os.path.exists(vocab_path):
            with open(vocab_path, encoding="utf-8") as vf:
                existing_words = [
                    line.strip().split()[0]
                    for line in vf
                    if line.strip() and not line.strip().startswith("#")
                ]
            if existing_words:
                st.markdown("**現有詞語（前 30 個）：**")
                tags = "".join(
                    f'<span style="background:#e3f2fd;border-radius:4px;padding:2px 6px;'
                    f'margin:2px;display:inline-block;font-size:0.85em">{w}</span>'
                    for w in existing_words[:30]
                )
                st.markdown(tags, unsafe_allow_html=True)

        st.divider()
        st.markdown("**手動輸入詞語**")
        manual = st.text_area(
            "詞語（換行或逗號分隔）",
            height=100,
            placeholder="例如（旅遊與款待科）：\n酒店管理\n餐飲服務\n旅遊業議會\nHKTA",
            key="manual_vocab_input",
        )
        if st.button("➕ 加入詞語", use_container_width=True, key="btn_add_manual"):
            terms = [t.strip() for t in manual.replace("，", ",").replace(",", ",").split(",") if t.strip()]
            if not terms:
                terms = [t.strip() for t in manual.split("\n") if t.strip()]
            if terms:
                added = add_subject_terms(subject, terms)
                st.success(f"✅ 新增 {added} 個詞語（已去重）")
                st.rerun()
            else:
                st.warning("請輸入詞語")

    with col_right:
        st.markdown("#### 從文件提取詞語")
        docs = st.file_uploader(
            "上傳課程大綱 / 通告 / 教材（PDF / DOCX / TXT）",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="vocab_docs",
        )
        if docs:
            if st.button("🔍 提取關鍵詞", use_container_width=True, key="btn_extract"):
                from ui.layout import _read_file
                texts = [_read_file(d) for d in docs if d]
                texts = [t for t in texts if t]
                if texts:
                    with st.spinner("分析文件中…"):
                        kws = extract_from_documents(texts, top_k=60)
                    valid_kws = [k["word"] for k in kws if not k["word"].startswith("⚠")]
                    st.session_state["extracted_vocab"] = valid_kws
                    st.success(f"提取到 {len(valid_kws)} 個候選詞語")
                else:
                    st.warning("無法讀取文件內容")

        if st.session_state.get("extracted_vocab"):
            kws = st.session_state["extracted_vocab"]
            st.markdown(f"**候選詞語（共 {len(kws)} 個，勾選後加入）：**")
            selected = []
            cols = st.columns(4)
            for i, w in enumerate(kws[:60]):
                if cols[i % 4].checkbox(w, key=f"kw_sel_{i}", value=True):
                    selected.append(w)
            if st.button(
                f"✅ 加入選定詞語（{len(selected)} 個）到「{subject}」",
                use_container_width=True,
            ):
                if selected:
                    added = add_subject_terms(subject, selected)
                    st.success(f"✅ 新增 {added} 個詞語")
                    st.session_state["extracted_vocab"] = []
                    st.rerun()

    st.divider()
    st.markdown("#### 所有科組詞庫狀態")
    cols = st.columns(4)
    for i, (subj, cnt) in enumerate(counts.items()):
        icon = "✅" if cnt > 0 else "⬜"
        cols[i % 4].metric(f"{icon} {subj}", f"{cnt} 詞")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2：匯出 / 匯入
# ══════════════════════════════════════════════════════════════════════════════
with tab_io:
    st.markdown("### 📤 詞庫匯出 / 匯入")
    st.info(
        "**用途：** 離職同事可匯出已累積的詞庫，交予新上任同事匯入，"
        "無需從頭建立詞庫。支援單科組或全部科組一次匯出。"
    )

    # ── 匯出 ─────────────────────────────────────────────────────────────
    st.markdown("#### ⬇️ 匯出詞庫")
    io_col1, io_col2 = st.columns(2)

    with io_col1:
        export_scope = st.radio(
            "匯出範圍",
            ["指定科組", "全部科組"],
            key="export_scope",
            horizontal=True,
        )
        if export_scope == "指定科組":
            export_subj = st.selectbox(
                "選擇科組", list(SUBJECTS.keys()), key="export_subj"
            )
        else:
            export_subj = None

        export_fmt = st.radio(
            "檔案格式",
            ["JSON（完整，推薦）", "TXT（純詞語列表）"],
            key="export_fmt",
            horizontal=True,
        )

    with io_col2:
        st.markdown("**格式說明**")
        st.markdown(
            """
- **JSON**：保留科組標籤，可一次存放多個科組詞庫，匯入時自動對應，推薦用於人員交接。
- **TXT**：純文字詞語列表（每行一詞），方便人工查閱或加入其他系統。
            """
        )

    if st.button("⬇️ 產生匯出檔案", use_container_width=True, key="btn_export"):
        try:
            _subjects_to_export = (
                list(SUBJECTS.keys()) if export_scope == "全部科組" else [export_subj]
            )
            _export_data = {}
            _total_words = 0
            for _subj in _subjects_to_export:
                _path = get_subject_vocab_path(_subj)
                if os.path.exists(_path):
                    with open(_path, encoding="utf-8") as _vf:
                        _words = [
                            line.strip().split()[0]
                            for line in _vf
                            if line.strip() and not line.strip().startswith("#")
                        ]
                    _export_data[_subj] = _words
                    _total_words += len(_words)
                else:
                    _export_data[_subj] = []

            if "TXT" in export_fmt:
                _all_words = []
                for _ws in _export_data.values():
                    _all_words.extend(_ws)
                _txt_content = "\n".join(sorted(set(_all_words)))
                st.download_button(
                    label=f"⬇️ 下載 TXT（共 {len(_all_words)} 詞）",
                    data=_txt_content.encode("utf-8"),
                    file_name="voicedoc_vocab_export.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            else:
                _json_payload = {
                    "_voicedoc_vocab_v1": True,
                    "_export_scope":      export_scope,
                    "_total_words":       _total_words,
                    "subjects":           _export_data,
                }
                _json_str = json.dumps(_json_payload, ensure_ascii=False, indent=2)
                st.download_button(
                    label=f"⬇️ 下載 JSON（共 {_total_words} 詞，{len(_subjects_to_export)} 科組）",
                    data=_json_str.encode("utf-8"),
                    file_name="voicedoc_vocab_export.json",
                    mime="application/json",
                    use_container_width=True,
                )
            st.success(
                f"✅ 已準備匯出：{_total_words} 個詞語（{len(_subjects_to_export)} 個科組）"
            )
        except Exception as _ex:
            st.error(f"匯出失敗：{_ex}")

    st.divider()

    # ── 匯入 ─────────────────────────────────────────────────────────────
    st.markdown("#### ⬆️ 匯入詞庫")
    st.caption(
        "上傳由「匯出詞庫」產生的 JSON 或 TXT 檔案。匯入時自動去重，不會刪除現有詞語。"
    )

    imp_file = st.file_uploader(
        "上傳詞庫檔案（JSON 或 TXT）",
        type=["json", "txt"],
        key="import_vocab_file",
    )

    if imp_file:
        imp_name = imp_file.name.lower()
        imp_raw  = imp_file.read()

        # ── JSON 匯入 ──────────────────────────────────────────────────
        if imp_name.endswith(".json"):
            try:
                imp_payload = json.loads(imp_raw.decode("utf-8"))
                if not imp_payload.get("_voicedoc_vocab_v1"):
                    st.warning("⚠️ 此 JSON 格式不是 VoiceDoc 標準匯出格式，仍嘗試讀取…")
                imp_subjects = imp_payload.get("subjects", {})

                st.markdown("**偵測到的科組及詞語數量：**")
                _preview_cols = st.columns(4)
                for _pi, (_ps, _pw) in enumerate(imp_subjects.items()):
                    _cnt_existing = list_subject_vocabs().get(_ps, 0)
                    _preview_cols[_pi % 4].metric(
                        f"{_ps}",
                        f"{len(_pw)} 詞（匯入）",
                        delta=f"現有 {_cnt_existing} 詞",
                    )

                imp_target = st.radio(
                    "匯入目標",
                    ["按原科組匯入（推薦）", "全部匯入至指定科組"],
                    key="imp_target",
                    horizontal=True,
                )
                imp_target_subj = None
                if "指定科組" in imp_target:
                    imp_target_subj = st.selectbox(
                        "目標科組", list(SUBJECTS.keys()), key="imp_target_subj"
                    )

                if st.button(
                    "⬆️ 確認匯入",
                    use_container_width=True,
                    type="primary",
                    key="btn_import_json",
                ):
                    _total_added = 0
                    for _is, _iw in imp_subjects.items():
                        if not _iw:
                            continue
                        if "指定科組" in imp_target and imp_target_subj:
                            _dest = imp_target_subj
                        else:
                            _dest = _is if _is in SUBJECTS else "通用"
                        _total_added += add_subject_terms(_dest, _iw)
                    invalidate_vocab_cache()
                    st.success(f"✅ 匯入完成！共新增 {_total_added} 個詞語（已去重）")
                    st.rerun()

            except Exception as _je:
                st.error(f"讀取 JSON 失敗：{_je}")

        # ── TXT 匯入 ───────────────────────────────────────────────────
        elif imp_name.endswith(".txt"):
            try:
                for _enc in ["utf-8", "utf-16", "big5"]:
                    try:
                        imp_text = imp_raw.decode(_enc)
                        break
                    except Exception:
                        imp_text = imp_raw.decode("utf-8", errors="ignore")
                imp_words = [w.strip() for w in imp_text.splitlines() if w.strip()]
                st.markdown(f"**偵測到 {len(imp_words)} 個詞語**")
                with st.expander("預覽詞語（前 30 個）", expanded=False):
                    st.write("、".join(imp_words[:30]))
                imp_txt_subj = st.selectbox(
                    "匯入至科組", list(SUBJECTS.keys()), key="imp_txt_subj"
                )
                if st.button(
                    "⬆️ 確認匯入",
                    use_container_width=True,
                    type="primary",
                    key="btn_import_txt",
                ):
                    _added = add_subject_terms(imp_txt_subj, imp_words)
                    invalidate_vocab_cache()
                    st.success(f"✅ 匯入完成！共新增 {_added} 個詞語（已去重）")
                    st.rerun()
            except Exception as _te:
                st.error(f"讀取 TXT 失敗：{_te}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3：自動學習修正詞
# ══════════════════════════════════════════════════════════════════════════════
with tab_learn:
    st.markdown("### 自動學習修正詞")
    st.info(
        "每次在「修正逐字稿」頁面修改錯誤詞語時，"
        "系統自動記錄「原詞 → 修正詞」配對，"
        "下次轉錄後自動套用修正。"
    )

    corrections = load_corrections()
    st.metric("已學習修正詞配對", len(corrections))

    if corrections:
        st.markdown("**現有修正詞配對：**")
        del_keys = []
        for i, (orig, corr) in enumerate(list(corrections.items())[:50]):
            c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
            c1.code(orig)
            c2.markdown("→")
            c3.code(corr)
            if c4.button("🗑", key=f"del_corr_{i}"):
                del_keys.append(orig)

        if del_keys:
            for k in del_keys:
                del corrections[k]
            from services.vocab_manager import CORRECTIONS_FILE
            with open(CORRECTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump({"corrections": corrections}, f, ensure_ascii=False, indent=2)
            st.rerun()

        st.divider()
        if st.button("🗑 清除所有修正詞", type="secondary"):
            from services.vocab_manager import CORRECTIONS_FILE
            with open(CORRECTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump({"corrections": {}}, f)
            st.success("已清除所有修正詞")
            st.rerun()
    else:
        st.info("尚未有自動學習的修正詞。\n修正逐字稿後，系統會自動記錄修正配對。")

    st.divider()
    st.markdown("**手動新增修正配對**")
    mc1, mc2 = st.columns(2)
    orig_input = mc1.text_input("原詞（錯誤）", placeholder="例如：DSC", key="manual_orig")
    corr_input = mc2.text_input("修正詞（正確）", placeholder="例如：DSE", key="manual_corr")
    if st.button("➕ 新增配對", key="btn_add_corr"):
        if orig_input and corr_input:
            save_correction_pair(orig_input.strip(), corr_input.strip())
            st.success(f"✅ 已新增：{orig_input} → {corr_input}")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4：修正頻率統計
# ══════════════════════════════════════════════════════════════════════════════
with tab_stats:
    st.markdown("### 📊 修正頻率統計")
    st.info(
        "記錄每個修正詞被套用的次數，反映哪些術語最常被 Whisper 辨識錯誤，"
        "有助優先維護最重要的詞庫。"
    )

    stats = get_correction_stats(top_n=30)

    if not stats:
        st.info("尚未有修正頻率記錄。\n修正逐字稿後，統計數據會自動更新。")
    else:
        total_corrections = sum(s["count"] for s in stats)
        most_common = stats[0] if stats else None
        m1, m2, m3 = st.columns(3)
        m1.metric("已記錄修正詞配對", len(stats))
        m2.metric("總修正次數", total_corrections)
        if most_common:
            m3.metric(
                "最常修正詞",
                f"{most_common['original']} → {most_common['corrected']}",
                delta=f"{most_common['count']} 次",
            )

        st.divider()
        st.markdown("**Top 修正詞（按頻率排列）：**")
        max_count = stats[0]["count"] if stats else 1
        for s in stats[:20]:
            bar_len = int(s["count"] / max_count * 20)
            bar     = "█" * bar_len + "░" * (20 - bar_len)
            col_a, col_b, col_c, col_d = st.columns([2, 2, 3, 1])
            col_a.code(s["original"])
            col_b.code(s["corrected"])
            col_c.markdown(f"`{bar}` {s['count']} 次")
            if col_d.button("🗑", key=f"del_stat_{s['original']}"):
                from services.vocab_manager import _load_corrections_data, _save_corrections_data
                data = _load_corrections_data()
                data["corrections"].pop(s["original"], None)
                data.get("counts", {}).pop(s["original"], None)
                _save_corrections_data(data)
                st.rerun()

        st.divider()

        # ── 高頻修正詞加入詞庫 ────────────────────────────────────────
        st.markdown("**💡 高頻修正詞加入詞庫**")
        st.caption(
            "將修正次數 ≥ 3 的正確詞語加入指定科組詞庫，讓下次 jieba 分詞更準確。"
        )
        high_freq = [s for s in stats if s["count"] >= 3]
        if high_freq:
            target_subj  = st.selectbox(
                "加入至科組詞庫", list(SUBJECTS.keys()), key="stat_target_subj"
            )
            words_to_add = [s["corrected"] for s in high_freq]
            tags_html = "".join(
                f'<span style="background:#e8f5e9;border-radius:4px;padding:2px 6px;'
                f'margin:2px;display:inline-block;font-size:0.85em">{w}</span>'
                for w in words_to_add[:20]
            )
            st.markdown(
                f"候選詞語（{len(words_to_add)} 個）：{tags_html}",
                unsafe_allow_html=True,
            )
            if st.button(
                f"✅ 加入「{target_subj}」詞庫",
                use_container_width=True,
                key="btn_add_highfreq",
            ):
                added = add_subject_terms(target_subj, words_to_add)
                invalidate_vocab_cache()
                st.success(f"✅ 新增 {added} 個高頻修正詞至「{target_subj}」詞庫")
                st.rerun()
        else:
            st.caption("尚未有修正次數 ≥ 3 的詞語。")

        st.divider()
        if st.button("🗑 清除所有統計記錄", type="secondary", key="btn_clear_stats"):
            from services.vocab_manager import _load_corrections_data, _save_corrections_data
            data = _load_corrections_data()
            data["counts"] = {}
            _save_corrections_data(data)
            st.success("已清除所有統計記錄（修正詞配對保留）")
            st.rerun()
