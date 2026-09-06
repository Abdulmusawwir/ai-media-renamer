"""One-shot setup: download llama-server.exe + model + mmproj + configure."""
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from engine import (  # noqa: E402
    LLAMACPP_GGUF_CATALOG,
    LLAMACPP_SERVER_EXE,
    config,
    configure_llamacpp_install,
    download_file,
)

APP_DIR = Path(os.environ["APPDATA"]) / "ai-media-renamer"
BIN_DIR = APP_DIR / "bin"
MODELS_DIR = APP_DIR / "models"
SERVER_PATH = BIN_DIR / LLAMACPP_SERVER_EXE

# ── Step 1: llama-server.exe ────────────────────────────────────────
print("=== Step 1: llama-server.exe ===")
skip_download = False
if SERVER_PATH.exists() and SERVER_PATH.stat().st_size > 1_000_000:
    print(f"  Already OK ({SERVER_PATH.stat().st_size} bytes)")
    skip_download = True
else:
    if SERVER_PATH.exists():
        SERVER_PATH.unlink()
        print("  Deleted corrupted stub")

if not skip_download:
    print("  Downloading llama.cpp release...")
    LLAMA_RELEASE = "b10327"
    url = (
        f"https://github.com/ggml-org/llama.cpp/releases/download/"
        f"{LLAMA_RELEASE}/llama-{LLAMA_RELEASE}-bin-win-cpu-x64.zip"
    )
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "llama.zip")
    last_pct = [-1]

    def _progress(block, block_size, total):
        done = block * block_size
        pct = int(done * 100 / total) if total > 0 else 0
        if pct != last_pct[0] and pct % 10 == 0:
            last_pct[0] = pct
            print(f"    {pct}%")

    urllib.request.urlretrieve(url, zip_path, reporthook=_progress)
    print(f"  Downloaded: {os.path.getsize(zip_path)} bytes")

    extract_dir = os.path.join(tmp_dir, "extracted")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            shutil.copy2(os.path.join(root, f), BIN_DIR / f)
            count += 1
    print(f"  Copied {count} files to bin/")
    shutil.rmtree(tmp_dir, ignore_errors=True)

# ── Step 2: Model file (GGUF) ──────────────────────────────────────
print("\n=== Step 2: Model file ===")
model_entry = next(m for m in LLAMACPP_GGUF_CATALOG if m["name"] == "qwen2.5vl:2b")
gguf_url = model_entry["url"]
gguf_path = MODELS_DIR / gguf_url.rsplit("/", 1)[-1]
print(f"  {gguf_path.name}")

if gguf_path.exists() and gguf_path.stat().st_size > 100_000_000:
    print(f"  Already exists ({gguf_path.stat().st_size} bytes)")
else:
    print(f"  Downloading from {gguf_url}...")
    download_file(gguf_url, gguf_path)
    print(f"  Downloaded: {gguf_path.stat().st_size} bytes")

# ── Step 3: MMProj file (vision projector) ──────────────────────────
print("\n=== Step 3: MMProj file ===")
mmproj_url = model_entry.get("mmproj_url", "")
mmproj_path = MODELS_DIR / mmproj_url.rsplit("/", 1)[-1] if mmproj_url else None

if mmproj_url and mmproj_path:
    print(f"  {mmproj_path.name}")
    if mmproj_path.exists() and mmproj_path.stat().st_size > 100_000_000:
        print(f"  Already exists ({mmproj_path.stat().st_size} bytes)")
    else:
        print(f"  Downloading from {mmproj_url}...")
        download_file(mmproj_url, mmproj_path)
        print(f"  Downloaded: {mmproj_path.stat().st_size} bytes")
else:
    print("  No mmproj URL in catalog")
    mmproj_path = None

# ── Step 4: Configure ──────────────────────────────────────────────
print("\n=== Step 4: Configure ===")
configure_llamacpp_install(
    model_name="qwen2.5vl:2b",
    gguf_path=gguf_path,
    mmproj_path=mmproj_path,
    make_default=True,
)
print("  config.json updated!")

# ── Step 5: Verify ─────────────────────────────────────────────────
print("\n=== Step 5: Verify ===")
llamacpp = config.get("model", {}).get("llamacpp", {})
print(f"  gguf_name:     {llamacpp.get('gguf_name', '')}")
print(f"  gguf_path:     {llamacpp.get('gguf_path', '')}")
print(f"  mmproj_path:   {llamacpp.get('mmproj_path', '')}")
print(f"  last_provider: {config.get('model', {}).get('last_provider', '')}")
print(f"  bin size:      {sum(f.stat().st_size for f in BIN_DIR.iterdir()) / 1024 / 1024:.0f}MB total")
print("\nDone!")
