"""
services/vocab_manager.py
科組詞庫管理 + 自動學習修正詞

正式整理版：
- SUBJECTS 使用標準科組名稱，value 對應 data/vocab/ 下的 txt 檔名
- SUBJECT_ALIASES 提供向後相容名稱解析
- 支援單一科組 / 全部科組詞庫讀取
- 支援批量新增詞語、自動去重、匯入/匯出場景
- 支援逐字稿修正配對學習
- 支援把已學習修正詞自動套用到文本 / segments
- 支援修正頻率統計
"""

from __future__ import annotations

import json
import re
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


# ── 路徑設定 ──────────────────────────────────────────────────────────────

_BASE_DIR = Path(__file__).resolve().parent.parent
VOCAB_DIR = _BASE_DIR / "data" / "vocab"
CORRECTIONS_FILE = _BASE_DIR / "data" / "corrections.json"

VOCAB_DIR.mkdir(parents=True, exist_ok=True)
CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── 科組定義（value = 檔名）───────────────────────────────────────────────

SUBJECTS: Dict[str, str] = {
    # 語文
    "中文科": "vocab_chinese.txt",
    "英文科": "vocab_english.txt",

    # 數學
    "數學科": "vocab_math.txt",

    # 人文與社會
    "公民與社會發展科（C&SD）": "vocab_csd.txt",
    "中國歷史科": "vocab_chinese_history.txt",
    "歷史科": "vocab_history.txt",
    "地理科": "vocab_geography.txt",
    "經濟科": "vocab_economics.txt",
    "公民、經濟與社會科（CES）": "vocab_ces.txt",
    "宗教科": "vocab_re.txt",

    # 科學
    "生物科": "vocab_biology.txt",
    "物理科": "vocab_physics.txt",
    "化學科": "vocab_chemistry.txt",
    "科學科（綜合）": "vocab_science.txt",

    # 商科
    "企業、會計與財務概論科（BAFS）": "vocab_bafs.txt",

    # 其他
    "資訊科技": "vocab_ict.txt",
    "體育科": "vocab_pe.txt",
    "音樂科": "vocab_music.txt",
    "視藝科": "vocab_va.txt",
    "旅遊與款待科": "vocab_tourism_hospitality.txt",

    # 行政 / 通用
    "學校行政": "vocab_admin.txt",
}


# ── 科組別名（舊名 / 簡稱 → 標準名稱）───────────────────────────────────

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
    "ICT": "資訊科技",
    "IT": "資訊科技",

    "行政": "學校行政",
    "通用": "學校行政",
    "校務": "學校行政",
}


# ── 快取 / 鎖 ───────────────────────────────────────────────────────────

_vocab_cache_all: Optional[Set[str]] = None
_vocab_cache_by_subject: Optional[Dict[str, List[str]]] = None
_cache_lock = threading.Lock()
_corr_lock = threading.Lock()


# ── 基本工具函式 ─────────────────────────────────────────────────────────

def _resolve_subject(name: str) -> str:
    """將輸入名稱（含別名）解析為 SUBJECTS 標準 key。"""
    raw = (name or "").strip()
    if raw in SUBJECTS:
        return raw
    canonical = SUBJECT_ALIASES.get(raw)
    if canonical and canonical in SUBJECTS:
        return canonical
    return "學校行政"


