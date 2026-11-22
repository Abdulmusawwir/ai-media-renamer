"""Path repair for client-supplied analysis inputs.

The folder picker always sends absolute paths, but the WebSocket payload can
carry cosmetic noise (quotes, stray whitespace, ``~``, env placeholders, or a
bare filename). ``_resolve_input_path`` repairs those before the route declares
a file missing, and always leaves a correct absolute path untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.routes.analysis import _resolve_input_path


@pytest.fixture
def real_file(tmp_path):
    f = tmp_path / "clip one.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    return f


def test_absolute_path_is_returned_unchanged(real_file):
    assert _resolve_input_path(str(real_file)) == real_file


def test_surrounding_quotes_and_whitespace_are_stripped(real_file):
    assert _resolve_input_path(f'  "{real_file}"  ') == real_file
    assert _resolve_input_path(f"'{real_file}'") == real_file


def test_tilde_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    target = tmp_path / "x.jpg"
    target.write_bytes(b"x")
    assert _resolve_input_path("~/x.jpg") == target


def test_env_placeholder_is_expanded(monkeypatch, real_file):
    monkeypatch.setenv("AMR_TEST_DIR", str(real_file.parent))
    resolved = _resolve_input_path("$AMR_TEST_DIR/clip one.jpg")
    assert resolved == real_file


def test_bare_name_resolves_against_cwd(monkeypatch, tmp_path, real_file):
    monkeypatch.chdir(tmp_path)
    assert _resolve_input_path(real_file.name) == real_file


def test_missing_relative_path_is_reported_as_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    resolved = _resolve_input_path("./nope-does-not-exist.jpg")
    assert resolved.is_absolute()
    assert resolved.name == "nope-does-not-exist.jpg"
    assert not resolved.exists()


def test_absolute_missing_path_keeps_its_shape(tmp_path):
    missing = Path(tmp_path) / "gone" / "x.jpg"
    assert _resolve_input_path(str(missing)) == missing
