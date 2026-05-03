
import json
import re
import time
import httpx
from services.config import LLM_TIMEOUT_SEC, LLM_MAX_RETRIES

"""
minutes_service.py — 完整整合強化版
- 保留原有 provider / prompt / 詳盡程度 / 兩階段生成 / 自訂指示 / agenda mode 功能
- 強化 agenda prompt：不得新增、刪除、合併、重排議項；逐項對應原議程；未討論也必須保留
- 補上 agenda 解析與後處理，確保輸出 agenda_items 與輸入議程一一對應
- 就算模型輸出有偏差，也以程式層重新對齊，避免漏項
"""

LLM_PROVIDERS = {
    "DeepSeek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "placeholder": "sk-...", "url": "https://platform.deepseek.com", "price": "💰 低成本"},
    "Grok (xAI)": {"base_url": "https://api.x.ai/v1", "model": "grok-3", "placeholder": "xai-...", "url": "https://console.x.ai", "price": "💰 低成本"},
    "OpenAI GPT-4o": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "placeholder": "sk-...", "url": "https://platform.openai.com", "price": "💰💰 較高"},
    "自定義 (OpenAI 相容)": {"base_url": "", "model": "", "placeholder": "your_api_key", "url": "", "price": "自定義"},
}

SCHOOL_TEMPLATES = {
    "常務委員會": (
        "請特別提取：校務決策、預算批核、表決結果、負責組別。"
        "若討論涉及財務，必須在對應 action_item 的 details 欄位標註："
        "budget_amount（金額）、budget_item（項目名稱）、vote_result（通過/否決/修訂後通過）。"
    ),
    "學務委員會": (
        "請特別提取：課程政策決定、評估安排。"
        "評估相關 action_item 的 details 須含："
        "subject_code（科目代號）、form_level（年級）、assessment_date（評估日期）。"
    ),
    "訓導委員會": (
        "所有學生姓名必須匿名化為「學生甲」「學生乙」等。"
        "每個紀律事件必須在 action_item 的 details 欄位標註："
        "incident_date、follow_up_deadline、disciplinary_measure。"
    ),
    "科組會議": (
        "請特別提取：subject_code、form_level、assessment_date、備課分工、教材安排。"
        "上述資訊放入對應 action_item 的 details 欄位。"
    ),
    "家長教師會": (
        "語氣須親切易讀。必須將家長提問與校方回應整理為頂層陣列 pta_qna，"
        "每項含：asker、question、response。若無問答環節，pta_qna 為空陣列 []。"
    ),
    "輔導委員會": (
        "請特別提取：個案跟進事項、心理健康活動安排、外展服務協作。"
        "所有學生資料必須匿名化。"
    ),
    "一般會議": "",
}

DETAIL_INSTRUCTIONS = {
    "簡略": (
        "【詳盡程度：簡略】\n"
        "每個議題只需 1–2 句描述核心結論，不需說明討論過程。\n"
        "決議以條列式列出，每項不超過 20 字。\n"
        "行動項目最多 5 項，只列任務、負責人、截止日期，不需 details。\n"
        "summary 控制在 100 字以內。"
    ),
    "標準": (
        "【詳盡程度：標準】\n"
        "每個議題用 3–4 句描述討論重點及結論。\n"
        "決議完整列出，每項 20–40 字。\n"
        "行動項目列出所有跟進事項，details 欄位填寫重要背景。\n"
        "summary 控制在 200–300 字。"
    ),
    "詳盡": (
        "【詳盡程度：詳盡】\n"
        "每個議題需 5–8 句，涵蓋：討論背景、各方觀點、正反意見、最終結論。\n"
        "若有人提出反對或保留意見，必須記錄。\n"
        "引用重要發言時，用「（某成員指出）」格式標注發言者角色（不需全名）。\n"
        "決議列出完整內容及通過方式（共識/表決）。\n"
        "行動項目 details 欄位詳細說明背景及執行要求。\n"
        "summary 控制在 350–500 字，涵蓋所有重要決定。"
    ),
}

EMPTY_MINUTES = {
    "summary": "",
    "topics": [],
    "decisions": [],
    "action_items": [],
    "next_meeting": None,
    "key_issues": [],
}

