"""
services/vocab_manager.py
科組詞庫管理 + 自動學習修正詞 + 自訂科組

重構重點：
- 保留既有內建科組與別名
- 新增 custom_subjects.json，支援用家自行建立科組
- 所有 subject 相關查詢改為動態合併「內建 + 自訂」
- 保留原有函式名稱，盡量向後相容
"""

from __future__ import annotations

import json
import re
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent.parent
DATA_DIR = _BASE_DIR / "data"
VOCAB_DIR = DATA_DIR / "vocab"
CORRECTIONS_FILE = DATA_DIR / "corrections.json"
CUSTOM_SUBJECTS_FILE = DATA_DIR / "custom_subjects.json"

VOCAB_DIR.mkdir(parents=True, exist_ok=True)
CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── 內建科目定義（value = 檔名）───────────────────────────────────────────────
BUILTIN_SUBJECTS: Dict[str, str] = {
    # 語文科
    "中文科": "vocab_chinese.txt",
    "英文科": "vocab_english.txt",
    # 數學科
    "數學科": "vocab_math.txt",
    # 人文與社會科學
    "公民與社會發展科（C&SD）": "vocab_csd.txt",
    "中國歷史科": "vocab_chinese_history.txt",
    "歷史科": "vocab_history.txt",
    "地理科": "vocab_geography.txt",
    "經濟科": "vocab_economics.txt",
    "公民、經濟與社會科（CES）": "vocab_ces.txt",
    "宗教科": "vocab_re.txt",
    # 科學科
    "生物科": "vocab_biology.txt",
    "物理科": "vocab_physics.txt",
    "化學科": "vocab_chemistry.txt",
    "科學科（綜合）": "vocab_science.txt",
    # 商科
    "企業、會計與財務概論科（BAFS）": "vocab_bafs.txt",
    # 其他科目
    "資訊科技": "vocab_ict.txt",
    "體育科": "vocab_pe.txt",
    "音樂科": "vocab_music.txt",
    "視藝科": "vocab_va.txt",
    # 行政 / 通用
    "學校行政": "vocab_admin.txt",
}

# ── 科目別名對照（舊名稱 / 簡稱 → 標準名稱）─────────────────────────────────
SUBJECT_ALIASES: Dict[str, str] = {
    "通識科": "公民與社會發展科（C&SD）",
    "通識/公社": "公民與社會發展科（C&SD）",
    "公社科": "公民與社會發展科（C&SD）",
    "C&SD": "公民與社會發展科（C&SD）",
    "BAFS": "企業、會計與財務概論科（BAFS）",
    "CES": "公民、經濟與社會科（CES）",
    "中史科": "中國歷史科",
    "中史": "中國歷史科",
    "生物": "生物科",
    "物理": "物理科",
    "化學": "化學科",
    "經濟": "經濟科",
    "科學科": "科學科（綜合）",
}

# ── 線程鎖 + 快取 ────────────────────────────────────────────────────────────
_vocab_cache: Optional[Set[str]] = None
_cache_lock = threading.Lock()
_corr_lock = threading.Lock()
_subject_lock = threading.Lock()


# ── 自訂科組工具 ──────────────────────────────────────────────────────────────
def _slugify_subject(name: str) -> str:
    """
    將科組名稱轉為安全檔名片段。
    保留中英文與數字，其餘轉為底線。
    """
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (name or "").strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "custom_subject"


def _load_custom_subjects() -> Dict[str, str]:
    """
    載入自訂科組設定：
    {
        "升學及就業輔導組": "vocab_custom_升學及就業輔導組.txt",
        ...
    }
    """
    if not CUSTOM_SUBJECTS_FILE.exists():
        return {}
    try:
        with CUSTOM_SUBJECTS_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_custom_subjects(data: Dict[str, str]) -> None:
    with _subject_lock:
        with CUSTOM_SUBJECTS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_subjects() -> Dict[str, str]:
    """
    回傳所有科組（內建 + 自訂）。
    """
    merged = dict(BUILTIN_SUBJECTS)
    merged.update(_load_custom_subjects())
    return merged


