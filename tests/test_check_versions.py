import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_versions.py"


def run(tag, latest_json=None, cwd=None):
    cmd = [sys.executable, str(SCRIPT), "--tag", tag]
    if latest_json is not None:
        cmd += ["--latest-json", str(latest_json)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or ROOT)


def test_versions_match():
    # Current repo is at 2.2.5 after the bump.
    result = run("v2.2.5")
    assert result.returncode == 0, result.stdout + result.stderr


def test_version_mismatch_reported():
    result = run("v9.9.9")
    assert result.returncode != 0
    assert "VERSION" in result.stdout or "VERSION" in result.stderr


def test_latest_json_validates():
    tmp = ROOT / "tests" / "_lj.json"
    data = {
        "version": "2.2.5",
        "url": "https://example.com/x.nsis.zip",
        "signature": "abc",
        "platforms": {"windows-x86_64": {"url": "u", "signature": "s"}},
    }
    tmp.write_text(json.dumps(data), encoding="utf-8")
    try:
        result = run("v2.2.5", latest_json=tmp)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        tmp.unlink(missing_ok=True)


def test_latest_json_mismatch_reported():
    tmp = ROOT / "tests" / "_lj2.json"
    data = {"version": "1.0.0", "url": "u", "signature": "s"}
    tmp.write_text(json.dumps(data), encoding="utf-8")
    try:
        result = run("v2.2.5", latest_json=tmp)
        assert result.returncode != 0
    finally:
        tmp.unlink(missing_ok=True)
