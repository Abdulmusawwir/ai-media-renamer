import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import requests

from engine import (
    VERSION,
    _is_vision_model,
    _resolve_binary_path,
    check_for_updates,
    download_file,
    stream_model_download,
    wait_for_ollama_service,
)

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

APP_PATH = BASE_DIR / "app.py"
CACHE_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ai-media-renamer"
BIN_DIR = CACHE_DIR / "bin"
OLLAMA_INSTALLER_CACHE = CACHE_DIR / "cache"

# ---------- theme colors ----------
BG = "#1e1e1e"
FG = "#e0e0e0"
ACCENT = "#3b82f6"
GREEN = "#22c55e"
BAR_BG = "#333333"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")


class SetupWindow:
    def __init__(self):
        self.root = tk.Tk() if tk else None
        if not self.root:
            print("tkinter not available — running in headless mode.")
            return
        self.root.title("AI Media Renamer — Setup")
        self.root.geometry("520x320")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._center_window()

        # Title
        title = tk.Label(self.root, text="AI Media Renamer", font=FONT_TITLE,
                         bg=BG, fg=FG)
        title.pack(pady=(20, 4))

        self.version_label = tk.Label(self.root, text=f"{VERSION}",
                                      font=("Segoe UI", 9), bg=BG, fg="#888888")
        self.version_label.pack(pady=(0, 16))

        # Status step label
        self.step_label = tk.Label(self.root, text="", font=FONT_BOLD,
                                   bg=BG, fg=FG, anchor="w")
        self.step_label.pack(fill="x", padx=40, pady=(0, 4))

        # Progress bar
        self.progress = ttk.Progressbar(self.root, length=440, mode="determinate",
                                         style="dark.Horizontal.TProgressbar")
        self.progress.pack(padx=40, pady=(0, 4))

        # Info text
        self.info_label = tk.Label(self.root, text="", font=("Segoe UI", 9),
                                   bg=BG, fg="#aaaaaa", anchor="w")
        self.info_label.pack(fill="x", padx=40, pady=(0, 16))

        # Update notification frame (hidden by default)
        self.update_frame = tk.Frame(self.root, bg=BG)
        self.update_frame.pack(fill="x", padx=40)
        self.update_frame.pack_forget()

        self.update_text = tk.Label(self.update_frame, text="", font=FONT_BOLD,
                                    bg=BG, fg=FG)
        self.update_text.pack(pady=(0, 8))

        btn_frame = tk.Frame(self.update_frame, bg=BG)
        btn_frame.pack()

        self.dl_btn = tk.Button(btn_frame, text="Download Update",
                                font=("Segoe UI", 10), bg=ACCENT, fg="white",
                                relief="flat", padx=16, pady=4, cursor="hand2",
                                command=self._on_download_update)
        self.dl_btn.pack(side="left", padx=(0, 12))

        self.cont_btn = tk.Button(btn_frame, text="Continue to App",
                                  font=("Segoe UI", 10), bg="#333333", fg=FG,
                                  relief="flat", padx=16, pady=4, cursor="hand2",
                                  command=self._on_continue)
        self.cont_btn.pack(side="left")

        self._update_info = {}

        self._stopped = False
        self._continue_event = threading.Event()

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close(self):
        self._stopped = True
        self.root.destroy()
        sys.exit(1)

    def set_progress(self, value):
        if self.root:
            self.progress["value"] = value

    def set_info(self, text):
        if self.root:
            self.info_label.config(text=text)

    def set_step(self, num, label):
        if self.root:
            self.step_label.config(text=label)

    def show_update(self, info):
        self._update_info = info
        self.update_text.config(text=f"Update available: {info['current']} → {info['latest']}")
        self.update_frame.pack(fill="x", padx=40, before=self.progress)
        self.dl_btn.config(state="normal")
        self.cont_btn.config(state="normal")

    def _on_download_update(self):
        webbrowser.open(self._update_info.get("download_url", ""))
        self.cont_btn.config(state="disabled")
        self.dl_btn.config(text="Opened in browser", state="disabled")

    def _on_continue(self):
        self._continue_event.set()

    def wait_for_user(self):
        self._continue_event.wait()

    def close(self):
        if self.root:
            self.root.destroy()

    def update(self):
        if self.root:
            self.root.update()


def _progress_callback(downloaded, total, win, step_text):
    pct = (downloaded / total) * 100 if total else 0
    win.set_progress(pct)
    mb_dl = downloaded / (1024 * 1024)
    mb_total = total / (1024 * 1024)
    win.set_info(f"{mb_dl:.1f} MB / {mb_total:.1f} MB ({pct:.0f}%)")
    win.update()


