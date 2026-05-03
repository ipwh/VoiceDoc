# 將以下全部內容追加至 core/pipeline_keywords.py 末尾

# ═══════════════════════════════════════════════════════════════════════════
# 以下三個函數追加至 core/pipeline_keywords.py 末尾
# v4.4：補全 extract_from_docs + build_context_prompt（pages/1 & pages/2 共用）
#        is_agenda_text（pages/1 & pages/2 統一議程辨識）
# ═══════════════════════════════════════════════════════════════════════════
from __future__ import annotations
import re as _re
from typing import List, Dict


def extract_from_docs(texts: list, top_k: int = 60) -> list:
    """從多份文件提取 TF-IDF 關鍵詞。

    Args:
        texts : 已讀取為字串的文件列表
        top_k : 返回前 k 個關鍵詞

    Returns:
        list of dict: [{"word": "...", "score": 0.xx}, ...]
        若 scikit-learn 未安裝，回退至簡單詞頻統計。
    """
    combined = "\n\n".join(t for t in texts if t)
    if not combined.strip():
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np

        vec   = TfidfVectorizer(
            max_features = top_k * 3,
            token_pattern = r"(?u)\b[\w\u4e00-\u9fff]{2,}\b",
            ngram_range  = (1, 2),
        )
        tfidf = vec.fit_transform([combined])
        names = vec.get_feature_names_out()
        scores = tfidf.toarray()[0]
        ranked = sorted(zip(names, scores), key=lambda x: -x[1])
        return [{"word": w, "score": round(float(s), 4)} for w, s in ranked[:top_k] if s > 0]

    except ImportError:
        # 回退：簡單字頻統計
        tokens = _re.findall(r"[\w\u4e00-\u9fff]{2,}", combined)
        freq: Dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
        ranked = sorted(freq.items(), key=lambda x: -x[1])[:top_k]
        max_f  = ranked[0][1] if ranked else 1
        return [{"word": w, "score": round(c / max_f, 4)} for w, c in ranked]


def build_context_prompt(
    manual_terms: list,
    keywords: list,
    max_chars: int = 800,
) -> str:
    """將人工術語 + TF-IDF 關鍵詞合併為 LLM context prompt 字串。

    Args:
        manual_terms : 用戶手動加入的術語列表（字串列表）
        keywords     : extract_from_docs() 的返回值
        max_chars    : 輸出字串最大長度

    Returns:
        str: 供 LLM prompt 使用的術語/關鍵詞字串
    """
    parts: List[str] = []

    # 人工術語優先
    for term in (manual_terms or []):
        t = str(term).strip()
        if t:
            parts.append(t)

    # TF-IDF 關鍵詞（排除警告標記）
    for kw in (keywords or []):
        w = kw.get("word", "").strip()
        if w and not w.startswith("⚠") and not w.startswith("（"):
            parts.append(w)

    # 去重、保序
    seen: set = set()
    unique: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    result = "、".join(unique)
    return result[:max_chars]


def is_agenda_text(text: str) -> bool:
    """偵測文字是否為會議議程格式（pages/1 & pages/2 統一使用）。

    判斷依據（任一條件成立即視為議程）：
      1. 包含議程標題關鍵詞（「議程」「Agenda」「會議事項」「討論事項」）
      2. 包含三個以上編號條目，且編號條目佔總行數比例 >= 30%
    """
    if not text or not text.strip():
        return False
    t = text.strip()
    if _re.search(r'議程|agenda|會議事項|討論事項', t, _re.IGNORECASE):
        return True
    numbered = _re.findall(
        r'(?m)^[\s]*(?:[一二三四五六七八九十百]+[、。．]|\d+[\.\、\s]|[IVXivx]+[\.\s])',
        t,
    )
    lines = [line for line in t.split("\n") if line.strip()]
    if len(numbered) >= 3 and lines and len(numbered) / len(lines) >= 0.3:
        return True
    return False

# 別名：等同 extract_from_docs
extract_from_documents = extract_from_docs   # noqa: F821


def build_prev_vocab(texts: list, top_k: int = 80) -> list:
    """從上年度紀錄建立詞庫（供 ui/layout.py sidebar 使用）。

    與 extract_from_docs 相同邏輯，但預設 top_k=80，
    並回傳純字串列表（方便詞庫儲存）。

    Args:
        texts : 已讀取為字串的文件列表
        top_k : 返回前 k 個詞彙

    Returns:
        list of str: 詞彙字串列表
    """
    kws = extract_from_docs(texts, top_k=top_k)
    return [kw["word"] for kw in kws if kw.get("word")]