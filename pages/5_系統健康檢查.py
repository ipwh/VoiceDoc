"""
pages/5_系統健康檢查.py
VoiceDoc AI — 系統健康檢查
v1.7 — 2026-05-03

更新：
- 移除說話人分離相關檢查
- 配合 sidebar / layout 精簡版
- 保留 Whisper、FFmpeg、API、磁碟、核心與增強元件檢查
"""
import importlib.metadata
import os
import re
import socket
import subprocess
import shutil
from pathlib import Path

import streamlit as st


@st.cache_data(ttl=60)
def _get_installed_packages() -> set[str]:
    try:
        return {d.metadata["Name"].lower() for d in importlib.metadata.distributions()}
    except Exception:
        return set()


def _pkg_installed(pip_name: str, installed: set[str]) -> bool:
    name_lower = pip_name.lower()
    name_normalized = name_lower.replace("-", "_")
    return name_lower in installed or name_normalized in installed


if "health_run" not in st.session_state:
    st.session_state["health_run"] = 0

if st.session_state["health_run"] > 0:
    _get_installed_packages.clear()

installed_pkgs = _get_installed_packages()

st.title("🏥 VoiceDoc AI — 系統健康檢查")
st.caption("🔴 核心元件缺失影響基本功能　🟡 增強元件缺失只影響附加功能　ℹ️ 參考資訊")

results: dict[str, tuple[str, str, str]] = {}

# ═══════════════════════════════════════
# 核心元件
# ═══════════════════════════════════════
if shutil.which("ffmpeg"):
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        raw_line = r.stdout.splitlines()[0] if r.stdout else ""
        m = re.search(r"ffmpeg version\s+([\S]+)", raw_line)
        ver = m.group(1).split("-")[0] if m else "（版本未知）"
        results["FFmpeg"] = ("✅", f"已安裝 v{ver}　音頻轉換 / 音頻上傳正常", "core")
    except Exception as e:
        results["FFmpeg"] = ("❌", f"執行失敗：{e}", "core")
else:
    results["FFmpeg"] = (
        "❌",
        "找不到 ffmpeg — 無法上傳 / 轉換音頻。請安裝 FFmpeg 並將 bin 資料夾加入系統 PATH。下載：https://ffmpeg.org/download.html",
        "core",
    )

CORE_PKGS: dict[str, str] = {
    "faster-whisper": "本地 Whisper 語音轉錄",
    "soundfile": "音頻讀取 / 時長計算",
    "scipy": "音頻降噪運算",
    "pydub": "音頻格式備用處理",
    "python-dotenv": ".env 環境變數載入",
    "python-docx": "DOCX 格式匯出",
    "pypdf": "PDF 情境文件讀取",
    "streamlit": "Web UI 框架",
}

for pip_name, desc in CORE_PKGS.items():
    if _pkg_installed(pip_name, installed_pkgs):
        results[f"套件 / {pip_name}"] = ("✅", f"已安裝　{desc}", "core")
    else:
        results[f"套件 / {pip_name}"] = ("❌", f"未安裝　{desc}　→ pip install {pip_name}", "core")

# ═══════════════════════════════════════
# 增強元件
# ═══════════════════════════════════════
ENHANCE_PKGS: dict[str, str] = {
    "cryptography": "API Key Fernet 持久加密，缺少時 Key 僅存於 session，重啟後需重新輸入",
    "keybert": "TF-IDF 關鍵詞提取（情境文件精選模式）",
    "deepfilternet": "DeepFilterNet 強效降噪，缺少時退回基礎降噪",
    "openai": "OpenAI API 供應商支援",
}

for pip_name, desc in ENHANCE_PKGS.items():
    if _pkg_installed(pip_name, installed_pkgs):
        results[f"套件（增強）/ {pip_name}"] = ("✅", f"已安裝　{desc}", "enhance")
    else:
        results[f"套件（增強）/ {pip_name}"] = ("⚠️", f"未安裝　{desc}　→ pip install {pip_name}", "enhance")

# ═══════════════════════════════════════
# Whisper 模型
# ═══════════════════════════════════════
CACHE_HF = Path.home() / ".cache" / "huggingface" / "hub"
CACHE_LEGACY = Path.home() / ".cache" / "whisper"

try:
    from ui.layout import get_cfg
    active_model = get_cfg().get("whisper_model", "medium")
except Exception:
    active_model = "medium"

warmed_up = st.session_state.get("model_warmed_up", False)

MODEL_DESC = {
    "small": "461 MB　速度快，適合低資源環境",
    "medium": "1.4 GB　平衡準確度與速度（系統預設）",
    "large-v3": "2.9 GB　最高準確度",
}

