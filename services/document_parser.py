"""
Document Parser Service
Parses PDF / DOCX / TXT / CSV context documents.
Extracts keywords to inject into Whisper initial_prompt.
"""
import io
import pypdf
import docx
import pandas as pd
from keybert import KeyBERT
import yake

_kw_model = None


def _get_kw_model():
    global _kw_model
    if _kw_model is None:
        _kw_model = KeyBERT()
    return _kw_model


def parse_pdf(file_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            parts.append(text)
    return "\n".join(parts)


def parse_docx(file_bytes: bytes) -> str:
    d = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in d.paragraphs if p.text.strip())


def parse_txt(file_bytes: bytes) -> str:
    for enc in ("utf-8", "utf-16", "big5", "gb2312"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")


def parse_csv(file_bytes: bytes) -> str:
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
        return df.to_string(index=False)
    except Exception:
        return parse_txt(file_bytes)


def extract_keywords(text: str, top_n: int = 150) -> list:
    kw_model = _get_kw_model()
    seen = set()
    keywords = []

    try:
        kb = kw_model.extract_keywords(
            text[:10000],
            keyphrase_ngram_range=(1, 2),
            stop_words=None,
            top_n=top_n // 2,
        )
        for word, score in kb:
            if word not in seen:
                keywords.append({"word": word, "score": float(score)})
                seen.add(word)
    except Exception:
        pass

    try:
        ye = yake.KeywordExtractor(lan="zh", n=2, top=top_n // 2)
        for word, score in ye.extract_keywords(text[:10000]):
            if word not in seen:
                keywords.append({"word": word, "score": float(1 - score)})
                seen.add(word)
    except Exception:
        pass

    keywords.sort(key=lambda x: x["score"], reverse=True)
    return keywords[:top_n]


def build_initial_prompt(keywords: list) -> str:
    return ", ".join(kw["word"] for kw in keywords[:100])


def process_document(uploaded_file) -> dict:
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        raw_text = parse_pdf(file_bytes)
    elif filename.endswith((".docx", ".doc")):
        raw_text = parse_docx(file_bytes)
    elif filename.endswith(".csv"):
        raw_text = parse_csv(file_bytes)
    else:
        raw_text = parse_txt(file_bytes)

    keywords = extract_keywords(raw_text)
    prompt = build_initial_prompt(keywords)

    return {
        "filename": uploaded_file.name,
        "raw_text": raw_text,
        "keywords": keywords,
        "initial_prompt": prompt,
        "keyword_count": len(keywords),
    }
