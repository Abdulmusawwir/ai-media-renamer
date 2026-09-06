"""Attempt to bootstrap llama-server + model."""
import os
import sys

sys.path.insert(0, ".")
os.chdir("D:\\Projects\\ai-media-renamer")

from engine import (  # noqa: E402
    _llamacpp_runtime_urls,
    _llamacpp_server_running,
    config,
    ensure_llamacpp_server,
)

print("1. Server already running?", _llamacpp_server_running())

print("\n2. Runtime URLs:")
urls = _llamacpp_runtime_urls()
print(f"   {urls}")

print("\n3. Current config model.llamacpp:")
llamacpp = config.get("model", {}).get("llamacpp", {})
print(f"   gguf_name: {llamacpp.get('gguf_name')!r}")
print(f"   gguf_path: {llamacpp.get('gguf_path')!r}")
print(f"   mmproj_path: {llamacpp.get('mmproj_path')!r}")

print("\n4. Trying ensure_llamacpp_server()...")
result = ensure_llamacpp_server(timeout=5)
print(f"   Result: {result}")
print(f"   Server running now: {_llamacpp_server_running()}")