for model in ("small", "medium", "large-v3"):
    desc = MODEL_DESC[model]
    is_active = model == active_model

    cached = False
    if CACHE_HF.exists():
        cached = any(CACHE_HF.rglob(f"*{model.replace('-', '_')}*"))
    if not cached and CACHE_LEGACY.exists():
        cached = bool(list(CACHE_LEGACY.glob(f"{model}*")))

    star = "★ " if is_active else ""
    if cached:
        if is_active and warmed_up:
            icon, note, grp = "✅", f"已預載至記憶體　{desc}", "core"
        elif is_active:
            icon, note, grp = "🔄", f"已快取，啟動時預載中…　{desc}", "core"
        else:
            icon, note, grp = "✅", f"已快取於本地　{desc}", "info"
    else:
        if is_active:
            icon, note, grp = "⬇️", f"尚未下載，首次使用時自動下載（需網絡）　{desc}", "core"
        else:
            icon, note, grp = "⚪", f"未下載，按需使用時自動下載　{desc}", "info"

    results[f"{star}Whisper / {model}"] = (icon, note, grp)

# ═══════════════════════════════════════
# API 可達性
# ═══════════════════════════════════════
API_HOSTS = {
    "DeepSeek": ("api.deepseek.com", 443, "DEEPSEEK_API_KEY"),
    "OpenAI": ("api.openai.com", 443, "OPENAI_API_KEY"),
    "Grok/xAI": ("api.x.ai", 443, "XAI_API_KEY"),
}

for name, (host, port, env_key) in API_HOSTS.items():
    api_key = os.getenv(env_key, "")
    if not api_key:
        results[f"API / {name}"] = ("⚪", f"未設定 {env_key}，跳過連線測試", "info")
        continue
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        results[f"API / {name}"] = ("✅", f"{host}:{port} 可達　AI 會議紀錄生成正常", "core")
    except OSError as e:
        results[f"API / {name}"] = ("❌", f"無法連線 {host}:{port}（{e}）　→ AI 會議紀錄生成將失敗", "core")

# ═══════════════════════════════════════
# 目錄與磁碟空間
# ═══════════════════════════════════════
try:
    from services.config import TEMP_ROOT, DATA_DIR
    for label, dpath in [("暫存目錄 TEMP_ROOT", TEMP_ROOT), ("資料目錄 DATA_DIR", DATA_DIR)]:
        p = Path(dpath)
        if p.exists():
            free_gb = shutil.disk_usage(dpath).free / (1024 ** 3)
            if free_gb >= 2.0:
                results[label] = ("✅", f"存在　可用空間 {free_gb:.1f} GB", "core")
            else:
                results[label] = ("⚠️", f"存在　可用空間僅 {free_gb:.1f} GB（建議保持 2 GB 以上）", "core")
        else:
            results[label] = ("⚠️", f"目錄不存在，首次使用時自動建立：{dpath}", "core")
except Exception as e:
    results["目錄檢查"] = ("⚠️", f"無法讀取 config：{e}", "core")

# ═══════════════════════════════════════
# 顯示
# ═══════════════════════════════════════
error_count = sum(1 for v in results.values() if v[0] == "❌")
warning_count = sum(1 for v in results.values() if v[0] == "⚠️")

st.divider()
if error_count:
    st.error(
        f"❌ 發現 **{error_count}** 個核心元件異常，基本功能將受影響。"
        + (f"　另有 **{warning_count}** 個增強元件未安裝。" if warning_count else "")
    )
elif warning_count:
    st.warning(f"⚠️ 發現 **{warning_count}** 個增強元件未安裝，基本功能不受影響。")
else:
    st.success("✅ 所有核心元件正常，增強元件亦完整安裝。")

SECTIONS = {
    "core": ("🔴 核心元件（必要）", "缺失影響音頻上傳、降噪、轉錄、AI 會議紀錄生成等基本功能"),
    "enhance": ("🟡 增強元件（可選）", "缺失只影響強效降噪、API Key 持久化、關鍵詞提取等附加功能"),
    "info": ("ℹ️ 參考資訊", ""),
}

for grp_key, (sec_title, sec_desc) in SECTIONS.items():
    items = {k: v for k, v in results.items() if v[2] == grp_key}
    if not items:
        continue
    st.divider()
    st.markdown(f"### {sec_title}")
    if sec_desc:
        st.caption(sec_desc)
    for item, (icon, msg, _) in items.items():
        c1, c2, c3 = st.columns([1, 3, 8])
        c1.markdown(f"## {icon}")
        c2.markdown(f"**{item}**")
        c3.caption(msg)

st.divider()
if st.button("🔄 重新檢查", key=f"btn_recheck_{st.session_state['health_run']}", use_container_width=False):
    st.session_state["health_run"] += 1
    st.rerun()