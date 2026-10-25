"""
Home.py — VoiceDoc AI 主頁 v4.7
結構：
1. 後台預載 Whisper 模型（靜默，不顯示訊息）
2. 標題
3. 四大功能介紹（四欄）
4. 系統特色
5. 私隱聲明（expander）
"""

import threading
import streamlit as st
from ui.layout import configure_page, render_header, render_sidebar

configure_page()
opts = render_sidebar()


def _warmup_model():
    try:
        from services.model_loader import preload_model
        preload_model(
            opts.get("whisper_model", "medium"),
            low_memory=opts.get("low_memory", False)
        )
    except Exception:
        pass


if not st.session_state.get("_model_warmed_up"):
    st.session_state["_model_warmed_up"] = True
    threading.Thread(target=_warmup_model, daemon=True).start()

render_header(
    "🎙️ VoiceDoc AI",
    "香港學校會議語音轉錄、詞庫管理與 AI 會議紀錄生成系統 v4.7"
)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 功能介紹
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 功能介紹")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("### 🎙️ 語音轉錄及會議紀錄生成")
    st.markdown("""
- 上傳 MP3 / MP4 / WAV / M4A / OGG / FLAC
- 自動降噪 + Whisper 轉錄（粵語 / 普通話 / 英語）
- 顯示實際轉錄進度與已處理時間
- 逐字稿即時檢視、修正與匯出
- AI 一鍵生成正式會議紀錄
- 支援議程模式及三種詳盡程度
""")
    st.page_link(
        "pages/1_語音轉錄及會議紀錄生成.py",
        label="▶ 開始轉錄及生成紀錄",
        icon="🎙️"
    )

with col2:
    st.markdown("### 📄 匯入逐字稿")
    st.markdown("""
- 貼上或上傳現有逐字稿（TXT / DOCX / PDF）
- 上傳情境文件提升生成質素
- 配合會議議程整理重點
- AI 直接生成會議紀錄
- 適合已有逐字稿或外部轉錄結果
""")
    st.page_link(
        "pages/2_匯入逐字稿.py",
        label="▶ 匯入逐字稿",
        icon="📄"
    )

with col3:
    st.markdown("### 🗂️ 歷史記錄")
    st.markdown("""
- 儲存所有會議紀錄
- 支援版本管理與還原
- 可重新下載 DOCX / TXT
- 方便追蹤不同修訂版本
- 一鍵清理暫存資料
""")
    st.page_link(
        "pages/3_歷史記錄.py",
        label="▶ 查看歷史",
        icon="🗂️"
    )

with col4:
    st.markdown("### 📚 詞庫管理")
    st.markdown("""
- 建立科組專屬詞庫
- 上傳教材 / 通告 / 課程文件自動提取詞語
- 支援詞庫匯出 / 匯入，方便交接
- 自動學習修正詞，改善常見錯字
- 提供修正頻率統計與高頻詞回寫詞庫
- 轉錄後推薦詞可逐項指定加入不同科組
""")
    st.page_link(
        "pages/4_詞庫管理.py",
        label="▶ 管理詞庫",
        icon="📚"
    )

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 系統特色
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 系統特色")

f1, f2, f3 = st.columns(3)

with f1:
    st.info(
        "**適合香港學校場景**\n\n"
        "支援粵語為主的會議錄音，並可配合學校行政、科組會議、學務、訓導等常見用語情境。"
    )

with f2:
    st.info(
        "**詞庫持續累積**\n\n"
        "除手動加入詞語外，系統亦可從文件提取關鍵詞、記錄修正詞配對，逐步提升不同科組的辨識準確度。"
    )

with f3:
    st.info(
        "**由逐字稿直達正式紀錄**\n\n"
        "從上傳錄音、修正逐字稿，到生成會議紀錄與匯出文件，可在同一系統內完成。"
    )

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 私隱聲明
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("🔒 私隱聲明 / Privacy Notice", expanded=False):
    st.markdown("""
**使用前請注意：**

1. **第三方 API 傳輸**  
   當使用 DeepSeek、Grok、OpenAI 或其他雲端 AI 供應商時，逐字稿及相關內容可能會經互聯網傳送至該供應商伺服器處理。

2. **本地模式**  
   如選擇本地模型或連接校內 / 本機相容伺服器，資料可保留於本地網絡，不經外部雲端。

3. **合規建議**
   - 請確保符合學校個人資料私隱政策及香港《個人資料（私隱）條例》
   - 建議在會議前提醒與會者，其發言內容將作語音轉錄及 AI 輔助整理
   - 避免在逐字稿中保留不必要的敏感個人資料

4. **資料保留**  
   會議紀錄及相關資料主要儲存於本機或指定環境，不會自動上傳至其他雲端服務。

---
*本工具由 VoiceDoc AI 提供。*
""")