def refresh_subjects() -> Dict[str, str]:
    """
    重新整理全域 SUBJECTS 快照，供舊代碼相容使用。
    """
    global SUBJECTS
    SUBJECTS = get_all_subjects()
    return SUBJECTS


def list_custom_subjects() -> Dict[str, str]:
    """
    回傳所有自訂科組。
    """
    return _load_custom_subjects()


def is_custom_subject(name: str) -> bool:
    return name in _load_custom_subjects()


def create_custom_subject(name: str) -> str:
    """
    建立自訂科組並建立對應詞庫檔案。
    若已存在則直接回傳原名稱。
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("科組名稱不可為空白")

    subjects = get_all_subjects()
    if name in subjects:
        return name

    custom = _load_custom_subjects()
    slug = _slugify_subject(name)
    filename = f"vocab_custom_{slug}.txt"

    existing_files = set(BUILTIN_SUBJECTS.values()) | set(custom.values())
    if filename in existing_files:
        i = 2
        while True:
            alt = f"vocab_custom_{slug}_{i}.txt"
            if alt not in existing_files:
                filename = alt
                break
            i += 1

    custom[name] = filename
    _save_custom_subjects(custom)
    (VOCAB_DIR / filename).touch(exist_ok=True)
    refresh_subjects()
    invalidate_vocab_cache()
    return name


def delete_custom_subject(name: str, delete_vocab_file: bool = False) -> bool:
    """
    刪除自訂科組設定；可選擇是否連詞庫檔一併刪除。
    不允許刪除內建科組。
    """
    name = (name or "").strip()
    custom = _load_custom_subjects()
    if name not in custom:
        return False

    filename = custom.pop(name)
    _save_custom_subjects(custom)

    if delete_vocab_file:
        path = VOCAB_DIR / filename
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    refresh_subjects()
    invalidate_vocab_cache()
    return True


# 舊代碼相容：保留 SUBJECTS 全域名稱
SUBJECTS: Dict[str, str] = get_all_subjects()


# ── 科組工具 ──────────────────────────────────────────────────────────────────
def _resolve_subject(name: str) -> str:
    """
    將輸入名稱（含別名）解析為標準科組名稱。

    解析順序：
    1. 直接命中所有科組（內建 + 自訂）
    2. 查找 SUBJECT_ALIASES
    3. 回退至「學校行政」
    """
    subjects = get_all_subjects()

    if name in subjects:
        return name

    canonical = SUBJECT_ALIASES.get(name)
    if canonical and canonical in subjects:
        return canonical

    return "學校行政"


def invalidate_vocab_cache() -> None:
    """
    清除詞庫快取，下次呼叫 load_all_vocab() 時重新載入。
    """
    global _vocab_cache
    with _cache_lock:
        _vocab_cache = None


def get_subject_vocab_path(subject: str) -> Path:
    """
    回傳科組詞庫的完整路徑，支援別名與自訂科組。
    """
    subjects = get_all_subjects()
    std_name = _resolve_subject(subject)
    filename = subjects[std_name]
    return VOCAB_DIR / filename


def _read_vocab_file(path: Path) -> Set[str]:
    """
    讀取詞庫檔案，回傳詞語集合（忽略空行與 # 註解）。
    每行只取第一個 token，與現有匯出邏輯一致。
    """
    words: Set[str] = set()
    if not path.exists():
        return words

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                words.add(line.split()[0])
    return words


def load_all_vocab() -> Set[str]:
    """
    載入所有詞庫檔案（內建 + 自訂），回傳詞語集合（帶快取）。
    """
    global _vocab_cache
    with _cache_lock:
        if _vocab_cache is not None:
            return _vocab_cache

        words: Set[str] = set()
        subjects = get_all_subjects()
        for filename in subjects.values():
            words |= _read_vocab_file(VOCAB_DIR / filename)

        _vocab_cache = words
        return _vocab_cache


def list_subject_vocabs() -> Dict[str, int]:
    """
    回傳各科組詞語數量 {科組名稱: 詞數}。
    """
    subjects = get_all_subjects()
    return {
        subject: len(_read_vocab_file(VOCAB_DIR / filename))
        for subject, filename in subjects.items()
    }


def add_subject_terms(subject: str, terms: List[str]) -> int:
    """
    批量加入詞語至科組詞庫。

    Args:
        subject: 科組名稱（支援別名 / 自訂科組）
        terms: 詞語列表

    Returns:
        實際新增數量（已去重）
    """
    path = get_subject_vocab_path(subject)
    existing = _read_vocab_file(path)

    new_terms = [t.strip() for t in terms if t and t.strip() not in existing]
    if not new_terms:
        return 0

    with path.open("a", encoding="utf-8") as f:
        for term in new_terms:
            f.write(term + "\n")

    invalidate_vocab_cache()
    return len(new_terms)


def add_vocab_word(word: str, dept: str = "學校行政") -> None:
    """
    加入單一詞語至指定科組詞庫。
    """
    word = (word or "").strip()
    if not word:
        return
    add_subject_terms(dept, [word])


# ── 修正詞管理 ────────────────────────────────────────────────────────────────
def _load_corrections_data() -> dict:
    """
    從 JSON 載入修正詞資料，結構：
    {
        "corrections": {},
        "counts": {}
    }
    """
    if not CORRECTIONS_FILE.exists():
        return {"corrections": {}, "counts": {}}

    try:
        with CORRECTIONS_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("corrections", {})
        data.setdefault("counts", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"corrections": {}, "counts": {}}


def _save_corrections_data(data: dict) -> None:
    """
    將修正詞資料寫回 JSON（線程安全）。
    """
    with _corr_lock:
        with CORRECTIONS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def load_corrections() -> Dict[str, str]:
    """
    載入所有修正詞配對 {原詞: 修正詞}。
    """
    return _load_corrections_data().get("corrections", {})


def save_correction_pair(original: str, corrected: str) -> None:
    """
    儲存單一修正詞配對。
    保留既有 counts，不主動累加。
    """
    data = _load_corrections_data()
    data["corrections"][original] = corrected
    _save_corrections_data(data)


def get_corrections_count() -> int:
    """
    回傳已學習修正詞配對總數。
    """
    return len(load_corrections())


def get_correction_stats(top_n: int = 30) -> List[dict]:
    """
    回傳修正頻率統計，按套用次數降序排列。

    Returns:
        List of {"original": str, "corrected": str, "count": int}
    """
    data = _load_corrections_data()
    counts = data.get("counts", {})
    corrs = data.get("corrections", {})

    stats = [
        {"original": orig, "corrected": corr, "count": counts.get(orig, 0)}
        for orig, corr in corrs.items()
    ]
    stats.sort(key=lambda x: -x["count"])
    return stats[:top_n]


def extract_correction_pairs(
    original_text: str, corrected_text: str
) -> List[Tuple[str, str]]:
    """
    比較前後文本，提取詞語級修正配對。
    """
    orig_words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", original_text)
    corr_words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", corrected_text)

    if not orig_words or not corr_words:
        return []

    matcher = SequenceMatcher(None, orig_words, corr_words)
    pairs: List[Tuple[str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            o_chunk = "".join(orig_words[i1:i2])
            c_chunk = "".join(corr_words[j1:j2])
            if o_chunk != c_chunk and 1 <= len(o_chunk) <= 10:
                pairs.append((o_chunk, c_chunk))

    return pairs


def bulk_save_correction_pairs(pairs: List[Tuple[str, str]]) -> int:
    """
    批量儲存修正配對，回傳實際儲存數量。
    """
    if not pairs:
        return 0

    data = _load_corrections_data()
    saved = 0

    for orig, corr in pairs:
        if orig and corr and orig != corr:
            data["corrections"][orig] = corr
            saved += 1

    if saved:
        _save_corrections_data(data)

    return saved