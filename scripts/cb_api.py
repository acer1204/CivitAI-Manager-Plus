"""CivitAI API client with retry, timeout, and caching."""

import requests
import json
import time
import os
import re
import hashlib
import platform
from io import BytesIO
from modules.shared import opts, cmd_opts
from modules.paths import models_path, data_path

try:
    from PIL import Image
except ImportError:
    Image = None


class CivitAIClient:
    BASE_URL = "https://civitai.com/api/v1"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
        })
        self._cache = {}
        self._cache_ttl = 300

    def _get_api_key(self):
        return getattr(opts, "civitai_api_key", "")

    def _request(self, url, params=None, use_cache=True, timeout=(10, 20)):
        """Make an API request with retry, timeout, and caching."""
        cache_key = url + (json.dumps(params, sort_keys=True) if params else "")

        if use_cache and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                return data

        api_key = self._get_api_key()
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, headers=headers,
                                        timeout=timeout, verify=True)
                resp.raise_for_status()
                resp.encoding = "utf-8"
                data = resp.json()
                if use_cache and isinstance(data, dict):
                    self._cache[cache_key] = (time.time(), data)
                return data
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

    def search_models(self, query="", search_type="Model name", content_type=None,
                      base_model=None, sort="Highest Rated", period="AllTime",
                      page=1, limit=20, nsfw=False, cursor=None):
        """Search for models on CivitAI. Returns dict with 'items' and 'metadata'."""
        params = {"limit": limit, "sort": sort, "nsfw": str(nsfw).lower()}

        if period and period != "AllTime":
            params["period"] = period.replace(" ", "")

        if content_type:
            if isinstance(content_type, list):
                params["types"] = ",".join(content_type)
            else:
                params["types"] = content_type

        if base_model:
            if isinstance(base_model, list):
                params["baseModels"] = ",".join(base_model)
            else:
                params["baseModels"] = base_model

        if query:
            if "civitai.com" in query:
                match = re.search(r'models/(\d+)', query)
                if match:
                    params["ids"] = match.group(1)
            elif search_type == "User name":
                params["username"] = query
            elif search_type == "Tag":
                params["tag"] = query
            else:
                params["query"] = query

        if cursor:
            params["cursor"] = cursor
        elif page > 1:
            params["page"] = page

        try:
            return self._request(f"{self.BASE_URL}/models", params=params, use_cache=False)
        except Exception as e:
            return {"items": [], "metadata": {"totalPages": 0, "currentPage": page},
                    "error": str(e)}

    def get_model(self, model_id):
        """Get detailed model information."""
        try:
            return self._request(f"{self.BASE_URL}/models/{model_id}")
        except Exception:
            return None

    def get_model_version(self, version_id):
        """Get model version details with images."""
        try:
            return self._request(f"{self.BASE_URL}/model-versions/{version_id}")
        except Exception:
            return None

    def get_image_metadata(self, image_url):
        """Fetch image and extract generation metadata (prompt, negative prompt, seed, etc.)."""
        if not Image:
            return None
        
        headers = {"User-Agent": "Mozilla/5.0"}
        api_key = self._get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        try:
            resp = requests.get(image_url, headers=headers, timeout=(10, 30))
            if resp.status_code == 200:
                image = Image.open(BytesIO(resp.content))
                # Use SD WebUI's built-in function to read info from image
                try:
                    from modules.images import read_info_from_image
                    geninfo = read_info_from_image(image)
                    return geninfo
                except ImportError:
                    # Fallback: try to read from PNG info
                    info = image.info.get('parameters', '')
                    return info if info else None
        except Exception:
            pass
        return None

    def clear_cache(self):
        self._cache.clear()


# --- Path utilities ---

CONTENT_TYPE_FOLDERS = {
    "Checkpoint": ("ckpt_dir", "Stable-diffusion"),
    "LORA": ("lora_dir", "Lora"),
    "LoCon": ("lora_dir", "Lora"),
    "DoRA": ("lora_dir", "Lora"),
    "TextualInversion": ("embeddings_dir", "embeddings"),
    "VAE": ("vae_dir", "VAE"),
    "Controlnet": ("controlnet_dir", "ControlNet"),
    "Hypernetwork": ("hypernetwork_dir", "hypernetworks"),
    "Poses": (None, "Poses"),
    "Wildcards": (None, "Wildcards"),
    "Workflows": (None, "Workflows"),
    "MotionModule": (None, "MotionModule"),
    "Other": (None, "Other"),
}


def get_model_folder(content_type):
    """Get the base folder path for a content type."""
    cmd_attr, default_folder = CONTENT_TYPE_FOLDERS.get(content_type, (None, "Other"))

    if cmd_attr:
        custom_path = getattr(cmd_opts, cmd_attr, None)
        if custom_path:
            return custom_path

    if content_type == "TextualInversion":
        return os.path.join(data_path, default_folder)

    return os.path.join(models_path, default_folder)