def _download_with_progress(win, step_num, label, url, dest):
    win.set_step(step_num, f"\u27f3 {label}")
    win.set_progress(0)
    win.set_info("Starting download...")
    win.update()

    def cb(d, t):
        _progress_callback(d, t, win, label)

    download_file(url, dest, progress_callback=cb)
    win.set_step(step_num, f"\u2713 {label} — ready")
    win.set_progress(100)
    win.update()


def _add_to_user_path(path):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Environment", 0, winreg.KEY_SET_VALUE)
        current, _ = winreg.QueryValueEx(key, "Path")
        if path not in current:
            new_path = current + ";" + str(path)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(key)
        os.environ["PATH"] = str(path) + ";" + os.environ.get("PATH", "")
    except Exception:
        pass


def _stream_model_with_progress(win, step_num, label, model_name):
    win.set_step(step_num, f"\u27f3 {label}")
    win.set_progress(0)
    win.set_info("Starting download...")
    win.update()

    for chunk in stream_model_download(model_name):
        if chunk.get("status") == "progress":
            pct = chunk.get("percentage", 0)
            completed = chunk.get("completed", 0) / (1024 * 1024)
            total = chunk.get("total", 0) / (1024 * 1024)
            win.set_progress(pct)
            win.set_info(f"{completed:.1f} MB / {total:.1f} MB ({pct:.0f}%)")
            win.update()
        elif chunk.get("status") == "success":
            win.set_step(step_num, f"\u2713 {label} — ready")
            win.set_progress(100)
            win.set_info("")
            win.update()
        elif chunk.get("status") == "error":
            raise RuntimeError(chunk.get("message", "Model download failed"))

    win.set_step(step_num, f"\u2713 {label} — ready")
    win.set_progress(100)
    win.update()


