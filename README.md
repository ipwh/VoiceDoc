# VoiceDoc AI 🎙️
**香港學校會議語音轉錄、詞庫管理與 AI 會議紀錄生成系統**

版本：v4.7 · 更新日期：2026-05-04

---

## 目錄
1. [系統簡介](#系統簡介)
2. [功能一覽](#功能一覽)
3. [系統需求](#系統需求)
4. [安裝步驟](#安裝步驟)
5. [啟動方式](#啟動方式)
6. [使用指南](#使用指南)
7. [Sidebar 設定說明](#sidebar-設定說明)
8. [Whisper 模型選擇](#whisper-模型選擇)
9. [AI 供應商對比](#ai-供應商對比)
10. [檔案結構](#檔案結構)
11. [常見問題](#常見問題)
12. [私隱合規說明](#私隱合規說明)
13. [版本更新記錄](#版本更新記錄)

---

## 系統簡介

VoiceDoc AI 專為香港學校場景設計，支援將會議錄音或現有逐字稿轉換為結構化的繁體中文會議紀錄，並可配合詞庫、議程、情境文件及 AI 供應商設定，提高整理質素與後續匯出效率。

**核心流程：**

```text
語音檔案 / 逐字稿
→ 格式處理 / 情境文件提取
→ Whisper 轉錄（本地）
→ AI 整理會議紀錄
→ DOCX / TXT / SRT 匯出
→ 歷史記錄保存
```

**支援語言：** 粵語、普通話、英語、自動偵測。

---

## 功能一覽

### 🎙️ 語音轉錄
- 支援 MP3、MP4、WAV、M4A、OGG、FLAC。
- 內建格式轉換、時長估算及降噪處理，支援快速 / 標準 / 強效濾波，並可選用 DeepFilterNet。
- 以 `services/model_loader.py` 統一載入 faster-whisper 模型，模型會下載至本機使用者資料夾，而非專案目錄。
- 首頁會背景預載目前所選 Whisper 模型，以縮短第一次實際轉錄等待時間。

### 📄 匯入逐字稿
- 可直接貼上逐字稿文字，或上傳 TXT / DOCX 檔案。
- 可一併載入情境文件與會議議程，再由 AI 按議程順序整理正式會議紀錄。
- 適合已由其他工具完成轉錄，或已有人工整理逐字稿的情況。

### 🤖 AI 會議紀錄生成
- 支援簡略 / 標準 / 詳盡三種詳盡程度。
- 詳盡模式會自動啟用兩階段生成流程，以提升長篇逐字稿的結構化與完整度。
- 可附加補充指示、會議類型、情境文件與議程內容，令生成結果更貼近香港學校行政場景。

### 📚 詞庫管理
- 支援科組專屬詞庫、文件抽詞、手動加入、匯出 / 匯入及修正詞學習。
- 支援**自訂科組**：可按學校實際需要建立如「升學及就業輔導組」、「價值教育組」、「STEAM 組」等校本科組，各組擁有獨立詞庫。
- 詞庫推薦引擎會從逐字稿中找出高頻新詞，協助把常見校本術語逐步回寫到指定科組詞庫。
- 已涵蓋科目：中文科、英文科、數學科、歷史科、地理科、宗教科、公民與社會發展科（C&SD）、公民、經濟與社會科（CES）、BAFS、資訊科技、體育科、學校行政等。

### 🗂️ 歷史記錄與健康檢查
- 會議紀錄可儲存至歷史記錄，支援版本管理與重新下載。
- 系統健康檢查頁可檢查 FFmpeg、Python 套件、Whisper 模型狀態及 API 可達性。

---

## 系統需求

| 項目 | 最低需求 | 建議配置 |
|------|---------|---------|
| 作業系統 | Windows 10 | Windows 11 |
| Python | 3.10 | 3.11 |
| RAM | 8 GB | 16 GB |
| 儲存空間 | 8 GB | 15 GB |
| CPU | 4 核心 | 8 核心 |
| 網絡 | 首次下載模型需要 | 穩定寬頻 |
| GPU | 非必需 | 有 NVIDIA GPU 可自行進階調整 |

> **注意：** 目前預設策略偏向穩定性，`model_loader.py` 以 CPU 為主，避免不同 Windows 電腦因 CUDA / DLL 差異導致啟動失敗。

---

## 安裝步驟

### 首次安裝（每台電腦只需做一次）

**1. 安裝 Python 3.10 或 3.11**

- 下載：[Python 官網](https://www.python.org/downloads/)
- 安裝時務必勾選 **Add Python to PATH**
- 安裝完成後，可在命令提示字元輸入以下指令確認：

```text
python --version
pip --version
```

若能顯示版本號，代表 Python 已可正常使用。

---

**2. 安裝 FFmpeg**

FFmpeg 是本系統處理音訊格式轉換的核心工具，必須正確安裝並加入系統 PATH 才能使用轉錄功能。

#### 步驟一：下載 FFmpeg

1. 前往 https://www.gyan.dev/ffmpeg/builds/
2. 在 **release builds** 區域，下載 `ffmpeg-release-essentials.zip`

> 或直接前往 https://ffmpeg.org/download.html，選擇 **Windows** → **Windows builds from gyan.dev**。

#### 步驟二：解壓縮

1. 將下載的 `.zip` 檔案解壓縮
2. 建議解壓到一個**不會移動的固定位置**，例如：

```text
C:\ffmpeg\
```

3. 解壓後的資料夾結構應如下：

```text
C:\ffmpeg\
├── bin\
│   ├── ffmpeg.exe
│   ├── ffplay.exe
│   └── ffprobe.exe
├── doc\
└── presets\
```

#### 步驟三：將 FFmpeg 加入系統 PATH

1. 按下 `Win + S`，搜尋「**環境變數**」，點選「**編輯系統環境變數**」
2. 在「系統內容」視窗中，點擊右下角「**環境變數(N)...**」
3. 在「**系統變數**」區域（下半部），找到名為 `Path` 的變數，雙擊開啟
4. 點擊「**新增**」，輸入 FFmpeg 的 `bin` 資料夾完整路徑：

```text
C:\ffmpeg\bin
```

5. 連續點擊「確定」關閉所有視窗

#### 步驟四：驗證安裝

1. 按下 `Win + R`，輸入 `cmd`，按 Enter 開啟命令提示字元
2. 輸入以下指令：

```text
ffmpeg -version
```

3. 若安裝成功，應看到類似以下輸出：

```text
ffmpeg version 7.x.x Copyright (c) 2000-2024 the FFmpeg developers
built with gcc ...
```

> **注意：**
> - 若顯示「`ffmpeg` 不是內部或外部命令」，表示 PATH 未正確設定，請重新檢查步驟三。
> - 修改 PATH 後需要**重新開啟**命令提示字元才會生效。
> - 若電腦同時裝有其他版本的 FFmpeg（例如透過 Chocolatey 安裝），請確保 `C:\ffmpeg\bin` 排列在 PATH 的**較前位置**，避免版本衝突。

---

**3. 執行 `setup.bat`**

- 自動建立本機虛擬環境：`C:\Users\你的名字\VoiceDoc_env\venv`
- 自動建立 Whisper 模型目錄：`C:\Users\你的名字\VoiceDoc_env\whisper_models`
- 自動安裝 `requirements.txt` 內的依賴套件
- 自動建立 `.env` 範本及 `venv_path.txt`

---

**4. 編輯 `.env`**

填入你的 API Key，可保留以下預設值：

```text
DEFAULT_WHISPER_MODEL=medium
DEFAULT_LANGUAGE=yue
VOICEDOC_MODEL_DIR=C:\Users\你的名字\VoiceDoc_env\whisper_models
HF_HOME=C:\Users\你的名字\VoiceDoc_env\hf_cache
TRANSFORMERS_CACHE=C:\Users\你的名字\VoiceDoc_env\hf_cache
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
XAI_API_KEY=
```

---

### API Key 申請

| 供應商 | 申請網址 | 費用 |
|--------|---------|------|
| DeepSeek | https://platform.deepseek.com | 低成本 |
| Grok (xAI) | https://console.x.ai | 低成本 |
| OpenAI GPT-4o | https://platform.openai.com | 較高 |

---

## 啟動方式

每次使用時，只需雙擊 `run.bat`。

```text
雙擊 run.bat
→ 載入 venv
→ 載入 .env
→ 設定本機 Whisper 模型路徑
→ 啟動 Streamlit
→ 瀏覽器開啟 http://localhost:8501
```

停止程式時，在命令提示字元視窗按 `Ctrl + C` 即可。

---

## 使用指南

### 1. 語音轉錄及會議紀錄生成
1. 前往「🎙️ 語音轉錄及會議紀錄生成」頁。
2. 上傳語音檔，系統會先轉換格式、估算時長，再進行降噪處理。
3. 按需要加入情境文件、議程或手動詞彙，然後開始轉錄。
<<<<<<< HEAD
4. 轉錄完成後可檢視逐字稿並修正內容，再生成會議紀錄。
=======
4. 轉錄完成後可檢視逐字稿、修正內容，再生成會議紀錄。
>>>>>>> d525784ef976ca273d4c639270ea37138ac01f0f
5. 生成結果可下載或儲存到歷史記錄。

### 2. 匯入逐字稿生成會議紀錄
1. 前往「📄 匯入逐字稿」頁。
2. 貼上逐字稿，或上傳 TXT / DOCX 檔。
3. 可額外加入情境文件與會議議程，提高輸出一致性。
4. 點擊生成後，AI 會依設定整理成正式會議紀錄。

### 3. 詞庫管理
1. 前往「📚 詞庫管理」頁。
2. 選擇科組，手動加入詞語，或由教材 / 通告 / PDF 自動提取詞語。
3. 如需建立新科組，可在「建立自訂科組」欄位填入名稱後按「建立科組」。
4. 可把詞庫匯出作備份或交接用途，亦可匯入現有詞庫檔案。
5. 轉錄過程中出現的高頻修正詞，可回寫到指定科組詞庫。

### 4. 系統健康檢查
- 可檢查 FFmpeg、核心套件、增強套件、Whisper 模型快取與 API 連線狀態。
- 適合部署後驗證新電腦是否已正確安裝。

---

## Sidebar 設定說明

Sidebar 已整合為 v4.7 配置模式，採用 `_cfg` 狀態保存機制，切頁時設定不會輕易重置。

### 🤖 AI 設定
- AI 供應商
- API Key
- 自定義 OpenAI 相容 Base URL / Model
<<<<<<< HEAD
- 本地 / 雲端模式提示
=======
- 本地 / 雲端模式提示。
>>>>>>> d525784ef976ca273d4c639270ea37138ac01f0f

### 📋 會議資訊
- 會議名稱
- 會議日期
- 地點
- 出席人員
- 會議類型
- 會議紀錄格式

### 💬 補充指示
可加入如「請特別詳細記錄財務部分」或「改用點列式」等額外要求。

### 📚 詞彙管理
可手動輸入常用詞，作為 Whisper prompt 與後續 AI 生成的語境補充。

> **補充：** 語音轉錄設定與詳盡程度已不再完全依賴 Sidebar，部分設定已移到頁面流程內，配合各頁用途使用。

---

## Whisper 模型選擇

| 模型 | 速度 | 準確度 | 記憶體需求 | 適用場景 |
|------|------|--------|-----------|---------|
| small | 最快 | 一般 | 約 1 GB | 短錄音、草稿用途 |
| medium | 中等 | 良好 | 約 2.5 GB | 大多數學校會議，預設推薦 |
| large-v3 | 較慢 | 最佳 | 約 5 GB | 正式會議、口音複雜、需重點存檔 |

**建議：**
- 一般學校會議先用 `medium`
- 若覆蓋率偏低、術語較多、錄音品質一般，可改用 `large-v3`
- 舊電腦或短錄音可先用 `small`

---

## AI 供應商對比

| 供應商 | 模型 | 速度 | 費用 | 適合場景 |
|--------|------|------|------|---------|
| DeepSeek | deepseek-chat | 快 | 低 | 日常主力 |
| Grok (xAI) | grok-3 | 快 | 低 | 備用選擇 |
| OpenAI | gpt-4o | 中 | 較高 | 對輸出質素要求最高 |
| 自定義 (OpenAI 相容) | 自填 | 視伺服器而定 | 自定 | 校內 / 本地部署 |

以上供應商名稱與預設模型來自目前 `services/minutes_service.py` 設定。

---

## 檔案結構

### 一、專案主資料夾

```text
VoiceDoc/
│
├── Home.py
│   └── 主頁，背景預載 Whisper 模型、顯示四大功能與私隱聲明
│
├── requirements.txt
│   └── Python 套件清單
│
├── setup.bat
│   └── 首次安裝程式，每台電腦執行一次；建立 venv、模型目錄與 .env
│
├── run.bat
│   └── 日常啟動程式；載入 venv、.env 與本機模型快取路徑
│
├── venv_path.txt
│   └── 虛擬環境路徑標記檔，由 setup.bat 生成
│
├── .env
│   └── API Key 與執行環境設定（請勿上傳到 GitHub）
│
├── .streamlit/
│   └── config.toml
│       └── Streamlit 設定
│
├── pages/
│   ├── 1_語音轉錄及會議紀錄生成.py
│   │   └── 上傳語音、轉錄、生成會議紀錄的主流程頁
│   │
│   ├── 2_匯入逐字稿.py
│   │   └── 直接上傳 / 貼上逐字稿，配合情境文件與議程生成會議紀錄
│   │
│   ├── 3_歷史記錄.py
│   │   └── 查看歷史版本、重新下載與還原會議紀錄
│   │
│   ├── 4_詞庫管理.py
│   │   └── 管理科組詞庫、自訂科組、文件抽詞、匯出 / 匯入與修正詞統計
│   │
│   └── 5_系統健康檢查.py
│       └── 檢查 FFmpeg、模型、套件、API 可達性與環境狀態
│
├── services/
│   ├── model_loader.py
│   │   └── faster-whisper 模型統一載入、快取與本機下載路徑控制
│   │
│   ├── audio_service.py
│   │   └── 音訊格式轉換、降噪、暫存管理、音檔刪除與私隱審計
│   │
│   ├── transcription_service.py
│   │   └── 轉錄整合層
│   │
│   ├── minutes_service.py
│   │   └── AI 會議紀錄生成、供應商設定、兩階段詳盡模式
│   │
│   ├── chunked_minutes.py
│   │   └── 長逐字稿分段生成支援
│   │
│   ├── privacy_guard.py
│   │   └── 本地 PII 偵測與遮罩
│   │
│   ├── key_manager.py
│   │   └── API Key 加密儲存
│   │
│   ├── vocab_manager.py
│   │   └── 詞庫存取、科目別名、自訂科組、修正詞保存與高頻詞回寫
│   │
│   ├── vocab_recommender.py
│   │   └── 從逐字稿推薦高頻新詞
│   │
│   ├── export_service.py
│   │   └── DOCX / TXT / SRT 匯出
│   │
│   ├── keyword_service.py
│   │   └── 文件關鍵詞提取
│   │
│   ├── checkpoint_service.py
│   │   └── 任務 checkpoint / 中斷恢復
│   │
│   ├── history_service.py
│   │   └── 歷史記錄讀寫
│   │
│   └── config.py
│       └── 系統預設值、資料目錄與環境設定
│
├── core/
│   ├── pipeline_transcribe.py
│   │   └── Whisper 轉錄核心流程、prompt 建立、VAD 與結果組裝
│   │
│   ├── pipeline_minutes.py
│   │   └── 會議紀錄生成流程協調
│   │
│   ├── pipeline_keywords.py
│   │   └── 情境文件抽詞與 prompt 內容整理
│   │
│   └── state.py
│       └── Session state 常數與初始化
│
├── ui/
│   ├── layout.py
│   │   └── 頁面配置、Sidebar、共用讀檔函式
│   │
│   ├── editors.py
│   │   └── 逐字稿 / 會議紀錄編輯器元件
│   │
│   └── widgets.py
│       └── 共用 UI 元件
│
└── data/
    ├── agenda_templates.py
    │   └── 議程範本
    │
    ├── vocab_base.txt
    │   └── 基礎詞庫
    │
    ├── vocab/
    │   └── 各科組詞庫檔（如 vocab_history.txt、vocab_admin.txt、vocab_custom_*.txt）
    │
    ├── custom_subjects.json
    │   └── 自訂科組設定（由詞庫管理頁建立與維護）
    │
    └── corrections.json
        └── 修正詞配對資料
```

### 二、本機使用者資料夾（不建議同步）

```text
C:\Users\你的名字\VoiceDoc_env\
├── venv\
│   └── Python 虛擬環境
│
└── whisper_models\
    └── faster-whisper 模型下載與快取位置
```

這個本機資料夾由 `setup.bat` / `run.bat` 管理，目的是避免把模型與 venv 放進 OneDrive 或專案同步資料夾內。

### 三、應用程式資料與運行資料

```text
~\.voicedoc\
├── history\
│   └── 已儲存的會議紀錄與版本資料
│
├── .keystore.enc
│   └── API Key 加密儲存檔
│
└── privacy_audit.log
    └── 私隱處理審計日誌
```

另有暫存音檔與 checkpoint 目錄，會由音訊服務與 checkpoint 服務在執行期間自動建立及清理。

---

## 常見問題

**Q1. 為什麼第一次轉錄比較慢？**
A：首次使用某個 Whisper 模型時，系統需要先下載模型到 `C:\Users\你的名字\VoiceDoc_env\whisper_models`，之後便會重用本機快取。

**Q2. 為什麼模型不放在專案資料夾？**
A：目前設計刻意把 venv 與模型放在 `%USERPROFILE%\VoiceDoc_env`，以避免 GitHub 同步大型模型檔與虛擬環境，減少損壞與衝突。

**Q3. API Key 會不會每次重啟都消失？**
A：`.env` 會在啟動時自動載入，而部分情況亦可由 `key_manager.py` 加密儲存 API Key，因此不必只依賴 session state。

**Q4. 轉錄後為什麼有些片段被移除？**
A：語音轉錄頁含有疑似亂碼 / 幻覺片段過濾邏輯，會自動移除明顯不合理的片段，以減少 Whisper hallucination 對逐字稿的污染。

**Q5. 舊電腦很慢，應該怎樣選模型？**
A：可先用 `small`；若準確度不足、術語較多，再改用 `medium` 或 `large-v3` 重試。

<<<<<<< HEAD
**Q6. 為什麼系統健康檢查顯示某些套件為可選？**
=======
**Q6. 為什麼系統健康檢查顯示某些套件為可選？**  
>>>>>>> d525784ef976ca273d4c639270ea37138ac01f0f
A：像 `cryptography`、`deepfilternet`、`openai` 都屬增強功能，缺少時只會影響特定附加能力，不會令整個系統完全不能用。

**Q7. 如何為其他科組或功能組別建立詞庫？**
A：前往「📚 詞庫管理」頁，在「建立自訂科組」欄位填入科組名稱並按「建立科組」，系統會自動建立專屬詞庫檔案。之後該科組會出現在所有詞庫選單及匯入目標中。

---

## 私隱合規說明

VoiceDoc AI 已加入多項本地優先與資料最小化設計，包括音檔轉錄完成後刪除、PII 偵測、私隱審計記錄及本地模型使用等安排。

| 合規方向 | 系統做法 |
|---------|---------|
| 資料最小化 | 轉錄後刪除音訊檔案，減少不必要保留。 |
| 本地優先 | Whisper 模型於本機載入與執行，不依賴雲端 ASR。 |
| 人為監督 | 逐字稿可人工修正後再生成會議紀錄。 |
| 透明告知 | 主頁已提供私隱聲明，說明第三方 API 傳輸風險。 |
| 審計追蹤 | 私隱相關操作可寫入 `privacy_audit.log`。 |
| 機密資料保護 | API Key 可由 `key_manager.py` 進行加密儲存。 |

> **注意：** 若使用 DeepSeek、OpenAI、Grok 等雲端 LLM，逐字稿內容仍會傳送到第三方 API 處理，請按學校政策決定是否需先做匿名化或改用本地模式。

---

## 版本更新記錄

### v4.7（2026-05-04）
- 詞庫管理新增自訂科組功能，用家可自行建立校本科組並累積專屬詞庫。
- 修正匯入詞庫時未知科組不再強制 fallback 至「學校行政」，支援自動建立缺少科組。
- `vocab_manager.py` 重構，科組改為「內建 + 自訂」動態合併，相容現有別名與 fallback 邏輯。
- 移除系統內說話人分離功能相關選項。

### v4.6（2026-05-03）
- 主頁改為使用 `services/model_loader.py` 進行 Whisper 背景預載。
- 新增 / 整合本機 Whisper 模型路徑管理，模型統一放到 `%USERPROFILE%\VoiceDoc_env\whisper_models`。
- 補強詞庫管理頁，加入詞庫匯出 / 匯入、科組詞庫與高頻詞回寫流程。
- 加入系統健康檢查頁，檢查 FFmpeg、核心 / 增強套件、模型與 API 狀態。
- Sidebar 與頁面流程進一步重整，詳盡程度與部分轉錄設定移到頁面內操作。

### v4.5（2026-05-02）
- `pipeline_transcribe.py` 改以 `services/model_loader.py` 載入 faster-whisper 模型。
- Whisper `initial_prompt` 改用語境描述句策略，而非單純詞表堆疊。
- 語音轉錄頁加入更完整的語音處理、議程、情境設定及中斷恢復流程。

### v4.x 其他改進
- 匯入逐字稿頁支援情境文件、議程與可編輯逐字稿流程。
- 詞庫推薦與修正詞統計持續強化。
- AI 會議紀錄詳盡模式支援兩階段生成，長逐字稿穩定性提升。

---

*VoiceDoc AI 由本地 Whisper 轉錄、詞庫優化與 AI 會議紀錄生成組成，適合香港學校會議、科組會議及行政用途。*