def _normalize_term(term: str) -> str:
    """清理單一詞語。"""
    t = (term or "").strip()
    t = t.replace("\u3000", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _fmt_ts(seconds: float) -> str:
    s = int(float(seconds or 0))
    return f"{s // 60:02d}:{s % 60:02d}"


def invalidate_vocab_cache() -> None:
    """清除詞庫快取。"""
    global _vocab_cache_all, _vocab_cache_by_subject
    with _cache_lock:
        _vocab_cache_all = None
        _vocab_cache_by_subject = None


def get_subject_vocab_path(subject: str) -> Path:
    """回傳科組詞庫檔案路徑，支援別名。"""
    std_name = _resolve_subject(subject)
    filename = SUBJECTS[std_name]
    return VOCAB_DIR / filename


def _read_vocab_file(path: Path) -> Set[str]:
    """讀取詞庫檔案，忽略空行與 # 註解。"""
    words: Set[str] = set()
    if not path.exists():
        return words

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            word = _normalize_term(line.split()[0])
            if word:
                words.add(word)
    return words


def _write_vocab_file(path: Path, words: Iterable[str]) -> None:
    """覆寫整個詞庫檔案。"""
    cleaned = sorted({_normalize_term(w) for w in words if _normalize_term(w)})
    with path.open("w", encoding="utf-8") as f:
        for w in cleaned:
            f.write(w + "\n")


# ── 詞庫讀取 ────────────────────────────────────────────────────────────

def load_all_vocab() -> Set[str]:
    """
    載入全部科組詞庫，回傳全系統詞語集合。
    給 ASR prompt、推薦過濾等用途。
    """
    global _vocab_cache_all

    with _cache_lock:
        if _vocab_cache_all is not None:
            return _vocab_cache_all

        words: Set[str] = set()
        for filename in SUBJECTS.values():
            path = VOCAB_DIR / filename
            words |= _read_vocab_file(path)

        _vocab_cache_all = words
        return _vocab_cache_all


def load_subject_vocab(subject: str) -> List[str]:
    """載入單一科組詞庫，回傳排序後詞語列表。"""
    path = get_subject_vocab_path(subject)
    return sorted(_read_vocab_file(path))


def load_all_vocab_by_subject() -> Dict[str, List[str]]:
    """載入所有科組詞庫，回傳 {科組: [詞語...]}。"""
    global _vocab_cache_by_subject

    with _cache_lock:
        if _vocab_cache_by_subject is not None:
            return _vocab_cache_by_subject

        out: Dict[str, List[str]] = {}
        for subject in SUBJECTS.keys():
            out[subject] = load_subject_vocab(subject)

        _vocab_cache_by_subject = out
        return _vocab_cache_by_subject


def list_subject_vocabs() -> Dict[str, int]:
    """回傳各科組詞語數量。"""
    return {subject: len(load_subject_vocab(subject)) for subject in SUBJECTS.keys()}


# ── 詞庫寫入 ────────────────────────────────────────────────────────────

def add_subject_terms(subject: str, terms: List[str]) -> int:
    """
    批量加入詞語到指定科組詞庫。
    會自動去重，並跳過空字串。
    """
    path = get_subject_vocab_path(subject)
    existing = _read_vocab_file(path)

    cleaned: List[str] = []
    seen_new: Set[str] = set()

    for term in terms:
        t = _normalize_term(term)
        if not t:
            continue
        if t in existing or t in seen_new:
            continue
        seen_new.add(t)
        cleaned.append(t)

    if not cleaned:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for term in cleaned:
            f.write(term + "\n")

    invalidate_vocab_cache()
    return len(cleaned)


def add_vocab_word(word: str, dept: str = "學校行政") -> None:
    """
    加入單一詞語至指定科組詞庫。
    供 page1 推薦詞按鈕直接呼叫。
    """
    w = _normalize_term(word)
    if not w:
        return
    add_subject_terms(dept, [w])


def remove_subject_term(subject: str, term: str) -> bool:
    """由指定科組詞庫移除詞語。"""
    path = get_subject_vocab_path(subject)
    existing = _read_vocab_file(path)
    t = _normalize_term(term)

    if t not in existing:
        return False

    existing.remove(t)
    _write_vocab_file(path, existing)
    invalidate_vocab_cache()
    return True


def replace_subject_vocab(subject: str, words: Iterable[str]) -> int:
    """
    以整批詞語覆蓋指定科組詞庫。
    主要供匯入 / 重建詞庫時使用。
    """
    path = get_subject_vocab_path(subject)
    cleaned = {_normalize_term(w) for w in words if _normalize_term(w)}
    _write_vocab_file(path, cleaned)
    invalidate_vocab_cache()
    return len(cleaned)


# ── 修正詞 JSON 管理 ─────────────────────────────────────────────────────

def _load_corrections_data() -> dict:
    """
    載入修正詞資料。
    結構：
    {
      "corrections": {原詞: 修正詞},
      "counts": {原詞: 套用次數}
    }
    """
    if not CORRECTIONS_FILE.exists():
        return {"corrections": {}, "counts": {}}

    try:
        with CORRECTIONS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"corrections": {}, "counts": {}}

        data.setdefault("corrections", {})
        data.setdefault("counts", {})
        if not isinstance(data["corrections"], dict):
            data["corrections"] = {}
        if not isinstance(data["counts"], dict):
            data["counts"] = {}

        return data

    except (json.JSONDecodeError, OSError):
        return {"corrections": {}, "counts": {}}


