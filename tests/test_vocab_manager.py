# test_vocab_manager.py
"""
VoiceDoc AI - tests for services/vocab_manager.py

設計目標：
1. 緊扣現有 services/vocab_manager.py 的函式與行為
2. 覆蓋香港天主教中學常見使用場景（宗教科、學校行政、C&SD、CES、BAFS）
3. 驗證詞庫檔案、別名解析、快取、修正詞、自動學習配對
4. 測試可在隔離環境執行，不污染正式 data/ 目錄

執行方式：
    pytest -q test_vocab_manager.py
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture()
def vm(tmp_path, monkeypatch):
    """
    載入一個隔離版 vocab_manager 模組：
    - VOCAB_DIR 指向 pytest tmp_path
    - CORRECTIONS_FILE 指向 pytest tmp_path
    - SUBJECTS / SUBJECT_ALIASES 沿用原模組
    """
    import services.vocab_manager as original_vm

    mod = importlib.reload(original_vm)

    test_vocab_dir = tmp_path / "data" / "vocab"
    test_vocab_dir.mkdir(parents=True, exist_ok=True)
    test_corr_file = tmp_path / "data" / "corrections.json"
    test_corr_file.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "VOCAB_DIR", test_vocab_dir, raising=True)
    monkeypatch.setattr(mod, "CORRECTIONS_FILE", test_corr_file, raising=True)
    monkeypatch.setattr(mod, "_vocab_cache", None, raising=True)

    return mod


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]


def test_subjects_should_cover_hk_catholic_school_core_context(vm):
    """
    香港天主教中學常見核心科組應存在。
    """
    expected = {
        "中文科",
        "英文科",
        "數學科",
        "公民與社會發展科（C&SD）",
        "公民、經濟與社會科（CES）",
        "宗教科",
        "中國歷史科",
        "歷史科",
        "地理科",
        "資訊科技",
        "企業、會計與財務概論科（BAFS）",
        "學校行政",
    }
    assert expected.issubset(set(vm.SUBJECTS.keys()))


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("通識科", "公民與社會發展科（C&SD）"),
        ("通識/公社", "公民與社會發展科（C&SD）"),
        ("公社科", "公民與社會發展科（C&SD）"),
        ("C&SD", "公民與社會發展科（C&SD）"),
        ("CES", "公民、經濟與社會科（CES）"),
        ("BAFS", "企業、會計與財務概論科（BAFS）"),
        ("中史", "中國歷史科"),
        ("中史科", "中國歷史科"),
        ("經濟", "經濟科"),
        ("生物", "生物科"),
        ("物理", "物理科"),
        ("化學", "化學科"),
        ("科學科", "科學科（綜合）"),
    ],
)
def test_resolve_subject_aliases(vm, alias, canonical):
    assert vm._resolve_subject(alias) == canonical


def test_unknown_subject_should_fallback_to_school_admin(vm):
    assert vm._resolve_subject("天主教倫理培育組") == "學校行政"


def test_get_subject_vocab_path_should_follow_subject_mapping(vm):
    path = vm.get_subject_vocab_path("宗教科")
    assert path.name == vm.SUBJECTS["宗教科"]
    assert path.parent == vm.VOCAB_DIR


def test_get_subject_vocab_path_should_support_alias(vm):
    path1 = vm.get_subject_vocab_path("BAFS")
    path2 = vm.get_subject_vocab_path("企業、會計與財務概論科（BAFS）")
    assert path1 == path2


def test_read_vocab_file_should_ignore_blank_and_comments(vm):
    path = vm.get_subject_vocab_path("學校行政")
    path.write_text(
        "# 香港學校行政常用詞\n"
        "\n"
        "法團校董會\n"
        "家長教師會 100\n"
        "學校發展計劃\n",
        encoding="utf-8",
    )

    words = vm._read_vocab_file(path)
    assert words == {"法團校董會", "家長教師會", "學校發展計劃"}


def test_add_subject_terms_should_create_file_and_deduplicate_existing(vm):
    added1 = vm.add_subject_terms("宗教科", ["福音分享", "公教報", "福音分享"])
    assert added1 == 3

    added2 = vm.add_subject_terms("宗教科", ["福音分享", "四旬期", "公教報"])
    assert added2 == 1

    words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
    assert "福音分享" in words
    assert "公教報" in words
    assert "四旬期" in words
    assert len(words) == 3


def test_add_subject_terms_should_support_alias_subject(vm):
    added = vm.add_subject_terms("中史", ["辛亥革命", "太平天國"])
    assert added == 2

    words = vm._read_vocab_file(vm.get_subject_vocab_path("中國歷史科"))
    assert {"辛亥革命", "太平天國"}.issubset(words)


def test_add_subject_terms_should_fallback_to_school_admin_for_unknown_subject(vm):
    added = vm.add_subject_terms("天主教核心價值培育組", ["真理", "義德", "愛德"])
    assert added == 3

    words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
    assert {"真理", "義德", "愛德"}.issubset(words)


def test_add_subject_terms_keeps_whitespace_bug_visible_and_documented(vm):
    """
    依照目前實作，existing 只用原字串比較，不會先 strip existing 再去重；
    但新詞會 strip 後寫入。此測試用來固定目前行為，避免改動時無意破壞。
    """
    path = vm.get_subject_vocab_path("學校行政")
    path.write_text("校務會議\n", encoding="utf-8")

    added = vm.add_subject_terms("學校行政", [" 校務會議 ", "教師專業發展"])
    # 目前實作會把 " 校務會議 " 視為新詞，因為比較時未先 strip existing
    assert added == 2

    words = vm._read_vocab_file(path)
    assert "校務會議" in words
    assert "教師專業發展" in words


def test_add_vocab_word_should_ignore_blank_input(vm):
    vm.add_vocab_word("", "學校行政")
    vm.add_vocab_word("   ", "學校行政")

    path = vm.get_subject_vocab_path("學校行政")
    assert not path.exists() or vm._read_vocab_file(path) == set()


def test_add_vocab_word_should_add_to_specified_subject(vm):
    vm.add_vocab_word("天主教教育五大核心價值", "宗教科")
    words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
    assert "天主教教育五大核心價值" in words


def test_add_vocab_word_should_fallback_to_school_admin(vm):
    vm.add_vocab_word("法團校董會", "不存在的部門")
    words = vm._read_vocab_file(vm.get_subject_vocab_path("學校行政"))
    assert "法團校董會" in words


def test_list_subject_vocabs_should_return_count_for_all_subjects(vm):
    vm.add_subject_terms("中文科", ["文言文", "修辭"])
    vm.add_subject_terms("宗教科", ["玫瑰經"])
    counts = vm.list_subject_vocabs()

    assert isinstance(counts, dict)
    assert set(vm.SUBJECTS.keys()).issubset(set(counts.keys()))
    assert counts["中文科"] == 2
    assert counts["宗教科"] == 1


def test_load_all_vocab_should_merge_all_subject_vocab_files(vm):
    vm.add_subject_terms("中文科", ["文憑試", "範文"])
    vm.add_subject_terms("宗教科", ["福傳"])
    vm.add_subject_terms("學校行政", ["法團校董會"])

    all_words = vm.load_all_vocab()
    assert {"文憑試", "範文", "福傳", "法團校董會"}.issubset(all_words)


def test_load_all_vocab_should_use_cache_until_invalidated(vm):
    path = vm.get_subject_vocab_path("學校行政")
    path.write_text("校友會\n", encoding="utf-8")

    first = vm.load_all_vocab()
    assert "校友會" in first

    path.write_text("校友會\n校本管理\n", encoding="utf-8")
    second = vm.load_all_vocab()
    assert "校本管理" not in second

    vm.invalidate_vocab_cache()
    third = vm.load_all_vocab()
    assert "校本管理" in third


def test_load_corrections_should_return_empty_when_file_missing(vm):
    assert vm.load_corrections() == {}
    assert vm.get_corrections_count() == 0


def test_load_corrections_should_return_empty_on_invalid_json(vm):
    vm.CORRECTIONS_FILE.write_text("{bad json", encoding="utf-8")
    assert vm.load_corrections() == {}
    assert vm.get_correction_stats() == []


def test_save_correction_pair_should_persist(vm):
    vm.save_correction_pair("公社發展科", "公民與社會發展科")
    vm.save_correction_pair("福音份享", "福音分享")

    data = json.loads(vm.CORRECTIONS_FILE.read_text(encoding="utf-8"))
    assert data["corrections"]["公社發展科"] == "公民與社會發展科"
    assert data["corrections"]["福音份享"] == "福音分享"


def test_get_corrections_count_should_match_saved_pairs(vm):
    vm.save_correction_pair("天主敎", "天主教")
    vm.save_correction_pair("靈修週", "靈修周")
    assert vm.get_corrections_count() == 2


def test_get_correction_stats_should_sort_by_count_desc(vm):
    vm.CORRECTIONS_FILE.write_text(
        json.dumps(
            {
                "corrections": {
                    "公社科": "公民與社會發展科",
                    "早禱週": "早禱周",
                    "聯課": "其他學習經歷",
                },
                "counts": {
                    "聯課": 7,
                    "公社科": 3,
                    "早禱週": 5,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    stats = vm.get_correction_stats(top_n=3)
    assert [s["original"] for s in stats] == ["聯課", "早禱週", "公社科"]
    assert stats[0]["corrected"] == "其他學習經歷"
    assert stats[0]["count"] == 7


def test_extract_correction_pairs_should_find_replacements_in_school_context(vm):
    original = "本年度公社科會議將討論靈修週及家長日安排"
    corrected = "本年度公民與社會發展科會議將討論靈修周及家長日安排"

    pairs = vm.extract_correction_pairs(original, corrected)

    assert ("公社科", "公民與社會發展科") in pairs
    assert ("靈修週", "靈修周") in pairs


def test_extract_correction_pairs_should_return_empty_for_empty_inputs(vm):
    assert vm.extract_correction_pairs("", "") == []
    assert vm.extract_correction_pairs("教師會議", "") == []
    assert vm.extract_correction_pairs("", "教師會議") == []


def test_extract_correction_pairs_should_skip_too_long_original_chunk(vm):
    original = "這是一段非常非常非常長的原始錯誤詞組內容"
    corrected = "短詞"
    pairs = vm.extract_correction_pairs(original, corrected)
    assert pairs == []


def test_bulk_save_correction_pairs_should_save_only_valid_pairs(vm):
    saved = vm.bulk_save_correction_pairs(
        [
            ("公社科", "公民與社會發展科"),
            ("", "無效"),
            ("家教會", "家長教師會"),
            ("宗教科", "宗教科"),
            ("早會", ""),
        ]
    )

    assert saved == 2

    data = json.loads(vm.CORRECTIONS_FILE.read_text(encoding="utf-8"))
    assert data["corrections"]["公社科"] == "公民與社會發展科"
    assert data["corrections"]["家教會"] == "家長教師會"
    assert "宗教科" not in data["corrections"]


def test_bulk_save_correction_pairs_should_return_zero_for_empty_list(vm):
    assert vm.bulk_save_correction_pairs([]) == 0
    assert not vm.CORRECTIONS_FILE.exists()


def test_bulk_save_correction_pairs_should_overwrite_same_original_with_latest_value(vm):
    saved = vm.bulk_save_correction_pairs(
        [
            ("公社科", "公民社會發展科"),
            ("公社科", "公民與社會發展科"),
        ]
    )
    assert saved == 2

    data = json.loads(vm.CORRECTIONS_FILE.read_text(encoding="utf-8"))
    assert data["corrections"]["公社科"] == "公民與社會發展科"


def test_internal_save_and_load_corrections_data_roundtrip(vm):
    payload = {
        "corrections": {
            "天主敎": "天主教",
            "校董會會義": "校董會會議",
        },
        "counts": {
            "天主敎": 6,
            "校董會會義": 2,
        },
    }
    vm._save_corrections_data(payload)
    loaded = vm._load_corrections_data()
    assert loaded == payload


def test_combined_school_workflow_vocab_and_corrections(vm):
    """
    模擬香港天主教中學常見完整流程：
    1. 宗教科、行政新增詞庫
    2. 從修正逐字稿中抽取錯詞配對
    3. 批次寫入修正詞
    4. 驗證詞庫與修正詞統計資料結構正常
    """
    vm.add_subject_terms("宗教科", ["四旬期", "公教報", "福音分享"])
    vm.add_subject_terms("學校行政", ["法團校董會", "家長教師會", "學校發展計劃"])

    original = (
        "法團校董會與家教會將討論四巡期活動，"
        "宗教科老師亦會分享公教部資源。"
    )
    corrected = (
        "法團校董會與家長教師會將討論四旬期活動，"
        "宗教科老師亦會分享公教報資源。"
    )

    pairs = vm.extract_correction_pairs(original, corrected)
    saved = vm.bulk_save_correction_pairs(pairs)

    vocab_all = vm.load_all_vocab()
    corrections = vm.load_corrections()

    assert "四旬期" in vocab_all
    assert "公教報" in vocab_all
    assert "法團校董會" in vocab_all
    assert saved >= 2
    assert corrections["家教會"] == "家長教師會"
    assert corrections["四巡期"] == "四旬期"
    assert corrections["公教部"] == "公教報"


def test_ces_and_csd_can_coexist_as_distinct_subjects(vm):
    vm.add_subject_terms("CES", ["個人成長", "家庭理財"])
    vm.add_subject_terms("C&SD", ["國家安全教育", "憲法與基本法"])

    ces_words = vm._read_vocab_file(vm.get_subject_vocab_path("公民、經濟與社會科（CES）"))
    csd_words = vm._read_vocab_file(vm.get_subject_vocab_path("公民與社會發展科（C&SD）"))

    assert "個人成長" in ces_words
    assert "家庭理財" in ces_words
    assert "國家安全教育" in csd_words
    assert "憲法與基本法" in csd_words


def test_religion_vocab_matches_catholic_school_context(vm):
    terms = [
        "天主教教育五大核心價值",
        "福傳",
        "靈修周",
        "主保瞻禮",
        "公教學生領袖",
    ]
    added = vm.add_subject_terms("宗教科", terms)
    assert added == len(terms)

    words = vm._read_vocab_file(vm.get_subject_vocab_path("宗教科"))
    assert set(terms).issubset(words)


def test_school_admin_vocab_matches_hong_kong_secondary_school_context(vm):
    terms = [
        "法團校董會",
        "學校發展計劃",
        "周年校務計劃",
        "教師專業發展",
        "家長教師會",
        "學生支援組",
    ]
    added = vm.add_subject_terms("學校行政", terms)
    assert added == len(terms)

    counts = vm.list_subject_vocabs()
    assert counts["學校行政"] == len(terms)


def test_vocab_files_are_plain_utf8_text_for_easy_handover(vm):
    """
    對應頁面 4 的設計理念：詞庫需容易交接、匯出、匯入。
    """
    vm.add_subject_terms("學校行政", ["法團校董會", "學校周年報告"])
    path = vm.get_subject_vocab_path("學校行政")

    raw = path.read_bytes()
    assert b"\x00" not in raw
    text = raw.decode("utf-8")
    assert "法團校董會" in text
    assert "學校周年報告" in text


def test_repeated_load_all_vocab_after_add_subject_terms_should_refresh_via_invalidate(vm):
    vm.add_subject_terms("中文科", ["校本評核"])
    first = vm.load_all_vocab()
    assert "校本評核" in first

    vm.add_subject_terms("中文科", ["公開試"])
    second = vm.load_all_vocab()
    assert "公開試" in second


def test_correction_stats_default_zero_when_counts_missing(vm):
    vm.CORRECTIONS_FILE.write_text(
        json.dumps(
            {
                "corrections": {
                    "靈修週": "靈修周",
                    "公社科": "公民與社會發展科",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    stats = vm.get_correction_stats()
    assert len(stats) == 2
    assert all(s["count"] == 0 for s in stats)


def test_correction_data_should_keep_counts_when_saving_single_pair(vm):
    vm.CORRECTIONS_FILE.write_text(
        json.dumps(
            {
                "corrections": {"公社科": "公民與社會發展科"},
                "counts": {"公社科": 5},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    vm.save_correction_pair("靈修週", "靈修周")

    data = json.loads(vm.CORRECTIONS_FILE.read_text(encoding="utf-8"))
    assert data["counts"]["公社科"] == 5
    assert data["corrections"]["靈修週"] == "靈修周"


def test_paths_should_be_under_isolated_tmp_directory(vm, tmp_path):
    assert str(vm.VOCAB_DIR).startswith(str(tmp_path))
    assert str(vm.CORRECTIONS_FILE).startswith(str(tmp_path))