BASE_SYSTEM = """你是一位香港中學的專業會議秘書，負責撰寫詳盡、結構清晰的會議紀錄。
只輸出合法 JSON，不要有 markdown 代碼框（```），不要有任何額外文字。
JSON 必須包含：
- summary（執行摘要）
- topics（陣列，每項「議題：具體討論說明」）
- decisions（陣列，每項具體決議）
- action_items（陣列，每項含：task、assignee、deadline、details）
- next_meeting（下次會議資訊，無則 null）
- key_issues（陣列，待跟進問題）
全部繁體中文。"""

AGENDA_SYSTEM = """你是一位香港中學的專業會議秘書，按照既定議程撰寫詳盡會議紀錄。
你必須絕對遵守以下規則：
1. agenda_items 的項目數量必須與輸入議程完全一致。
2. 不得新增、刪除、合併、拆分、重排任何議項。
3. 每個 agenda_items[n] 必須逐項對應輸入議程的第 n 項。
4. item_no 與 title 必須保留並對應原議程，不可自行改寫成其他議題。
5. 若逐字稿沒有該議項內容，discussion 必須填「（會議中未有討論）」，decisions 必須為 []，action_items 必須為 []。
6. 不可把某議項的內容搬到另一議項。
7. 若有「其他事項 / Any Other Business / AOB」，只有在原議程明確存在時才可寫入對應議項；否則請放在 other_matters，且不得影響 agenda_items 順序。
8. 只可根據逐字稿與議程整理，不可幻想未出現的決議。

只輸出合法 JSON，不要有 markdown 代碼框，不要有額外文字。
JSON 格式：
{
  "summary": "整體執行摘要",
  "agenda_items": [
    {
      "item_no": "",
      "title": "",
      "discussion": "",
      "decisions": [],
      "action_items": [
        {"task":"","assignee":null,"deadline":null,"details":""}
      ]
    }
  ],
  "other_matters": "",
  "next_meeting": null,
  "key_issues": []
}
全部繁體中文。"""

STAGE1_SYSTEM = """你是一位香港中學的會議秘書。
第一階段任務：從逐字稿提取會議骨架。
只輸出合法 JSON，格式：
{
  "topics": [
    {
      "title": "議題標題",
      "key_points": ["要點1","要點2"],
      "decisions": ["決議1"],
      "action_items": [{"task":"","assignee":null,"deadline":null}]
    }
  ],
  "next_meeting": null,
  "key_issues": []
}
全部繁體中文。簡短精準，不需展開。"""

STAGE2_SYSTEM = """你是一位香港中學的會議秘書。
第二階段任務：根據骨架和逐字稿，深度撰寫完整會議紀錄。
要求：
- 每個議題詳細描述討論過程、各方觀點、正反意見、結論
- 引用重要發言用「（某成員指出）」格式標注角色
- 若有反對或保留意見，必須記錄
- 決議列出完整內容及通過方式（共識/表決）
- action_items 的 details 欄位詳細說明背景及執行要求
- summary 350–500 字，涵蓋所有重要決定
只輸出合法 JSON，格式與標準會議紀錄相同：
{summary, topics, decisions, action_items, next_meeting, key_issues}
全部繁體中文。資訊寧多勿少。"""