def _save_corrections_data(data: dict) -> None:
    """線程安全寫回 corrections.json。"""
    with _corr_lock:
        with CORRECTIONS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def load_corrections() -> Dict[str, str]:
    """載入所有修正詞配對。"""
    data = _load_corrections_data()
    return {str(k): str(v) for k, v in data.get("corrections", {}).items()}


def save_correction_pair(original: str, corrected: str) -> None:
    """儲存單一修正詞配對。"""
    orig = _normalize_term(original)
    corr = _normalize_term(corrected)

    if not orig or not corr or orig == corr:
        return

    data = _load_corrections_data()
    data["corrections"][orig] = corr
    data.setdefault("counts", {}).setdefault(orig, 0)
    _save_corrections_data(data)


def bulk_save_correction_pairs(pairs: List[Tuple[str, str]]) -> int:
    """
    批量儲存修正配對。
    回傳實際寫入數量。
    """
    if not pairs:
        return 0

    data = _load_corrections_data()
    saved = 0

    for orig, corr in pairs:
        o = _normalize_term(orig)
        c = _normalize_term(corr)
        if not o or not c or o == c:
            continue
        data["corrections"][o] = c
        data.setdefault("counts", {}).setdefault(o, 0)
        saved += 1

    if saved > 0:
        _save_corrections_data(data)

    return saved


def delete_correction_pair(original: str) -> bool:
    """刪除單一修正詞配對及其統計。"""
    orig = _normalize_term(original)
    if not orig:
        return False

    data = _load_corrections_data()
    existed = False

    if orig in data.get("corrections", {}):
        data["corrections"].pop(orig, None)
        existed = True

    if orig in data.get("counts", {}):
        data["counts"].pop(orig, None)

    if existed:
        _save_corrections_data(data)

    return existed


def clear_all_corrections(keep_counts: bool = False) -> None:
    """清除所有修正詞；可選擇保留 counts。"""
    data = _load_corrections_data()
    data["corrections"] = {}
    if not keep_counts:
        data["counts"] = {}
    _save_corrections_data(data)


def clear_all_correction_counts() -> None:
    """清除所有修正套用次數統計，但保留修正詞配對。"""
    data = _load_corrections_data()
    data["counts"] = {}
    _save_corrections_data(data)


def get_corrections_count() -> int:
    """回傳已學習修正詞配對數量。"""
    return len(load_corrections())


def get_correction_stats(top_n: int = 30) -> List[dict]:
    """
    回傳修正頻率統計，依 count 由高至低排序。
    每項格式：
    {"original": str, "corrected": str, "count": int}
    """
    data = _load_corrections_data()
    corrs = data.get("corrections", {})
    counts = data.get("counts", {})

    stats = []
    for orig, corr in corrs.items():
        stats.append({
            "original": str(orig),
            "corrected": str(corr),
            "count": int(counts.get(orig, 0)),
        })

    stats.sort(key=lambda x: (-x["count"], x["original"]))
    return stats[: int(top_n)]


