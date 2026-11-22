#!/usr/bin/env python
"""Verify that every version-bearing file agrees with the release tag.

Usage:
    python scripts/check_versions.py --tag v2.2.0
    python scripts/check_versions.py --tag v2.2.0 --latest-json path/to/latest.json

Exits 0 when all versions match (and latest.json validates when present),
non-zero otherwise, printing every mismatch.
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (file relative to ROOT, regex capturing the version string)
VERSION_SOURCES = [
    ("VERSION", re.compile(r"^\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.M)),
    ("engine.py", re.compile(r'^VERSION\s*=\s*"([^"]+)"', re.M)),
    ("pyproject.toml", re.compile(r'^version\s*=\s*"([^"]+)"', re.M)),
    ("server/__init__.py", re.compile(r'^__version__\s*=\s*"([^"]+)"', re.M)),
    ("frontend/package.json", re.compile(r'"version"\s*:\s*"([^"]+)"')),
    ("package.json", re.compile(r'"version"\s*:\s*"([^"]+)"')),
    ("src-tauri/Cargo.toml", re.compile(r'^version\s*=\s*"([^"]+)"', re.M)),
    ("src-tauri/tauri.conf.json", re.compile(r'"version"\s*:\s*"([^"]+)"')),
]


def read_version(path: Path, pattern: re.Pattern) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = pattern.search(text)
    return match.group(1) if match else None


def check_versions(tag: str) -> list[str]:
    expected = tag.lstrip("v")
    errors = []
    for rel, pattern in VERSION_SOURCES:
        path = ROOT / rel
        found = read_version(path, pattern)
        if found is None:
            errors.append(f"{rel}: could not read version")
        elif found != expected:
            errors.append(f"{rel}: {found} != {expected}")
    return errors


def check_latest_json(path: Path, tag: str) -> list[str]:
    errors = []
    if not path.is_file():
        return errors
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"{path}: invalid JSON ({exc})"]
    expected = tag.lstrip("v")
    if data.get("version") != expected:
        errors.append(f"{path}: version {data.get('version')!r} != {expected!r}")
    for field in ("url", "signature"):
        if not data.get(field):
            errors.append(f"{path}: missing or empty '{field}'")
    platforms = data.get("platforms")
    if isinstance(platforms, dict):
        for plat, info in platforms.items():
            if not isinstance(info, dict) or not info.get("url") or not info.get("signature"):
                errors.append(f"{path}: platform {plat!r} missing url/signature")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check version consistency.")
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v2.2.0")
    parser.add_argument(
        "--latest-json",
        default=None,
        help="Optional path to latest.json to validate.",
    )
    args = parser.parse_args(argv)

    errors = check_versions(args.tag)
    if args.latest_json:
        errors.extend(check_latest_json(Path(args.latest_json), args.tag))

    if errors:
        for err in errors:
            print(err)
        return 1
    print(f"All versions match {args.tag}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
