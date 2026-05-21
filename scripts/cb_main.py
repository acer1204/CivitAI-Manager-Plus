"""CivitAI Manager Plus - Main UI for Stable Diffusion WebUI."""

import sys
import os
# Add this extension's scripts dir to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
import html as html_mod
import json
import random
import threading
from modules import script_callbacks, shared
from modules.paths import models_path
from cb_api import (
    CivitAIClient, make_model_cards_html, scan_installed_models,
    flatten_to_version_items,
    get_model_folder, build_install_path, clean_folder_name,
    load_favorites, save_favorites, toggle_favorite, CONTENT_TYPE_FOLDERS
)
from cb_downloader import DownloadManager, delete_model, _format_size

# Singletons
api = CivitAIClient()
dl_manager = DownloadManager()

# State
_current_page = 1
_total_pages = 1
_last_search_items = []   # store search results for Select All
_selected_model_ids = set()  # track selected model IDs for batch download
_selected_installed_paths = set()  # track selected installed model paths for batch delete
_installed_files = set()
_installed_hashes = set()
_installed_model_ids = set()
_last_base_model_filter = []   # base_model filter used in the last search
_page_cursors = {}  # page_number -> nextCursor from that page's response

# Local model info storage - use extension directory for reliability
_EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_INFO_DIR = os.path.join(_EXT_DIR, "model_info_cache")
_model_data_cache = {}  # Temporary cache: model_id -> {"model_data": ..., "version_images": ...}

# Search config persistence
_SEARCH_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "search_config.json")


