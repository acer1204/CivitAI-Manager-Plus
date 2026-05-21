"""One-time audit: list .json sidecars with missing/zero version_id.

Runs standalone — no SD WebUI needed. Walks the SD WebUI model directories
the same way the extension does and reports which model files would still
fall back to the wrong popup display because their sidecar lacks a usable
version_id.

Usage (from this folder):
    python audit_version_ids.py

Or specify SD WebUI root explicitly:
    python audit_version_ids.py F:\\sd-webui-aki-v4.10
"""

import json
import os
import sys


MODEL_EXTENSIONS = ('.safetensors', '.ckpt', '.pt', '.bin', '.pth')


def find_webui_root():
    """Try to auto-detect SD WebUI root from this script's location.
    Script lives at <webui>/extensions/sd-civitai-browser-new/audit_version_ids.py."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.dirname(os.path.dirname(here))
    if os.path.isdir(os.path.join(candidate, 'models')):
        return candidate
    return None


def audit(webui_root):
    models_path = os.path.join(webui_root, 'models')
    embeddings_path = os.path.join(webui_root, 'embeddings')

    scan_roots = []
    if os.path.isdir(models_path):
        scan_roots.append(('models', models_path))
    if os.path.isdir(embeddings_path):
        scan_roots.append(('embeddings', embeddings_path))

    if not scan_roots:
        print(f"ERROR: no models/ or embeddings/ folder found under {webui_root}")
        return 1

    total_models = 0
    total_with_sidecar = 0
    bad = []   # version_id missing / 0 / None
    no_json = []  # no sidecar at all

    for root_name, root_path in scan_roots:
        for dirpath, _dirs, files in os.walk(root_path, followlinks=True):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in MODEL_EXTENSIONS:
                    continue
                total_models += 1
                model_path = os.path.join(dirpath, f)
                base = os.path.splitext(model_path)[0]
                json_path = base + '.json'

                rel = os.path.relpath(model_path, webui_root).replace('\\', '/')

                if not os.path.exists(json_path):
                    no_json.append(rel)
                    continue

                total_with_sidecar += 1
                try:
                    with open(json_path, 'r', encoding='utf-8') as jf:
                        meta = json.load(jf)
                except Exception as e:
                    bad.append((rel, f'(unreadable JSON: {e})', None, None))
                    continue

                if not isinstance(meta, dict):
                    bad.append((rel, '(JSON not an object)', None, None))
                    continue

                vid = meta.get('version_id')
                mid = meta.get('model_id')
                mname = meta.get('model_name') or ''
                vname = meta.get('version_name') or ''

                if not vid or vid in (0, '0', None):
                    bad.append((rel, mname, mid, vname))

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'audit_report.txt')
    lines = []
    lines.append('=' * 72)
    lines.append(f'SD WebUI root: {webui_root}')
    lines.append(f'Total model files found: {total_models}')
    lines.append(f'   with .json sidecar  : {total_with_sidecar}')
    lines.append(f'   without .json       : {len(no_json)}')
    lines.append(f'   sidecar but version_id is 0/missing: {len(bad)}')
    lines.append('=' * 72)

    if bad:
        lines.append('')
        lines.append('--- Sidecars with version_id = 0 / missing ---')
        lines.append('(These will fall back to top-5 versions in the popup)')
        lines.append('')
        for rel, mname, mid, vname in bad:
            mid_disp = mid if mid else '(no model_id)'
            vname_disp = f' / {vname}' if vname else ''
            lines.append(f'  {rel}')
            lines.append(f'      model_id={mid_disp}  name={mname}{vname_disp}')

    if no_json:
        lines.append('')
        lines.append(f'--- Model files with NO sidecar ({len(no_json)}) ---')
        lines.append('(Not downloaded via this extension. Popup will not show version-specific data.)')
        lines.append('')
        for rel in no_json:
            lines.append(f'  {rel}')

    # Write full report to file (UTF-8, safe for Japanese/Chinese/special chars)
    with open(report_path, 'w', encoding='utf-8') as rf:
        rf.write('\n'.join(lines) + '\n')

    # Print summary to stdout — safe ASCII only, so it works in cp950 / Big5 consoles
    print('=' * 60)
    print(f'Total model files: {total_models}')
    print(f'  With sidecar     : {total_with_sidecar}')
    print(f'  Without sidecar  : {len(no_json)}')
    print(f'  Bad version_id   : {len(bad)}')
    print('=' * 60)
    print(f'Full report (UTF-8): {report_path}')
    print('Open it with VS Code / Notepad to see the model list.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 1:
        root = sys.argv[1]
    else:
        root = find_webui_root()
        if not root:
            print('ERROR: could not auto-detect SD WebUI root.')
            print('Usage: python audit_version_ids.py <path-to-sd-webui>')
            sys.exit(1)
    sys.exit(audit(root))