def _classify_llm_error(err: Exception) -> str:
    msg = str(err).lower()
    status = getattr(getattr(err, "response", None), "status_code", None)
    if status is None:
        m = re.search(r"status[\s_]?code[=:\s]+([0-9]+)", msg, re.IGNORECASE)
        status = int(m.group(1)) if m else None

    if status == 401 or any(k in msg for k in ["invalid api key", "api key", "unauthorized", "authentication"]):
        return "🔑 **API Key 無效或已失效**\n\n請在左側 Sidebar 重新輸入正確的 API Key。\n如需申請新 Key，請前往對應供應商網站。"
    if status == 402 or any(k in msg for k in ["insufficient balance", "billing", "quota exceeded", "out of credit", "insufficient_quota"]):
        return "💳 **帳戶餘額不足**\n\n請登入 API 供應商後台充值，或切換至其他供應商。"
    if status == 429 or any(k in msg for k in ["rate limit", "too many requests", "ratelimit"]):
        return "⏳ **請求過於頻繁（速率限制）**\n\n請稍等 30–60 秒後重試。若持續出現，請切換至其他供應商。"
    if status == 400 or any(k in msg for k in ["context length", "maximum context", "too long", "input too long", "tokens", "content too large", "max_tokens"]):
        return "✂️ **逐字稿內容過長**\n\n建議：\n1. 將詳盡程度改為「簡略」\n2. 刪除不重要段落\n3. 或切換至支援更長上下文的模型"
    if any(k in msg for k in ["json", "parse", "invalid response", "decode"]):
        return "🔄 **AI 回應格式異常**\n\n系統已自動重試。若仍失敗，請嘗試重新生成，或切換 AI 供應商。"
    if any(k in msg for k in ["timeout", "timed out", "connection", "network", "connect"]):
        return "🌐 **網絡連接問題**\n\n請檢查網絡連接，或稍後重試。\n如在學校網絡環境，請確認防火牆未封鎖 API 請求。"
    if any(k in msg for k in ["model not found", "no such model", "model_not_found"]):
        return "🤖 **找不到指定模型**\n\n請在 Sidebar 切換至其他 AI 供應商或確認模型名稱正確。"
    short = str(err)[:200]
    return f"❌ **AI 生成失敗**\n\n錯誤詳情：`{short}`\n\n請重試，或切換 AI 供應商。"


def get_provider_names():
    return list(LLM_PROVIDERS.keys())


def _get_client(provider_name, api_key, custom_base_url="", custom_model=""):
    from openai import OpenAI
    p = LLM_PROVIDERS.get(provider_name, LLM_PROVIDERS["DeepSeek"])
    base_url = custom_base_url if provider_name == "自定義 (OpenAI 相容)" else p["base_url"]
    model = custom_model if provider_name == "自定義 (OpenAI 相容)" else p["model"]
    client = OpenAI(api_key=api_key, base_url=base_url, http_client=httpx.Client(timeout=LLM_TIMEOUT_SEC))
    return client, model


def _extract_json(raw):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]+\}", cleaned)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}


def _call_llm(client, model, messages):
    last_err = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise RuntimeError(_classify_llm_error(last_err))


def _repair_call(client, model, bad_response, system):
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"你上一次的回覆不是合法 JSON，請只回傳 JSON，不要有任何其他文字：\n{(bad_response or '')[:2000]}"},
    ]
    return _extract_json(_call_llm(client, model, msgs))


def _normalize_action_items(action_items: list, meeting_date_str: str = "") -> list:
    from datetime import date, timedelta
    try:
        base = date.fromisoformat(meeting_date_str) if meeting_date_str else date.today()
    except Exception:
        base = date.today()

    wd_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    n_map = {"一": 1, "兩": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8}

    def _to_n(s):
        return n_map.get(s, int(s) if str(s).isdigit() else 2)

    def _resolve(dl):
        if not dl or not isinstance(dl, str):
            return dl
        dl = dl.strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", dl):
            return dl
        m = re.search(r"下週([一二三四五六日天])", dl)
        if m:
            wd = wd_map[m.group(1)]
            days = (wd - base.weekday() + 7) % 7
            return str(base + timedelta(days=days if days > 0 else 7))
        m = re.search(r"本週([一二三四五六日天])", dl)
        if m:
            wd = wd_map[m.group(1)]
            days = (wd - base.weekday()) % 7
            return str(base + timedelta(days=days))
        m = re.search(r"([一兩二三四五六七八\d]+)[個]?[週星期]", dl)
        if m:
            return str(base + timedelta(weeks=_to_n(m.group(1))))
        if "下月" in dl or "下個月" in dl:
            nm = base.month % 12 + 1
            ny = base.year + (1 if base.month == 12 else 0)
            try:
                return str(base.replace(year=ny, month=nm))
            except Exception:
                return dl
        m = re.search(r"([一兩二三四五六\d]+)[個]?月[後內内]?", dl)
        if m:
            add = _to_n(m.group(1))
            nm = base.month + add
            ny = base.year + (nm - 1) // 12
            nm = (nm - 1) % 12 + 1
            try:
                return str(base.replace(year=ny, month=nm))
            except Exception:
                return dl
        return dl

    return [dict(item, deadline=_resolve(item.get("deadline"))) for item in (action_items or [])]


