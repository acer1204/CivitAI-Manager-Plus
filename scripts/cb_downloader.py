"""Download manager with retry, concurrent downloads, and auto-organize."""

import os
import re
import json
import time
import threading
import requests
import concurrent.futures
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable
from modules.shared import opts
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cb_api import get_model_folder, build_install_path, clean_folder_name

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


@dataclass
class DownloadItem:
    dl_id: int
    url: str
    filename: str
    install_path: str
    model_name: str
    version_name: str
    model_id: int
    version_id: int = 0
    sha256: str = ""
    preview_url: str = ""
    preview_type: str = "image"  # "image" or "video"
    published_at: str = ""  # CivitAI publish date
    trained_words: list = None  # Trigger words
    status: str = "queued"  # queued | downloading | completed | failed | cancelled
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    error: str = ""
    retries: int = 0
    max_retries: int = 5


class DownloadManager:
    def __init__(self):
        self._queue = []
        self._completed = []
        self._failed = []
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._next_id = 1
        self._running = False

    def add(self, url, filename, install_path, model_name, version_name,
            model_id, version_id=0, sha256="", preview_url="", preview_type="image",
            published_at="", trained_words=None) -> int:
        """Add a download to the queue and ensure background processor is running."""
        with self._lock:
            dl_id = self._next_id
            self._next_id += 1
            item = DownloadItem(
                dl_id=dl_id, url=url, filename=filename,
                install_path=install_path, model_name=model_name,
                version_name=version_name, model_id=model_id,
                version_id=int(version_id) if version_id else 0,
                sha256=sha256, preview_url=preview_url,
                preview_type=preview_type, published_at=published_at,
                trained_words=trained_words
            )
            self._queue.append(item)
        # Auto-start background processor
        self._ensure_processor_running()
        return dl_id

    def _ensure_processor_running(self):
        """Start background processor thread if not already running."""
        if self._running:
            return
        self._running = True
        self._cancel_event.clear()
        threading.Thread(target=self._background_processor, daemon=True).start()

    def _background_processor(self):
        """Background thread that continuously processes the download queue."""
        try:
            while True:
                has_more, _ = self.process_one_step()
                if not has_more:
                    break
                time.sleep(0.5)
        finally:
            self._running = False

    def remove(self, dl_id):
        with self._lock:
            self._queue = [i for i in self._queue if i.dl_id != dl_id]

    def cancel_all(self):
        self._cancel_event.set()
        with self._lock:
            for item in self._queue:
                if item.status == "queued":
                    item.status = "cancelled"

    def get_queue(self):
        with self._lock:
            return list(self._queue)

    def get_completed(self):
        return list(self._completed)

    def get_failed(self):
        return list(self._failed)

    def retry_failed(self):
        """Move all failed items back to queue for retry."""
        with self._lock:
            count = len(self._failed)
            for item in self._failed:
                item.status = "queued"
                item.error = ""
                item.retries = 0
                item.progress = 0
                self._queue.append(item)
            self._failed.clear()
        if count > 0:
            self._ensure_processor_running()
        return count

    def process_queue(self):
        """Process entire queue (blocking). Use process_next() for incremental."""
        if self._running:
            return
        self._running = True
        self._cancel_event.clear()
        try:
            while self.process_next():
                pass
        finally:
            self._running = False

    def process_next(self):
        """Process one pending item fully. Returns True if there are more items to process."""
        with self._lock:
            pending = [i for i in self._queue if i.status == "queued"]
            if not pending:
                return False

        item = pending[0]
        self._download_single(item, None)

        with self._lock:
            remaining = [i for i in self._queue if i.status == "queued"]
        return len(remaining) > 0

    def process_one_step(self):
        """Process downloads up to max_concurrent limit.
        Returns (has_more_steps, item_status_html) for incremental progress updates."""
        with self._lock:
            pending = [i for i in self._queue if i.status == "queued"]
            downloading = [i for i in self._queue if i.status == "downloading"]

        # If nothing is downloading and no pending, we're done
        if not pending and not downloading:
            return False, self.get_status_html()

        # Start more downloads up to max_concurrent
        max_concurrent = getattr(opts, "civitai_max_concurrent", 2)
        while pending and len(downloading) < max_concurrent:
            item = pending.pop(0)
            item.status = "downloading"
            downloading.append(item)
            threading.Thread(target=self._download_single_threaded, args=(item,), daemon=True).start()

        if downloading or pending:
            return True, self.get_status_html()

        return False, self.get_status_html()

    def _download_single_threaded(self, item):
        """Download a single item in a background thread with progress."""
        for attempt in range(item.max_retries):
            if self._cancel_event.is_set():
                item.status = "cancelled"
                return

            try:
                os.makedirs(item.install_path, exist_ok=True)
                file_path = os.path.join(item.install_path, item.filename)

                # Get actual download URL (follow redirects from CivitAI)
                download_url = self._resolve_download_url(item.url, item.model_id)
                if not download_url:
                    item.error = "File not found on CivitAI"
                    item.status = "failed"
                    self._move_to_failed(item)
                    return
                if download_url == "NO_API":
                    item.error = "CivitAI API key required"
                    item.status = "failed"
                    self._move_to_failed(item)
                    return

                # Download with progress
                self._http_download(download_url, file_path, item, None)

                if item.status == "completed":
                    self._save_metadata(item, file_path)
                    self._save_preview_image(item, file_path)
                    self._move_to_completed(item)
                    return

            except Exception as e:
                item.error = str(e)
                # Clean up partial file
                file_path = os.path.join(item.install_path, item.filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

            if attempt < item.max_retries - 1:
                # Longer delay for CDN errors (400/403), shorter for others
                wait = 5 * (attempt + 1) if '400' in str(item.error) or '403' in str(item.error) else 2 ** attempt
                item.retries = attempt + 1
                time.sleep(wait)

        item.status = "failed"
        if not item.error:
            item.error = f"Failed after {item.max_retries} attempts"
        self._move_to_failed(item)

    def _download_single(self, item, progress_callback=None):
        """Download a single item with retry logic."""
        item.status = "downloading"

        for attempt in range(item.max_retries):
            if self._cancel_event.is_set():
                item.status = "cancelled"
                return

            try:
                os.makedirs(item.install_path, exist_ok=True)
                file_path = os.path.join(item.install_path, item.filename)

                # Get actual download URL (follow redirects from CivitAI)
                download_url = self._resolve_download_url(item.url, item.model_id)
                if not download_url:
                    item.error = "File not found on CivitAI"
                    item.status = "failed"
                    self._move_to_failed(item)
                    return
                if download_url == "NO_API":
                    item.error = "CivitAI API key required"
                    item.status = "failed"
                    self._move_to_failed(item)
                    return

                # Download with progress
                self._http_download(download_url, file_path, item, progress_callback)

                if item.status == "completed":
                    self._save_metadata(item, file_path)
                    self._save_preview_image(item, file_path)
                    self._move_to_completed(item)
                    return

            except Exception as e:
                item.error = str(e)
                # Clean up partial file
                file_path = os.path.join(item.install_path, item.filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

            if attempt < item.max_retries - 1:
                wait = 2 ** attempt
                item.retries = attempt + 1
                if progress_callback:
                    progress_callback(0, f"Retry {attempt+1}/{item.max_retries}: {item.model_name}")
                time.sleep(wait)

        item.status = "failed"
        if not item.error:
            item.error = f"Failed after {item.max_retries} attempts"
        self._move_to_failed(item)

    def _resolve_download_url(self, url, model_id):
        """Get the actual download URL by following CivitAI redirects.
        Tries multiple auth methods: token query param, Bearer header, and no auth."""
        api_key = getattr(opts, "civitai_api_key", "")
        base_headers = {"User-Agent": "Mozilla/5.0"}

        # Build different auth attempts
        attempts = []
        if api_key:
            # 1. Token as query parameter
            sep = "&" if "?" in url else "?"
            attempts.append((f"{url}{sep}token={api_key}", base_headers))
            # 2. Authorization Bearer header
            attempts.append((url, {**base_headers, "Authorization": f"Bearer {api_key}"}))
        # 3. No auth
        attempts.append((url, base_headers))

        last_error = ""
        for try_url, try_headers in attempts:
            try:
                resp = requests.get(try_url, headers=try_headers, allow_redirects=False, timeout=(10, 10))
                if 300 <= resp.status_code <= 308:
                    location = resp.headers.get("Location", "")
                    if "login?returnUrl" in (location + resp.text):
                        continue  # Auth required, try next method
                    return location if location else try_url
                elif resp.status_code == 200:
                    return try_url
                elif resp.status_code in (401, 403):
                    continue  # Auth failed, try next method
                else:
                    # Log unexpected status (400, 404, etc.)
                    body = ""
                    try:
                        body = resp.text[:200]
                    except Exception:
                        pass
                    last_error = f"HTTP {resp.status_code}: {body}"
                    print(f"[DEBUG] Download resolve for model {model_id}: {last_error}", file=sys.stderr)
                    continue
            except Exception as e:
                last_error = str(e)
                print(f"[DEBUG] Download resolve error for model {model_id}: {e}", file=sys.stderr)

        # All attempts failed
        if not api_key:
            return "NO_API"
        return None

    def _http_download(self, url, file_path, item, progress_callback=None):
        """Download file via HTTP with progress tracking."""
        headers = {"User-Agent": "Mozilla/5.0"}

        # Only add auth header for CivitAI URLs, NOT for CDN pre-signed URLs
        # Pre-signed CDN URLs (cloudflarestorage, etc.) reject extra Authorization headers
        if "civitai.com" in url or "civitai.red" in url:
            api_key = getattr(opts, "civitai_api_key", "")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.get(url, headers=headers, stream=True, timeout=(10, 60))
        resp.raise_for_status()

        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        start_time = time.time()

        with open(file_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if self._cancel_event.is_set():
                    item.status = "cancelled"
                    return

                f.write(chunk)
                downloaded += len(chunk)

                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0

                if total > 0:
                    item.progress = downloaded / total
                    remaining = (total - downloaded) / speed if speed > 0 else 0
                    item.eta = time.strftime("%H:%M:%S", time.gmtime(remaining))
                    item.speed = _format_size(int(speed)) + "/s"

                    if progress_callback and elapsed > 0.5:
                        progress_callback(
                            item.progress,
                            f"Downloading {item.filename}: {_format_size(downloaded)}/{_format_size(total)} - {item.speed}"
                        )

        item.status = "completed"
        item.progress = 1.0

    def _save_metadata(self, item, file_path):
        """Save .json metadata for the downloaded model."""
        json_path = os.path.splitext(file_path)[0] + ".json"
        metadata = {
            "sha256": item.sha256,
            "model_id": item.model_id,
            "version_id": item.version_id,
            "model_name": item.model_name,
            "version_name": item.version_name,
            "download_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "published_at": item.published_at,
            "trained_words": item.trained_words or [],
        }
        try:
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    if isinstance(existing, dict):
                        existing.update(metadata)
                        metadata = existing
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _save_preview_image(self, item, file_path):
        """Download and save preview image/video alongside the model file."""
        if not item.preview_url:
            return
        try:
            base = os.path.splitext(file_path)[0]
            url = item.preview_url

            if item.preview_type == 'video':
                preview_path = base + ".preview.mp4"
                url = url.replace("width=", "transcode=true,width=")
            else:
                preview_path = base + ".preview.png"

            if os.path.exists(preview_path):
                return

            resp = requests.get(url, timeout=(10, 60),
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                with open(preview_path, 'wb') as f:
                    f.write(resp.content)
        except Exception:
            pass

    def _move_to_completed(self, item):
        with self._lock:
            if item in self._queue:
                self._queue.remove(item)
            self._completed.append(item)

    def _move_to_failed(self, item):
        with self._lock:
            if item in self._queue:
                self._queue.remove(item)
            self._failed.append(item)

    def get_status_html(self):
        """Generate HTML for download queue display."""
        parts = ['<div class="civ-dl-queue">']

        with self._lock:
            all_items = list(self._queue) + list(self._completed) + list(self._failed)

        if not all_items:
            parts.append('<div class="civ-dl-empty">No downloads</div>')
        else:
            for item in all_items:
                status_class = f"civ-dl-{item.status}"
                progress_width = f"{item.progress * 100:.1f}%"

                if item.status == "downloading":
                    status_text = f"{item.speed} - ETA: {item.eta or 'Calculating...'}"
                else:
                    status_text = {
                        "queued": "Queued",
                        "completed": "Completed",
                        "failed": f"Failed: {item.error}",
                        "cancelled": "Cancelled",
                    }.get(item.status, item.status)

                parts.append(f'''<div class="civ-dl-item {status_class}">
                    <div class="civ-dl-name">{item.model_name} - {item.version_name}</div>
                    <div class="civ-dl-filename">{item.filename}</div>
                    <div class="civ-dl-progress-bar">
                        <div class="civ-dl-progress-fill" style="width:{progress_width}"></div>
                    </div>
                    <div class="civ-dl-status">{status_text}</div>
                </div>''')

        parts.append('</div>')
        return ''.join(parts)

    def clear_finished(self):
        """Clear completed and failed items."""
        self._completed.clear()
        self._failed.clear()


def delete_model(file_path):
    """Delete a model file and its associated metadata."""
    if not os.path.exists(file_path):
        return False

    base = os.path.splitext(file_path)[0]
    files_to_delete = [file_path]

    for ext in ['.json', '.preview.png', '.preview.jpg', '.civitai.info']:
        p = base + ext
        if os.path.exists(p):
            files_to_delete.append(p)

    for f in files_to_delete:
        try:
            if send2trash:
                send2trash(f)
            else:
                os.remove(f)
        except Exception:
            pass

    return True


def _format_size(size_bytes):
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
