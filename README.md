# SD CivitAI Browser Helper

A feature-rich [CivitAI](https://civitai.com/) model browser extension for [Stable Diffusion WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui). Browse, search, download, and manage CivitAI models directly from the WebUI interface.

---

## Features Overview

### Browse Tab - Search & Discovery

- **Flexible Search** - Search by model name, username, or tag
- **Advanced Filters** - Filter by content type (Checkpoint, LORA, LoCon, DoRA, VAE, ControlNet, etc.), base model (SD 1.5, SDXL, Pony, Illustrious, NoobAI, Flux.1, SD 3.5, etc.), sort order, and time period
- **NSFW Toggle** - Show or hide NSFW content
- **Adjustable Page Size** - 5 to 100 cards per page
- **Cursor-Based Pagination** - Reliable page navigation for large result sets
- **Installed Indicator** - Green badge on models you already have
- **Search Config Persistence** - All search settings are saved and restored across sessions

### Model Cards

- Thumbnail preview with lazy loading
- Model name, base model, and metadata
- Selection checkbox for batch operations
- Hover animation with accent glow
- Video thumbnail support

### Model Details

- **Version Selector** - Choose from available model versions
- **File Selector** - Pick between multiple file variants (shows file size and format)
- **Custom Install Path** - Auto-populated with organized folder structure, editable
- **Single Download** - Download individual models with live progress
- **Favorite Toggle** - Add/remove models from your favorites list

### Batch Download

- **Select All / Deselect All** - Quickly select models (auto-skips already installed)
- **Download Selected** - Queue all selected models for download
- **Save Local Info** - Optionally cache model info and preview images locally during batch download

---

### Model Info Popup

Full-screen popup with detailed model information, accessible from Browse and Installed tabs.

**Header:**
- Model title linked to CivitAI page
- Creator name and content type
- Data source badge: `Online` / `Local`
- **Save Local** checkbox to cache all data offline

**Description Tab:**
- Full model description with embedded images
- Scrollable content within the popup

**Preview Images Tab:**
- Grouped by version (up to 5 versions)
- Each image shows:
  - Preview thumbnail
  - Prompt and negative prompt with **Copy** buttons
  - Generation parameters (steps, sampler, CFG scale, seed, size, model, clip skip)
  - **Send to txt2img** button - sends all generation parameters directly to txt2img

---

### Save Local (Offline Model Info)

Save complete model information locally for offline access. Useful when models may be taken down from CivitAI.

**What gets saved:**
- Model metadata (name, creator, type, description)
- All preview images (downloaded to local disk)
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
- Hierarchical folder navigation
- Auto-scans all model directories
- Click a folder to filter the model grid
- "All Models" option to show everything

**Model Grid (Right Panel):**
- Shows all installed models with thumbnails
- File size and folder path info
- Click to open model info popup (if CivitAI metadata available)
- Reads `.json` metadata files for CivitAI model identification

**Supported Model Types:**
Checkpoint, LORA, LoCon, DoRA, TextualInversion, VAE, ControlNet, Hypernetwork, Poses, Wildcards, Workflows, MotionModule

---

### Downloads Tab

- **Download Queue** with live progress display
- **Progress Bar** with download speed and ETA
- **Concurrent Downloads** - Download multiple models simultaneously (configurable 1-5)
- **Auto-Retry** - Up to 3 attempts with exponential backoff
- **Metadata Auto-Save** - `.json` metadata file saved alongside each model
- **Preview Image Save** - `.preview.png` cached for each download
- **Aria2 Support** - Optional faster, resumable downloads via Aria2
- **Clear Finished** - Remove completed/failed items from the queue

---

## Settings

Configurable in **Settings > CivitAI Browser**:

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
3. Paste: `https://github.com/acer1204/SD-Civitai-Browser-Helper.git`
4. Click **Install**
5. Restart SD WebUI

### Method 2: Manual
```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/acer1204/SD-Civitai-Browser-Helper.git sd-civitai-browser-new
```
Restart SD WebUI.

---

## Usage

1. Navigate to the **CivitAI Browser** tab in the WebUI
2. Enter a search query and click **Search** (or press Enter)
3. Use the **Filters** accordion to narrow results
4. Click a model card to view details, select a version and file, then click **Download**
5. For batch downloads: check model cards, then click **Download Selected**
6. Use **Model Info** button to view detailed information with preview images
7. Check **Save Local** to cache model info offline

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