def _build_system_prompt(base_system, meeting_type, detail_level, custom_instructions, llm_context_terms):
    parts = [base_system]
    template_hint = SCHOOL_TEMPLATES.get(meeting_type, "")
    if template_hint:
        parts.append(template_hint)
    parts.append(DETAIL_INSTRUCTIONS.get(detail_level, DETAIL_INSTRUCTIONS["標準"]))
    if custom_instructions and custom_instructions.strip():
        parts.append(f"【用家補充指示】\n{custom_instructions.strip()}")
    if llm_context_terms:
        parts.append(f"學校常用詞彙供參考：{llm_context_terms}")
    return "\n\n".join(parts)


def _parse_agenda_lines(agenda_text: str) -> list:
    lines = []
    for raw in (agenda_text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^[\-•●▪◦‧]+\s*", "", s)
        lines.append(s)

    items = []
    pat = re.compile(r"^(?P<no>(?:第[一二三四五六七八九十百零〇\d]+項|[一二三四五六七八九十百零〇]+[、.]?|\d+[、.]?|\([一二三四五六七八九十百零〇\d]+\)|[A-Za-z][.)]))\s*(?P<title>.+)$")
    for idx, line in enumerate(lines, 1):
        m = pat.match(line)
        if m:
            item_no = m.group("no").strip()
            title = m.group("title").strip()
        else:
            item_no = str(idx)
            title = line.strip()
        items.append({"item_no": item_no, "title": title, "raw": line})
    return items


def _normalize_ai_agenda_items(ai_items):
    norm = []
    for item in (ai_items or []):
        if not isinstance(item, dict):
            continue
        norm.append({
            "item_no": str(item.get("item_no", "") or "").strip(),
            "title": str(item.get("title", "") or "").strip(),
            "discussion": str(item.get("discussion", "") or "").strip(),
            "decisions": item.get("decisions", []) if isinstance(item.get("decisions", []), list) else [],
            "action_items": item.get("action_items", []) if isinstance(item.get("action_items", []), list) else [],
        })
    return norm


def _align_agenda_result(result: dict, agenda_text: str) -> dict:
    agenda_src = _parse_agenda_lines(agenda_text)
    ai_items = _normalize_ai_agenda_items(result.get("agenda_items", []))
    aligned = []

    for idx, src in enumerate(agenda_src):
        ai = ai_items[idx] if idx < len(ai_items) else {}
        discussion = str(ai.get("discussion", "") or "").strip()
        decisions = ai.get("decisions", []) if isinstance(ai.get("decisions", []), list) else []
        action_items = ai.get("action_items", []) if isinstance(ai.get("action_items", []), list) else []

        empty_like = (not discussion) and not decisions and not action_items
        if empty_like:
            discussion = "（會議中未有討論）"
            decisions = []
            action_items = []

        aligned.append({
            "item_no": src["item_no"],
            "title": src["title"],
            "discussion": discussion,
            "decisions": decisions,
            "action_items": action_items,
        })

    result["agenda_items"] = aligned
    if "other_matters" not in result or result.get("other_matters") is None:
        result["other_matters"] = ""
    return result


def _finalize(result, provider_name, model, has_agenda=False, meeting_date_str="", detail_level="標準", two_stage=False, agenda_text=""):
    if has_agenda:
        result = _align_agenda_result(result or {}, agenda_text)
        result["topics"] = [f"{i.get('item_no','')} {i.get('title','')}: {i.get('discussion','')}".strip() for i in result.get("agenda_items", [])]
        all_d, all_a = [], []
        for i in result.get("agenda_items", []):
            all_d.extend(i.get("decisions", []))
            all_a.extend(i.get("action_items", []))
        result["decisions"] = all_d
        result["action_items"] = all_a

    for k, v in EMPTY_MINUTES.items():
        result.setdefault(k, v)
    if result.get("action_items"):
        result["action_items"] = _normalize_action_items(result["action_items"], meeting_date_str)
        if has_agenda:
            cursor = 0
            for item in result.get("agenda_items", []):
                cnt = len(item.get("action_items", []))
                if cnt:
                    item["action_items"] = result["action_items"][cursor:cursor+cnt]
                    cursor += cnt

    tag = f"{provider_name} ({model})"
    if two_stage:
        tag += " · 兩階段深度生成"
    if has_agenda:
        tag += " · 議程模式"
    tag += f" · {detail_level}"
    result["_generated_by"] = tag
    result["_has_agenda"] = has_agenda
    result["_detail_level"] = detail_level
    return result


def _two_stage_generate(client, model, transcript_text, system_msg, meeting_type, detail_level, custom_instructions, llm_context_terms, progress_callback=None):
    if progress_callback:
        progress_callback(0.1, "兩階段生成：階段一 — 提取會議骨架…")
    s1_system = _build_system_prompt(STAGE1_SYSTEM, meeting_type, "標準", custom_instructions, llm_context_terms)
    s1_msgs = [
        {"role": "system", "content": s1_system},
        {"role": "user", "content": f"請從以下逐字稿提取會議骨架：\n\n{transcript_text}"},
    ]
    s1_raw = _call_llm(client, model, s1_msgs)
    skeleton = _extract_json(s1_raw)
    if not skeleton:
        skeleton = _repair_call(client, model, s1_raw, s1_system)

    if progress_callback:
        progress_callback(0.55, "兩階段生成：階段二 — 深度撰寫完整會議紀錄…")
    skeleton_json = json.dumps(skeleton, ensure_ascii=False, indent=2)
    s2_system = _build_system_prompt(STAGE2_SYSTEM, meeting_type, detail_level, custom_instructions, llm_context_terms)
    s2_msgs = [
        {"role": "system", "content": s2_system},
        {"role": "user", "content": f"【會議骨架（階段一結果）】\n{skeleton_json}\n\n【完整逐字稿】\n{transcript_text}\n\n請根據骨架和逐字稿，撰寫詳盡完整的會議紀錄 JSON。"},
    ]
    s2_raw = _call_llm(client, model, s2_msgs)
    result = _extract_json(s2_raw)
    if not result:
        result = _repair_call(client, model, s2_raw, s2_system)
    if progress_callback:
        progress_callback(1.0, "✅ 兩階段生成完成")
    return result


def generate_minutes(transcript_text, template_type="formal_tc", provider_name="DeepSeek", api_key="", meeting_type="一般會議", custom_base_url="", custom_model="", llm_context_terms="", meeting_date_str="", detail_level="標準", custom_instructions="", progress_callback=None):
    if not api_key:
        raise ValueError("請填入 API Key")
    client, model = _get_client(provider_name, api_key, custom_base_url, custom_model)
    use_two_stage = (detail_level == "詳盡")
    system_msg = _build_system_prompt(BASE_SYSTEM, meeting_type, detail_level, custom_instructions, llm_context_terms)

    if use_two_stage:
        result = _two_stage_generate(client, model, transcript_text, system_msg, meeting_type, detail_level, custom_instructions, llm_context_terms, progress_callback)
    else:
        if progress_callback:
            progress_callback(0.1, "AI 生成中…")
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"會議類型：{meeting_type}\n模板：{template_type}\n\n逐字稿：\n{transcript_text}"},
        ]
        raw = _call_llm(client, model, messages)
        result = _extract_json(raw)
        if not result:
            result = _repair_call(client, model, raw, system_msg)
        if progress_callback:
            progress_callback(1.0, "✅ 完成")

    if not result:
        result = {**EMPTY_MINUTES, "summary": "（生成失敗）", "_parse_failed": True}
    return _finalize(result, provider_name, model, has_agenda=False, meeting_date_str=meeting_date_str, detail_level=detail_level, two_stage=use_two_stage)