def _save_search_config(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local=False):
    """Save last search configuration to file."""
    config = {
        "query": query or "",
        "search_type": str(search_type) if search_type else "Model name",
        "content_type": content_type if content_type else [],
        "base_model": base_model if base_model else [],
        "sort_type": sort_type or "Highest Rated",
        "period": period or "AllTime",
        "nsfw": True if nsfw else False,
        "cards_per_page": int(cards_per_page) if cards_per_page else 20,
        "save_local": True if save_local else False,
    }
    try:
        with open(_SEARCH_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_search_config():
    """Load last search configuration from file."""
    defaults = {
        "query": "",
        "search_type": "Model name",
        "content_type": None,
        "base_model": None,
        "sort_type": "Highest Rated",
        "period": "AllTime",
        "nsfw": getattr(shared.opts, "civitai_default_nsfw", False),
        "cards_per_page": 20,
        "save_local": False,
        "installed_sort": "date_desc"
    }
    try:
        if os.path.exists(_SEARCH_CONFIG_FILE):
            with open(_SEARCH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            for key in defaults:
                if key in config:
                    defaults[key] = config[key]
            # Normalize empty lists to None for multiselect dropdowns
            if not defaults["content_type"]:
                defaults["content_type"] = None
            if not defaults["base_model"]:
                defaults["base_model"] = None
    except Exception as e:
        print(f"[DEBUG] Failed to load search config: {e}", file=sys.stderr)
    return defaults


def _download_image(url, local_path):
    """Download a single image. Returns True on success."""
    try:
        resp = api.session.get(url, timeout=30)
        if resp.status_code == 200:
            with open(local_path, 'wb') as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"[DEBUG] Failed to download {url}: {e}", file=sys.stderr)
    return False


def _localize_description_images(desc_html, images_dir):
    """Download images embedded in description HTML and replace URLs with local paths."""
    import re
    if not desc_html:
        return desc_html

    img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', desc_html, re.IGNORECASE)
    for i, url in enumerate(img_urls):
        if not url.startswith('http'):
            continue
        filename = f"desc_{i}.jpeg"
        local_path = os.path.join(images_dir, filename)
        if _download_image(url, local_path):
            desc_html = desc_html.replace(url, f"/file={local_path}")

    return desc_html


def _save_installed_sort(sort_value):
    """Save installed sort preference to search config."""
    try:
        config = {}
        if os.path.exists(_SEARCH_CONFIG_FILE):
            with open(_SEARCH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        config["installed_sort"] = sort_value
        with open(_SEARCH_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _save_model_info_local(model_id):
    """Save model info + download ALL images (preview + description) to local storage."""
    if model_id not in _model_data_cache:
        print(f"[DEBUG] Save local: model {model_id} not in memory cache", file=sys.stderr)
        return False

    cache = _model_data_cache[model_id]
    model_dir = os.path.join(_MODEL_INFO_DIR, str(model_id))
    images_dir = os.path.join(model_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 1. Download all preview images and build version_images with local paths
    version_images = cache.get("version_images", {})
    saved_version_images = {}
    downloaded = 0

    for vid_str, images in version_images.items():
        saved_imgs = []
        for i, img in enumerate(images):
            saved_img = dict(img)  # shallow copy
            url = img.get("url", "")
            img_id = img.get("id", i)
            img_type = img.get("type", "image")

            if url and img_type != "video":
                filename = f"{vid_str}_{img_id}.jpeg"
                local_path = os.path.join(images_dir, filename)
                if _download_image(url, local_path):
                    saved_img["local_path"] = local_path
                    downloaded += 1

            saved_imgs.append(saved_img)
        saved_version_images[vid_str] = saved_imgs

    # 2. Download description images and localize HTML
    model_data_copy = dict(cache["model_data"])
    desc = model_data_copy.get("description", "")
    if desc:
        model_data_copy["description"] = _localize_description_images(desc, images_dir)

    # 3. Save JSON
    from datetime import datetime
    save_data = {
        "model_id": model_id,
        "saved_at": datetime.now().isoformat(),
        "model_data": model_data_copy,
        "version_images": saved_version_images
    }
    filepath = os.path.join(model_dir, "info.json")
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        print(f"[DEBUG] Saved model {model_id} locally: {downloaded} preview images + description images", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[DEBUG] Failed to save model {model_id}: {e}", file=sys.stderr)
        return False


def _load_model_info_local(model_id):
    """Load model info from local storage. Returns (model_data, version_images) or None."""
    filepath = os.path.join(_MODEL_INFO_DIR, str(model_id), "info.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        model_data = data.get("model_data")
        if not model_data:
            return None
        return model_data, data.get("version_images", {})
    except Exception:
        return None


def _ensure_model_info_cached(model_id):
    """Ensure model data is in memory cache (fetch from API if needed). Returns True if cached."""
    if model_id in _model_data_cache:
        return True
    data = api.get_model(model_id)
    if not data:
        return False
    versions = data.get("modelVersions", [])
    version_images_cache = {}
    for v in versions[:5]:
        vid = v.get('id', '')
        if vid:
            try:
                vdata = api.get_model_version(vid)
                if vdata:
                    version_images_cache[str(vid)] = vdata.get('images', [])
            except Exception:
                pass
            if str(vid) not in version_images_cache:
                version_images_cache[str(vid)] = v.get('images', [])
    _model_data_cache[model_id] = {"model_data": data, "version_images": version_images_cache}
    return True


def _delete_model_info_local(model_id):
    """Delete local model info directory (JSON + images)."""
    import shutil
    model_dir = os.path.join(_MODEL_INFO_DIR, str(model_id))
    try:
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)
            print(f"[DEBUG] Deleted local model info for {model_id}", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] Failed to delete model info {model_id}: {e}", file=sys.stderr)


def _strip_random_suffix(value):
    """Hidden textboxes get a random suffix to force Gradio change detection.
    Strip everything from the last '_' onward."""
    if not value:
        return ""
    s = str(value)
    return s.rsplit('_', 1)[0] if '_' in s else s


def do_select_all_installed(filter_folder, sort_label):
    """Select every installed card currently visible (i.e. matching filter_folder).
    With an empty filter, selects ALL installed models — handy for mass cleanup."""
    from cb_api import scan_installed_civitai_models
    installed, _ = scan_installed_civitai_models()

    if filter_folder:
        normalized = filter_folder.replace('\\', '/')
        visible = [
            m for m in installed
            if m.get('folder', '').replace('\\', '/').startswith(normalized)
        ]
    else:
        visible = installed

    # If everything visible is already selected, treat this as "toggle off" —
    # gives the user a quick way to clear the selection without per-card clicks.
    visible_paths = {m.get('path') for m in visible if m.get('path')}
    if visible_paths and visible_paths.issubset(_selected_installed_paths):
        _selected_installed_paths.difference_update(visible_paths)
    else:
        _selected_installed_paths.update(visible_paths)

    sort_key = {
        "Publish Date (Newest)": "date_desc",
        "Publish Date (Oldest)": "date_asc",
        "Filename (A-Z)": "name_asc",
        "Filename (Z-A)": "name_desc",
    }.get(sort_label, "date_desc")
    return gr.update(value=get_installed_models_html(filter_folder, sort_key))


def do_toggle_installed_selection(path_with_suffix, filter_folder, sort_label):
    """Toggle a path in the installed-selection set, then re-render the cards.

    The hidden textbox carries 'path_random' so Gradio fires on every click
    even when the user re-clicks the same checkbox; we drop the suffix here.
    """
    raw = _strip_random_suffix(path_with_suffix)
    if raw and raw in _selected_installed_paths:
        _selected_installed_paths.discard(raw)
    elif raw:
        _selected_installed_paths.add(raw)
    sort_key = {
        "Publish Date (Newest)": "date_desc",
        "Publish Date (Oldest)": "date_asc",
        "Filename (A-Z)": "name_asc",
        "Filename (Z-A)": "name_desc",
    }.get(sort_label, "date_desc")
    return gr.update(value=get_installed_models_html(filter_folder, sort_key))


def do_delete_selected_installed(filter_folder, sort_label):
    """Delete every model in _selected_installed_paths along with sidecars and
    (conditionally) the cached local model-info directory."""
    from cb_downloader import delete_model
    from cb_api import scan_installed_civitai_models, invalidate_installed_scan_cache

    paths = list(_selected_installed_paths)
    if not paths:
        # Nothing selected — keep current HTML, surface a status line
        sort_key = {
            "Publish Date (Newest)": "date_desc",
            "Publish Date (Oldest)": "date_asc",
            "Filename (A-Z)": "name_asc",
            "Filename (Z-A)": "name_desc",
        }.get(sort_label, "date_desc")
        return (
            gr.update(value=get_installed_models_html(filter_folder, sort_key)),
            gr.update(value="No models selected."),
        )

    # Collect model_ids for each path so we know which local-info caches to drop.
    # Only drop the cached info when ZERO files with that model_id remain after delete.
    pre_delete_models, _ = scan_installed_civitai_models()
    path_to_mid = {
        m.get('path'): m.get('civitai_model_id')
        for m in pre_delete_models if m.get('path')
    }
    mids_being_deleted = {path_to_mid.get(p) for p in paths if path_to_mid.get(p)}

    deleted = 0
    failed = []
    for p in paths:
        try:
            if delete_model(p):
                deleted += 1
            else:
                failed.append(os.path.basename(p))
        except Exception as e:
            failed.append(f"{os.path.basename(p)} ({e})")

    # delete_model invalidates the scan cache; re-scan to see what's left
    invalidate_installed_scan_cache()
    post_delete_models, _ = scan_installed_civitai_models()
    remaining_mids = {m.get('civitai_model_id') for m in post_delete_models if m.get('civitai_model_id')}

    # Drop cached local-info for any model_id that no longer has files on disk
    local_info_dropped = 0
    for mid in mids_being_deleted:
        if mid and mid not in remaining_mids:
            _delete_model_info_local(mid)
            local_info_dropped += 1

    _selected_installed_paths.clear()

    sort_key = {
        "Publish Date (Newest)": "date_desc",
        "Publish Date (Oldest)": "date_asc",
        "Filename (A-Z)": "name_asc",
        "Filename (Z-A)": "name_desc",
    }.get(sort_label, "date_desc")

    parts = [f"Deleted {deleted} model(s)"]
    if local_info_dropped:
        parts.append(f"cleared {local_info_dropped} cached info folder(s)")
    if failed:
        parts.append(f"failed: {', '.join(failed[:5])}{'…' if len(failed) > 5 else ''}")
    status = " | ".join(parts)

    return (
        gr.update(value=get_installed_models_html(filter_folder, sort_key)),
        gr.update(value=status),
    )


BASE_MODELS = [
    "SD 1.4", "SD 1.5", "SD 1.5 LCM", "SD 1.5 Hyper",
    "SD 2.0", "SD 2.1",
    "SDXL 0.9", "SDXL 1.0", "SDXL 1.0 LCM", "SDXL Turbo", "SDXL Lightning", "SDXL Hyper",
    "SD 3", "SD 3.5", "SD 3.5 Medium", "SD 3.5 Large",
    "Pony", "Illustrious", "NoobAI",
    "Flux.1 S", "Flux.1 D",
    "Stable Cascade", "SVD", "SVD XT",
    "Hunyuan 1", "Kolors", "AuraFlow",
    "Other"
]

CONTENT_TYPES = list(CONTENT_TYPE_FOLDERS.keys())

SORT_OPTIONS = ["Highest Rated", "Most Downloaded", "Most Liked", "Most Buzz",
                "Most Discussed", "Most Collected", "Most Images", "Newest"]

PERIOD_OPTIONS = ["AllTime", "Year", "Month", "Week", "Day"]


def _refresh_installed():
    """Refresh installed models cache."""
    global _installed_files, _installed_hashes, _installed_model_ids
    _installed_files, _installed_hashes, _installed_model_ids = scan_installed_models()


# --- Search & Browse ---

def _do_search_internal(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, page):
    """Internal search that stores results."""
    global _current_page, _total_pages, _last_search_items, _page_cursors, _last_base_model_filter

    _current_page = page

    # Use cursor for page > 1 if available (CivitAI uses cursor-based pagination)
    cursor = _page_cursors.get(page - 1) if page > 1 else None

    result = api.search_models(
        query=query, search_type=search_type,
        content_type=content_type if content_type else None,
        base_model=base_model if base_model else None,
        sort=sort_type, period=period,
        page=page, limit=int(cards_per_page), nsfw=nsfw,
        cursor=cursor
    )

    if "error" in result:
        _last_search_items = []
        return f'<div class="civ-error">Error: {result["error"]}</div>', f"Page {page} / 1"

    meta = result.get("metadata", {})

    # Save cursor for next page navigation
    next_cursor = meta.get("nextCursor")
    if next_cursor:
        _page_cursors[page] = next_cursor

    _total_pages = meta.get("totalPages", 0)
    if not _total_pages:
        if next_cursor or meta.get("nextPage"):
            _total_pages = page + 1  # At least one more page
        else:
            _total_pages = page  # This is the last page

    items = result.get("items", [])
    # Store base model filter for select-all / download logic
    _last_base_model_filter = base_model if isinstance(base_model, list) else ([base_model] if base_model else [])
    # Expand multi-version models into per-version cards
    _last_search_items = flatten_to_version_items(items, _last_base_model_filter)

    html = make_model_cards_html(_last_search_items, _installed_hashes, _installed_files, installed_model_ids=_installed_model_ids)

    page_display = f"Page {_current_page} / {_total_pages}" if meta.get("totalPages") else f"Page {_current_page}"
    return html, page_display


def do_search(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local=False):
    global _page_cursors
    _page_cursors = {}  # Reset cursors for new search
    _refresh_installed()
    _save_search_config(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local)
    return _do_search_internal(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, 1)


def do_page(direction, query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local=False):
    page = _current_page
    if direction == "next" and page < _total_pages:
        page += 1
    elif direction == "prev" and page > 1:
        page -= 1
    return _do_search_internal(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, page)


# --- Model Details ---

def load_model_details(model_id_str):
    """Load model details when a card is clicked."""
    if not model_id_str:
        # Return 8 updates to match the outputs
        return [gr.update()] * 8

    try:
        model_id = int(model_id_str)
    except (ValueError, TypeError):
        return [gr.update()] * 8

    data = api.get_model(model_id)
    if not data:
        return [gr.update()] * 8

    model_name = data.get("name", "Unknown")
    creator = data.get("creator", {}).get("username", "Unknown")
    content_type = data.get("type", "")
    nsfw = data.get("nsfw", False)
    versions = data.get("modelVersions", [])

    version_names = [v.get("name", "Unknown") for v in versions]
    version_value = version_names[0] if version_names else None

    # Build path
    auto_organize = getattr(shared.opts, "civitai_auto_organize", True)
    base_model = versions[0].get("baseModel", "") if versions else ""
    install_path = build_install_path(content_type, base_model, creator, model_name, auto_organize)

    # Preview HTML
    preview_parts = [f'<div class="civ-preview">']
    preview_parts.append(f'<h2>{model_name}</h2>')
    preview_parts.append(f'<p>by <b>{creator}</b> | {content_type} | {base_model}</p>')

    desc = data.get("description", "")
    if desc:
        preview_parts.append(f'<div class="civ-description">{desc}</div>')

    # Sample images
    if versions:
        imgs = versions[0].get("images", [])
        if imgs:
            preview_parts.append('<div class="civ-sample-images">')
            for img in imgs[:8]:
                url = img.get("url", "")
                if img.get("type") == "video":
                    url = url.replace("width=", "transcode=true,width=")
                    preview_parts.append(f'<video controls muted playsinline style="max-width:300px"><source src="{url}" type="video/mp4"></video>')
                else:
                    preview_parts.append(f'<img loading="lazy" src="{url}" style="max-width:300px;border-radius:8px;margin:4px">')
            preview_parts.append('</div>')

    preview_parts.append('</div>')
    preview_html = ''.join(preview_parts)

    # Extract thumbnail URL
    thumbnail = ""
    if versions:
        imgs = versions[0].get("images", [])
        if imgs:
            thumbnail = imgs[0].get("url", "")

    return (
        gr.update(choices=version_names, value=version_value, visible=True),  # 1. versions dropdown
        gr.update(value=install_path, visible=True),  # 2. install path
        gr.update(visible=True),  # 3. download btn
        gr.update(visible=True),  # 4. save info btn
        gr.update(value=preview_html),  # 5. preview html
        gr.update(value=str(model_id)),  # 6. model_id state
        gr.update(value=model_name),  # 7. model_name state
        gr.update(value=thumbnail),  # 8. thumbnail state
    )


def do_show_model_info_btn(model_id_str):
    """Show model info button when model is selected."""
    return gr.update(visible=bool(model_id_str))


def on_version_change(version_name, model_id_str):
    """Update file info when version changes."""
    if not model_id_str:
        return gr.update(), gr.update()

    data = api.get_model(int(model_id_str))
    if not data:
        return gr.update(), gr.update()

    for v in data.get("modelVersions", []):
        if v.get("name") == version_name:
            files = v.get("files", [])
            file_names = []
            for f in files:
                size = _format_size(f.get("sizeKB", 0) * 1024)
                fmt = f.get("metadata", {}).get("format", "")
                file_names.append(f"{f.get('name', '')} ({size}, {fmt})")

            base_model = v.get("baseModel", "")
            creator = data.get("creator", {}).get("username", "Unknown")
            auto_organize = getattr(shared.opts, "civitai_auto_organize", True)
            path = build_install_path(data.get("type", ""), base_model, creator, data.get("name", ""), auto_organize)

            return (
                gr.update(choices=file_names, value=file_names[0] if file_names else None, visible=True),
                gr.update(value=path),
            )

    return gr.update(), gr.update()


# --- Select All / Download Selected ---

def do_select_all():
    """Toggle select all — if any selected, deselect all; otherwise select all non-installed cards."""
    global _selected_model_ids

    if _selected_model_ids:
        _selected_model_ids.clear()
    else:
        for item in _last_search_items:
            if not item.get("modelVersions"):
                continue

            model_id     = str(item.get("id", ""))
            model_id_int = item.get("id")
            is_version_item = "_version_id" in item

            if is_version_item:
                version_id    = str(item.get("_version_id", ""))
                selection_key = f"{model_id}:{version_id}"
                check_files   = item.get("_files", [])
            else:
                selection_key = model_id
                check_files   = []
                for v in item.get("modelVersions", []):
                    check_files.extend(v.get("files", []))

            # Check installed status
            is_installed = False
            if model_id_int and model_id_int in _installed_model_ids:
                is_installed = True
            if not is_installed:
                for f in check_files:
                    sha   = f.get("hashes", {}).get("SHA256", "").upper()
                    fname = f.get("name", "").lower()
                    if (sha and sha in _installed_hashes) or fname in _installed_files:
                        is_installed = True
                        break

            if not is_installed:
                _selected_model_ids.add(selection_key)

    html = make_model_cards_html(_last_search_items, _installed_hashes, _installed_files, _selected_model_ids, _installed_model_ids)
    status = f"Selected {len(_selected_model_ids)} models" if _selected_model_ids else "Deselected all"
    return gr.update(value=html), status


def _extract_model_id_from_card(card_html):
    """Extract model ID from card HTML data attribute."""
    import re
    match = re.search(r'data-model-id="(\d+)"', card_html)
    return match.group(1) if match else None


def do_download_selected(save_local_info=False):
    """Queue all selected models for download and return immediately."""
    global _selected_model_ids

    if not _selected_model_ids:
        yield gr.update(value='<div class="civ-dl-empty">No models selected</div>'), ""
        return

    selection_keys = list(_selected_model_ids)
    total = len(selection_keys)
    auto_organize = getattr(shared.opts, "civitai_auto_organize", True)
    added = 0
    skipped = []

    # Immediate feedback
    yield gr.update(value=dl_manager.get_status_html()), f"⏳ Queuing {total} models..."

    # Queue all models for download
    for i, key in enumerate(selection_keys):
        # Parse selection key: "model_id:version_id" or plain "model_id"
        if ':' in str(key):
            mid_str, vid_str = str(key).split(':', 1)
        else:
            mid_str, vid_str = str(key), None

        try:
            data = api.get_model(int(mid_str))
            if not data:
                skipped.append((f"ID:{mid_str}", "Not found"))
                continue

            model_name = data.get("name", "Unknown")
            content_type = data.get("type", "")
            creator = data.get("creator", {}).get("username", "Unknown")
            versions = data.get("modelVersions", [])
            if not versions:
                skipped.append((model_name, "No versions"))
                continue

            # Pick the specific version if version_id is encoded in the key
            if vid_str:
                version = next((v for v in versions if str(v.get("id", "")) == vid_str), None)
                if not version:
                    version = versions[0]  # fallback
            else:
                version = versions[0]

            files = version.get("files", [])
            primary = next((f for f in files if f.get("primary")), files[0] if files else None)
            if not primary:
                skipped.append((model_name, "No files (login or Early Access required)"))
                continue

            dl_url = primary.get("downloadUrl", "")
            if dl_url and dl_url.startswith("//"):
                dl_url = "https:" + dl_url
            if not dl_url:
                skipped.append((model_name, "No download URL"))
                continue

            install_path = build_install_path(
                content_type, version.get("baseModel", ""),
                creator, model_name, auto_organize
            )
            preview_url = ""
            preview_type = "image"
            images = version.get("images", [])
            if images:
                preview_url = images[0].get("url", "")
                preview_type = images[0].get("type", "image")

            dl_manager.add(
                url=dl_url,
                filename=primary.get("name", "model.safetensors"),
                install_path=install_path,
                model_name=model_name,
                version_name=version.get("name", ""),
                model_id=int(mid_str),
                version_id=int(vid_str) if vid_str else 0,
                sha256=primary.get("hashes", {}).get("SHA256", ""),
                preview_url=preview_url,
                preview_type=preview_type,
                published_at=version.get("publishedAt", ""),
                trained_words=version.get("trainedWords", [])
            )
            added += 1

            # Show queuing progress
            if (i + 1) % 5 == 0 or i == total - 1:
                yield gr.update(value=dl_manager.get_status_html()), \
                    f"⏳ Queued {added} / {total} models..."
        except Exception as e:
            skipped.append((f"ID:{mid_str}", str(e)))

    # Clear selection
    _selected_model_ids.clear()

    # Save model info locally in background — deduplicate model IDs
    if save_local_info and selection_keys:
        unique_model_ids = list({k.split(':')[0] if ':' in str(k) else str(k) for k in selection_keys})
        def _bg_save_all(ids):
            count = 0
            for mid in ids:
                try:
                    if _ensure_model_info_cached(int(mid)):
                        if _save_model_info_local(int(mid)):
                            count += 1
                except Exception:
                    pass
            print(f"[DEBUG] Background save complete: {count}/{len(ids)} model info saved", file=sys.stderr)
        threading.Thread(target=_bg_save_all, args=(unique_model_ids,), daemon=True).start()

    # Final summary
    status_parts = []
    if added > 0:
        status_parts.append(f"✅ Queued {added} downloads")
    if save_local_info:
        status_parts.append(f"💾 Saving model info in background")
    if skipped:
        skip_details = "; ".join([f"{n}: {r}" for n, r in skipped[:5]])
        status_parts.append(f"Skipped {len(skipped)}: {skip_details}")

    yield gr.update(value=dl_manager.get_status_html()), " | ".join(status_parts)


# --- Download ---

def start_download(model_id_str, version_name, file_index_str, install_path, save_local_info=False):
    """Start downloading a model with live progress."""
    if not model_id_str:
        yield gr.update()
        return

    data = api.get_model(int(model_id_str))
    if not data:
        yield gr.update(value='<div class="civ-error">Model not found</div>')
        return

    model_name = data.get("name", "Unknown")
    content_type = data.get("type", "")
    creator = data.get("creator", {}).get("username", "Unknown")

    for v in data.get("modelVersions", []):
        if v.get("name") == version_name:
            files = v.get("files", [])
            if not files:
                break

            file_idx = 0
            if file_index_str:
                for i, f in enumerate(files):
                    size = _format_size(f.get("sizeKB", 0) * 1024)
                    fmt = f.get("metadata", {}).get("format", "")
                    if f"{f.get('name', '')} ({size}, {fmt})" == file_index_str:
                        file_idx = i
                        break

            file_data = files[file_idx]
            dl_url = file_data.get("downloadUrl", "")
            if dl_url and dl_url.startswith("//"):
                dl_url = "https:" + dl_url
            filename = file_data.get("name", "model.safetensors")
            sha256 = file_data.get("hashes", {}).get("SHA256", "")

            preview_url = ""
            preview_type = "image"
            images = v.get("images", [])
            if images:
                preview_url = images[0].get("url", "")
                preview_type = images[0].get("type", "image")

            os.makedirs(install_path, exist_ok=True)

            dl_manager.add(
                url=dl_url, filename=filename, install_path=install_path,
                model_name=model_name, version_name=version_name,
                model_id=int(model_id_str),
                version_id=int(v.get("id") or 0),
                sha256=sha256,
                preview_url=preview_url, preview_type=preview_type,
                published_at=v.get("publishedAt", ""),
                trained_words=v.get("trainedWords", [])
            )

            yield gr.update(value=dl_manager.get_status_html())

            # Save model info locally in background (doesn't block UI)
            if save_local_info:
                def _bg_save(mid):
                    try:
                        if _ensure_model_info_cached(mid):
                            _save_model_info_local(mid)
                    except Exception as e:
                        print(f"[DEBUG] Failed to save local info: {e}", file=sys.stderr)
                threading.Thread(target=_bg_save, args=(int(model_id_str),), daemon=True).start()
            return

    yield gr.update(value='<div class="civ-error">Version not found</div>')


# --- Favorites Tab ---

def get_favorites_html():
    """Generate HTML for favorites display."""
    favs = load_favorites()
    if not favs:
        return '<div class="civ-no-results">No favorites yet. Click the star on a model to add it.</div>'

    parts = ['<div class="civ-card-grid">']
    for fav in favs:
        thumb = fav.get("thumbnail", "")
        name = fav.get("name", "Unknown")
        display_name = name[:35] + "..." if len(name) > 35 else name
        esc_name = name.replace('"', '&quot;')
        mid = fav.get("model_id", "")
        img = f'<img class="civ-card-media" loading="lazy" src="{thumb}">' if thumb else '<div class="civ-card-no-img">No Preview</div>'

        parts.append(f'''<div class="civ-card civ-fav-card" data-model-id="{mid}" data-model-name="{esc_name}">
            {img}
            <div class="civ-card-name" title="{esc_name}">{display_name}</div>
            <div class="civ-card-meta">{fav.get("type", "")}</div>
        </div>''')

    parts.append('</div>')
    return ''.join(parts)


def do_toggle_favorite(model_id_str, model_name, thumbnail):
    """Add/remove from favorites."""
    if not model_id_str:
        return gr.update(), "No model selected"

    _, was_added = toggle_favorite(model_id_str, model_name, "", thumbnail or "")
    status = f"{'Added' if was_added else 'Removed'}: {model_name}"
    return gr.update(value=get_favorites_html()), status


def do_prev_page(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local=False):
    return do_page("prev", query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local)


def do_next_page(query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local=False):
    return do_page("next", query, search_type, content_type, base_model, sort_type, period, nsfw, cards_per_page, save_local)


def do_refresh_fav():
    return gr.update(value=get_favorites_html())


def do_refresh_installed():
    from cb_api import invalidate_installed_scan_cache
    invalidate_installed_scan_cache()
    return gr.update(value=get_installed_models_html())


def do_refresh_dl():
    return gr.update(value=dl_manager.get_status_html())


def do_clear_dl():
    dl_manager.clear_finished()
    return gr.update(value=dl_manager.get_status_html())


def do_retry_failed():
    count = dl_manager.retry_failed()
    return gr.update(value=dl_manager.get_status_html())


def do_show_fav_btn(model_id_str):
    return gr.update(visible=bool(model_id_str))


def do_toggle_card_selection(selection_key_str):
    """Toggle selection state for a single model card.
    selection_key_str is either 'model_id' (legacy) or 'model_id:version_id' (version item).
    """
    global _selected_model_ids

    if not selection_key_str:
        return gr.update(value=get_favorites_html())

    selection_key_str = str(selection_key_str)
    if selection_key_str in _selected_model_ids:
        _selected_model_ids.discard(selection_key_str)
    else:
        _selected_model_ids.add(selection_key_str)

    # Re-render cards with updated selection
    html = make_model_cards_html(_last_search_items, _installed_hashes, _installed_files, _selected_model_ids, _installed_model_ids)
    return gr.update(value=html)


def get_model_info_html(model_id_str):
    """Generate detailed model info HTML for popup window with two tabs."""
    import sys
    import gradio as gr
    
    # Debug logging - show EVERY call
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[DEBUG] === get_model_info_html CALLED ===", file=sys.stderr)
    print(f"[DEBUG] Input model_id_str: '{model_id_str}'", file=sys.stderr)
    print(f"[DEBUG] Input type: {type(model_id_str)}", file=sys.stderr)
    print(f"[DEBUG] Input is empty: {not model_id_str}", file=sys.stderr)
    
    # Ignore empty strings - return gr.update() to keep current state
    if not model_id_str or str(model_id_str).strip() == '':
        print(f"[DEBUG] Ignoring empty value", file=sys.stderr)
        print(f"[DEBUG] Returning gr.update()", file=sys.stderr)
        return gr.update()  # Keep current HTML, don't show error
    
    # Clean the model ID string.
    # Supported formats:
    #   "modelId_randomSuffix"           → model only
    #   "modelId:versionId_randomSuffix" → model + version hint
    #   "modelId"                        → plain (installed tab)
    model_id_str = str(model_id_str)
    # Strip random suffix (everything after last '_')
    base = model_id_str.rsplit('_', 1)[0] if '_' in model_id_str else model_id_str

    version_id_hint = None
    if ':' in base:
        model_id_clean, version_id_hint = base.split(':', 1)
        model_id_clean = ''.join(c for c in model_id_clean if c.isdigit())
        version_id_hint = ''.join(c for c in version_id_hint if c.isdigit()) or None
    else:
        model_id_clean = ''.join(c for c in base if c.isdigit())

    print(f"[DEBUG] Cleaned model_id: '{model_id_clean}', version_hint: '{version_id_hint}'", file=sys.stderr)
    
    if not model_id_clean:
        print(f"[DEBUG] No digits found in model_id_str", file=sys.stderr)
        return gr.update()  # Keep current HTML
    
    try:
        model_id = int(model_id_clean)
    except (ValueError, TypeError) as e:
        print(f"[DEBUG] Failed to convert to int: {e}", file=sys.stderr)
        return gr.update(value='<div class="civ-error">Invalid model ID</div>')

    # Check local cache first
    is_local = False
    version_images_cache = {}
    local_info = _load_model_info_local(model_id)

    if local_info:
        data, version_images_cache = local_info
        is_local = True
        print(f"[DEBUG] Loaded model {model_id} from local cache", file=sys.stderr)
    else:
        print(f"[DEBUG] Fetching model {model_id} from CivitAI...", file=sys.stderr)
        data = api.get_model(model_id)
        if not data:
            print(f"[DEBUG] Model {model_id} not found", file=sys.stderr)
            return gr.update(value='<div class="civ-error">Model not found</div>')

    print(f"[DEBUG] Model: {data.get('name', 'Unknown')} (source: {'local' if is_local else 'online'})", file=sys.stderr)
    print(f"[DEBUG] Generating HTML...", file=sys.stderr)

    model_name = data.get("name", "Unknown")
    creator = data.get("creator", {}).get("username", "Unknown")
    content_type = data.get("type", "")
    nsfw = data.get("nsfw", False)
    versions = data.get("modelVersions", [])

    # Find installed safetensors filename for LoRA tag injection.
    # Prefer exact version match when version_id_hint is available.
    _lora_filename = ""
    try:
        from cb_api import scan_installed_civitai_models
        _installed, _ = scan_installed_civitai_models()
        for _m in _installed:
            if str(_m.get("civitai_model_id", "")) != str(model_id):
                continue
            if version_id_hint and str(_m.get("civitai_version_id", "")) == version_id_hint:
                _lora_filename = os.path.splitext(os.path.basename(_m["path"]))[0]
                break
            if not _lora_filename:
                _lora_filename = os.path.splitext(os.path.basename(_m["path"]))[0]
    except Exception:
        pass
    lora_name_escaped = _lora_filename.replace('"', '&quot;')
    
    # Build CivitAI URL
    civitai_url = f"https://civitai.red/models/{model_id}"
    
    parts = [f'<div class="civ-model-info">']

    # Source indicator and save checkbox
    source_class = 'local' if is_local else 'online'
    source_label = '📁 Local' if is_local else '🌐 Online'
    checked_attr = 'checked' if is_local else ''

    # Header with clickable title
    parts.append(f'''<div class="civ-model-header">
        <h2 class="civ-model-title">
            <a href="{civitai_url}" target="_blank" class="civ-model-link" title="Open on CivitAI">
                {model_name} 🔗
            </a>
        </h2>
        <div class="civ-header-actions">
            <span class="civ-data-source civ-source-{source_class}">{source_label}</span>
            <label class="civ-save-local-label">
                <input type="checkbox" class="civ-save-local-checkbox" data-model-id="{model_id}" {checked_attr}> 💾 Save Local
            </label>
        </div>
        <span class="civ-model-meta">by <b>{creator}</b> | {content_type}</span>
    </div>''')

    # Tab navigation buttons (at top for better UX)
    parts.append('''<div class="civ-tab-nav">
        <button class="civ-tab-btn civ-tab-btn-active" data-tab-target="description">📖 Description</button>
        <button class="civ-tab-btn" data-tab-target="images">🖼️ Preview Images</button>
        <button class="civ-tab-btn" data-tab-target="triggers">🔑 Trigger Words</button>
    </div>''')

    # Tabs container
    parts.append('<div class="civ-model-tabs">')
    
    # Tab 1: Model Description & Info (visible by default)
    parts.append('<div class="civ-tab-content civ-tab-description" id="civ-tab-description">')
    parts.append('<div class="civ-tab-header"><h3>📖 Model Description</h3></div>')
    
    # Model description
    desc = data.get("description", "")
    if desc:
        parts.append(f'<div class="civ-model-description">{desc}</div>')
    else:
        parts.append('<div class="civ-model-description"><em>No description available.</em></div>')
    
    parts.append('</div>')  # End Tab 1 (Description)
    
    # Tab 2: Preview Images (hidden by default)
    parts.append('<div class="civ-tab-content civ-tab-images" id="civ-tab-images" style="display:none;">')
    parts.append('<div class="civ-tab-header"><h3>🖼️ Preview Images</h3></div>')
    
    # Determine which versions to display throughout the popup.
    # If a specific version was clicked, restrict to that version only.
    if version_id_hint:
        display_versions = [v for v in versions if str(v.get('id', '')) == version_id_hint]
        if not display_versions:
            display_versions = versions[:5]  # fallback if hint doesn't match
    else:
        display_versions = versions[:5]

    # Sample images with metadata - list view layout
    parts.append('<div class="civ-model-versions">')

    if versions:

        for v in display_versions:
            version_name = v.get("name", "")
            base_model = v.get("baseModel", "")
            version_id = v.get('id', '')

            # Get images - use local cache if available, otherwise fetch from API
            images = []
            vid_str = str(version_id)
            if vid_str in version_images_cache:
                images = version_images_cache[vid_str]
            elif version_id:
                try:
                    version_data = api.get_model_version(version_id)
                    if version_data:
                        images = version_data.get('images', [])
                except Exception:
                    pass

            # Fallback to search result images
            if not images:
                images = v.get('images', [])

            # Store in cache for potential local save
            if version_id:
                version_images_cache[vid_str] = images

            # If still no images, skip this version
            if not images:
                continue

            parts.append(f'<div class="civ-version-block">')
            parts.append(f'<h4 class="civ-version-title">{version_name} <span class="civ-base-model">{base_model}</span></h4>')

            # Sample images with metadata - list view layout
            parts.append('<div class="civ-version-images-list">')
            for img in images:
                url = img.get("url", "")
                img_id = img.get("id", "")
                img_type = img.get("type", "image")

                # Use local image path if available and file exists
                local_path = img.get("local_path", "")
                if is_local and local_path and os.path.exists(local_path):
                    url = f"/file={local_path}"

                # Get metadata from image
                img_meta_raw = img.get('meta')
                prompt_text = ''
                neg_prompt_text = ''

                if img_meta_raw:
                    try:
                        if isinstance(img_meta_raw, str):
                            img_meta = json.loads(img_meta_raw)
                        else:
                            img_meta = img_meta_raw

                        if isinstance(img_meta, dict):
                            prompt_text = img_meta.get('prompt', '') or ''
                            neg_prompt_text = img_meta.get('negativePrompt', '') or ''
                    except Exception:
                        pass

                if img_type == "video":
                    video_url = img.get("url", "").replace("width=", "transcode=true,width=")
                    parts.append(f'<div class="civ-sample-item-list"><video class="civ-sample-media" controls muted playsinline><source src="{video_url}" type="video/mp4"></video></div>')
                else:
                    prompt_escaped = prompt_text.replace(chr(34), "&quot;").replace(chr(10), "&#10;") if prompt_text else ''
                    neg_prompt_escaped = neg_prompt_text.replace(chr(34), "&quot;").replace(chr(10), "&#10;") if neg_prompt_text else ''

                    # Build generation info string for Send to txt2img
                    geninfo_lines = []
                    if prompt_text:
                        geninfo_lines.append(prompt_text)
                    if neg_prompt_text:
                        geninfo_lines.append(f"Negative prompt: {neg_prompt_text}")
                    if isinstance(img_meta_raw, dict) if not isinstance(img_meta_raw, str) else False:
                        _m = img_meta_raw
                    elif img_meta_raw:
                        try:
                            _m = json.loads(img_meta_raw) if isinstance(img_meta_raw, str) else {}
                        except Exception:
                            _m = {}
                    else:
                        _m = {}
                    def _mget(d, *keys):
                        """Try multiple key variants, return first non-falsy value."""
                        for k in keys:
                            v = d.get(k)
                            if v is not None and v != '':
                                return v
                        return None

                    params = []
                    _v = _mget(_m, 'steps')
                    if _v: params.append(f"Steps: {_v}")
                    _v = _mget(_m, 'sampler', 'Sampler')
                    if _v: params.append(f"Sampler: {_v}")
                    _v = _mget(_m, 'cfgScale', 'cfg scale', 'CFG scale', 'cfgscale')
                    if _v: params.append(f"CFG scale: {_v}")
                    _v = _mget(_m, 'seed')
                    if _v: params.append(f"Seed: {_v}")
                    _v = _mget(_m, 'Size', 'size')
                    if _v:
                        params.append(f"Size: {_v}")
                    elif _m.get('width') and _m.get('height'):
                        params.append(f"Size: {_m['width']}x{_m['height']}")
                    _v = _mget(_m, 'Model')
                    if _v: params.append(f"Model: {_v}")
                    _v = _mget(_m, 'clipSkip', 'Clip skip', 'clip skip')
                    if _v: params.append(f"Clip skip: {_v}")
                    # Hires. fix — try both camelCase and A1111 space-separated keys
                    _v = _mget(_m, 'hiresUpscaler', 'hires upscaler', 'Hires upscaler')
                    if _v: params.append(f"Hires upscaler: {_v}")
                    _v = _mget(_m, 'hiresUpscale', 'hiresUpscaleBy', 'hiresScale',
                                    'hires upscale', 'Hires upscale')
                    if _v: params.append(f"Hires upscale: {_v}")
                    _v = _mget(_m, 'hiresSteps', 'hires steps', 'Hires steps')
                    if _v: params.append(f"Hires steps: {_v}")
                    _v = _mget(_m, 'denoisingStrength', 'hiresDenoising',
                                    'Denoising strength', 'denoising strength')
                    if _v: params.append(f"Denoising strength: {_v}")
                    if params:
                        geninfo_lines.append(", ".join(params))
                    geninfo_str = chr(10).join(geninfo_lines)
                    geninfo_escaped = geninfo_str.replace(chr(34), "&quot;").replace(chr(10), "&#10;") if geninfo_str else ''

                    prompt_display = html_mod.escape(prompt_text).replace('\n', '<br>') if prompt_text else '<span class="civ-no-prompt">No prompt data</span>'
                    neg_display = html_mod.escape(neg_prompt_text).replace('\n', '<br>') if neg_prompt_text else '<span class="civ-no-prompt">No negative prompt data</span>'
                    parts.append(f'''<div class="civ-sample-item-list" data-img-url="{url}">
                        <div class="civ-sample-img-container">
                            <img class="civ-sample-img-list" loading="lazy" src="{url}" data-url="{url}">
                        </div>
                        <div class="civ-sample-prompts">
                            <div class="civ-prompt-block">
                                <div class="civ-prompt-label">Prompt <button class="civ-copy-btn" data-copy-type="prompt" data-copy="{prompt_escaped}" data-lora-name="{lora_name_escaped}">📋 Copy</button></div>
                                <div class="civ-prompt-text">{prompt_display}</div>
                            </div>
                            <div class="civ-prompt-block">
                                <div class="civ-prompt-label">Negative prompt <button class="civ-copy-btn" data-copy-type="negative" data-copy="{neg_prompt_escaped}">📋 Copy</button></div>
                                <div class="civ-prompt-text">{neg_display}</div>
                            </div>
                        </div>
                        <div class="civ-sample-actions">
                            <button class="civ-send-txt2img-btn" data-geninfo="{geninfo_escaped}" data-lora-name="{lora_name_escaped}" title="Send all to txt2img">📤 Send</button>
                        </div>
                    </div>''')
            parts.append('</div>')  # End version-images-list
            parts.append('</div>')  # End version-block
    
    parts.append('</div>')  # End model-versions
    parts.append('</div>')  # End Tab 2 (Images)

    # Tab 3: Trigger Words (hidden by default)
    parts.append('<div class="civ-tab-content civ-tab-triggers" id="civ-tab-triggers" style="display:none;">')
    parts.append('<div class="civ-tab-header"><h3>🔑 Trigger Words</h3></div>')
    parts.append('<div class="civ-triggers-container">')

    trigger_count = 0
    for v in display_versions:
        trained_words = v.get("trainedWords") or []
        # Each element in trainedWords is a separate trigger group (comma-separated chips inside)
        for word_group in trained_words:
            # Split the group string into individual chips
            chips = [c.strip() for c in word_group.split(',') if c.strip()]
            if not chips:
                continue
            trigger_count += 1
            label = f"Trigger example {trigger_count:02d}"
            copy_str = ", ".join(chips)
            copy_escaped = copy_str.replace('"', '&quot;')
            words_html = "".join(f'<span class="civ-trigger-chip">{c}</span>' for c in chips)
            parts.append(f'''<div class="civ-trigger-block">
                <div class="civ-trigger-block-header">
                    <span class="civ-trigger-label">{label}</span>
                    <button class="civ-copy-btn" data-copy="{copy_escaped}" data-lora-name="{lora_name_escaped}">📋 Copy All</button>
                </div>
                <div class="civ-trigger-chips">{words_html}</div>
            </div>''')

    if trigger_count == 0:
        parts.append('<div class="civ-no-triggers">No trigger words provided for this model.</div>')

    parts.append('</div>')  # End triggers-container
    parts.append('</div>')  # End Tab 3 (Triggers)

    parts.append('</div>')  # End tabs container
    parts.append('</div>')  # End main container
    
    html_output = ''.join(parts)

    # Cache the data in memory for potential local save
    _model_data_cache[model_id] = {
        "model_data": data,
        "version_images": version_images_cache
    }

    # Debug: Count tabs and images
    tab_desc_count = html_output.count('civ-tab-description')
    tab_img_count = html_output.count('civ-tab-images')
    img_count = html_output.count('civ-sample-item-list')
    print(f"[DEBUG] Generated HTML - Description tabs: {tab_desc_count}, Image tabs: {tab_img_count}, Images: {img_count}", file=sys.stderr)
    print(f"[DEBUG] === get_model_info_html COMPLETE ===", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    
    # Add data attribute to trigger popup (include timestamp to ensure Gradio always re-renders)
    import time
    html_with_trigger = html_output.replace('<div class="civ-model-info">', f'<div class="civ-model-info" data-auto-popup="true" data-popup-ts="{int(time.time() * 1000)}">')
    
    # Log the first 200 chars of HTML for debugging
    print(f"[DEBUG] HTML preview: {html_with_trigger[:200]}...", file=sys.stderr)
    
    # Return as gr.update to ensure proper rendering
    return gr.update(value=html_with_trigger)


def fetch_and_send_image_metadata(image_url):
    """Fetch image metadata and send to txt2img."""
    geninfo = api.get_image_metadata(image_url)
    
    if geninfo:
        # read_info_from_image may return tuple (geninfo, items)
        if isinstance(geninfo, tuple):
            geninfo = geninfo[0]
        
        # Add random number prefix like the original implementation
        import random
        nr = str(random.randint(0, 999)).zfill(3) + "."
        full_info = nr + str(geninfo)
        return gr.update(value=full_info)
    else:
        return gr.update(value="")


# --- Installed Models Tab ---

def get_installed_models_html(filter_folder="", sort_by="date_desc"):
    """Scan and display installed models as cards with preview.

    Uses the cached scan from scan_installed_civitai_models(); cache is invalidated
    on download-complete, delete, or explicit refresh, so folder/sort clicks are
    instant after the first scan."""
    from cb_api import scan_installed_civitai_models, make_installed_cards_html

    installed_models, folders = scan_installed_civitai_models()

    # Filter by folder
    if filter_folder:
        filter_folder_normalized = filter_folder.replace('\\', '/')
        installed_models = [
            m for m in installed_models
            if m.get('folder', '').replace('\\', '/').startswith(filter_folder_normalized)
        ]

    # Sort models
    import time as _time
    def _date_key(m):
        # Use published_at first, then download_date, then file mtime
        pa = m.get('published_at', '')
        if pa:
            return pa
        dd = m.get('download_date', '')
        if dd:
            return dd
        mt = m.get('mtime', 0)
        return _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime(mt)) if mt else ''

    def _name_key(m):
        return (m.get('civitai_model_name') or m.get('filename', '')).lower()

    if sort_by == "date_desc":
        installed_models.sort(key=_date_key, reverse=True)
    elif sort_by == "date_asc":
        installed_models.sort(key=_date_key)
    elif sort_by == "name_asc":
        installed_models.sort(key=_name_key)
    elif sort_by == "name_desc":
        installed_models.sort(key=_name_key, reverse=True)

    # For models without local preview, fetch thumbnails from API in background
    needs_fetch = [m for m in installed_models if not m.get('thumbnail') and m.get('civitai_model_id')]
    if needs_fetch:
        def _bg_fetch_thumbnails(models):
            for model in models:
                try:
                    data = api.get_model(model['civitai_model_id'])
                    if not data:
                        continue
                    versions = data.get('modelVersions', [])
                    if not versions:
                        continue
                    images = versions[0].get('images', [])
                    if not images:
                        continue

                    img = images[0]
                    url = img.get('url', '')
                    img_type = img.get('type', 'image')
                    if not url:
                        continue

                    base = os.path.splitext(model['path'])[0]

                    if img_type == 'video':
                        # Video: download as .preview.mp4
                        dl_url = url.replace("width=", "transcode=true,width=")
                        preview_path = base + '.preview.mp4'
                        if not os.path.exists(preview_path):
                            try:
                                resp = api.session.get(dl_url, timeout=60)
                                if resp.status_code == 200:
                                    with open(preview_path, 'wb') as f:
                                        f.write(resp.content)
                            except Exception:
                                pass
                        model['thumbnail'] = f"/file={preview_path}" if os.path.exists(preview_path) else url
                        model['thumbnail_type'] = 'video'
                    else:
                        # Image: download as .preview.png
                        preview_path = base + '.preview.png'
                        if not os.path.exists(preview_path):
                            try:
                                resp = api.session.get(url, timeout=30)
                                if resp.status_code == 200:
                                    with open(preview_path, 'wb') as f:
                                        f.write(resp.content)
                            except Exception:
                                pass
                        model['thumbnail'] = f"/file={preview_path}" if os.path.exists(preview_path) else url
                        model['thumbnail_type'] = 'image'
                except Exception:
                    pass
        threading.Thread(target=_bg_fetch_thumbnails, args=(needs_fetch,), daemon=True).start()

    return make_installed_cards_html(installed_models, selected_paths=_selected_installed_paths)


def get_folder_tree_html():
    """Generate HTML for folder tree navigation."""
    from cb_api import scan_installed_civitai_models

    installed_models, _ = scan_installed_civitai_models()

    # Build folder tree from model folder paths (e.g. "models/Lora/sub", "embeddings")
    folder_tree = {}
    for model in installed_models:
        folder = model.get('folder', '').replace('\\', '/')
        if folder:
            parts = folder.split('/')
            current = folder_tree
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]

    def render_folder_tree(tree, indent=0, path=''):
        html_parts = []
        for folder_name, sub_tree in sorted(tree.items()):
            full_path = f"{path}/{folder_name}" if path else folder_name
            pad = indent * 16 + 12
            icon = "📁" if indent <= 1 else "📂"
            html_parts.append(
                f'<div class="civ-folder-subitem" data-folder="{full_path.replace(chr(34), "&quot;")}" '
                f'style="padding-left: {pad}px;">{icon} {folder_name}</div>'
            )
            if sub_tree:
                html_parts.append(render_folder_tree(sub_tree, indent + 1, full_path))
        return ''.join(html_parts)

    parts = ['<div class="civ-folder-tree">']
    parts.append('<div class="civ-folder-item civ-folder-all" data-folder="">📁 All Models</div>')
    parts.append(render_folder_tree(folder_tree))
    parts.append('</div>')

    return ''.join(parts)


def load_installed_model_details(model_id_str, model_name):
    """Load model details when an installed model card is clicked."""
    if not model_id_str:
        # No CivitAI ID, show basic file info
        if model_name:
            return (
                gr.update(value=f'<div class="civ-preview"><h2>{model_name}</h2><p>No CivitAI metadata found. This model was not downloaded from CivitAI Manager Plus.</p></div>'),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(visible=False),
            )
        return [gr.update()] * 5
    
    try:
        model_id = int(model_id_str)
    except (ValueError, TypeError):
        return [gr.update()] * 5
    
    # Fetch model info from CivitAI API
    data = api.get_model(model_id)
    if not data:
        return (
            gr.update(value=f'<div class="civ-error">Could not fetch model info from CivitAI</div>'),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(visible=False),
        )
    
    model_name = data.get("name", "Unknown")
    creator = data.get("creator", {}).get("username", "Unknown")
    content_type = data.get("type", "")
    versions = data.get("modelVersions", [])
    
    # Preview HTML
    preview_parts = [f'<div class="civ-preview">']
    preview_parts.append(f'<h2>{model_name}</h2>')
    preview_parts.append(f'<p>by <b>{creator}</b> | {content_type}</p>')
    
    desc = data.get("description", "")
    if desc:
        preview_parts.append(f'<div class="civ-description">{desc}</div>')
    
    # Sample images
    if versions:
        imgs = versions[0].get("images", [])
        if imgs:
            preview_parts.append('<div class="civ-sample-images">')
            for img in imgs[:8]:
                url = img.get("url", "")
                if img.get("type") == "video":
                    url = url.replace("width=", "transcode=true,width=")
                    preview_parts.append(f'<video controls muted playsinline style="max-width:300px"><source src="{url}" type="video/mp4"></video>')
                else:
                    preview_parts.append(f'<img loading="lazy" src="{url}" style="max-width:300px;border-radius:8px;margin:4px">')
            preview_parts.append('</div>')
    
    preview_parts.append('</div>')
    preview_html = ''.join(preview_parts)
    
    # Extract thumbnail URL
    thumbnail = ""
    if versions:
        imgs = versions[0].get("images", [])
        if imgs:
            thumbnail = imgs[0].get("url", "")
    
    return (
        gr.update(value=preview_html),
        gr.update(value=str(model_id)),
        gr.update(value=model_name),
        gr.update(value=thumbnail),
        gr.update(visible=True),
    )


def do_show_installed_model_info_btn(model_id_str):
    """Show model info button when installed model is selected."""
    return gr.update(visible=bool(model_id_str))


def do_toggle_local_save(trigger_str):
    """Handle save/delete local model info triggered by checkbox in popup.
    Format: "model_id:action:random_suffix"
    Returns result string for JS feedback.
    """
    if not trigger_str or ':' not in trigger_str:
        return gr.update()

    parts = trigger_str.split(':')
    try:
        model_id = int(parts[0])
        action = parts[1]  # "save" or "delete"
    except (ValueError, IndexError):
        return gr.update()

    import time
    ts = int(time.time() * 1000)

    if action == "save":
        ok = _save_model_info_local(model_id)
        print(f"[DEBUG] Save local model info {model_id}: {'OK' if ok else 'FAILED'}", file=sys.stderr)
        return gr.update(value=f"{'ok' if ok else 'error'}:{model_id}:{ts}")
    elif action == "delete":
        _delete_model_info_local(model_id)
        print(f"[DEBUG] Deleted local model info {model_id}", file=sys.stderr)
        return gr.update(value=f"deleted:{model_id}:{ts}")

    return gr.update()


# --- UI Definition ---

def on_ui_tabs():
    with gr.Blocks() as civitai_browser:

        # Hidden states
        model_id_state = gr.Textbox(visible=False, elem_id="civ_model_id")
        model_name_state = gr.Textbox(visible=False, elem_id="civ_model_name")
        model_thumbnail_state = gr.Textbox(visible=False, elem_id="civ_model_thumb")
        model_select_trigger = gr.Textbox(visible=False, elem_id="civ_model_select")
        card_checkbox_trigger = gr.Textbox(visible=False, elem_id="civ_card_checkbox")

        # Model info popup
        model_info_html = gr.HTML(value="", elem_id="civ_model_info_html", visible=False)
        save_model_info_trigger = gr.Textbox(visible=False, elem_id="civ_save_model_info")
        save_model_info_result = gr.Textbox(visible=False, elem_id="civ_save_model_info_result")

        # Image metadata for txt2img
        civitai_image_url_input = gr.Textbox(visible=False, elem_id="civitai_image_url_input")
        civitai_txt2img_output = gr.Textbox(visible=False, elem_id="civitai_txt2img_output")

        # Load saved search config for default values
        _saved = _load_search_config()
        print(f"[DEBUG] Loaded search config: {_saved}", file=sys.stderr)

        with gr.Tabs():
            # === TAB 1: Browse ===
            with gr.Tab("Browse"):
                with gr.Row():
                    search_input = gr.Textbox(
                        label="Search", placeholder="Search CivitAI models...",
                        value=_saved["query"], max_lines=1, scale=4
                    )
                    search_type = gr.Dropdown(
                        choices=["Model name", "User name", "Tag"],
                        value=_saved["search_type"], label="Search by", scale=1
                    )
                    search_btn = gr.Button("Search", variant="primary", scale=1)

                with gr.Accordion("Filters", open=False):
                    with gr.Row():
                        content_type = gr.Dropdown(
                            choices=CONTENT_TYPES, label="Content type",
                            multiselect=True, value=_saved["content_type"], scale=2
                        )
                        base_model_filter = gr.Dropdown(
                            choices=BASE_MODELS, label="Base model",
                            multiselect=True, value=_saved["base_model"], scale=2
                        )
                    with gr.Row():
                        sort_type = gr.Dropdown(
                            choices=SORT_OPTIONS, value=_saved["sort_type"],
                            label="Sort by", scale=1
                        )
                        period_type = gr.Dropdown(
                            choices=PERIOD_OPTIONS, value=_saved["period"],
                            label="Period", scale=1
                        )
                        show_nsfw = gr.Checkbox(
                            label="Show NSFW",
                            value=_saved["nsfw"],
                            scale=1
                        )
                        cards_per_page = gr.Slider(
                            minimum=5, maximum=100, value=_saved["cards_per_page"], step=5,
                            label="Cards per page", scale=1
                        )

                with gr.Row():
                    prev_btn = gr.Button("< Prev", scale=1)
                    page_info = gr.Textbox(value="Page 1 / 1", interactive=False, show_label=False, scale=2)
                    next_btn = gr.Button("Next >", scale=1)

                model_cards = gr.HTML(value='<div class="civ-no-results">Search for models above.</div>')

                with gr.Row():
                    select_all_btn = gr.Button("Select All / Deselect All", scale=1)
                    download_selected_btn = gr.Button("Download Selected", variant="primary", scale=1)
                    save_local_on_download = gr.Checkbox(
                        label="💾 Save Local Info",
                        value=_saved["save_local"], scale=1
                    )
                select_status = gr.Textbox(value="", show_label=False, interactive=False, max_lines=1)

            # === TAB 2: Favorites ===
            with gr.Tab("Favorites"):
                fav_refresh_btn = gr.Button("Refresh Favorites")
                fav_status = gr.Textbox(value="", show_label=False, interactive=False)
                fav_html = gr.HTML(value=get_favorites_html())

            # === TAB 3: Installed Models ===
            with gr.Tab("Installed"):
                with gr.Row():
                    # Left side: Sort + Folder tree (collapsible — see hamburger
                    # toggle below; classes civ-sidebar-hidden / civ-sidebar-overlay
                    # are flipped from JS at runtime to hide it or float it
                    # over the cards as an overlay).
                    # Start collapsed — first ☰ click opens it as an overlay.
                    with gr.Column(
                        scale=1, min_width=200,
                        elem_id="civ_folder_sidebar",
                        elem_classes=["civ-sidebar-hidden"],
                    ):
                        installed_sort = gr.Dropdown(
                            choices=["Publish Date (Newest)", "Publish Date (Oldest)",
                                     "Filename (A-Z)", "Filename (Z-A)"],
                            value={
                                "date_desc": "Publish Date (Newest)",
                                "date_asc": "Publish Date (Oldest)",
                                "name_asc": "Filename (A-Z)",
                                "name_desc": "Filename (Z-A)"
                            }.get(_saved.get("installed_sort", "date_desc"), "Publish Date (Newest)"),
                            label="Sort by", scale=1
                        )
                        installed_refresh_btn = gr.Button("Refresh Folder Tree", variant="secondary")
                        gr.Markdown("### Folders", elem_id="civ_folders_title")
                        folder_tree_html = gr.HTML(value=get_folder_tree_html(), elem_id="civ_folder_tree")

                    # Right side: Model cards + batch-action row
                    with gr.Column(scale=4):
                        with gr.Row(elem_id="civ_installed_actions"):
                            # Hamburger toggle for the Folders sidebar.
                            # Pure-JS behavior; no backend handler bound.
                            sidebar_toggle_btn = gr.Button(
                                "☰",
                                elem_id="civ_sidebar_toggle_btn",
                                scale=0
                            )
                            installed_delete_btn = gr.Button(
                                "🗑️ Delete Selected",
                                variant="stop",
                                elem_id="civ_installed_delete_btn",
                                scale=1
                            )
                            installed_select_all_btn = gr.Button(
                                "✓ Select All in View",
                                variant="secondary",
                                elem_id="civ_installed_select_all_btn",
                                scale=1
                            )
                            # Use gr.HTML rather than gr.Markdown — older Gradio
                            # versions can fail to register an event endpoint
                            # when Markdown is in outputs[], producing the
                            # "unnamed_endpoints" JS error and silently breaking
                            # adjacent bindings (e.g. the folder filter click).
                            installed_delete_status = gr.HTML(
                                value="", elem_id="civ_installed_delete_status"
                            )
                        installed_html = gr.HTML(
                            value='<div class="civ-no-results">Select a folder to view models.</div>',
                            elem_id="civ_installed_html"
                        )

                # Hidden states for installed model selection
                installed_model_id_state = gr.Textbox(visible=False, elem_id="civ_installed_model_id")
                installed_model_name_state = gr.Textbox(visible=False, elem_id="civ_installed_model_name")
                installed_filter_folder = gr.Textbox(visible=False, elem_id="civ_installed_filter_folder")
                # Hidden bridge: JS writes "<path>_<random>" here on checkbox click
                installed_select_toggle = gr.Textbox(visible=False, elem_id="civ_installed_select_toggle")

            # === TAB 4: Downloads ===
            with gr.Tab("Downloads"):
                with gr.Row():
                    dl_refresh_btn = gr.Button("Refresh", scale=1)
                    dl_retry_btn = gr.Button("Retry Failed", variant="primary", scale=1)
                    dl_clear_btn = gr.Button("Clear Finished", scale=1)
                dl_html = gr.HTML(value=dl_manager.get_status_html())
                dl_auto_refresh_trigger = gr.Textbox(visible=False, elem_id="civ_dl_auto_refresh")

        # --- Event Bindings ---
        search_inputs = [search_input, search_type, content_type, base_model_filter,
                         sort_type, period_type, show_nsfw, cards_per_page, save_local_on_download]
        search_outputs = [model_cards, page_info]

        search_btn.click(fn=do_search, inputs=search_inputs, outputs=search_outputs)
        search_input.submit(fn=do_search, inputs=search_inputs, outputs=search_outputs)

        prev_btn.click(fn=do_prev_page, inputs=search_inputs, outputs=search_outputs)
        next_btn.click(fn=do_next_page, inputs=search_inputs, outputs=search_outputs)

        # Browse card click → open model info popup (triggered from JS via textbox)
        model_select_trigger.change(
            fn=get_model_info_html,
            inputs=[model_select_trigger],
            outputs=[model_info_html]
        )

        # Select All - updates model cards HTML and shows status
        select_all_btn.click(
            fn=do_select_all,
            inputs=[],
            outputs=[model_cards, select_status]
        )

        # Download Selected
        download_selected_btn.click(
            fn=do_download_selected,
            inputs=[save_local_on_download],
            outputs=[dl_html, select_status]
        )

        # Card checkbox toggle - update selection state and re-render cards
        card_checkbox_trigger.change(
            fn=do_toggle_card_selection,
            inputs=[card_checkbox_trigger],
            outputs=[model_cards]
        )

        # Image URL input - fetch metadata and send to txt2img
        civitai_image_url_input.change(
            fn=fetch_and_send_image_metadata,
            inputs=[civitai_image_url_input],
            outputs=[civitai_txt2img_output]
        )
        
        # Output change triggers JS to send to txt2img
        civitai_txt2img_output.change(fn=None, inputs=[civitai_txt2img_output], _js="(genInfo) => genInfo_to_txt2img(genInfo)")

        # Favorites
        fav_refresh_btn.click(fn=do_refresh_fav, outputs=[fav_html])

        # Save model info locally (triggered by checkbox in popup)
        save_model_info_trigger.change(
            fn=do_toggle_local_save,
            inputs=[save_model_info_trigger],
            outputs=[save_model_info_result],
            queue=False,
            show_progress=False
        )

        # Map display labels to sort keys
        _sort_label_to_key = {
            "Publish Date (Newest)": "date_desc",
            "Publish Date (Oldest)": "date_asc",
            "Filename (A-Z)": "name_asc",
            "Filename (Z-A)": "name_desc",
        }

        def _installed_with_sort(folder, sort_label):
            sort_key = _sort_label_to_key.get(sort_label, "date_desc")
            _save_installed_sort(sort_key)
            return get_installed_models_html(folder, sort_key)

        # Installed - Folder click or sort change triggers scan + filter.
        # queue=False so Gradio doesn't enqueue these behind unrelated events —
        # the handler is fast once the installed-scan cache is warm.
        installed_filter_folder.change(
            fn=_installed_with_sort,
            inputs=[installed_filter_folder, installed_sort],
            outputs=[installed_html],
            queue=False,
            show_progress=False
        )
        installed_sort.change(
            fn=_installed_with_sort,
            inputs=[installed_filter_folder, installed_sort],
            outputs=[installed_html],
            queue=False,
            show_progress=False
        )

        # Installed model selection → popup
        installed_model_id_state.change(
            fn=get_model_info_html,
            inputs=[installed_model_id_state],
            outputs=[model_info_html],
            queue=False,
            show_progress=False
        )

        # Refresh folder tree — also invalidate the installed-scan cache so the
        # next folder/sort click picks up newly added/removed files from disk.
        def _refresh_folder_tree():
            from cb_api import invalidate_installed_scan_cache
            invalidate_installed_scan_cache()
            return get_folder_tree_html()

        installed_refresh_btn.click(
            fn=_refresh_folder_tree,
            inputs=[],
            outputs=[folder_tree_html]
        )

        # Installed - Checkbox toggle (JS writes "<path>_<random>" to the bridge textbox)
        installed_select_toggle.change(
            fn=do_toggle_installed_selection,
            inputs=[installed_select_toggle, installed_filter_folder, installed_sort],
            outputs=[installed_html],
            queue=False,
            show_progress=False
        )

        # Installed - Batch delete selected models (+ refresh cards + status line)
        installed_delete_btn.click(
            fn=do_delete_selected_installed,
            inputs=[installed_filter_folder, installed_sort],
            outputs=[installed_html, installed_delete_status],
            queue=False,
            show_progress=False
        )

        # Installed - Select all visible (or toggle off if already all selected)
        installed_select_all_btn.click(
            fn=do_select_all_installed,
            inputs=[installed_filter_folder, installed_sort],
            outputs=[installed_html],
            queue=False,
            show_progress=False
        )

        # Downloads
        dl_refresh_btn.click(fn=do_refresh_dl, outputs=[dl_html])
        dl_retry_btn.click(fn=do_retry_failed, outputs=[dl_html])
        dl_clear_btn.click(fn=do_clear_dl, outputs=[dl_html])
        dl_auto_refresh_trigger.change(
            fn=do_refresh_dl, outputs=[dl_html], queue=False, show_progress=False
        )

        # Force-apply saved config on UI load (some Gradio versions ignore value= for certain widgets)
        _sort_key_to_label = {v: k for k, v in _sort_label_to_key.items()}

        def _apply_saved_config():
            return (
                gr.update(value=_saved["search_type"]),
                gr.update(value=_saved["sort_type"]),
                gr.update(value=_saved["period"]),
                gr.update(value=_saved["nsfw"]),
                gr.update(value=_saved["save_local"]),
                gr.update(value=_saved["cards_per_page"]),
                gr.update(value=_sort_key_to_label.get(_saved.get("installed_sort", "date_desc"), "Publish Date (Newest)")),
            )
        civitai_browser.load(
            fn=_apply_saved_config,
            outputs=[search_type, sort_type, period_type, show_nsfw, save_local_on_download, cards_per_page, installed_sort]
        )

    return (civitai_browser, "CivitAI Manager Plus", "civitai_browser_new"),


script_callbacks.on_ui_tabs(on_ui_tabs)
