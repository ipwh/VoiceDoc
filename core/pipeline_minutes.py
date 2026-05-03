"""
core/pipeline_minutes.py — LLM 紀要生成流程
v2.2 — 2026-05-02
修正：移除所有 print("[DEBUG]...") 語句，改用 logging.debug()，
      防止在生產環境洩露 API Key 狀態及內部資訊。
"""
from __future__ import annotations
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def run_generate_minutes(
    transcript_text: str,
    agenda_text: str = "",
    opts: dict = None,
    meeting_info: dict = None,
    meeting_date_str: str = "",
    detail_level: str = "標準",
    custom_instructions: str = "",
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    統一入口。opts keys：
    selected_provider, minutes_api_key, template_code,
    meeting_type, custom_base_url, custom_model, llm_context_terms
    """
    try:
        if opts is None:
            opts = {}
        if meeting_info is None:
            meeting_info = {}

        from services.minutes_service import (
            generate_minutes as _gen,
            generate_minutes_with_agenda as _gen_ag,
        )

        _detail = (
            opts.get("detail_level", detail_level)
            if opts.get("_is_chunk")
            else detail_level
        )
        _custom_instr = (
            opts.get("custom_instructions", custom_instructions)
            if opts.get("_is_chunk")
            else custom_instructions
        )

        common = dict(
            template_type       = opts.get("template_code", "formal_tc"),
            provider_name       = opts.get("selected_provider", "DeepSeek"),
            api_key             = opts.get("minutes_api_key", ""),
            meeting_type        = opts.get("meeting_type", meeting_info.get("meeting_type", "一般會議")),
            custom_base_url     = opts.get("custom_base_url", ""),
            custom_model        = opts.get("custom_model", ""),
            llm_context_terms   = opts.get("llm_context_terms", ""),
            meeting_date_str    = meeting_date_str,
            detail_level        = _detail,
            custom_instructions = _custom_instr,
            progress_callback   = progress_callback,
        )

        # 遞迴保護：分段內部呼叫直接走短文本路徑
        if opts.get("_is_chunk"):
            if agenda_text.strip():
                result = _gen_ag(transcript_text, agenda_text, **common)
            else:
                result = _gen(transcript_text, **common)
            logger.debug(
                "_is_chunk=True: result_type=%s keys=%s",
                type(result).__name__,
                list(result.keys()) if isinstance(result, dict) else "N/A",
            )
            return result if isinstance(result, dict) else {}

        # 長逐字稿自動分段（頂層呼叫才判斷）
        from services.chunked_minutes import should_use_chunked, generate_chunked_minutes

        if should_use_chunked(transcript_text):
            logger.debug("觸發分段模式，逐字稿長度=%d 字", len(transcript_text))
            agenda_items = (
                [line.strip() for line in agenda_text.strip().split("\n") if line.strip()]
                if agenda_text.strip()
                else []
            )
            chunked_opts = dict(opts)
            chunked_opts.setdefault("detail_level", detail_level)
            chunked_opts.setdefault("custom_instructions", custom_instructions)
            result = generate_chunked_minutes(
                transcript_text   = transcript_text,
                opts              = chunked_opts,
                agenda_items      = agenda_items if len(agenda_items) >= 2 else None,
                progress_callback = progress_callback,
            )
            logger.debug(
                "分段生成完成：result_type=%s keys=%s",
                type(result).__name__,
                list(result.keys()) if isinstance(result, dict) else "N/A",
            )
            return result if isinstance(result, dict) else {}

        # 正常短文本路徑
        if agenda_text.strip():
            result = _gen_ag(transcript_text, agenda_text, **common)
        else:
            result = _gen(transcript_text, **common)
        logger.debug(
            "短文本路徑完成：result_type=%s keys=%s",
            type(result).__name__,
            list(result.keys()) if isinstance(result, dict) else "N/A",
        )
        return result if isinstance(result, dict) else {}

    except Exception as e:
        logger.error(
            "run_generate_minutes() 異常：%s: %s", type(e).__name__, e, exc_info=True
        )
        return {
            "summary":       f"❌ 紀要生成失敗：{str(e)[:200]}",
            "topics":        [],
            "decisions":     [],
            "action_items":  [],
            "next_meeting":  None,
            "key_issues":    [f"生成失敗：{str(e)[:100]}"],
            "_generated_by": "Error Handler",
            "_has_agenda":   False,
            "_detail_level": detail_level,
            "_parse_failed": True,
            "_error":        str(e),
        }


def generate_minutes(
    transcript_text: str,
    meeting_info: dict,
    llm_options: dict,
    context_terms: str = "",
    agenda_text: str = "",
    detail_level: str = "標準",
    custom_instructions: str = "",
    progress_callback: Optional[Callable] = None,
) -> dict:
    """舊版相容入口（已棄用，請改用 run_generate_minutes）"""
    import warnings
    warnings.warn(
        "generate_minutes() 已棄用，請改用 run_generate_minutes()",
        DeprecationWarning,
        stacklevel=2,
    )
    from services.minutes_service import (
        generate_minutes as _gen,
        generate_minutes_with_agenda as _gen_ag,
    )
    kw = dict(
        template_type       = llm_options.get("template_type", "formal_tc"),
        provider_name       = llm_options.get("provider_name", "DeepSeek"),
        api_key             = llm_options.get("api_key", ""),
        meeting_type        = meeting_info.get("meeting_type", "一般會議"),
        custom_base_url     = llm_options.get("custom_base_url", ""),
        custom_model        = llm_options.get("custom_model", ""),
        llm_context_terms   = context_terms,
        meeting_date_str    = meeting_info.get("date", ""),
        detail_level        = detail_level,
        custom_instructions = custom_instructions,
        progress_callback   = progress_callback,
    )
    if agenda_text.strip():
        return _gen_ag(transcript_text, agenda_text, **kw)
    return _gen(transcript_text, **kw)