def main():
    if "--streamlit-server" in sys.argv:
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", str(APP_PATH),
                     "--server.port", "8501",
                     "--browser.gatherUsageStats", "false"]
        stcli.main()
        return

    win = SetupWindow()

    if not win.root:
        _headless_run()
        return

    try:
        # ---- Step 1: ExifTool ----
        if _resolve_binary_path("exiftool"):
            win.set_step(1, "\u2713 Checking ExifTool... found")
            win.set_progress(100)
            win.set_info("")
        else:
            url = "https://exiftool.org/exiftool-12.91.zip"
            dest = BIN_DIR / "exiftool.exe"
            _download_with_progress(win, 1, "Downloading ExifTool...", url, dest)
            _add_to_user_path(BIN_DIR)
        win.update()

        # ---- Step 2: FFmpeg ----
        if _resolve_binary_path("ffmpeg"):
            win.set_step(2, "\u2713 Checking FFmpeg... found")
            win.set_progress(100)
            win.set_info("")
        else:
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            win.set_step(2, "\u27f3 Downloading FFmpeg...")
            win.set_progress(0)
            win.set_info("Downloading...")
            win.update()
            zip_dest = CACHE_DIR / "ffmpeg.zip"
            download_file(url, zip_dest, progress_callback=lambda d, t: _progress_callback(d, t, win, "FFmpeg"))
            import zipfile
            with zipfile.ZipFile(zip_dest, "r") as zf:
                for member in zf.namelist():
                    if member.endswith("ffmpeg.exe") or member.endswith("ffprobe.exe"):
                        zf.extract(member, CACHE_DIR / "ffmpeg_extracted")
            for f in CACHE_DIR.glob("ffmpeg_extracted/**/ffmpeg.exe"):
                shutil.move(str(f), str(BIN_DIR / "ffmpeg.exe"))
                break
            for f in CACHE_DIR.glob("ffmpeg_extracted/**/ffprobe.exe"):
                shutil.move(str(f), str(BIN_DIR / "ffprobe.exe"))
                break
            shutil.rmtree(CACHE_DIR / "ffmpeg_extracted", ignore_errors=True)
            zip_dest.unlink(missing_ok=True)
            _add_to_user_path(BIN_DIR)
            win.set_step(2, "\u2713 Checking FFmpeg... ready")
            win.set_progress(100)
        win.update()

        # ---- Step 3: Ollama ----
        ollama_binary = shutil.which("ollama")
        installer_path = OLLAMA_INSTALLER_CACHE / "OllamaSetup.exe"

        if not ollama_binary:
            if not installer_path.exists():
                url = "https://ollama.com/download/OllamaSetup.exe"
                win.set_step(3, "\u27f3 Downloading Ollama installer...")
                win.set_progress(0)
                win.set_info("Downloading...")
                win.update()

                def cb(d, t):
                    _progress_callback(d, t, win, "Ollama installer")

                download_file(url, installer_path, progress_callback=cb)
            win.set_step(3, "\u27f3 Installing Ollama...")
            win.set_progress(50)
            win.set_info("Running silent installer (this may take a moment)...")
            win.update()
            subprocess.run([str(installer_path), "/S"], check=True, capture_output=True)
            ollama_binary = shutil.which("ollama")

        # Check if the Ollama service is actually running
        ollama_running = False
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            ollama_running = resp.status_code == 200
        except Exception:
            pass

        if ollama_running:
            win.set_step(3, "\u2713 Checking Ollama... running")
            win.set_progress(100)
            win.set_info("")
        elif ollama_binary:
            win.set_step(3, "\u27f3 Starting Ollama service...")
            win.set_progress(50)
            win.set_info("Launching Ollama in background...")
            win.update()
            subprocess.Popen(
                [ollama_binary, "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if wait_for_ollama_service(timeout=30):
                win.set_step(3, "\u2713 Checking Ollama... running")
                win.set_progress(100)
                win.set_info("")
            else:
                win.set_step(3, "\u26a0 Ollama service did not start")
                win.set_progress(100)
                win.set_info("Please start Ollama manually and restart this app.")
                win.wait_for_user()
                win.close()
                return
        else:
            win.set_step(3, "\u26a0 Ollama not found")
            win.set_progress(100)
            win.set_info("Ollama installation may have failed. Please install manually from ollama.com.")
            win.wait_for_user()
            win.close()
            return
        win.update()

        # ---- Step 4: AI Model ----
        def _vision_model_installed():
            try:
                import ollama as _ollama
                tags = _ollama.list()
                for m in tags.get("models", []):
                    if isinstance(m, dict):
                        name = m.get("name", "")
                    elif hasattr(m, "model"):
                        name = m.model
                    else:
                        name = str(m)
                    if name and _is_vision_model(name):
                        return True
            except Exception:
                pass
            return False

        if _vision_model_installed():
            win.set_step(4, "\u2713 AI model (qwen2.5vl:7b)... found")
            win.set_progress(100)
            win.set_info("")
        else:
            _stream_model_with_progress(win, 4, "Downloading AI model (qwen2.5vl:7b)...",
                                        "qwen2.5vl:7b")
        win.update()

        # ---- Step 5: Update check ----
        update_info = check_for_updates()
        if update_info.get("ok") and update_info.get("update_available"):
            win.set_step(5, "\u26a0 Update available")
            win.set_progress(100)
            win.set_info("")
            win.show_update(update_info)
            win.update()
            win.wait_for_user()
        else:
            win.set_step(5, "\u2713 Checking for updates... up to date")
            win.set_progress(100)
            win.set_info("")
        win.update()

        # ---- Step 6: Launch ----
        _launch_app(win)

    except Exception as exc:
        if win.root:
            win.set_step(0, "\u2716 Setup failed")
            win.set_progress(0)
            win.set_info(str(exc))
            win.update()
            import time
            time.sleep(5)
        else:
            print(f"Setup failed: {exc}")
        win.close()
        sys.exit(1)


def _launch_app(win):
    win.set_step(6, "\u2713 Starting app...")
    win.set_progress(100)
    win.set_info("Starting Streamlit server...")
    win.update()

    proc = subprocess.Popen(
        [sys.executable, "--streamlit-server"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for Streamlit to be ready
    import time
    health_url = "http://localhost:8501/_stcore/health"
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        try:
            r = requests.get(health_url, timeout=2)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.5)

    if not ready:
        win.set_info("App taking longer than expected — opening browser...")
        win.update()
    else:
        win.set_info("Opening app window...")
        win.update()

    win.close()

    # Try pywebview native window; fall back to browser
    try:
        import webview
        webview.create_window("AI Media Renamer", "http://localhost:8501",
                              width=1280, height=800, resizable=True)
        webview.start(private_mode=True, gui="edgechromium")
    except Exception:
        webbrowser.open("http://localhost:8501")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        sys.exit(0)

    # Clean shutdown on window close
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    sys.exit(0)


def _headless_run():
    print("AI Media Renamer — Setup (headless mode)")
    print(f"Version: {VERSION}")
    for step, check in enumerate([
        ("ExifTool", _resolve_binary_path("exiftool")),
        ("FFmpeg", _resolve_binary_path("ffmpeg")),
        ("Ollama", shutil.which("ollama")),
    ]):
        status = "\u2713 found" if check else "missing"
        print(f"  [{step+1}/5] {check[0]}: {status}")
    info = check_for_updates()
    if info.get("update_available"):
        print(f"  Update available: {info['current']} -> {info['latest']}")
        print(f"  Download: {info['download_url']}")
    print("Use 'streamlit run app.py' to start manually.")


if __name__ == "__main__":
    main()
