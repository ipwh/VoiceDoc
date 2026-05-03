"""
Keyword Service — jieba + TF-IDF
改進：
  1. 啟動時自動載入內建香港學校詞庫（data/vocab_base.txt）
  2. 文件數限制 ≤ 10，文本截斷至 50,000 字符
  3. _load_jieba_userdict 只執行一次（_vocab_loaded flag）
"""
import re, os
from typing import List, Dict
from services.config import VOCAB_BASE_PATH

STOP_WORDS = set("""
的 了 和 是 就 都 而 及 與 著 或 一個 沒有 我們 你們 他們 在 有 這 那
學校 老師 同學 學生 會議 今天 今次 大家 各位 方面 情況 問題 工作 進行
需要 可以 認為 表示 提出 討論 通過 同意 決定 建議 報告 負責 跟進
""".split())

_vocab_loaded = False


def _load_jieba_userdict(extra_path: str = ""):
    """載入內建詞庫及用戶詞庫到 jieba（每次啟動只執行一次內建部分）。"""
    global _vocab_loaded
    try:
        import jieba
        if not _vocab_loaded and os.path.exists(VOCAB_BASE_PATH):
            jieba.load_userdict(VOCAB_BASE_PATH)
            _vocab_loaded = True
        if extra_path and os.path.exists(extra_path):
            jieba.load_userdict(extra_path)
    except Exception:
        pass


def _jieba_cut(text: str) -> list:
    _load_jieba_userdict()
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        return text.split()


def extract_keywords_tfidf(
    texts: List[str],
    top_k: int = 30,
    user_vocab_path: str = "",
) -> List[Dict]:
    """
    TF-IDF 關鍵詞提取。
    - 最多處理 10 個文件（超過靜默截斷，頁面層應提示用戶）
    - 文本總長度截斷至 50,000 字符
    - 自動載入內建詞庫
    """
    _load_jieba_userdict(user_vocab_path)

    if len(texts) > 10:
        texts = texts[:10]

    combined = " ".join(texts)
    if not combined.strip():
        return []

    truncated = False
    if len(combined) > 50000:
        combined  = combined[:50000]
        texts     = [combined]
        truncated = True

    if len(combined) < 300:
        return _yake_fallback(combined, top_k)

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        def tokenizer(text):
            tokens = _jieba_cut(text)
            return [
                t.strip() for t in tokens
                if t.strip()
                and len(t.strip()) >= 2
                and t.strip() not in STOP_WORDS
                and not re.match(r"^[\d\s\W]+$", t)
            ]

        vec  = TfidfVectorizer(
            tokenizer=tokenizer,
            token_pattern=None,
            ngram_range=(1, 2),
            max_features=500,
        )
        docs = texts if len(texts) > 1 else re.split(r"[。！？\n]", combined)
        docs = [d for d in docs if d.strip()]
        if len(docs) < 2:
            docs = docs + docs

        tfidf  = vec.fit_transform(docs)
        scores = tfidf.sum(axis=0).A1
        vocab  = vec.get_feature_names_out()
        pairs  = sorted(zip(vocab, scores), key=lambda x: -x[1])
        result = [{"word": w, "score": round(float(s), 4)} for w, s in pairs[:top_k]]
        if truncated:
            result = [{"word": "⚠ 文件過長，已分析前 50,000 字符", "score": 0}] + result
        return result
    except Exception:
        return _yake_fallback(combined, top_k)


def _yake_fallback(text: str, top_k: int) -> List[Dict]:
    try:
        import yake
        kw_extractor = yake.KeywordExtractor(lan="zh", n=2, top=top_k)
        kws = kw_extractor.extract_keywords(text)
        return [{"word": k, "score": round(1 - s, 4)} for k, s in kws]
    except Exception:
        return []


def merge_manual_terms(
    manual_terms: List[str],
    extracted_terms: List[Dict],
    max_len_chars: int = 250,
) -> str:
    seen, result = set(), []
    for t in manual_terms:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    for item in extracted_terms:
        w = item["word"].strip()
        if w and w not in seen and not w.startswith("⚠"):
            seen.add(w)
            result.append(w)
    return "，".join(result)[:max_len_chars]


def build_vocab_from_previous_minutes(
    file_contents: List[str],
    top_k: int = 80,
    user_vocab_path: str = "",
) -> List[Dict]:
    if not file_contents:
        return []
    return extract_keywords_tfidf(file_contents, top_k=top_k, user_vocab_path=user_vocab_path)


def save_user_vocab(terms: List[str], vocab_path: str):
    existing = set()
    if os.path.exists(vocab_path):
        with open(vocab_path, "r", encoding="utf-8") as fh:
            existing = {line.split()[0] for line in fh if line.strip()}
    with open(vocab_path, "a", encoding="utf-8") as fh:
        for t in terms:
            t = t.strip()
            if t and t not in existing:
                fh.write(f"{t} 100 n\n")
