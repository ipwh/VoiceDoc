"""
services/key_manager.py — API Key 安全儲存 v1.0
優先次序：
  1. 環境變數（伺服器部署 / Streamlit Cloud st.secrets）
  2. 本機加密檔案（基於機器 UUID 派生密鑰）
  3. 系統 keyring（Windows Credential Manager / macOS Keychain）
  4. Fallback：明文 session（不建議，已有舊有行為）
"""
import os
import base64
import hashlib
import json
from pathlib import Path
from services.config import DATA_DIR

_KEY_STORE_PATH = os.path.join(DATA_DIR, ".keystore.enc")
_SALT           = b"voicedoc_hk_school_2025"   # 固定 salt（非密碼學用途，僅防止直接讀取）


def _derive_machine_key() -> bytes:
    """
    從機器 UUID 派生 32-byte Fernet 密鑰。
    相同電腦結果一致，跨機器不同（Key 無法跨機器解密）。
    """
    machine_id = ""
    try:
        # Windows
        import subprocess
        r = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True, text=True, timeout=3
        )
        lines = [l.strip() for l in r.stdout.split("\n") if l.strip() and "UUID" not in l]
        if lines:
            machine_id = lines[0]
    except Exception:
        pass

    if not machine_id:
        try:
            # macOS / Linux
            with open("/etc/machine-id") as f:
                machine_id = f.read().strip()
        except Exception:
            pass

    if not machine_id:
        # Fallback：用 hostname + 用戶名
        import socket, getpass
        machine_id = socket.gethostname() + getpass.getuser()

    raw = machine_id.encode() + _SALT
    key_bytes = hashlib.pbkdf2_hmac("sha256", raw, _SALT, iterations=100_000, dklen=32)
    return base64.urlsafe_b64encode(key_bytes)


def _load_keystore() -> dict:
    if not os.path.exists(_KEY_STORE_PATH):
        return {}
    try:
        from cryptography.fernet import Fernet, InvalidToken
        fernet = Fernet(_derive_machine_key())
        with open(_KEY_STORE_PATH, "rb") as f:
            encrypted = f.read()
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except Exception:
        return {}


def _save_keystore(store: dict) -> bool:
    try:
        from cryptography.fernet import Fernet
        os.makedirs(DATA_DIR, exist_ok=True)
        fernet = Fernet(_derive_machine_key())
        encrypted = fernet.encrypt(json.dumps(store, ensure_ascii=False).encode())
        with open(_KEY_STORE_PATH, "wb") as f:
            f.write(encrypted)
        return True
    except Exception:
        return False


def store_api_key(provider: str, api_key: str) -> bool:
    """
    儲存 API Key（先嘗試 keyring，fallback 至加密檔案）。
    回傳是否成功。
    """
    if not api_key or not provider:
        return False
    # 1. 嘗試系統 keyring
    try:
        import keyring
        keyring.set_password("VoiceDocAI", provider, api_key)
        return True
    except Exception:
        pass
    # 2. Fernet 加密本地檔案
    store = _load_keystore()
    store[provider] = api_key
    return _save_keystore(store)


def get_api_key(provider: str) -> str:
    """
    按優先順序取得 API Key：
    環境變數 → keyring → 加密檔案 → 空字串
    """
    # 1. 環境變數（最高優先，適合 Streamlit Cloud）
    env_var = provider.upper().replace(" ", "_").replace("(", "").replace(")", "") + "_API_KEY"
    env_val = os.environ.get(env_var, "")
    if env_val:
        return env_val

    # 2. 嘗試 st.secrets（Streamlit Cloud）
    try:
        import streamlit as st
        secret_key = provider.lower().replace(" ", "_")
        val = st.secrets.get(secret_key, {}).get("api_key", "")
        if val:
            return val
    except Exception:
        pass

    # 3. 系統 keyring
    try:
        import keyring
        val = keyring.get_password("VoiceDocAI", provider)
        if val:
            return val
    except Exception:
        pass

    # 4. 加密本地檔案
    store = _load_keystore()
    return store.get(provider, "")


def delete_api_key(provider: str) -> bool:
    """刪除指定供應商的 API Key"""
    deleted = False
    try:
        import keyring
        keyring.delete_password("VoiceDocAI", provider)
        deleted = True
    except Exception:
        pass
    store = _load_keystore()
    if provider in store:
        del store[provider]
        _save_keystore(store)
        deleted = True
    return deleted


def mask_key_display(api_key: str) -> str:
    """顯示用遮罩：sk-...xxxx（最後 4 字）"""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    prefix = api_key[:3] if api_key[2] == "-" else api_key[:2]
    return f"{prefix}-{'*' * 16}{api_key[-4:]}"


def is_cryptography_available() -> bool:
    """檢查 cryptography 套件是否可用"""
    try:
        from cryptography.fernet import Fernet
        return True
    except ImportError:
        return False