def generate_minutes_with_agenda(transcript_text, agenda_text="", template_type="formal_tc", provider_name="DeepSeek", api_key="", meeting_type="一般會議", custom_base_url="", custom_model="", llm_context_terms="", meeting_date_str="", detail_level="標準", custom_instructions="", progress_callback=None):
    if not agenda_text.strip():
        return generate_minutes(transcript_text, template_type, provider_name, api_key, meeting_type, custom_base_url, custom_model, llm_context_terms, meeting_date_str, detail_level, custom_instructions, progress_callback)
    if not api_key:
        raise ValueError("請填入 API Key")

    client, model = _get_client(provider_name, api_key, custom_base_url, custom_model)
    system_msg = _build_system_prompt(AGENDA_SYSTEM, meeting_type, detail_level, custom_instructions, llm_context_terms)
    parsed_agenda = _parse_agenda_lines(agenda_text)
    agenda_json = json.dumps(parsed_agenda, ensure_ascii=False, indent=2)

    if progress_callback:
        progress_callback(0.1, "議程模式 AI 生成中…")

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": (
            f"【原始會議議程】\n{agenda_text}\n\n"
            f"【已解析議程（必須 100% 逐項對應）】\n{agenda_json}\n\n"
            f"【會議逐字稿】\n{transcript_text}\n\n"
            "請嚴格按已解析議程輸出 agenda_items。"
            "agenda_items 長度必須與已解析議程完全相同。"
            "不得新增、刪除、合併、拆分、重排。"
            "若某項未討論，discussion 請填「（會議中未有討論）」、decisions=[]、action_items=[]。"
        )},
    ]

    raw = _call_llm(client, model, messages)
    result = _extract_json(raw)
    if not result:
        result = _repair_call(client, model, raw, system_msg)
    if not result:
        result = {**EMPTY_MINUTES, "summary": (raw or "")[:800], "_parse_failed": True}

    if progress_callback:
        progress_callback(1.0, "✅ 完成")

    return _finalize(result, provider_name, model, has_agenda=True, meeting_date_str=meeting_date_str, detail_level=detail_level, two_stage=False, agenda_text=agenda_text)


