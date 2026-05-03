# config.py
"""
VoiceDoc AI — Central Configuration (integrated & Windows-safe)

整合內容：
- 保留原本所有設定與環境變數覆蓋行為
- Windows 預設 DATA_DIR 改用 %LOCALAPPDATA%\\VoiceDoc（避免 OneDrive/鎖檔/暫存遺失）
- 非 Windows 預設仍使用 ~/.voicedoc
- 強化 APP_DIR 推斷（兼容 config.py 放在 root 或 services/）
- 修正 VOCAB_BASE_PATH 不要成為 tuple
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 專案根目錄推斷（兼容 root/config.py 及 services/config.py）
# ──────────────────────────────────────────────────────────────────────────────
_THIS_FILE = Path(__file__).resolve()
# 原本你用 dirname(dirname(__file__))，我保留其精神但更穩健：
# - 若此檔在 services/ 下，專案根應為上一層
# - 若此檔在根目錄，專案根就是當前目錄
_CANDIDATE_ROOT = _THIS_FILE.parent
if (_CANDIDATE_ROOT / "pages").exists():
    APP_DIR = str(_CANDIDATE_ROOT)
elif (_CANDIDATE_ROOT.parent / "pages").exists():
    APP_DIR = str(_CANDIDATE_ROOT.parent)
else:
    # fallback：沿用原本做法（向上兩層）
    APP_DIR = str(_THIS_FILE.parent.parent)

# ──────────────────────────────────────────────────────────────────────────────
# 資料目錄（保留環境變數可覆蓋；預設因 OS 而異）
# ──────────────────────────────────────────────────────────────────────────────
_IS_WINDOWS = platform.system().lower().startswith("win")
_LOCALAPPDATA = os.environ.get("LOCALAPPDATA", str(Path.home()))

# 原本預設：~/.voicedoc  [1](https://pccss-my.sharepoint.com/personal/ipwh_ms_pochiu_edu_hk/Documents/Microsoft%20Copilot%20Chat%20%E6%AA%94%E6%A1%88/config.py)
# 修正：Windows 預設改用 %LOCALAPPDATA%\\VoiceDoc（避開 OneDrive，同時對 st.audio 更穩）
DEFAULT_DATA_DIR = (
    os.path.join(_LOCALAPPDATA, "VoiceDoc")
    if _IS_WINDOWS
    else os.path.join(str(Path.home()), ".voicedoc")
)

DATA_DIR = os.environ.get("DATA_DIR", DEFAULT_DATA_DIR)
HISTORY_DIR = os.environ.get("HISTORY_DIR", os.path.join(DATA_DIR, "history"))
CHECKPOINT_DIR = os.environ.get("CHECKPOINT_DIR", os.path.join(DATA_DIR, "checkpoints"))
TEMP_ROOT = os.environ.get("TEMP_ROOT", os.path.join(DATA_DIR, "tmp"))
VOCAB_DIR = os.environ.get("VOCAB_DIR", os.path.join(DATA_DIR, "vocab"))

# 模型快取（保留你原本 VOICEDOC_MODEL_CACHE / MODEL_CACHE 覆蓋行為）[1](https://pccss-my.sharepoint.com/personal/ipwh_ms_pochiu_edu_hk/Documents/Microsoft%20Copilot%20Chat%20%E6%AA%94%E6%A1%88/config.py)
MODEL_CACHE = os.environ.get(
    "VOICEDOC_MODEL_CACHE",
    os.environ.get(
        "MODEL_CACHE",
        os.path.join(str(Path.home()), ".cache", "voicedoc")
    ),
)

BACKUP_DIR = os.environ.get("VOICEDOC_BACKUP_DIR", "")

# 建立資料夾（保留原本行為）[1](https://pccss-my.sharepoint.com/personal/ipwh_ms_pochiu_edu_hk/Documents/Microsoft%20Copilot%20Chat%20%E6%AA%94%E6%A1%88/config.py)
for d in [HISTORY_DIR, CHECKPOINT_DIR, TEMP_ROOT, VOCAB_DIR]:
    os.makedirs(d, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 預設 ASR / LLM 設定（保留原本變數）
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_WHISPER_MODEL = os.environ.get("DEFAULT_WHISPER_MODEL", "medium")
DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "yue")

TEMP_MAX_AGE_HOURS = int(os.environ.get("TEMP_MAX_AGE_HOURS", "12"))

LLM_TIMEOUT_SEC = int(os.environ.get("LLM_TIMEOUT_SEC", "120"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))

KEYWORD_TOP_K = int(os.environ.get("KEYWORD_TOP_K", "30"))
KEYWORD_MAX_ASR_CHARS = int(os.environ.get("KEYWORD_MAX_ASR_CHARS", "250"))
KEYWORD_MIN_TEXT_LEN = int(os.environ.get("KEYWORD_MIN_TEXT_LEN", "300"))

SPEAKER_WINDOW_SEC = float(os.environ.get("SPEAKER_WINDOW_SEC", "1.5"))
SPEAKER_OVERLAP = float(os.environ.get("SPEAKER_OVERLAP", "0.5"))
SPEAKER_DEFAULT_K = int(os.environ.get("SPEAKER_DEFAULT_K", "2"))

# 低記憶體模式（保留原本）
LOW_MEMORY_MODE = os.environ.get("VOICEDOC_LOW_MEMORY", "false").lower() == "true"

# 內建香港學校詞庫路徑（修正：避免尾端逗號令其變成 tuple）
VOCAB_BASE_PATH = os.path.join(APP_DIR, "data", "vocab_base.txt")

# ── 以下為 v4.1 新增常數（向後兼容，勿移除原有常數）────────────────────────
import os

# Whisper
WHISPER_DEFAULT_MODEL    = os.getenv("DEFAULT_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
WHISPER_DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE",      DEFAULT_LANGUAGE)

# VAD 參數（對應 faster-whisper VadOptions 正確欄位名）
VAD_THRESHOLD          = float(os.getenv("VAD_THRESHOLD",          "0.45"))
VAD_MIN_SILENCE_MS     = int(os.getenv("VAD_MIN_SILENCE_MS",       "600"))   # → min_silence_duration_ms
VAD_SPEECH_PAD_MS      = int(os.getenv("VAD_SPEECH_PAD_MS",        "300"))   # → speech_pad_ms