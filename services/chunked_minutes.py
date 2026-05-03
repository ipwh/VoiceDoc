"""
services/chunked_minutes.py
v2.2 — 2026-05-02
修正：split_by_agenda() 的 break 改為 continue，確保議程模式下所有議項均被處理。
"""
from __future__ import annotations
import logging
import re
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_CHUNK_CHARS  = 2500
_MAX_RETRIES      = 3
_RETRY_BASE_DELAY = 2


# ════════════════════════════════════════════════════════════════════════════
# 1. 分段邏輯
# ════════════════════════════════════════════════════════════════════════════

def split_by_agenda(transcript_text: str, agenda_items: List[str]) -> List[Dict]:
    """按議程項分段（關鍵詞比對）。

    修正（v2.2）：找不到下一議項分隔點時改為 continue 而非 break，
    確保後續所有議項均被正確處理。
    """
    chunks: List[Dict] = []
    remaining = transcript_text

    for i, item in enumerate(agenda_items):
        if not remaining.strip():
            continue
        next_item = agenda_items[i + 1] if i + 1 < len(agenda_items) else None
        if next_item:
            idx = remaining.find(next_item[:6])
            if idx > 0:
                chunks.append({"title": item, "text": remaining[:idx].strip()})
                remaining = remaining[idx:]
                continue
            # 找不到分隔點：歸入當前議項，繼續迴圈（✅ 修正：不 break）
            chunks.append({"title": item, "text": remaining.strip()})
            remaining = ""
            continue
        else:
            chunks.append({"title": item, "text": remaining.strip()})
            remaining = ""

    if remaining.strip():
        chunks.append({"title": f"其他（第 {len(chunks)+1} 段）", "text": remaining.strip()})

    valid = [c for c in chunks if c["text"]]
    if not valid:
        logger.warning("split_by_agenda：所有議項均無對應文本，退回全文模式")
        return [{"title": "全文", "text": transcript_text}]
    logger.debug("split_by_agenda：%d 議項 → %d 段", len(agenda_items), len(valid))
    return valid


def split_by_paragraph(transcript_text: str) -> List[Dict]:
    """按段落分段，每段不超過 _MAX_CHUNK_CHARS 字。
    策略：雙換行 → 單換行 → 固定字數強制切割。
    """
    SEP2 = "\n\n"
    SEP1 = "\n"

    def _do_split(paras: list) -> list:
        chunks, cur, cur_len = [], [], 0
        for p in paras:
            if cur and cur_len + len(p) > _MAX_CHUNK_CHARS:
                chunks.append(SEP2.join(cur))
                cur, cur_len = [], 0
            cur.append(p)
            cur_len += len(p)
        if cur:
            chunks.append(SEP2.join(cur))
        return chunks

    paras  = [p.strip() for p in re.split(r"\n{2,}", transcript_text) if p.strip()]
    chunks = _do_split(paras)

    if len(chunks) <= 1 and len(transcript_text) > _MAX_CHUNK_CHARS:
        paras  = [p.strip() for p in transcript_text.split(SEP1) if p.strip()]
        chunks = _do_split(paras)

    if len(chunks) <= 1 and len(transcript_text) > _MAX_CHUNK_CHARS:
        chunks = [
            transcript_text[i:i + _MAX_CHUNK_CHARS].strip()
            for i in range(0, len(transcript_text), _MAX_CHUNK_CHARS)
            if transcript_text[i:i + _MAX_CHUNK_CHARS].strip()
        ]

    result = [{"title": f"第 {i+1} 段", "text": t} for i, t in enumerate(chunks)]
    return result or [{"title": "全文", "text": transcript_text}]


# ════════════════════════════════════════════════════════════════════════════
# 2. 主函數
# ════════════════════════════════════════════════════════════════════════════

def generate_chunked_minutes(
    transcript_text: str,
    opts: dict,
    agenda_items: Optional[List[str]] = None,
    progress_callback=None,
) -> Dict:
    """將長逐字稿分段，循序生成各段會議紀錄，最後合併為標準格式。"""
    if agenda_items and len(agenda_items) >= 2:
        chunks = split_by_agenda(transcript_text, agenda_items)
    else:
        chunks = split_by_paragraph(transcript_text)

    total = len(chunks)
    if progress_callback:
        progress_callback(0.0, f"📄 逐字稿已分為 {total} 段，開始循序生成…")

    results: List[Dict] = []
    failed_idxs: List[int] = []

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(i / total, f"⚙️ 正在生成第 {i+1}/{total} 段：{chunk['title']}…")

        chunk_result = _generate_one_chunk_with_retry(
            chunk_text=chunk["text"], chunk_title=chunk["title"],
            chunk_idx=i, total=total, opts=opts,
        )
        has_content = bool(
            chunk_result.get("summary") or
            chunk_result.get("topics")  or
            chunk_result.get("decisions")
        )
        if chunk_result.get("_error") and not has_content:
            failed_idxs.append(i)
            results.append({"chunk_idx": i, "title": chunk["title"],
                             "_error": chunk_result["_error"], "data": None})
        else:
            results.append({"chunk_idx": i, "title": chunk["title"],
                             "_error": None, "data": chunk_result})
        if i < total - 1:
            time.sleep(0.8)

    if progress_callback:
        progress_callback(0.95, "🔗 合併各段結果…")

    merged = _merge_chunk_results(results, opts)
    if failed_idxs:
        merged["_chunk_warnings"] = (
            f"⚠️ 第 {', '.join(str(x+1) for x in failed_idxs)} 段生成失敗，已跳過。"
        )
    if progress_callback:
        progress_callback(1.0, "✅ 分段生成完成")
    return merged


