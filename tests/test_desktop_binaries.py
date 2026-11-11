"""Desktop binary resolution, llama-server lifecycle, and runtime install."""

import importlib
import sys
import threading
import zipfile
from pathlib import Path

import bootstrap
import engine


def _write(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class _FakeProc:
    def __init__(self, returncode=None, terminate_error=None):
        self._returncode = returncode
        self.terminate_error = terminate_error
        self.terminated = False
        self.killed = False
        self.wait_calls: list[float | None] = []

    def poll(self):
        return self._returncode

    def terminate(self):
        if self.terminate_error is not None:
            raise self.terminate_error
        self.terminated = True
        self._returncode = 0

    def kill(self):
        self.killed = True
        self._returncode = -9

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self._returncode


class _FakeWin:
    def __init__(self):
        self.steps: list[str] = []
        self.infos: list[str] = []
        self.progress: list[float] = []

    def set_step(self, step, text):
        self.steps.append(text)

    def set_progress(self, value):
        self.progress.append(value)

    def set_info(self, text):
        self.infos.append(text)

    def update(self):
        pass


# ---------------------------------------------------------------------------
# _resolve_binary_path
# ---------------------------------------------------------------------------

class TestResolveBinaryPath:
    def test_binary_prefers_user_bin(self, monkeypatch, tmp_path):
        data = tmp_path / "data"
        user_bin = data / "bin"
        _write(user_bin / "ffmpeg.exe")
        bundle = tmp_path / "bundle"
        _write(bundle / "bin" / "ffmpeg.exe")

        monkeypatch.setattr(engine, "USER_DATA_DIR", data)
        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        monkeypatch.setattr(engine.shutil, "which", lambda name: "C:/PATH/ffmpeg.exe")

        assert engine._resolve_binary_path("ffmpeg") == str(user_bin / "ffmpeg.exe")

    def test_binary_accepts_exe_suffix(self, monkeypatch, tmp_path):
        data = tmp_path / "data"
        _write(data / "bin" / "llama-server.exe")

        monkeypatch.setattr(engine, "USER_DATA_DIR", data)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(engine.shutil, "which", lambda name: None)

        expected = str(data / "bin" / "llama-server.exe")
        assert engine._resolve_binary_path("llama-server") == expected
        assert engine._resolve_binary_path("llama-server.exe") == expected

    def test_binary_falls_back_to_meipass(self, monkeypatch, tmp_path):
        data = tmp_path / "data"
        bundle = tmp_path / "bundle"
        _write(bundle / "bin" / "ffmpeg.exe")

        monkeypatch.setattr(engine, "USER_DATA_DIR", data)
        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        monkeypatch.setattr(engine.shutil, "which", lambda name: "C:/PATH/ffmpeg.exe")

        assert engine._resolve_binary_path("ffmpeg") == str(bundle / "bin" / "ffmpeg.exe")

    def test_binary_falls_back_to_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(engine, "USER_DATA_DIR", tmp_path / "data")
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(
            engine.shutil,
            "which",
            lambda name: "C:/tools/ffmpeg.exe" if name == "ffmpeg" else None,
        )

        assert engine._resolve_binary_path("ffmpeg") == "C:/tools/ffmpeg.exe"


# ---------------------------------------------------------------------------
# llama-server lifecycle
# ---------------------------------------------------------------------------

class TestLlamaServerLifecycle:
    def test_stop_server_terminates_owned_process(self, monkeypatch):
        proc = _FakeProc()
        monkeypatch.setattr(engine, "_llamacpp_proc", proc)

        assert engine.stop_llamacpp_server() is True
        assert proc.terminated is True
        assert proc.killed is False
        assert engine._llamacpp_proc is None

    def test_stop_server_noop_when_not_owned(self, monkeypatch):
        monkeypatch.setattr(engine, "_llamacpp_proc", None)

        assert engine.stop_llamacpp_server() is False
        assert engine._llamacpp_proc is None

    def test_ensure_server_is_locked(self, monkeypatch, tmp_path):
        gguf = _write(tmp_path / "model.gguf")
        monkeypatch.setattr(engine, "config", {
            "model": {"llamacpp": {
                "gguf_path": str(gguf), "gguf_name": "", "mmproj_path": "",
            }},
        })
        monkeypatch.setattr(engine, "wait_for_model_migration", lambda timeout=300: True)
        monkeypatch.setattr(engine, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(
            engine, "_resolve_binary_path",
            lambda name: "C:/tools/llama-server.exe" if name == engine.LLAMACPP_SERVER_EXE else None,
        )
        monkeypatch.setattr(engine, "_llamacpp_proc", None)

        running = {"value": False}
        spawns: list[list[str]] = []

        def fake_running():
            return running["value"]

        def fake_popen(args, **kwargs):
            spawns.append(args)
            running["value"] = True
            return _FakeProc()

        monkeypatch.setattr(engine, "_llamacpp_server_running", fake_running)
        monkeypatch.setattr(engine.subprocess, "Popen", fake_popen)

        barrier = threading.Barrier(2)
        results: list[bool] = []

        def worker():
            barrier.wait()
            results.append(engine.ensure_llamacpp_server(timeout=5))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)

        assert len(spawns) == 1
        assert results == [True, True]

    def test_ensure_server_respawns_after_owned_process_exits(self, monkeypatch, tmp_path):
        gguf = _write(tmp_path / "model.gguf")
        monkeypatch.setattr(engine, "config", {
            "model": {"llamacpp": {
                "gguf_path": str(gguf), "gguf_name": "", "mmproj_path": "",
            }},
        })
        monkeypatch.setattr(engine, "wait_for_model_migration", lambda timeout=300: True)
        monkeypatch.setattr(engine, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(
            engine, "_resolve_binary_path",
            lambda name: "C:/tools/llama-server.exe" if name == engine.LLAMACPP_SERVER_EXE else None,
        )
        # An owned process that already exited must not block a fresh spawn.
        monkeypatch.setattr(engine, "_llamacpp_proc", _FakeProc(returncode=1))

        running = {"value": False}
        spawns: list[list[str]] = []

        def fake_popen(args, **kwargs):
            spawns.append(args)
            running["value"] = True
            return _FakeProc()

        monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: running["value"])
        monkeypatch.setattr(engine.subprocess, "Popen", fake_popen)

        assert engine.ensure_llamacpp_server(timeout=5) is True
        assert len(spawns) == 1
        assert engine._llamacpp_proc is not None

    def test_ensure_server_replaces_live_unhealthy_owned_process(self, monkeypatch, tmp_path):
        gguf = _write(tmp_path / "model.gguf")
        monkeypatch.setattr(engine, "config", {
            "model": {"llamacpp": {
                "gguf_path": str(gguf), "gguf_name": "", "mmproj_path": "",
            }},
        })
        monkeypatch.setattr(engine, "wait_for_model_migration", lambda timeout=300: True)
        monkeypatch.setattr(engine, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(
            engine, "_resolve_binary_path",
            lambda name: "C:/tools/llama-server.exe" if name == engine.LLAMACPP_SERVER_EXE else None,
        )
        # Live but never answered: a previous spawn failed to become healthy.
        dead = _FakeProc()
        monkeypatch.setattr(engine, "_llamacpp_proc", dead)
        monkeypatch.setattr(engine, "_llamacpp_proc_healthy", False)
        monkeypatch.setattr(engine, "_llamacpp_proc_pending", False)

        running = {"value": False}
        spawns: list[list[str]] = []
        replacement = _FakeProc()

        def fake_popen(args, **kwargs):
            spawns.append(args)
            running["value"] = True
            return replacement

        monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: running["value"])
        monkeypatch.setattr(engine.subprocess, "Popen", fake_popen)

        assert engine.ensure_llamacpp_server(timeout=5) is True
        assert dead.terminated is True
        assert len(spawns) == 1
        assert engine._llamacpp_proc is replacement
        assert engine._llamacpp_proc_healthy is True
        assert engine._llamacpp_proc_pending is False

    def test_ensure_server_stops_owned_process_after_failed_start(self, monkeypatch, tmp_path):
        gguf = _write(tmp_path / "model.gguf")
        monkeypatch.setattr(engine, "config", {
            "model": {"llamacpp": {
                "gguf_path": str(gguf), "gguf_name": "", "mmproj_path": "",
            }},
        })
        monkeypatch.setattr(engine, "wait_for_model_migration", lambda timeout=300: True)
        monkeypatch.setattr(engine, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(
            engine, "_resolve_binary_path",
            lambda name: "C:/tools/llama-server.exe" if name == engine.LLAMACPP_SERVER_EXE else None,
        )
        monkeypatch.setattr(engine, "_llamacpp_proc", None)

        spawned = _FakeProc()

        def fake_popen(args, **kwargs):
            return spawned

        monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: False)
        monkeypatch.setattr(engine.subprocess, "Popen", fake_popen)

        assert engine.ensure_llamacpp_server(timeout=0) is False
        assert spawned.terminated is True
        assert engine._llamacpp_proc is None

    def test_stop_retains_handle_when_terminate_fails(self, monkeypatch):
        proc = _FakeProc(terminate_error=OSError("access denied"))
        monkeypatch.setattr(engine, "_llamacpp_proc", proc)

        assert engine.stop_llamacpp_server() is False
        assert engine._llamacpp_proc is proc

        proc.terminate_error = None
        assert engine.stop_llamacpp_server() is True
        assert proc.terminated is True
        assert engine._llamacpp_proc is None


# ---------------------------------------------------------------------------
# Runtime tree install
# ---------------------------------------------------------------------------

def _runtime_tree(root: Path, *, include_impl: bool = True) -> dict[str, bytes]:
    files = {
        "llama-server.exe": b"exe",
        "llama.dll": b"llama",
        "ggml.dll": b"ggml",
        "ggml-base.dll": b"ggml-base",
        "ggml-cpu.dll": b"ggml-cpu",
        "mtmd.dll": b"mtmd",
        "libomp140.x86_64.dll": b"omp",
        "sub/extra.dat": b"extra",
    }
    if include_impl:
        files["llama-server-impl.dll"] = b"impl"
    for rel, data in files.items():
        _write(root / rel, data)
    return files


class TestRuntimeInstall:
    def test_runtime_install_copies_all_adjacent_dlls(self, tmp_path):
        src = tmp_path / "extract" / "llama-b10327-bin-win-cpu-x64"
        files = _runtime_tree(src)
        bin_dir = tmp_path / "bin"

        copied = bootstrap._copy_llamacpp_runtime_tree(src, bin_dir)

        assert {p.relative_to(bin_dir).as_posix() for p in copied} == set(files)
        for rel, data in files.items():
            assert (bin_dir / rel).read_bytes() == data

    def test_runtime_install_fails_when_impl_dll_missing(self, monkeypatch, tmp_path):
        extract_root = tmp_path / "archive"
        _runtime_tree(extract_root, include_impl=False)
        zip_path = tmp_path / "llamacpp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for file in extract_root.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(extract_root))

        url = "https://example.com/runtime.zip"
        bin_dir = tmp_path / "bin"
        monkeypatch.setattr(bootstrap, "_llamacpp_runtime_urls", lambda: [url])
        monkeypatch.setattr(bootstrap, "_llamacpp_runtime_digests", lambda: {url: "0" * 64})
        monkeypatch.setattr(bootstrap, "CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr(bootstrap, "BIN_DIR", bin_dir)
        monkeypatch.setattr(bootstrap, "LLAMACPP_EXE", bin_dir / "llama-server.exe")
        monkeypatch.setattr(bootstrap, "LLAMACPP_ZIP_CACHE", zip_path)
        monkeypatch.setattr(bootstrap.time, "sleep", lambda *_: None)

        zip_bytes = zip_path.read_bytes()

        def fake_download(url, dest, **kwargs):
            Path(dest).write_bytes(zip_bytes)
            return True

        monkeypatch.setattr(bootstrap, "download_file", fake_download)

        win = _FakeWin()
        bootstrap._install_llamacpp_runtime(win, 1)

        assert not any("ready" in step for step in win.steps)
        assert any("failed" in step for step in win.steps)
        assert any("llama-server-impl.dll" in info for info in win.infos)


# ---------------------------------------------------------------------------
# bootstrap paths derive from the engine data root
# ---------------------------------------------------------------------------

def test_bootstrap_bin_follows_amr_data_dir(monkeypatch, tmp_path):
    data = tmp_path / "amr-data"
    with monkeypatch.context() as patch:
        patch.setenv("AMR_DATA_DIR", str(data))
        patch.setattr(engine, "USER_DATA_DIR", data)

        reloaded = importlib.reload(bootstrap)

        assert reloaded.CACHE_DIR == data / "cache"
        assert reloaded.BIN_DIR == data / "bin"
        assert reloaded.LLAMACPP_EXE == data / "bin" / "llama-server.exe"

    importlib.reload(bootstrap)
