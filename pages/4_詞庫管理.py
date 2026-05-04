"""
pages/4_詞庫管理.py

功能：
- 科組詞庫管理
- 支援自訂科組建立
- 詞庫匯出 / 匯入（JSON / TXT）
- 自動學習修正詞
- 修正頻率統計
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from ui.layout import configure_page, render_sidebar
from core.pipeline_keywords import extract_from_documents
from services.vocab_manager import (
    SUBJECTS,
    CORRECTIONS_FILE,
    _load_corrections_data,
    _save_corrections_data,
    create_custom_subject,
    refresh_subjects,
    list_custom_subjects,
    load_all_vocab,
    list_subject_vocabs,
    add_subject_terms,
    get_subject_vocab_path,
    load_corrections,
    bulk_save_correction_pairs,
    get_corrections_count,
    get_correction_stats,
    save_correction_pair,
    invalidate_vocab_cache,
)

configure_page()
render_sidebar()

st.title("📚 詞庫管理")
st.caption("管理科組專屬詞庫、自訂科組及自動學習修正詞，提升語音辨識準確度。")

# 每次載入頁面時重新整理科組清單
SUBJECTS = refresh_subjects()

# 確保旅遊與款待科存在（向後相容）
if "旅遊與款待科" not in SUBJECTS:
    try:
        create_custom_subject("旅遊與款待科")
        SUBJECTS = refresh_subjects()
    except Exception:
        SUBJECTS = refresh_subjects()

tab_vocab, tab_io, tab_learn, tab_stats = st.tabs(
    ["🏫 科組詞庫", "📤 匯出 / 匯入", "🧠 自動學習修正詞", "📊 修正頻率統計"]
)


def _subject_options() -> list[str]:
    return list(refresh_subjects().keys())


def _read_words_for_export(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [
            line.strip().split()[0]
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def _parse_manual_terms(text: str) -> list[str]:
    if not text:
        return []
    terms = [t.strip() for t in text.replace("，", ",").replace("、", ",").split(",") if t.strip()]
    if not terms:
        terms = [t.strip() for t in text.splitlines() if t.strip()]
    return terms


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1：科組詞庫管理
# ══════════════════════════════════════════════════════════════════════════════
with tab_vocab:
    st.markdown("### 科組詞庫管理")
    st.info(
        "上傳各科課程大綱、通告或教材，系統可提取詞語加入對應科組詞庫；"
        "也可建立自訂科組，讓校內不同功能組別累積專屬高頻詞語。"
    )

    col_left, col_right = st.columns([1, 2])

    with col_left:
        subjects_now = _subject_options()

        st.markdown("#### 選擇科組")
        subject = st.selectbox("科組", subjects_now, key="sel_subject")
        vocab_path = get_subject_vocab_path(subject)
        counts = list_subject_vocabs()
        st.metric("現有詞語數", counts.get(subject, 0))

        existing_words = _read_words_for_export(vocab_path)
        if existing_words:
            st.markdown("**現有詞語（前 30 個）：**")
            tags = "".join(
                f'<span style="display:inline-block;background:#f3f4f6;padding:4px 8px;'
                f'border-radius:999px;margin:3px;font-size:0.9rem;">{w}</span>'
                for w in existing_words[:30]
            )
            st.markdown(tags, unsafe_allow_html=True)

        st.divider()
        st.markdown("**➕ 建立自訂科組**")
        st.caption("適用於未預設於系統的校本科組，例如升學及就業輔導組、價值教育組、STEAM 組等。")
        new_subject = st.text_input(
            "新科組名稱",
            placeholder="例如：升學及就業輔導組",
            key="new_custom_subject",
        )
        if st.button("建立科組", use_container_width=True, key="btn_create_custom_subject"):
            try:
                created = create_custom_subject(new_subject)
                st.success(f"✅ 已建立自訂科組：{created}")
                st.rerun()
            except Exception as ex:
                st.error(f"建立失敗：{ex}")

        custom_subjects = list_custom_subjects()
        if custom_subjects:
            st.caption(f"現有自訂科組：{len(custom_subjects)} 個")

        st.divider()
        st.markdown("**手動輸入詞語**")
        manual = st.text_area(
            "詞語（換行或逗號分隔）",
            height=110,
            placeholder="例如：\n法團校董會\n家長教師會\n學校發展計劃",
            key="manual_vocab_input",
        )

        if st.button("➕ 加入詞語", use_container_width=True, key="btn_add_manual"):
            terms = _parse_manual_terms(manual)
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
                    valid_kws = [k["word"] for k in kws if not str(k.get("word", "")).startswith("⚠")]
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
                key="btn_add_selected_keywords",
            ):
                if selected:
                    added = add_subject_terms(subject, selected)
                    st.success(f"✅ 新增 {added} 個詞語")
                    st.session_state["extracted_vocab"] = []
                    st.rerun()

        st.divider()
        st.markdown("#### 所有科組詞庫狀態")
        counts = list_subject_vocabs()
        cols = st.columns(4)
        for i, subj in enumerate(_subject_options()):
            cnt = counts.get(subj, 0)
            icon = "✅" if cnt > 0 else "⬜"
            cols[i % 4].metric(f"{icon} {subj}", f"{cnt} 詞")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2：匯出 / 匯入
# ══════════════════════════════════════════════════════════════════════════════
with tab_io:
    st.markdown("### 📤 詞庫匯出 / 匯入")
    st.info(
        "**用途：** 可將已累積的詞庫匯出作交接或備份，再於其他裝置 / 同事帳戶匯入；"
        "支援單一科組或全部科組。自訂科組亦可一併匯出與匯入。"
    )

    st.markdown("#### ⬇️ 匯出詞庫")
    io_col1, io_col2 = st.columns(2)

    with io_col1:
        export_scope = st.radio(
            "匯出範圍",
            ["指定科組", "全部科組"],
            key="export_scope",
            horizontal=True,
        )

        export_subj = None
        if export_scope == "指定科組":
            export_subj = st.selectbox(
                "選擇科組",
                _subject_options(),
                key="export_subj",
            )

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
            subjects_to_export = (
                _subject_options() if export_scope == "全部科組" else [export_subj]
            )

            export_data = {}
            total_words = 0

            for subj in subjects_to_export:
                path = get_subject_vocab_path(subj)
                words = _read_words_for_export(path)
                export_data[subj] = words
                total_words += len(words)

            if "TXT" in export_fmt:
                all_words = []
                for ws in export_data.values():
                    all_words.extend(ws)
                txt_content = "\n".join(sorted(set(all_words)))
                st.download_button(
                    label=f"⬇️ 下載 TXT（共 {len(set(all_words))} 詞）",
                    data=txt_content.encode("utf-8"),
                    file_name="voicedoc_vocab_export.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            else:
                json_payload = {
                    "_voicedoc_vocab_v1": True,
                    "_export_scope": export_scope,
                    "_total_words": total_words,
                    "subjects": export_data,
                }
                json_str = json.dumps(json_payload, ensure_ascii=False, indent=2)
                st.download_button(
                    label=f"⬇️ 下載 JSON（共 {total_words} 詞，{len(subjects_to_export)} 科組）",
                    data=json_str.encode("utf-8"),
                    file_name="voicedoc_vocab_export.json",
                    mime="application/json",
                    use_container_width=True,
                )

            st.success(f"✅ 已準備匯出：{total_words} 個詞語（{len(subjects_to_export)} 個科組）")
        except Exception as ex:
            st.error(f"匯出失敗：{ex}")

    st.divider()

    st.markdown("#### ⬆️ 匯入詞庫")
    st.caption("上傳由本頁匯出的 JSON 或 TXT 檔案。匯入時自動去重，不會刪除現有詞語。")

    imp_file = st.file_uploader(
        "上傳詞庫檔案（JSON 或 TXT）",
        type=["json", "txt"],
        key="import_vocab_file",
    )

    if imp_file:
        imp_name = imp_file.name.lower()
        imp_raw = imp_file.read()

        if imp_name.endswith(".json"):
            try:
                imp_payload = json.loads(imp_raw.decode("utf-8"))
                if not imp_payload.get("_voicedoc_vocab_v1"):
                    st.warning("⚠️ 此 JSON 格式不是 VoiceDoc 標準匯出格式，仍嘗試讀取…")

                imp_subjects = imp_payload.get("subjects", {})
                if not isinstance(imp_subjects, dict):
                    raise ValueError("JSON 中 subjects 格式不正確")

                st.markdown("**偵測到的科組及詞語數量：**")
                preview_cols = st.columns(4)
                now_counts = list_subject_vocabs()
                for i, (ps, pw) in enumerate(imp_subjects.items()):
                    cnt_existing = now_counts.get(ps, 0)
                    preview_cols[i % 4].metric(
                        f"{ps}",
                        f"{len(pw)} 詞（匯入）",
                        delta=f"現有 {cnt_existing} 詞",
                    )

                imp_target = st.radio(
                    "匯入目標",
                    ["按原科組匯入（推薦）", "全部匯入至指定科組"],
                    key="imp_target",
                    horizontal=True,
                )

                auto_create_missing = False
                if "按原科組" in imp_target:
                    auto_create_missing = st.checkbox(
                        "自動建立匯入檔中尚未存在的科組",
                        value=True,
                        key="auto_create_missing_subjects",
                    )

                imp_target_subj = None
                if "指定科組" in imp_target:
                    imp_target_subj = st.selectbox(
                        "目標科組",
                        _subject_options(),
                        key="imp_target_subj",
                    )

                if st.button(
                    "⬆️ 確認匯入",
                    use_container_width=True,
                    type="primary",
                    key="btn_import_json",
                ):
                    total_added = 0

                    for src_subject, words in imp_subjects.items():
                        if not words:
                            continue

                        if "指定科組" in imp_target and imp_target_subj:
                            dest = imp_target_subj
                        else:
                            subjects_now = refresh_subjects()
                            if src_subject in subjects_now:
                                dest = src_subject
                            elif auto_create_missing:
                                create_custom_subject(src_subject)
                                dest = src_subject
                            else:
                                dest = "學校行政"

                        total_added += add_subject_terms(dest, list(words))

                    invalidate_vocab_cache()
                    st.success(f"✅ 匯入完成！共新增 {total_added} 個詞語（已去重）")
                    st.rerun()

            except Exception as ex:
                st.error(f"讀取 JSON 失敗：{ex}")

        elif imp_name.endswith(".txt"):
            try:
                imp_text = None
                for enc in ["utf-8", "utf-16", "big5"]:
                    try:
                        imp_text = imp_raw.decode(enc)
                        break
                    except Exception:
                        pass

                if imp_text is None:
                    imp_text = imp_raw.decode("utf-8", errors="ignore")

                imp_words = [w.strip() for w in imp_text.splitlines() if w.strip()]
                st.markdown(f"**偵測到 {len(imp_words)} 個詞語**")
                with st.expander("預覽詞語（前 30 個）", expanded=False):
                    st.write("、".join(imp_words[:30]))

                imp_txt_subj = st.selectbox(
                    "匯入至科組",
                    _subject_options(),
                    key="imp_txt_subj",
                )

                if st.button(
                    "⬆️ 確認匯入",
                    use_container_width=True,
                    type="primary",
                    key="btn_import_txt",
                ):
                    added = add_subject_terms(imp_txt_subj, imp_words)
                    invalidate_vocab_cache()
                    st.success(f"✅ 匯入完成！共新增 {added} 個詞語（已去重）")
                    st.rerun()

            except Exception as ex:
                st.error(f"讀取 TXT 失敗：{ex}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3：自動學習修正詞
# ══════════════════════════════════════════════════════════════════════════════
with tab_learn:
    st.markdown("### 自動學習修正詞")
    st.info(
        "每次在「修正逐字稿」頁面修改錯誤詞語時，"
        "系統可記錄「原詞 → 修正詞」配對，下次轉錄後自動套用修正。"
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
                corrections.pop(k, None)
            with CORRECTIONS_FILE.open("w", encoding="utf-8") as f:
                json.dump({"corrections": corrections}, f, ensure_ascii=False, indent=2)
            st.rerun()

        st.divider()
        if st.button("🗑 清除所有修正詞", type="secondary", key="btn_clear_all_corrections"):
            with CORRECTIONS_FILE.open("w", encoding="utf-8") as f:
                json.dump({"corrections": {}}, f, ensure_ascii=False, indent=2)
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
        if orig_input.strip() and corr_input.strip():
            save_correction_pair(orig_input.strip(), corr_input.strip())
            st.success(f"✅ 已新增：{orig_input.strip()} → {corr_input.strip()}")
            st.rerun()
        else:
            st.warning("請同時輸入原詞及修正詞")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4：修正頻率統計
# ══════════════════════════════════════════════════════════════════════════════
with tab_stats:
    st.markdown("### 📊 修正頻率統計")
    st.info(
        "記錄每個修正詞被套用的次數，反映哪些術語最常被辨識錯誤，"
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
        max_count = max(max_count, 1)

        for s in stats[:20]:
            bar_len = int(s["count"] / max_count * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            col_a, col_b, col_c, col_d = st.columns([2, 2, 3, 1])
            col_a.code(s["original"])
            col_b.code(s["corrected"])
            col_c.markdown(f"`{bar}` {s['count']} 次")

            if col_d.button("🗑", key=f"del_stat_{s['original']}"):
                data = _load_corrections_data()
                data["corrections"].pop(s["original"], None)
                data.get("counts", {}).pop(s["original"], None)
                _save_corrections_data(data)
                st.rerun()

        st.divider()
        st.markdown("**💡 高頻修正詞加入詞庫**")
        st.caption("將修正次數 ≥ 3 的正確詞語加入指定科組詞庫，讓下次分詞更準確。")

        high_freq = [s for s in stats if s["count"] >= 3]
        if high_freq:
            target_subj = st.selectbox(
                "加入至科組詞庫",
                _subject_options(),
                key="stat_target_subj",
            )

            words_to_add = [s["corrected"] for s in high_freq]
            tags_html = "".join(
                f'<span style="display:inline-block;background:#eef2ff;padding:4px 8px;'
                f'border-radius:999px;margin:3px;font-size:0.9rem;">{w}</span>'
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
            data = _load_corrections_data()
            data["counts"] = {}
            _save_corrections_data(data)
            st.success("已清除所有統計記錄（修正詞配對保留）")
            st.rerun()