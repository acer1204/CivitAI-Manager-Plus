# CivitAI Manager Plus

A feature-rich [CivitAI](https://civitai.com/) model manager extension for [Stable Diffusion WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui). Browse, search, download, and manage CivitAI models directly from the WebUI interface.

**[中文說明](#中文說明)**

---

## Features Overview

### Browse Tab - Search & Discovery

- **Flexible Search** - Search by model name, username, or tag
- **Advanced Filters** - Filter by content type (Checkpoint, LORA, LoCon, DoRA, VAE, ControlNet, etc.), base model (SD 1.5, SDXL, Pony, Illustrious, NoobAI, Flux.1, SD 3.5, etc.), sort order, and time period
- **NSFW Toggle** - Show or hide NSFW content
- **Adjustable Page Size** - 5 to 100 cards per page
- **Cursor-Based Pagination** - Reliable page navigation for large result sets
- **Installed Indicator** - Green badge on models you already have
- **Search Config Persistence** - All search settings (including Search by, Show NSFW, Save Local Info) are saved and restored across sessions

### Model Cards

- Thumbnail preview with lazy loading
- Video thumbnail support (auto-play)
- Model name, base model, and metadata
- Selection checkbox for batch operations
- Click card to open Model Info popup
- Hover animation with accent glow

### Batch Download

- **Select All / Deselect All** - Quickly select models (auto-skips already installed)
- **Download Selected** - Queue all selected models for background download
- **Save Local Info** - Optionally cache model info and preview images locally during batch download
- **Non-blocking** - Downloads run in background, you can continue browsing and adding more

---

### Model Info Popup

Full-screen popup with detailed model information, accessible from both Browse and Installed tabs by clicking any model card.

**Header:**
- Model title linked to CivitAI page
- Creator name and content type
- Data source badge: `Online` (blue) / `Local` (green)
- **Save Local** checkbox to cache all data offline

**Description Tab:**
- Full model description with embedded images
- Scrollable content within the popup

**Preview Images Tab:**
- Grouped by version (up to 5 versions)
- Each image shows:
  - Preview thumbnail (image or video)
  - Prompt and negative prompt with **Copy** buttons
  - Generation parameters (steps, sampler, CFG scale, seed, size, model, clip skip)
  - **Send to txt2img** button - sends all generation parameters directly to txt2img

---

### Save Local (Offline Model Info)

Save complete model information locally for offline access. Useful when models may be taken down from CivitAI.

**What gets saved:**
- Model metadata (name, creator, type, description)
- All preview images and videos (downloaded to local disk)
- Images embedded in model description
- Generation parameters (prompts, settings) for each preview image

**How it works:**
- Check the `Save Local` checkbox in the model info popup, or
- Enable the `Save Local Info` checkbox in Browse tab before batch downloading
- Saved data is stored in `model_info_cache/{model_id}/`
- When reopening model info, local data is used automatically (no API calls)
- Badge shows `Local` (green) when viewing cached data

---

### Favorites Tab

- Save frequently used models for quick access
- Card grid display with thumbnails
- Click to view model details
- Persistent storage in `civitai_favorites.json`

---

### Installed Models Tab

**Folder Tree (Left Panel):**
- Hierarchical folder navigation based on actual disk structure
- Shows `models/` and `embeddings/` directories
- Click any folder to directly load and display its models
- No need to scan first - just click and view

**Model Grid (Right Panel):**
- Shows installed models with thumbnails (image and video)
- Local preview files (`.preview.png`, `.preview.mp4`) loaded instantly
- Missing previews fetched in background and cached for next time
- File size and folder path info
- Click to open model info popup (if CivitAI metadata available)

---

### Downloads Tab

- **Download Queue** with live progress display (auto-refresh)
- **Progress Bar** with download speed and ETA
- **Concurrent Downloads** - Download multiple models simultaneously (configurable 1-5)
- **Auto-Retry** - Up to 5 attempts with adaptive backoff for CDN errors
- **Metadata Auto-Save** - `.json` metadata file saved alongside each model
- **Preview Auto-Save** - `.preview.png` or `.preview.mp4` saved alongside each model
- **Background Processing** - Downloads continue even while browsing other tabs
- **Clear Finished** - Remove completed/failed items from the queue

---

## Settings

Configurable in **Settings > CivitAI Manager Plus**:

| Setting | Default | Description |
|---------|---------|-------------|
| CivitAI API Key | (empty) | Personal API key for authenticated downloads |
| Auto-organize Downloads | ON | Organize by `base_model / author / model_name` |
| Max Concurrent Downloads | 2 | Parallel download limit (1-5) |
| Use Aria2 | ON | Faster, resumable downloads (fallback to HTTP) |
| Show NSFW by Default | OFF | Initial NSFW content visibility |
| HTTP Proxy | (empty) | Proxy URL (e.g., `http://127.0.0.1:7890`) |

---

## Installation

### Method 1: From URL (Recommended)
1. Open **Extensions** tab in SD WebUI
2. Go to **Install from URL**
3. Paste: `https://github.com/acer1204/SD-CivitAI-Manager-Plus.git`
4. Click **Install**
5. Restart SD WebUI

### Method 2: Manual
```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/acer1204/SD-CivitAI-Manager-Plus.git
```
Restart SD WebUI.

---

## Usage

1. Navigate to the **CivitAI Manager Plus** tab in the WebUI
2. Enter a search query and click **Search** (or press Enter)
3. Use the **Filters** accordion to narrow results
4. Click a model card to view detailed model info popup
5. For batch downloads: check model cards, then click **Download Selected**
6. Check **Save Local Info** to cache model info offline
7. Go to **Downloads** tab to monitor progress

---

## Requirements

- Stable Diffusion WebUI (AUTOMATIC1111 or compatible fork)
- Python 3.10+
- `requests` library (auto-installed)
- Optional: `aria2c` for accelerated downloads
- Optional: `send2trash` for safe file deletion

---

## License

MIT License

---

# 中文說明

## CivitAI Manager Plus

功能豐富的 [CivitAI](https://civitai.com/) 模型管理擴充功能，適用於 [Stable Diffusion WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui)。直接在 WebUI 介面中瀏覽、搜尋、下載和管理 CivitAI 模型。

---

## 功能概覽

### Browse 分頁 - 搜尋與發現

- **彈性搜尋** - 支援以模型名稱、使用者名稱或標籤搜尋
- **進階篩選** - 依內容類型（Checkpoint、LORA、LoCon、DoRA、VAE、ControlNet 等）、基底模型（SD 1.5、SDXL、Pony、Illustrious、NoobAI、Flux.1、SD 3.5 等）、排序方式及時間範圍篩選
- **NSFW 開關** - 顯示或隱藏 NSFW 內容
- **可調每頁數量** - 每頁 5 至 100 張卡片
- **游標分頁** - 大量結果也能可靠翻頁
- **已安裝標示** - 已下載的模型顯示綠色徽章
- **搜尋設定記憶** - 所有搜尋設定（含 Search by、Show NSFW、Save Local Info）重啟後自動還原

### 模型卡片

- 縮圖預覽（支援圖片和影片自動播放）
- 模型名稱、基底模型等資訊
- 勾選框供批量操作
- 點擊卡片直接開啟 Model Info 彈窗
- 滑鼠懸停動畫效果

### 批量下載

- **全選 / 取消全選** - 快速選取（自動跳過已安裝）
- **下載已選** - 將所有選取的模型加入背景下載佇列
- **本地保存資訊** - 可選擇在批量下載時同時快取模型資訊和預覽圖
- **非阻塞** - 下載在背景執行，可繼續瀏覽和新增下載

---

### Model Info 彈窗

全螢幕彈窗，顯示詳細模型資訊。在 Browse 和 Installed 分頁中點擊任何模型卡片即可開啟。

**標題區：**
- 模型名稱（連結至 CivitAI 頁面）
- 作者與內容類型
- 資料來源徽章：`Online`（藍色）/ `Local`（綠色）
- **Save Local** 勾選框，一鍵離線快取所有資料

**Description 分頁：**
- 完整模型說明（含嵌入圖片）
- 可捲動的內容區域

**Preview Images 分頁：**
- 依版本分組（最多 5 個版本）
- 每張圖片顯示：
  - 預覽縮圖（圖片或影片）
  - 正向提示詞與反向提示詞，附 **Copy** 按鈕
  - 生成參數（steps、sampler、CFG scale、seed、size、model、clip skip）
  - **Send to txt2img** 按鈕 - 將所有生成參數直接傳送至 txt2img

---

### 本地保存（離線模型資訊）

將完整模型資訊保存至本地，供離線存取。適用於模型可能從 CivitAI 下架的情況。

**保存內容：**
- 模型中繼資料（名稱、作者、類型、說明）
- 所有預覽圖片和影片（下載至本地磁碟）
- 說明中嵌入的圖片
- 每張預覽圖的生成參數（提示詞、設定）

**使用方式：**
- 在 Model Info 彈窗中勾選 `Save Local`，或
- 在 Browse 分頁批量下載前勾選 `Save Local Info`
- 資料儲存於 `model_info_cache/{model_id}/`
- 重新開啟模型資訊時自動使用本地資料（不需 API 呼叫）
- 使用本地資料時徽章顯示 `Local`（綠色）

---

### Favorites 分頁

- 收藏常用模型以便快速存取
- 卡片格線顯示，附縮圖
- 點擊查看模型詳情
- 持久儲存於 `civitai_favorites.json`

---

### Installed 分頁 - 已安裝模型

**資料夾樹（左側面板）：**
- 階層式資料夾導覽，反映實際磁碟結構
- 顯示 `models/` 和 `embeddings/` 目錄
- 點擊任何資料夾直接載入並顯示其中的模型
- 不需先掃描 — 點擊即可檢視

**模型格線（右側面板）：**
- 顯示已安裝模型及縮圖（支援圖片和影片）
- 本地預覽檔案（`.preview.png`、`.preview.mp4`）瞬間載入
- 缺少的預覽圖在背景自動抓取並快取
- 顯示檔案大小和資料夾路徑
- 點擊開啟 Model Info 彈窗（需有 CivitAI 中繼資料）

---

### Downloads 分頁

- **下載佇列** 即時進度顯示（自動刷新）
- **進度條** 顯示下載速度和預估時間
- **並行下載** - 同時下載多個模型（可設定 1-5 個）
- **自動重試** - 最多 5 次，CDN 錯誤自動延長等待時間
- **自動保存中繼資料** - 模型旁自動保存 `.json` 檔案
- **自動保存預覽** - 模型旁自動保存 `.preview.png` 或 `.preview.mp4`
- **背景處理** - 瀏覽其他分頁時下載繼續進行
- **清除已完成** - 移除已完成/失敗的項目

---

## 設定

在 **Settings > CivitAI Manager Plus** 中設定：

| 設定 | 預設值 | 說明 |
|------|--------|------|
| CivitAI API Key | （空） | 個人 CivitAI API 金鑰，部分下載需要認證 |
| Auto-organize Downloads | 開啟 | 依 `基底模型 / 作者 / 模型名稱` 自動整理 |
| Max Concurrent Downloads | 2 | 並行下載上限（1-5） |
| Use Aria2 | 開啟 | 使用 Aria2 加速下載（不可用時自動退回 HTTP） |
| Show NSFW by Default | 關閉 | 預設是否顯示 NSFW 內容 |
| HTTP Proxy | （空） | HTTP 代理 URL（例如 `http://127.0.0.1:7890`） |

---

## 安裝

### 方法一：從 URL 安裝（推薦）
1. 開啟 SD WebUI 的 **Extensions** 分頁
2. 前往 **Install from URL**
3. 貼上：`https://github.com/acer1204/SD-CivitAI-Manager-Plus.git`
4. 點擊 **Install**
5. 重啟 SD WebUI

### 方法二：手動安裝
```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/acer1204/SD-CivitAI-Manager-Plus.git
```
重啟 SD WebUI。

---

## 使用方式

1. 在 WebUI 中切換到 **CivitAI Manager Plus** 分頁
2. 輸入搜尋關鍵字並點擊 **Search**（或按 Enter）
3. 使用 **Filters** 摺疊面板縮小搜尋範圍
4. 點擊模型卡片查看詳細資訊彈窗
5. 批量下載：勾選模型卡片，然後點擊 **Download Selected**
6. 勾選 **Save Local Info** 可將模型資訊離線快取
7. 前往 **Downloads** 分頁查看下載進度

---

## 系統需求

- Stable Diffusion WebUI（AUTOMATIC1111 或相容版本）
- Python 3.10+
- `requests` 函式庫（自動安裝）
- 可選：`aria2c` 加速下載
- 可選：`send2trash` 安全刪除檔案

---

## 授權

MIT License