def clean_folder_name(name):
    """Sanitize a string for use as a folder name."""
    if not name:
        return "Unknown"
    name = re.sub(r'[<>:"/\\|?*]', '', str(name))
    name = name.strip().rstrip('.')
    return name if name else "Unknown"


def build_install_path(content_type, base_model="", author="", model_name="", auto_organize=True):
    """Build the full install path, optionally auto-organized.
    Path structure: base_folder / base_model / author / (model files directly)
    """
    base = get_model_folder(content_type)

    if not auto_organize:
        return base

    parts = [base]
    if base_model:
        parts.append(clean_folder_name(base_model))
    if author:
        parts.append(clean_folder_name(author))

    return os.path.join(*parts)


# --- Model card HTML generation ---

def make_model_cards_html(items, installed_hashes=None, installed_files=None, selected_ids=None):
    """Generate HTML for model cards grid."""
    if installed_hashes is None:
        installed_hashes = set()
    if installed_files is None:
        installed_files = set()
    if selected_ids is None:
        selected_ids = set()

    if not items:
        return '<div class="civ-no-results">No models found.</div>'

    parts = ['<div class="civ-card-grid">']

    for item in items:
        model_id = str(item.get("id", ""))
        model_name = item.get("name", "Unknown")
        nsfw = "civ-nsfw" if item.get("nsfw") else ""
        content_type = item.get("type", "")
        creator = item.get("creator", {}).get("username", "Unknown")

        versions = item.get("modelVersions", [])
        if not versions:
            continue

        version = versions[0]
        base_model = version.get("baseModel", "")
        images = version.get("images", [])

        # Determine install status
        is_installed = False
        for v_idx, v in enumerate(versions):
            for f in v.get("files", []):
                sha = f.get("hashes", {}).get("SHA256", "").upper()
                fname = f.get("name", "").lower()
                if (sha and sha in installed_hashes) or fname in installed_files:
                    is_installed = True
                    break
            if is_installed:
                break

        # Selection status
        is_selected = model_id in selected_ids
        selected_class = "civ-card-selected" if is_selected else ""
        installed_class = "civ-installed" if is_installed else ""

        # Image
        if images:
            img = images[0]
            img_url = img.get("url", "")
            if img.get("type") == "video":
                img_url = img_url.replace("width=", "transcode=true,width=")
                media_tag = f'<video class="civ-card-media" autoplay loop muted playsinline><source src="{img_url}" type="video/mp4"></video>'
            else:
                media_tag = f'<img class="civ-card-media" loading="lazy" src="{img_url}">'
        else:
            media_tag = '<div class="civ-card-no-img">No Preview</div>'

        # Truncate name
        display_name = model_name[:35] + "..." if len(model_name) > 35 else model_name

        # Escape for HTML attributes
        esc_name = model_name.replace('"', '&quot;').replace("'", "&#39;")

        # Hide checkbox for installed models
        checkbox_html = ""
        if not is_installed:
            checkbox_class = "civ-card-checkbox checked" if is_selected else "civ-card-checkbox"
            checkbox_html = f'<div class="{checkbox_class}" data-model-id="{model_id}"></div>'

        card = f'''<div class="civ-card {nsfw} {installed_class} {selected_class}"
                        data-model-id="{model_id}"
                        data-model-name="{esc_name}"
                        data-content-type="{content_type}"
                        data-base-model="{base_model}"
                        data-creator="{creator}"
                        data-installed="{str(is_installed).lower()}">
            {media_tag}
            <div class="civ-card-name" title="{esc_name}">{display_name}</div>
            <div class="civ-card-meta">{base_model}</div>
            {checkbox_html}
        </div>'''

        parts.append(card)

    parts.append('</div>')
    return ''.join(parts)


# --- Installed model scanning ---

def scan_installed_models():
    """Scan all model folders for installed files. Returns (filenames_set, sha256_set)."""
    filenames = set()
    sha256s = set()

    for ctype in CONTENT_TYPE_FOLDERS:
        folder = get_model_folder(ctype)
        if not os.path.isdir(folder):
            continue
        try:
            for root, dirs, files in os.walk(folder, followlinks=True):
                for f in files:
                    filenames.add(f.lower())
                    if f.endswith('.json'):
                        try:
                            with open(os.path.join(root, f), 'r', encoding='utf-8') as jf:
                                data = json.load(jf)
                                if isinstance(data, dict) and data.get('sha256'):
                                    sha256s.add(data['sha256'].upper())
                        except Exception:
                            pass
        except Exception:
            pass

    return filenames, sha256s


