# services/privacy_guard.py
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

_HK_PII_PATTERNS: Dict[str, Tuple[str, str]] = {
    "hkid":       (r"\b[A-Z]{1,2}\d{6}\(?[\dA]\)?\b",                       "身份證號碼"),
    "phone":      (r"(?:\+?852[\s\-]?)?[2-9]\d{3}[\s\-]?\d{4}\b",          "電話號碼"),
    "email":      (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",  "電郵地址"),
    "student_id": (r"\b\d{6,8}\b",                                               "疑似學號"),
}

_STUDENT_CONTEXT_KW = frozenset([
    "學生", "同學", "學號", "編號", "班號", "訓導", "輔導", "個案", "跟進學生", "家長"
])

_NON_STUDENT_NUMBERS = frozenset(["2024", "2025", "2026", "2027"])


def _is_student_id_context(text: str, start: int, end: int) -> bool:
    num_str = text[start:end]
    if num_str in _NON_STUDENT_NUMBERS:
        return False
    ctx = text[max(0, start - 30): min(len(text), end + 10)]
    return any(kw in ctx for kw in _STUDENT_CONTEXT_KW)


def detect_pii(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []

    findings: List[Dict[str, Any]] = []
    for pii_type, (pattern, label) in _HK_PII_PATTERNS.items():
        for m in re.finditer(pattern, text):
            val = m.group(0)
            s, e = m.start(), m.end()

            if pii_type == "student_id":
                if val in _NON_STUDENT_NUMBERS:
                    continue
                if not _is_student_id_context(text, s, e):
                    continue
                conf = "medium"
            else:
                conf = "high"

            findings.append({
                "type":       pii_type,
                "label":      label,
                "value":      val,
                "start":      s,
                "end":        e,
                "confidence": conf,
            })

    # 去重
    uniq: Dict[tuple, Dict[str, Any]] = {}
    for f in findings:
        key = (f["type"], f["value"], f["start"], f["end"])
        uniq[key] = f
    return list(uniq.values())


def pii_summary(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return "無"
    cnt: Dict[str, int] = {}
    label_map: Dict[str, str] = {}
    for f in findings:
        t = f.get("type", "unknown")
        cnt[t] = cnt.get(t, 0) + 1
        label_map[t] = f.get("label", t)
    parts = [
        f"{label_map[t]} {n}"
        for t, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))
    ]
    return "、".join(parts)


def mask_pii(
    text: str,
    findings: List[Dict[str, Any]] | None = None,
) -> Tuple[str, Dict[str, str]]:
    if not text or not findings:
        return text, {}

    findings_sorted = sorted(findings, key=lambda f: f.get("start", 0), reverse=True)
    restore_map: Dict[str, str] = {}
    seq: Dict[str, int] = {}
    out = text

    for f in findings_sorted:
        t = (f.get("type") or "pii").upper()
        seq[t] = seq.get(t, 0) + 1
        token = f"[{t}_{seq[t]}]"
        restore_map[token] = f.get("value", "")

        s = int(f.get("start", 0))
        e = int(f.get("end", 0))
        if 0 <= s < e <= len(out):
            out = out[:s] + token + out[e:]

    return out, restore_map
