"""Tauri v2 is deny-by-default: every custom command needs an ACL grant.

A missing grant does not fail the build — the webview just gets
"Command <name> not allowed by ACL" at runtime, which is easy to miss. This
test keeps the Rust handler list and the capabilities in sync.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
TAURI = ROOT / "src-tauri"


def _registered_commands() -> set[str]:
    source = (TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    match = re.search(r"generate_handler!\[(.*?)\]", source, re.S)
    assert match, "could not find generate_handler! in lib.rs"
    return set(re.findall(r"commands::(\w+)", match.group(1)))


def _permission_commands() -> set[str]:
    data = tomllib.loads((TAURI / "permissions" / "desktop.toml").read_text(encoding="utf-8"))
    grants = [p for p in data["permission"] if p["identifier"] == "desktop-commands"]
    assert len(grants) == 1, "expected one desktop-commands permission"
    return set(grants[0]["commands"]["allow"])


def test_every_registered_command_is_granted():
    registered = _registered_commands()
    assert registered, "no commands registered"
    assert registered <= _permission_commands(), (
        f"commands missing from desktop.toml: {sorted(registered - _permission_commands())}"
    )


def test_both_capabilities_include_the_grant():
    for name in ("default.json", "remote.json"):
        data = json.loads((TAURI / "capabilities" / name).read_text(encoding="utf-8"))
        assert "desktop-commands" in data["permissions"], f"{name} is missing desktop-commands"