# ── 修正詞抽取 / 套用 ───────────────────────────────────────────────────

def extract_correction_pairs(original_text: str, corrected_text: str) -> List[Tuple[str, str]]:
    """
    比較修正前後全文，抽取詞語級修正配對。

    規則：
    - 只處理 replace 區段
    - 避免過長片段，減少整句誤收錄
    """
    orig_words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9&\-/]+", original_text or "")
    corr_words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9&\-/]+", corrected_text or "")

    if not orig_words or not corr_words:
        return []

    matcher = SequenceMatcher(None, orig_words, corr_words)
    pairs: List[Tuple[str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace":
            continue

        o_chunk = "".join(orig_words[i1:i2]).strip()
        c_chunk = "".join(corr_words[j1:j2]).strip()

        if not o_chunk or not c_chunk:
            continue
        if o_chunk == c_chunk:
            continue
        if len(o_chunk) > 20 or len(c_chunk) > 20:
            continue

        pairs.append((o_chunk, c_chunk))

    deduped: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for p in pairs:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    return deduped


def apply_corrections_to_text(text: str, record_counts: bool = True) -> str:
    """
    把已學習修正詞套用到文本。
    會按原詞長度由長至短替換，減少短詞覆蓋長詞問題。
    """
    if not text:
        return text

    data = _load_corrections_data()
    corrections = data.get("corrections", {})
    if not corrections:
        return text

    result = str(text)
    touched: Dict[str, int] = {}

    for orig, corr in sorted(corrections.items(), key=lambda x: -len(str(x[0]))):
        o = _normalize_term(str(orig))
        c = _normalize_term(str(corr))

        if not o or not c or o == c:
            continue

        hit = result.count(o)
        if hit <= 0:
            continue

        result = result.replace(o, c)
        touched[o] = touched.get(o, 0) + hit

    if record_counts and touched:
        counts = data.setdefault("counts", {})
        for orig, n in touched.items():
            counts[orig] = int(counts.get(orig, 0)) + int(n)
        _save_corrections_data(data)

    return result


def apply_corrections_to_segments(segments: List[dict], record_counts: bool = True) -> List[dict]:
    """
    把已學習修正詞套用到逐字稿 segments。
    """
    if not segments:
        return []

    out: List[dict] = []
    for seg in segments:
        item = dict(seg)
        item["text"] = apply_corrections_to_text(str(item.get("text", "")), record_counts=record_counts)
        out.append(item)
    return out


def rebuild_full_text_from_segments(segments: List[dict]) -> str:
    """
    由 segments 重建 full_text。
    如有 speaker，會保留 speaker 前綴。
    """
    lines: List[str] = []

    for s in segments or []:
        start = s.get("start", 0)
        end = s.get("end", 0)
        text = str(s.get("text", "")).strip()
        speaker = str(s.get("speaker", "")).strip()

        prefix = f"[{_fmt_ts(start)}–{_fmt_ts(end)}] "
        if speaker:
            prefix += f"{speaker}："

        lines.append(prefix + text)

    return "\n".join(lines)


def apply_corrections_to_transcript(transcript: dict, record_counts: bool = True) -> dict:
    """
    把修正詞套用到整份 transcript dict。
    若有 segments，優先修正 segments 並重建 full_text。
    """
    if not transcript or not isinstance(transcript, dict):
        return transcript

    out = dict(transcript)
    segs = out.get("segments") or []

    if segs:
        new_segs = apply_corrections_to_segments(segs, record_counts=record_counts)
        out["segments"] = new_segs
        out["full_text"] = rebuild_full_text_from_segments(new_segs)
        return out

    out["full_text"] = apply_corrections_to_text(str(out.get("full_text", "")), record_counts=record_counts)
    return out