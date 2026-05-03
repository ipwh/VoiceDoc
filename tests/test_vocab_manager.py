"""
tests/test_vocab_manager.py
vocab_manager 單元測試
執行：pytest tests/ -v
"""
import json
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def tmp_vocab_dir(tmp_path, monkeypatch):
    """每個測試使用獨立臨時目錄，不污染真實詞庫。"""
    import services.vocab_manager as vm
    monkeypatch.setattr(vm, "VOCAB_DIR", tmp_path)
    # CORRECTIONS_FILE 也改至臨時目錄
    monkeypatch.setattr(vm, "CORRECTIONS_FILE", tmp_path / "corrections.json")
    vm.invalidate_vocab_cache()
    yield tmp_path
    vm.invalidate_vocab_cache()


# ── _resolve_subject ──────────────────────────────────────────────────────────

def test_resolve_subject_known():
    from services.vocab_manager import _resolve_subject
    assert _resolve_subject("中文科") == "中文科"


def test_resolve_subject_alias_tongshi():
    from services.vocab_manager import _resolve_subject
    result = _resolve_subject("通識科")
    assert "公民" in result or result == "公民與社會發展科"


def test_resolve_subject_alias_zhongshi():
    from services.vocab_manager import _resolve_subject
    result = _resolve_subject("中史")
    assert "中國歷史" in result


def test_resolve_subject_unknown_falls_back():
    from services.vocab_manager import _resolve_subject
    result = _resolve_subject("外星科")
    # 未知科目應回傳預設值（不能拋出 exception）
    assert isinstance(result, str) and len(result) > 0


# ── add_vocab_word & get_subject_vocab_path ───────────────────────────────────

def test_add_vocab_word_creates_file():
    from services.vocab_manager import add_vocab_word, get_subject_vocab_path
    add_vocab_word("測試詞語", dept="中文科")
    path = Path(get_subject_vocab_path("中文科"))   # 兼容 str 或 Path
    assert path.exists(), f"詞庫檔案應存在：{path}"
    assert "測試詞語" in path.read_text(encoding="utf-8")


def test_add_vocab_word_deduplication():
    from services.vocab_manager import add_vocab_word, get_subject_vocab_path
    add_vocab_word("重複詞", dept="歷史科")
    add_vocab_word("重複詞", dept="歷史科")
    path    = Path(get_subject_vocab_path("歷史科"))
    content = path.read_text(encoding="utf-8")
    assert content.count("重複詞") == 1, "相同詞語不應重複寫入"


def test_add_vocab_word_ignores_empty():
    from services.vocab_manager import add_vocab_word
    # 不應拋出 exception
    add_vocab_word("", dept="中文科")
    add_vocab_word("   ", dept="中文科")


def test_add_vocab_word_resolves_alias():
    from services.vocab_manager import add_vocab_word, get_subject_vocab_path, _resolve_subject
    add_vocab_word("別名詞", dept="通識科")
    resolved = _resolve_subject("通識科")
    path     = Path(get_subject_vocab_path(resolved))
    assert path.exists()
    assert "別名詞" in path.read_text(encoding="utf-8")


# ── load_all_vocab & cache ────────────────────────────────────────────────────

def test_load_all_vocab_contains_added_word():
    from services.vocab_manager import add_vocab_word, load_all_vocab
    add_vocab_word("快取詞", dept="數學科")
    vocab = load_all_vocab()
    assert "快取詞" in vocab


def test_load_all_vocab_cache_identity():
    from services.vocab_manager import add_vocab_word, load_all_vocab
    add_vocab_word("快取詞", dept="數學科")
    v1 = load_all_vocab()
    v2 = load_all_vocab()
    assert v1 is v2, "連續兩次呼叫應回傳同一快取物件"


def test_invalidate_cache_forces_reload():
    from services.vocab_manager import add_vocab_word, load_all_vocab, invalidate_vocab_cache
    add_vocab_word("原有詞", dept="數學科")
    v1 = load_all_vocab()
    invalidate_vocab_cache()
    add_vocab_word("新增詞", dept="數學科")
    v2 = load_all_vocab()
    assert "新增詞" in v2
    assert v1 is not v2


# ── bulk_save_correction_pairs & load_corrections ────────────────────────────

def test_bulk_save_and_load_corrections():
    from services.vocab_manager import bulk_save_correction_pairs, load_corrections
    saved = bulk_save_correction_pairs([("通過", "決議"), ("老是", "老師")])
    assert saved == 2
    corrs = load_corrections()
    assert corrs.get("通過") == "決議"
    assert corrs.get("老是") == "老師"


def test_bulk_save_deduplication():
    from services.vocab_manager import bulk_save_correction_pairs, load_corrections
    bulk_save_correction_pairs([("重複", "正確")])
    bulk_save_correction_pairs([("重複", "正確")])
    corrs = load_corrections()
    assert list(corrs.values()).count("正確") == 1


def test_bulk_save_returns_zero_on_empty():
    from services.vocab_manager import bulk_save_correction_pairs
    result = bulk_save_correction_pairs([])
    assert result == 0


# ── list_subject_vocabs ───────────────────────────────────────────────────────

def test_list_subject_vocabs_counts():
    from services.vocab_manager import add_vocab_word, list_subject_vocabs
    add_vocab_word("物理詞一", dept="物理科")
    add_vocab_word("物理詞二", dept="物理科")
    counts = list_subject_vocabs()
    assert counts.get("物理科", 0) >= 2


def test_list_subject_vocabs_empty_subject_has_zero():
    from services.vocab_manager import list_subject_vocabs
    counts = list_subject_vocabs()
    # 從未寫入的科目應為 0 或不存在於 dict（不應拋 exception）
    assert isinstance(counts, dict)