def format_minutes_text(minutes, meeting_info=None) -> str:
    lines = []
    if meeting_info:
        lines += [
            "=" * 50,
            f" {meeting_info.get('meeting_name','會議紀錄')}",
            f" 日期：{meeting_info.get('date','-')}",
            f" 地點：{meeting_info.get('venue','-')}",
            f" 出席：{meeting_info.get('attendees','-')}",
            "=" * 50,
            "",
        ]

    lines += ["【執行摘要】", minutes.get("summary", "—"), ""]
    if minutes.get("_has_agenda") and minutes.get("agenda_items"):
        lines.append("【議程討論紀錄】")
        for item in minutes["agenda_items"]:
            lines += ["", f" {item.get('item_no','')} {item.get('title','')}".strip(), f" {item.get('discussion','')}"]
            for d in item.get("decisions", []):
                lines.append(f" ✓ {d}")
            for a in item.get("action_items", []):
                lines.append(f" • {a.get('task','—')} （{a.get('assignee') or '待定'} / {a.get('deadline') or '待定'}）")
        if minutes.get("other_matters"):
            lines += ["", "【其他事項】", minutes["other_matters"]]
    else:
        if minutes.get("topics"):
            lines.append("【主要議題】")
            for t in minutes["topics"]:
                lines.append(f" • {t}")
            lines.append("")
        if minutes.get("decisions"):
            lines.append("【決議事項】")
            for d in minutes["decisions"]:
                lines.append(f" ✓ {d}")
            lines.append("")
        if minutes.get("action_items"):
            lines.append("【行動項目】")
            for i, a in enumerate(minutes["action_items"], 1):
                lines.append(f" {i}. {a.get('task','—')} — {a.get('assignee') or '待定'} / {a.get('deadline') or '待定'}")

    if minutes.get("key_issues"):
        lines += ["", "【待跟進事項】"] + [f" ⚠ {q}" for q in minutes["key_issues"]]
    if minutes.get("next_meeting"):
        lines.append(f"\n【下次會議】{minutes['next_meeting']}")
    if minutes.get("_generated_by"):
        lines.append(f"\n（{minutes['_generated_by']} 自動生成）")
    return "\n".join(lines)
