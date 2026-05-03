# services/vocab_recommender.py
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List, Set, Tuple

_STOP_WORDS = frozenset([
    "咁", "囉", "喺", "係", "唔", "佢", "我", "你", "嘅", "呢", "嗰", "啲",
    "但係", "所以", "因為", "然後", "即係",
    "我們", "你們", "他們", "就是", "可以", "應該",
    "會議", "討論", "報告", "同意", "通過", "提議", "建議", "主席", "老師",
    "的", "了", "在", "和", "與", "或", "也", "都", "就", "這", "那",
    "一個", "一些", "有些", "沒有", "非常", "已經",
    "今日", "今天", "昨日", "昨天", "明天", "今年", "明年",
    "大家", "同事", "學生", "家長", "學校", "老師們",
])

_KNOWN_ABBREVS = frozenset([
    "DSE", "HKDSE", "STEM", "STEAM", "SEN", "SBA", "ECA", "PTA",
    "EDB", "ICT", "NSS", "QEF", "CDC", "PSHE", "PE", "IT",
    "AI", "A1", "A2", "A3", "K1", "K2", "K3",
])

_MIN_CN_LEN = 2
_MAX_CN_LEN = 8
_MIN_EN_LEN = 3
_MAX_EN_LEN = 24


def _is_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s))


def _clean_token(token: str) -> str:
    if not token:
        return ""
    t = str(token).strip()
    t = re.sub(r"^[\s\-–—_,.;:()（）【】「」『』、，。]+", "", t)
    t = re.sub(r"[\s\-–—_,.;:()（）【】「」『』、，。]+$", "", t)
    return t.strip()


def normalize_existing_vocab(existing_vocab: Iterable[str] | None) -> Set[str]:
    out: Set[str] = set()
    if not existing_vocab:
        return out
    for w in existing_vocab:
        t = _clean_token(str(w))
        if t:
            out.add(t)
            out.add(t.lower())
    return out


def _tokenize_en(text: str) -> List[str]:
    return re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-/&]{2,}\b", text or "")


def _tokenize_cn(text: str) -> List[str]:
    if not text:
        return []

    try:
        import jieba
        try:
            jieba.setLogLevel(60)
        except Exception:
            pass

        words = []
        for w in jieba.cut(text):
            w = _clean_token(w)
            if _is_cjk(w) and _MIN_CN_LEN <= len(w) <= _MAX_CN_LEN:
                words.append(w)
        return words

    except Exception:
        cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        cn: List[str] = []
        for chunk in cjk_chunks:
            L = len(chunk)
            for n in range(_MIN_CN_LEN, min(_MAX_CN_LEN, L) + 1):
                for i in range(0, L - n + 1):
                    cn.append(chunk[i:i + n])
        return cn


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    en = _tokenize_en(text)
    cn = _tokenize_cn(text)
    return en + cn


def _is_candidate(word: str) -> bool:
    w = _clean_token(word)
    if not w:
        return False

    if w in _STOP_WORDS or w.lower() in {x.lower() for x in _STOP_WORDS}:
        return False

    if w.upper() in _KNOWN_ABBREVS:
        return False

    if re.fullmatch(r"\d+", w):
        return False

    if re.fullmatch(r"[A-Za-z]\d+", w):
        return False

    if _is_cjk(w):
        return _MIN_CN_LEN <= len(w) <= _MAX_CN_LEN

    if re.fullmatch(r"[A-Za-z0-9\-/&]+", w):
        return _MIN_EN_LEN <= len(w) <= _MAX_EN_LEN

    return False


def pick_min_freq_by_length(text: str) -> int:
    n = len(text or "")
    if n < 800:
        return 2
    if n < 3000:
        return 3
    return 4


def recommend_vocab(
    text: str,
    existing_vocab: Iterable[str] | None = None,
    min_freq: int = 2,
    top_n: int = 20,
) -> List[Tuple[str, int]]:
    if not text:
        return []

    existing = normalize_existing_vocab(existing_vocab)
    tokens = [_clean_token(t) for t in _tokenize(text)]
    tokens = [t for t in tokens if _is_candidate(t)]

    if not tokens:
        return []

    c = Counter(tokens)
    items: List[Tuple[str, int]] = []

    for w, n in c.items():
        if n < int(min_freq):
            continue
        if w in existing or w.lower() in existing:
            continue
        items.append((w, n))

    items.sort(key=lambda x: (-x[1], -len(x[0]), x[0].lower()))
    return items[: int(top_n)]


def recommend_vocab_words(
    text: str,
    existing_vocab: Iterable[str] | None = None,
    min_freq: int | None = None,
    top_n: int = 20,
) -> List[str]:
    mf = pick_min_freq_by_length(text) if min_freq is None else int(min_freq)
    return [w for w, _ in recommend_vocab(text, existing_vocab=existing_vocab, min_freq=mf, top_n=top_n)]