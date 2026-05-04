# tests/test_page4_vocab_flow.py
"""
tests/test_page4_vocab_flow.py

page 4「詞庫管理」流程級測試藍本
================================

目標
----
這份測試不直接依賴 Streamlit 前端互動框架去點按鈕，
而是將 pages/4_詞庫管理.py 的核心流程抽象成可測試的 helper，
以驗證整個頁面邏輯是否符合預期。

涵蓋流程
--------
1. 科組詞庫管理（手動輸入）
2. 詞庫匯出：JSON / TXT
3. 詞庫匯入：JSON / TXT
4. 自動學習修正詞：單筆新增、批次新增、刪除、清空
5. 修正頻率統計：讀取、刪除個別統計、清空統計
6. 高頻修正詞加入指定科組詞庫

設計重點
--------
- 緊扣 pages/4_詞庫管理.py 現有邏輯
- 緊扣 services/vocab_manager.py 當前行為
- 測試內容貼近香港天主教中學環境
- 不污染正式 data 目錄
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


# =============================================================================
# fixture / helper
# =============================================================================

@pytest.fixture()
def vm(tmp_path, monkeypatch):
    """
    隔離版 services.vocab_manager：
    - VOCAB_DIR 指向 pytest tmp_path
    - CORRECTIONS_FILE 指向 pytest tmp_path
    - 清空 _vocab_cache
    """
    import services.vocab_manager as original_vm

    mod = importlib.reload(original_vm)

    vocab_dir = tmp_path / "data" / "vocab"
    vocab_dir.mkdir(parents=True, exist_ok=True)

    corrections_file = tmp_path / "data" / "corrections.json"
    corrections_file.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "VOCAB_DIR", vocab_dir, raising=True)
    monkeypatch.setattr(mod, "CORRECTIONS_FILE", corrections_file, raising=True)
    monkeypatch.setattr(mod, "_vocab_cache", None, raising=True)

    return mod


@pytest.fixture()
def page4_helpers(vm):
    """
    將 pages/4_詞庫管理.py 的流程抽成 helper，方便做流程級測試。
    注意：這些 helper 是「按 page 4 實作反推」的測試藍本，不是正式產品碼。
    """

    class H:
        # ---------------------------------------------------------------------
        # Tab 1：手動新增詞語
        # ---------------------------------------------------------------------
        @staticmethod
        def parse_manual_terms(manual: str) -> list[str]:
            """
            對應 page 4：
            1. 先嘗試用逗號拆分
            2. 若無結果，再改用換行拆分
            """
            terms = [t.strip() for t in manual.replace("，", ",").replace("、", ",").split(",") if t.strip()]
            if not terms:
                terms = [t.strip() for t in manual.splitlines() if t.strip()]
            return terms

        @staticmethod
        def add_manual_terms(subject: str, manual: str) -> int:
            terms = H.parse_manual_terms(manual)
            if not terms:
                return 0
            return vm.add_subject_terms(subject, terms)

        # ---------------------------------------------------------------------
        # Tab 2：匯出詞庫
        # ---------------------------------------------------------------------
        @staticmethod
        def export_vocab(export_scope: str, export_subj: str | None, export_fmt: str):
            subjects_to_export = list(vm.SUBJECTS.keys()) if export_scope == "全部科組" else [export_subj]

            export_data = {}
            total_words = 0
            for subj in subjects_to_export:
                path = vm.get_subject_vocab_path(subj)
                if path.exists():
                    words = [
                        line.strip().split()[0]
                        for line in path.read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.strip().startswith("#")
                    ]
                    export_data[subj] = words
                    total_words += len(words)
                else:
                    export_data[subj] = []

            if "TXT" in export_fmt:
                all_words = []
                for ws in export_data.values():
                    all_words.extend(ws)
                txt_content = "\n".join(sorted(set(all_words)))
                return {
                    "kind": "txt",
                    "filename": "voicedoc_vocab_export.txt",
                    "content": txt_content,
                    "total_words_raw": len(all_words),
                    "total_words_unique": len(sorted(set(all_words))),
                }

            payload = {
                "_voicedoc_vocab_v1": True,
                "_export_scope": export_scope,
                "_total_words": total_words,
                "subjects": export_data,
            }
            return {
                "kind": "json",
                "filename": "voicedoc_vocab_export.json",
                "content": payload,
            }

        # ---------------------------------------------------------------------
        # Tab 2：匯入詞庫（JSON）
        # ---------------------------------------------------------------------
        @staticmethod
        def import_json_payload(payload: dict, import_mode: str, target_subject: str | None = None) -> int:
            imp_subjects = payload.get("subjects", {})
            total_added = 0

            for src_subject, words in imp_subjects.items():
                if not words:
                    continue

                if "指定科組" in import_mode and target_subject:
                    dest = target_subject
                else:
                    # 這裡刻意保留 page 4 的邏輯：
                    # 若來源科組不在 SUBJECTS，先設成 "通用"
                    # 之後再交由 vocab_manager fallback 到學校行政
                    dest = src_subject if src_subject in vm.SUBJECTS else "通用"

                total_added += vm.add_subject_terms(dest, words)

            vm.invalidate_vocab_cache()
            return total_added

        # ---------------------------------------------------------------------
        # Tab 2：匯入詞庫（TXT）
        # ---------------------------------------------------------------------
        @staticmethod
        def decode_txt_import(raw: bytes) -> str:
            """
            對應 page 4：
            嘗試 utf-8 -> utf-16 -> big5
            若失敗則 fallback utf-8 ignore
            """
            for enc in ["utf-8", "utf-16", "big5"]:
                try:
                    return raw.decode(enc)
                except Exception:
                    pass
            return raw.decode("utf-8", errors="ignore")

        @staticmethod
        def import_txt_content(raw: bytes, target_subject: str) -> tuple[int, list[str]]:
            text = H.decode_txt_import(raw)
            words = [w.strip() for w in text.splitlines() if w.strip()]
            added = vm.add_subject_terms(target_subject, words)
            vm.invalidate_vocab_cache()
            return added, words

        # ---------------------------------------------------------------------
        # Tab 3：自動學習修正詞
        # ---------------------------------------------------------------------
        @staticmethod
        def add_manual_correction(original: str, corrected: str) -> bool:
            original = (original or "").strip()
            corrected = (corrected or "").strip()
            if not original or not corrected:
                return False
            vm.save_correction_pair(original, corrected)
            return True

        @staticmethod
        def delete_corrections(keys_to_delete: list[str]) -> dict:
            corrections = vm.load_corrections()
            for k in keys_to_delete:
                corrections.pop(k, None)

            with vm.CORRECTIONS_FILE.open("w", encoding="utf-8") as f:
                json.dump({"corrections": corrections}, f, ensure_ascii=False, indent=2)

            return corrections

        @staticmethod
        def clear_all_corrections() -> None:
            with vm.CORRECTIONS_FILE.open("w", encoding="utf-8") as f:
                json.dump({"corrections": {}}, f, ensure_ascii=False, indent=2)

        # ---------------------------------------------------------------------
        # Tab 4：修正頻率統計
        # ---------------------------------------------------------------------
        @staticmethod
        def delete_stat_item(original: str) -> dict:
            data = vm._load_corrections_data()
            data["corrections"].pop(original, None)
            data.get("counts", {}).pop(original, None)
            vm._save_corrections_data(data)
            return data

        @staticmethod
        def clear_all_stats() -> dict:
            data = vm._load_corrections_data()
            data["counts"] = {}
            vm._save_corrections_data(data)
            return data

        @staticmethod
        def get_high_freq_corrected_words(min_count: int = 3) -> list[str]:
            stats = vm.get_correction_stats(top_n=30)
            return [s["corrected"] for s in stats if s["count"] >= min_count]

        @staticmethod
        def add_high_freq_words_to_subject(subject: str, min_count: int = 3) -> int:
            words = H.get_high_freq_corrected_words(min_count=min_count)
            added = vm.add_subject_terms(subject, words)
            vm.invalidate_vocab_cache()
            return added

    return H


def _seed_vocab_for_school(vm):
    vm.add_subject_terms("宗教科", ["四旬期", "福傳", "公教報"])
    vm.add_subject_terms("學校行政", ["法團校董會", "家長教師會", "學校發展計劃"])
    vm.add_subject_terms("公民與社會發展科（C&SD）", ["國家安全教育", "憲法與基本法"])


def _seed_corrections_with_counts(vm):
    vm._save_corrections_data(
        {
            "corrections": {
                "公社科": "公民與社會發展科",
                "靈修週": "靈修周",
                "家教會": "家長教師會",
                "福音份享": "福音分享",
            },
            "counts": {
                "公社科": 5,
                "靈修週": 2,
                "家教會": 4,
                "福音份享": 3,
            },
        }
    )


# =============================================================================
# Tab 1：科組詞庫管理
# =============================================================================

class TestPage4Tab1ManualVocab:
    """對應 page 4 的『手動輸入詞語』流程。"""

    @pytest.mark.parametrize(
        ("manual", "expected"),
        [
            ("四旬期, 福傳, 公教報", ["四旬期", "福傳", "公教報"]),
            ("四旬期，福傳，公教報", ["四旬期", "福傳", "公教報"]),
            ("法團校董會\n家長教師會\n學校發展計劃", ["法團校董會", "家長教師會", "學校發展計劃"]),
            ("  四旬期  ,  福傳  ", ["四旬期", "福傳"]),
        ],
    )
    def test_parse_manual_terms(self, page4_helpers, manual, expected):
        assert page4_helpers.parse_manual_terms(manual) == expected

    def test_add_manual_terms_into_religion_subject(self, vm, page4_helpers):
        added = page4_helpers.add_manual_terms("宗教科", "四旬期, 福傳, 公教報")
        assert added == 3

        words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
        assert {"四旬期", "福傳", "公教報"}.issubset(words)

    def test_add_manual_terms_empty_input_returns_zero(self, vm, page4_helpers):
        added = page4_helpers.add_manual_terms("學校行政", "   \n \n ")
        assert added == 0

    def test_add_manual_terms_alias_subject_supported(self, vm, page4_helpers):
        added = page4_helpers.add_manual_terms("C&SD", "國家安全教育, 憲法與基本法")
        assert added == 2

        words = vm._read_vocab_file(vm.get_subject_vocab_path("公民與社會發展科（C&SD）"))
        assert {"國家安全教育", "憲法與基本法"}.issubset(words)


# =============================================================================
# Tab 2：匯出
# =============================================================================

class TestPage4Tab2Export:
    """對應 page 4 的『匯出詞庫』流程。"""

    def test_export_json_single_subject(self, vm, page4_helpers):
        vm.add_subject_terms("宗教科", ["四旬期", "福傳", "公教報"])

        result = page4_helpers.export_vocab(
            export_scope="指定科組",
            export_subj="宗教科",
            export_fmt="JSON（完整，推薦）",
        )

        assert result["kind"] == "json"
        assert result["filename"] == "voicedoc_vocab_export.json"
        payload = result["content"]
        assert payload["_voicedoc_vocab_v1"] is True
        assert payload["_export_scope"] == "指定科組"
        assert payload["_total_words"] == 3
        assert payload["subjects"]["宗教科"] == ["四旬期", "福傳", "公教報"]

    def test_export_json_all_subjects(self, vm, page4_helpers):
        _seed_vocab_for_school(vm)

        result = page4_helpers.export_vocab(
            export_scope="全部科組",
            export_subj=None,
            export_fmt="JSON（完整，推薦）",
        )

        payload = result["content"]
        assert payload["_voicedoc_vocab_v1"] is True
        assert payload["_export_scope"] == "全部科組"
        assert "宗教科" in payload["subjects"]
        assert "學校行政" in payload["subjects"]
        assert "公民與社會發展科（C&SD）" in payload["subjects"]
        assert payload["_total_words"] >= 8

    def test_export_txt_single_subject(self, vm, page4_helpers):
        vm.add_subject_terms("學校行政", ["法團校董會", "家長教師會", "學校發展計劃"])

        result = page4_helpers.export_vocab(
            export_scope="指定科組",
            export_subj="學校行政",
            export_fmt="TXT（純詞語列表）",
        )

        assert result["kind"] == "txt"
        assert result["filename"] == "voicedoc_vocab_export.txt"
        lines = [x for x in result["content"].splitlines() if x.strip()]
        assert lines == sorted(["法團校董會", "家長教師會", "學校發展計劃"])

    def test_export_txt_all_subjects_should_deduplicate(self, vm, page4_helpers):
        vm.add_subject_terms("宗教科", ["福傳", "靈修周"])
        vm.add_subject_terms("學校行政", ["福傳", "法團校董會"])

        result = page4_helpers.export_vocab(
            export_scope="全部科組",
            export_subj=None,
            export_fmt="TXT（純詞語列表）",
        )

        lines = [x for x in result["content"].splitlines() if x.strip()]
        assert "福傳" in lines
        assert lines.count("福傳") == 1
        assert "靈修周" in lines
        assert "法團校董會" in lines


# =============================================================================
# Tab 2：匯入
# =============================================================================

class TestPage4Tab2Import:
    """對應 page 4 的『匯入詞庫』流程。"""

    def test_import_json_by_original_subject(self, vm, page4_helpers):
        payload = {
            "_voicedoc_vocab_v1": True,
            "_export_scope": "全部科組",
            "_total_words": 5,
            "subjects": {
                "宗教科": ["四旬期", "福傳"],
                "學校行政": ["法團校董會", "家長教師會"],
                "公民與社會發展科（C&SD）": ["國家安全教育"],
            },
        }

        added = page4_helpers.import_json_payload(
            payload=payload,
            import_mode="按原科組匯入（推薦）",
        )
        assert added == 5

        religion_words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
        admin_words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
        csd_words = vm._read_vocab_file(vm.get_subject_vocab_path("公民與社會發展科（C&SD）"))

        assert {"四旬期", "福傳"}.issubset(religion_words)
        assert {"法團校董會", "家長教師會"}.issubset(admin_words)
        assert {"國家安全教育"}.issubset(csd_words)

    def test_import_json_all_into_target_subject(self, vm, page4_helpers):
        payload = {
            "_voicedoc_vocab_v1": True,
            "_export_scope": "全部科組",
            "_total_words": 4,
            "subjects": {
                "宗教科": ["四旬期", "福傳"],
                "學校行政": ["法團校董會", "家長教師會"],
            },
        }

        added = page4_helpers.import_json_payload(
            payload=payload,
            import_mode="全部匯入至指定科組",
            target_subject="學校行政",
        )
        assert added == 4

        admin_words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
        assert {"四旬期", "福傳", "法團校董會", "家長教師會"}.issubset(admin_words)

    def test_import_json_unknown_subject_eventually_falls_back_to_school_admin(self, vm, page4_helpers):
        payload = {
            "_voicedoc_vocab_v1": True,
            "_export_scope": "全部科組",
            "_total_words": 2,
            "subjects": {
                "天主教核心價值教育組": ["真理", "義德"],
            },
        }

        added = page4_helpers.import_json_payload(
            payload=payload,
            import_mode="按原科組匯入（推薦）",
        )
        assert added == 2

        admin_words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
        assert {"真理", "義德"}.issubset(admin_words)

    def test_import_json_deduplicates_existing_words(self, vm, page4_helpers):
        vm.add_subject_terms("宗教科", ["四旬期"])

        payload = {
            "_voicedoc_vocab_v1": True,
            "_export_scope": "指定科組",
            "_total_words": 2,
            "subjects": {
                "宗教科": ["四旬期", "福傳"],
            },
        }

        added = page4_helpers.import_json_payload(
            payload=payload,
            import_mode="按原科組匯入（推薦）",
        )
        assert added == 1

    @pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "big5"])
    def test_decode_txt_import_supports_multiple_encodings(self, page4_helpers, encoding):
        text = "法團校董會\n家長教師會\n"
        raw = text.encode(encoding)
        decoded = page4_helpers.decode_txt_import(raw)
        assert "法團校董會" in decoded
        assert "家長教師會" in decoded

    def test_import_txt_content_into_target_subject(self, vm, page4_helpers):
        raw = "法團校董會\n家長教師會\n學校發展計劃\n".encode("utf-8")

        added, words = page4_helpers.import_txt_content(raw, target_subject="學校行政")
        assert added == 3
        assert words == ["法團校董會", "家長教師會", "學校發展計劃"]

        admin_words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
        assert {"法團校董會", "家長教師會", "學校發展計劃"}.issubset(admin_words)

    def test_import_txt_content_ignores_blank_lines(self, vm, page4_helpers):
        raw = "\n法團校董會\n\n家長教師會\n \n學校發展計劃\n".encode("utf-8")

        added, words = page4_helpers.import_txt_content(raw, target_subject="學校行政")
        assert added == 3
        assert words == ["法團校董會", "家長教師會", "學校發展計劃"]


# =============================================================================
# Tab 3：自動學習修正詞
# =============================================================================

class TestPage4Tab3Corrections:
    """對應 page 4 的『自動學習修正詞』流程。"""

    def test_add_manual_correction_success(self, vm, page4_helpers):
        ok = page4_helpers.add_manual_correction("DSC", "DSE")
        assert ok is True

        corrections = vm.load_corrections()
        assert corrections["DSC"] == "DSE"

    @pytest.mark.parametrize(
        ("original", "corrected"),
        [
            ("", "DSE"),
            ("DSC", ""),
            (" ", "DSE"),
            ("DSC", " "),
        ],
    )
    def test_add_manual_correction_rejects_blank(self, vm, page4_helpers, original, corrected):
        ok = page4_helpers.add_manual_correction(original, corrected)
        assert ok is False
        assert vm.load_corrections() == {}

    def test_delete_selected_corrections(self, vm, page4_helpers):
        vm.save_correction_pair("DSC", "DSE")
        vm.save_correction_pair("公社科", "公民與社會發展科")
        vm.save_correction_pair("福音份享", "福音分享")

        left = page4_helpers.delete_corrections(["DSC", "福音份享"])
        assert "DSC" not in left
        assert "福音份享" not in left
        assert left["公社科"] == "公民與社會發展科"

    def test_clear_all_corrections(self, vm, page4_helpers):
        vm.save_correction_pair("DSC", "DSE")
        vm.save_correction_pair("公社科", "公民與社會發展科")

        page4_helpers.clear_all_corrections()
        assert vm.load_corrections() == {}


# =============================================================================
# Tab 4：修正頻率統計
# =============================================================================

class TestPage4Tab4Stats:
    """對應 page 4 的『修正頻率統計』流程。"""

    def test_delete_one_stat_item_should_remove_both_correction_and_count(self, vm, page4_helpers):
        _seed_corrections_with_counts(vm)

        data = page4_helpers.delete_stat_item("家教會")
        assert "家教會" not in data["corrections"]
        assert "家教會" not in data["counts"]

    def test_clear_all_stats_should_keep_corrections(self, vm, page4_helpers):
        _seed_corrections_with_counts(vm)

        data = page4_helpers.clear_all_stats()
        assert data["counts"] == {}
        assert "公社科" in data["corrections"]
        assert "家教會" in data["corrections"]

    def test_get_high_freq_corrected_words(self, vm, page4_helpers):
        _seed_corrections_with_counts(vm)

        words = page4_helpers.get_high_freq_corrected_words(min_count=3)
        assert "公民與社會發展科" in words
        assert "家長教師會" in words
        assert "福音分享" in words
        assert "靈修周" not in words

    def test_add_high_freq_words_to_subject(self, vm, page4_helpers):
        _seed_corrections_with_counts(vm)

        added = page4_helpers.add_high_freq_words_to_subject("學校行政", min_count=3)
        assert added == 3

        admin_words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
        assert {"公民與社會發展科", "家長教師會", "福音分享"}.issubset(admin_words)

    def test_add_high_freq_words_to_subject_is_deduplicated(self, vm, page4_helpers):
        _seed_corrections_with_counts(vm)
        vm.add_subject_terms("學校行政", ["家長教師會"])

        added = page4_helpers.add_high_freq_words_to_subject("學校行政", min_count=3)
        assert added == 2


# =============================================================================
# 跨 tab 綜合流程
# =============================================================================

class TestPage4IntegratedFlows:
    """模擬 page 4 使用者真實操作鏈。"""

    def test_handover_flow_export_json_then_import_json(self, vm, page4_helpers):
        """
        離職同事匯出 JSON，新同事再按原科組匯入。
        """
        _seed_vocab_for_school(vm)

        exported = page4_helpers.export_vocab(
            export_scope="全部科組",
            export_subj=None,
            export_fmt="JSON（完整，推薦）",
        )
        payload = exported["content"]

        # 模擬新環境：清空目前詞庫
        for p in vm.VOCAB_DIR.glob("*"):
            p.unlink()
        vm.invalidate_vocab_cache()

        added = page4_helpers.import_json_payload(
            payload=payload,
            import_mode="按原科組匯入（推薦）",
        )
        assert added >= 8

        religion_words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
        admin_words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
        assert {"四旬期", "福傳", "公教報"}.issubset(religion_words)
        assert {"法團校董會", "家長教師會", "學校發展計劃"}.issubset(admin_words)

    def test_manual_add_then_export_txt_then_import_to_other_subject(self, vm, page4_helpers):
        """
        行政組先建立詞庫，再以 TXT 匯出給其他科組使用。
        """
        page4_helpers.add_manual_terms("學校行政", "法團校董會, 家長教師會, 學校發展計劃")

        exported = page4_helpers.export_vocab(
            export_scope="指定科組",
            export_subj="學校行政",
            export_fmt="TXT（純詞語列表）",
        )

        added, imported_words = page4_helpers.import_txt_content(
            exported["content"].encode("utf-8"),
            target_subject="宗教科",
        )

        assert added == 3
        assert imported_words == sorted(["法團校董會", "家長教師會", "學校發展計劃"])

        religion_words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
        assert {"法團校董會", "家長教師會", "學校發展計劃"}.issubset(religion_words)

    def test_transcript_correction_learning_flow(self, vm, page4_helpers):
        """
        模擬使用者在其他頁修正逐字稿後，page 4 讀取修正詞與統計。
        """
        original = "法團校董會與家教會將討論四巡期活動，宗教科老師分享福音份享稿件。"
        corrected = "法團校董會與家長教師會將討論四旬期活動，宗教科老師分享福音分享稿件。"

        pairs = vm.extract_correction_pairs(original, corrected)
        saved = vm.bulk_save_correction_pairs(pairs)

        assert saved >= 3
        corrections = vm.load_corrections()
        assert corrections["家教會"] == "家長教師會"
        assert corrections["四巡期"] == "四旬期"
        assert corrections["福音份享"] == "福音分享"

    def test_stats_to_vocab_promotion_flow(self, vm, page4_helpers):
        """
        對應 page 4：
        高頻修正詞 >= 3 次 -> 加入指定科組詞庫。
        """
        _seed_corrections_with_counts(vm)

        added = page4_helpers.add_high_freq_words_to_subject("宗教科", min_count=3)
        assert added == 3

        religion_words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
        assert {"公民與社會發展科", "家長教師會", "福音分享"}.issubset(religion_words)

    def test_correction_cleanup_flow(self, vm, page4_helpers):
        """
        先新增修正詞，再刪除部分，最後清空全部。
        """
        page4_helpers.add_manual_correction("DSC", "DSE")
        page4_helpers.add_manual_correction("天主敎", "天主教")
        page4_helpers.add_manual_correction("公社科", "公民與社會發展科")

        left = page4_helpers.delete_corrections(["DSC"])
        assert "DSC" not in left
        assert "天主敎" in left

        page4_helpers.clear_all_corrections()
        assert vm.load_corrections() == {}


# =============================================================================
# 特定香港天主教中學情境
# =============================================================================

class TestPage4HongKongCatholicContext:
    """讓 page 4 流程測試貼近你的實際校本場景。"""

    def test_religion_subject_manual_vocab_flow(self, vm, page4_helpers):
        added = page4_helpers.add_manual_terms(
            "宗教科",
            "天主教教育五大核心價值, 福傳, 靈修周, 主保瞻禮"
        )
        assert added == 4

        words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
        assert {
            "天主教教育五大核心價值",
            "福傳",
            "靈修周",
            "主保瞻禮",
        }.issubset(words)

    def test_school_admin_import_txt_flow(self, vm, page4_helpers):
        raw = "法團校董會\n家長教師會\n教師專業發展\n".encode("utf-8")
        added, words = page4_helpers.import_txt_content(raw, target_subject="學校行政")

        assert added == 3
        assert words == ["法團校董會", "家長教師會", "教師專業發展"]

    def test_csd_and_ces_remain_separate_in_import_export_flow(self, vm, page4_helpers):
        page4_helpers.add_manual_terms("C&SD", "國家安全教育, 憲法與基本法")
        page4_helpers.add_manual_terms("CES", "個人成長, 家庭理財")

        exported = page4_helpers.export_vocab(
            export_scope="全部科組",
            export_subj=None,
            export_fmt="JSON（完整，推薦）",
        )
        payload = exported["content"]

        assert payload["subjects"]["公民與社會發展科（C&SD）"] == ["國家安全教育", "憲法與基本法"]
        assert payload["subjects"]["公民、經濟與社會科（CES）"] == ["個人成長", "家庭理財"]


# =============================================================================
# 安全檢查
# =============================================================================

def test_paths_are_isolated(vm, tmp_path):
    assert str(vm.VOCAB_DIR).startswith(str(tmp_path))
    assert str(vm.CORRECTIONS_FILE).startswith(str(tmp_path))