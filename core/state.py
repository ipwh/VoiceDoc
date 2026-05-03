"""
core/state.py
集中初始化所有 session_state key，避免任何頁面出現 KeyError。
每頁最頂部 import 後立即呼叫 init_state()。
"""
import streamlit as st
from datetime import datetime

APP_STATE_VERSION = "3.1"

# ── Key 常數（避免打字錯誤）────────────────────────────────────────────────────
K_APP_INIT        = "app_initialized"
K_STATE_VER       = "_state_version"
K_MEETING_ID      = "meeting_id"
K_TMP_DIR         = "tmp_dir"
K_AUDIO_RESULT    = "audio_result"
K_TRANSCRIPT      = "transcript"
K_MINUTES         = "minutes"
K_IMPORT_MINUTES  = "import_minutes"
K_MANUAL_TERMS    = "manual_terms"
K_PREV_VOCAB      = "prev_vocab"
K_SEL_VOCAB       = "selected_vocab"
K_INIT_PROMPT     = "initial_prompt"
K_LLM_TERMS       = "llm_context_terms"
K_CTX_KW          = "context_keywords"
K_AG_TAB1         = "tab1_agenda_text"
K_AG_TAB2         = "tab2_agenda_text"
K_DIARIZATION     = "diarization"
K_HIST_FILE       = "current_history_file"
K_STEP_STATUS     = "step_status"
K_STEP_ERROR      = "step_error"
K_HIST_TAB        = "_history_loaded_tab"
K_IMP_TXT         = "_import_transcript_txt"
K_RECOVERY_DONE   = "recovery_dismissed"
K_MEETING_INFO    = "meeting_info"

STEPS = ["audio", "context", "transcript", "minutes"]

_DEFAULTS = {
    K_APP_INIT:       False,
    K_STATE_VER:      APP_STATE_VERSION,
    K_MEETING_ID:     None,
    K_TMP_DIR:        None,
    K_AUDIO_RESULT:   None,
    K_TRANSCRIPT:     None,
    K_MINUTES:        None,
    K_IMPORT_MINUTES: None,
    K_MANUAL_TERMS:   [],
    K_PREV_VOCAB:     [],
    K_SEL_VOCAB:      [],
    K_INIT_PROMPT:    "",
    K_LLM_TERMS:      "",
    K_CTX_KW:         [],
    K_AG_TAB1:        "",
    K_AG_TAB2:        "",
    K_DIARIZATION:    None,
    K_HIST_FILE:      None,
    K_STEP_STATUS:    {s: "wait" for s in STEPS},
    K_STEP_ERROR:     {s: ""    for s in STEPS},
    K_HIST_TAB:       None,
    K_IMP_TXT:        "",
    K_RECOVERY_DONE:  False,
    'sb_mtg_date':    None,  # 由 layout._set_defaults 補充
    K_MEETING_INFO:   {
        "meeting_name": "",
        "date": str(datetime.today().date()),
        "venue": "",
        "attendees": "",
        "meeting_type": "一般會議",
    },
}


def init_state():
    """每頁最頂部呼叫一次，setdefault 所有 key。"""
    ss = st.session_state
    for k, v in _DEFAULTS.items():
        if k not in ss:
            ss[k] = v

    # 一次性啟動任務（用 .get() 確保 rerun 不重複觸發）
    if not ss.get(K_APP_INIT, False):
        try:
            from services.audio_service import purge_old_temps
            from services.checkpoint_service import cleanup_old_checkpoints
            _cur_tmp = ss.get(K_TMP_DIR)
            purge_old_temps(protect_dirs=[_cur_tmp] if _cur_tmp else [])
            cleanup_old_checkpoints()
        except Exception:
            pass
        ss[K_APP_INIT] = True  # 必須在 try 外，確保一定被設定


def reset_all():
    """清除所有 session_state（保留 _cfg 設定由呼叫方自行處理）。"""
    ss = st.session_state
    for k in list(ss.keys()):
        del ss[k]



def mark(step: str, status: str, error: str = ""):
    ss = st.session_state
    ss[K_STEP_STATUS][step] = status
    ss[K_STEP_ERROR][step]  = error


def get_ss():
    """快捷取得 session_state。"""
    return st.session_state

# ── 別名：確保舊版 page 代碼相容（pages/1_語音轉錄.py 使用的名稱）────────────
mark_step        = mark              # mark_step() → mark()
K_INITIAL_PROMPT = K_INIT_PROMPT    # 統一名稱
K_LLM_CONTEXT    = K_LLM_TERMS      # 統一名稱
K_HISTORY_FILE   = K_HIST_FILE      # 統一名稱
K_TAB1_AGENDA    = K_AG_TAB1        # 統一名稱
K_TMP_MGR        = "_tmp_mgr"       # TempAudioManager 儲存 key
K_HISTORY_TAB    = K_HIST_TAB        # 3_歷史記錄.py 使用的名稱