def scan_installed_civitai_models():
    """Scan installed models and try to find CivitAI model info from metadata files.
    Returns list of dicts with model info including civitai_model_id if available."""
    installed_models = []
    folders_set = set()
    seen_paths = set()  # Track seen file paths to avoid duplicates

    for ctype, (_, default_folder) in CONTENT_TYPE_FOLDERS.items():
        folder = get_model_folder(ctype)
        if not os.path.isdir(folder):
            continue

        try:
            for root, dirs, files in os.walk(folder, followlinks=True):
                # Collect folder paths for tree
                rel_folder = os.path.relpath(root, folder)
                if rel_folder != '.':
                    folders_set.add(rel_folder)

                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in ('.safetensors', '.ckpt', '.pt', '.bin', '.pth'):
                        continue

                    file_path = os.path.join(root, f)
                    
                    # Skip if we've already seen this file
                    if file_path in seen_paths:
                        continue
                    seen_paths.add(file_path)
                    
                    json_path = os.path.splitext(file_path)[0] + '.json'

                    model_info = {
                        'filename': f,
                        'path': file_path,
                        'folder': rel_folder if rel_folder != '.' else '',
                        'content_type': ctype,
                        'size': os.path.getsize(file_path),
                        'civitai_model_id': None,
                        'civitai_model_name': None,
                        'thumbnail': None,
                    }

                    # Try to read metadata from JSON file
                    if os.path.exists(json_path):
                        try:
                            with open(json_path, 'r', encoding='utf-8') as jf:
                                meta = json.load(jf)
                                if isinstance(meta, dict):
                                    model_info['civitai_model_id'] = meta.get('model_id')
                                    model_info['civitai_model_name'] = meta.get('model_name')
                                    model_info['version_name'] = meta.get('version_name')
                        except Exception:
                            pass

                    installed_models.append(model_info)
        except Exception:
            pass

    return installed_models, sorted(folders_set)


def make_installed_cards_html(installed_models):
    """Generate HTML for installed models grid with preview images."""
    if not installed_models:
        return '<div class="civ-no-results">No models found. Download models from the Browse tab.</div>'
    
    parts = ['<div class="civ-card-grid">']
    
    for model in installed_models:
        filename = model.get('filename', 'Unknown')
        content_type = model.get('content_type', '')
        model_id = model.get('civitai_model_id')
        model_name = model.get('civitai_model_name') or os.path.splitext(filename)[0]
        size = model.get('size', 0)
        size_str = _format_size(size)
        folder = model.get('folder', '')
        thumbnail = model.get('thumbnail')
        
        # Truncate name for display
        display_name = model_name[:35] + "..." if len(model_name) > 35 else model_name
        esc_name = model_name.replace('"', '&quot;').replace("'", "&#39;")
        esc_folder = folder.replace('"', '&quot;')

        # Create image/video tag if thumbnail available
        thumb_type = model.get('thumbnail_type', 'image')
        if thumbnail and thumb_type == 'video':
            video_url = thumbnail.replace("width=", "transcode=true,width=")
            media_tag = f'<video class="civ-card-media" autoplay loop muted playsinline><source src="{video_url}" type="video/mp4"></video>'
        elif thumbnail:
            media_tag = f'<img class="civ-card-media" loading="lazy" src="{thumbnail}">'
        elif model_id:
            # Has CivitAI ID but no thumbnail cached - show placeholder with loading indicator
            media_tag = '<div class="civ-card-media-placeholder civ-loading"><div class="civ-loading-spinner">⏳</div><div class="civ-card-type-label">Loading...</div></div>'
        else:
            media_tag = '<div class="civ-card-media-placeholder"><div class="civ-card-type-label">' + content_type + '</div><div class="civ-card-file-icon">📦</div></div>'

        # Create card - click directly opens model info
        # Only add data-model-id if we have a valid ID
        card = f'''<div class="civ-card civ-installed-card{' civ-has-civitai-id' if model_id else ''}"
                        data-model-id="{model_id if model_id else ''}"
                        data-model-name="{esc_name}"
                        data-filename="{esc_name}"
                        data-folder="{esc_folder}"
                        data-content-type="{content_type}">
            {media_tag}
            <div class="civ-card-name" title="{esc_name}">{display_name}</div>
            <div class="civ-card-meta">{size_str}{f' • {folder}' if folder else ''}</div>
        </div>'''
        
        parts.append(card)
    
    parts.append('</div>')
    return ''.join(parts)


def _format_size(size_bytes):
    """Format bytes to human-readable string."""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# --- Favorites ---

def _favorites_path():
    config_dir = os.path.join(os.getcwd(), "config_states")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "civitai_favorites.json")


def load_favorites():
    path = _favorites_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_favorites(favorites):
    with open(_favorites_path(), 'w', encoding='utf-8') as f:
        json.dump(favorites, f, indent=2, ensure_ascii=False)


def toggle_favorite(model_id, model_name="", content_type="", thumbnail=""):
    """Add or remove a model from favorites. Returns (new_favorites_list, was_added)."""
    favs = load_favorites()
    model_id = int(model_id)

    existing = [f for f in favs if f.get("model_id") == model_id]
    if existing:
        favs = [f for f in favs if f.get("model_id") != model_id]
        save_favorites(favs)
        return favs, False
    else:
        favs.append({
            "model_id": model_id,
            "name": model_name,
            "type": content_type,
            "thumbnail": thumbnail,
            "added": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_favorites(favs)
        return favs, True
