"""
core/errors.py
統一錯誤顯示與提示文字。
"""
import streamlit as st

MSGS = {
    "no_audio":      "⬆️ 請先在步驟①上傳音頻檔案",
    "no_api_key":    "⚠️ 請在側欄填入 LLM API Key",
    "no_transcript": "⬆️ 請先完成步驟③轉錄",
    "no_import_txt": "⬆️ 請先輸入或上傳逐字稿",
    "model_load":    "❌ 模型載入失敗，請檢查 requirements.txt 是否安裝完整",
}

def show(key: str, extra: str = ""):
    msg = MSGS.get(key, key)
    st.info(msg + (f"\n{extra}" if extra else ""))

def show_error(e: Exception, context: str = ""):
    label = f"❌ {context}：" if context else "❌ "
    st.error(f"{label}{e}")