# ════════════════════════════════════════════════════════════════════════════
# 3. 單段生成（帶重試）
# ════════════════════════════════════════════════════════════════════════════

def _generate_one_chunk_with_retry(
    chunk_text: str, chunk_title: str, chunk_idx: int,
    total: int, opts: dict, max_retries: int = _MAX_RETRIES,
) -> Dict:
    """生成單段會議紀錄，含指數退避重試。"""
    from core.pipeline_minutes import run_generate_minutes
    NL = "\n"
    chunk_prompt = (
        f"【逐字稿段落 {chunk_idx+1}/{total}：{chunk_title}】{NL}"
        f"請只處理以下段落的內容，不要假設其他段落的資訊。{NL}{NL}"
        f"{chunk_text}"
    )
    chunk_opts = dict(opts)
    chunk_opts["_is_chunk"] = True

    last_error = None
    for attempt in range(max_retries):
        try:
            result = run_generate_minutes(chunk_prompt, opts=chunk_opts)
            if result and isinstance(result, dict):
                if result.get("summary") or result.get("topics") or result.get("decisions"):
                    return result
            last_error = "AI 輸出解析失敗或無內容"
        except Exception as e:
            last_error = str(e)
            logger.warning("第 %d 段第 %d 次重試失敗：%s", chunk_idx+1, attempt+1, e)
            if attempt < max_retries - 1:
                time.sleep(_RETRY_BASE_DELAY * (2 ** attempt))

    return {"_error": last_error, "summary": f"（第 {chunk_idx+1} 段生成失敗：{last_error}）"}


# ════════════════════════════════════════════════════════════════════════════
# 4. 合併結構化 dict
# ════════════════════════════════════════════════════════════════════════════

def _merge_chunk_results(results: List[Dict], opts: dict) -> Dict:
    """合併各段結構化會議紀錄 dict。"""
    all_summaries: List = []
    all_topics:    List = []
    all_decisions: List = []
    all_action_items: List = []
    all_key_issues:   List = []
    next_meeting = None
    chunk_count  = 0
    failed_chunks: List[str] = []

    for r in sorted(results, key=lambda x: x["chunk_idx"]):
        data = r.get("data")
        if not data:
            if r.get("_error"):
                failed_chunks.append(f"第 {r['chunk_idx']+1} 段（{r['title']}）：{r['_error']}")
            continue
        chunk_count += 1
        title = r["title"]
        if s := data.get("summary", ""):
            all_summaries.append(f"**{title}**：{s}")
        all_topics        += data.get("topics",       [])
        all_decisions     += data.get("decisions",    [])
        all_action_items  += data.get("action_items", [])
        all_key_issues    += data.get("key_issues",   [])
        if data.get("next_meeting"):
            next_meeting = data["next_meeting"]

    seen_tasks: set = set()
    deduped: List = []
    for a in all_action_items:
        key = re.sub(r"\s+", "", str(a.get("task", a) if isinstance(a, dict) else a))
        if key not in seen_tasks:
            seen_tasks.add(key)
            deduped.append(a)

    provider_tag = opts.get("selected_provider", "AI")
    detail_level = opts.get("detail_level", "標準")

    if chunk_count == 0:
        NL = "\n"
        final_summary = "⚠️ 所有段落生成失敗：" + NL + NL.join(failed_chunks)
    else:
        NL2 = "\n\n"
        final_summary = NL2.join(all_summaries) if all_summaries else "（分段生成，見各段摘要）"
        if failed_chunks:
            NL = "\n"
            final_summary += NL2 + "⚠️ 以下段落生成失敗：" + NL + NL.join(failed_chunks)

    return {
        "summary":       final_summary,
        "topics":        all_topics,
        "decisions":     all_decisions,
        "action_items":  deduped,
        "key_issues":    all_key_issues,
        "next_meeting":  next_meeting,
        "_generated_by": f"{provider_tag} · 分段模式（{chunk_count}/{len(results)} 段）· {detail_level}",
        "_is_chunked":   True,
        "_chunk_count":  chunk_count,
        "_has_agenda":   False,
        "_detail_level": detail_level,
    }


# ════════════════════════════════════════════════════════════════════════════
# 5. 輔助函數
# ════════════════════════════════════════════════════════════════════════════

def should_use_chunked(transcript_text: str, threshold: int = 3500) -> bool:
    return len(transcript_text) > threshold


def estimate_chunk_count(transcript_text: str) -> int:
    return max(1, len(transcript_text) // _MAX_CHUNK_CHARS + 1)
