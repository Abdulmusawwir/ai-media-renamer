import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
import zipfile
from pathlib import Path

if getattr(sys, "frozen", False) and sys.stdin is None:
    sys.stdin = open(os.devnull, "r")
if getattr(sys, "frozen", False) and sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if getattr(sys, "frozen", False) and sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

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
        try:
            self.root.iconbitmap(str(BASE_DIR / "icon.ico"))
        except Exception:
            pass

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
        while not self._continue_event.is_set():
            self.root.update()
            self.root.after(50)

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


def _is_valid_zip(path: Path) -> bool:
    """Return True if the given file is a readable ZIP archive."""
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except Exception:
        return False


def _exiftool_download_urls() -> list[str]:
    """Return candidate download URLs for the latest Windows ExifTool build.

    ExifTool's Windows builds are hosted on SourceForge with a versioned
    filename like 'exiftool-13.59_64.zip'. The current version is resolved
    dynamically from exiftool.org's ver.txt, with pinned fallbacks so the
    setup never hardcodes a version that could go stale.
    """
    urls: list[str] = []
    try:
        resp = requests.get("https://exiftool.org/ver.txt", timeout=10)
        ver = resp.text.strip()
        if re.fullmatch(r"\d+\.\d+", ver):
            urls.append(
                f"https://sourceforge.net/projects/exiftool/files/exiftool-{ver}_64.zip/download"
            )
    except Exception:
        pass
    for pinned in ("13.59", "13.58", "13.57"):
        urls.append(
            f"https://sourceforge.net/projects/exiftool/files/exiftool-{pinned}_64.zip/download"
        )
    return urls


def _extract_exiftool(zip_path: Path) -> bool:
    """Extract the ExifTool Windows zip and install exiftool.exe + support files.

    The Windows exiftool package ships 'exiftool(-k).exe' plus an
    'exiftool_files' folder that MUST sit next to the executable. Returns
    True when exiftool.exe is in place under BIN_DIR.
    """
    try:
        extract_dir = CACHE_DIR / "exiftool_extracted"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        exe_src = None
        for f in extract_dir.rglob("*.exe"):
            if f.name.lower() in ("exiftool(-k).exe", "exiftool.exe"):
                exe_src = f
                break
        if exe_src is None:
            return False

        BIN_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe_src, BIN_DIR / "exiftool.exe")
        files_dir = exe_src.parent / "exiftool_files"
        if files_dir.is_dir():
            shutil.copytree(files_dir, BIN_DIR / "exiftool_files", dirs_exist_ok=True)
        return True
    except Exception:
        return False


def _verify_exiftool() -> bool:
    """Run 'exiftool -ver' against the installed binary to confirm it works."""
    try:
        result = subprocess.run(
            [str(BIN_DIR / "exiftool.exe"), "-ver"],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def _install_exiftool(win) -> None:
    """Download, extract, and verify the Windows ExifTool build."""
    win.set_step(1, "\u27f3 Downloading ExifTool...")
    win.set_progress(0)
    win.set_info("Downloading...")
    win.update()

    zip_dest = CACHE_DIR / "exiftool.zip"
    last_err = None
    for url in _exiftool_download_urls():
        try:
            zip_dest.unlink(missing_ok=True)
            download_file(url, zip_dest,
                          progress_callback=lambda d, t: _progress_callback(d, t, win, "ExifTool"))
            if not _is_valid_zip(zip_dest):
                raise RuntimeError("downloaded file is not a valid ZIP archive")
            if not _extract_exiftool(zip_dest):
                raise RuntimeError("exiftool.exe not found inside archive")
            if not _verify_exiftool():
                raise RuntimeError("installed exiftool.exe did not run correctly")
            zip_dest.unlink(missing_ok=True)
            win.set_step(1, "\u2713 Checking ExifTool... ready")
            win.set_progress(100)
            win.set_info("")
            win.update()
            return
        except Exception as exc:
            last_err = exc
            continue

    win.set_step(1, "\u2716 ExifTool download failed")
    win.set_progress(0)
    win.set_info(f"Automatic download failed: {last_err}. "
                 "Install ExifTool manually from exiftool.org (64-bit Windows zip) and retry.")
    win.update()
    import time
    time.sleep(5)


def _install_ffmpeg(win) -> None:
    """Download, extract, and verify FFmpeg/FFprobe from the Gyan.dev essentials build."""
    win.set_step(2, "\u27f3 Downloading FFmpeg...")
    win.set_progress(0)
    win.set_info("Downloading...")
    win.update()

    zip_dest = CACHE_DIR / "ffmpeg.zip"
    try:
        download_file("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
                      zip_dest,
                      progress_callback=lambda d, t: _progress_callback(d, t, win, "FFmpeg"))
        if not _is_valid_zip(zip_dest):
            raise RuntimeError("downloaded file is not a valid ZIP archive")
        extract_dir = CACHE_DIR / "ffmpeg_extracted"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_dest, "r") as zf:
            zf.extractall(extract_dir)

        moved = 0
        for f in extract_dir.rglob("*.exe"):
            if f.name.lower() == "ffmpeg.exe":
                shutil.copy2(f, BIN_DIR / "ffmpeg.exe")
                moved += 1
            elif f.name.lower() == "ffprobe.exe":
                shutil.copy2(f, BIN_DIR / "ffprobe.exe")
                moved += 1
        if moved < 2:
            raise RuntimeError("ffmpeg.exe/ffprobe.exe not found inside archive")
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_dest.unlink(missing_ok=True)
        win.set_step(2, "\u2713 Checking FFmpeg... ready")
        win.set_progress(100)
        win.set_info("")
        win.update()
    except Exception as exc:
        win.set_step(2, "\u2716 FFmpeg download failed")
        win.set_progress(0)
        win.set_info(f"Automatic download failed: {exc}. "
                     "Install FFmpeg manually from gyan.dev and retry.")
        win.update()
        import time
        time.sleep(5)


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


def _log(msg):
    try:
        log_path = CACHE_DIR / "debug.log"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


MODEL_CATALOG = [
    {
        "name": "qwen2.5vl:7b",
        "label": "Qwen 2.5 VL 7B",
        "size": "6.0 GB",
        "quality": "Best",
        "speed": "Moderate",
        "desc": "Recommended. Best quality for structured JSON extraction and visual analysis.",
        "recommended": True,
    },
    {
        "name": "qwen2.5vl:3b",
        "label": "Qwen 2.5 VL 3B",
        "size": "3.2 GB",
        "quality": "Good",
        "speed": "Fast",
        "desc": "Lighter model. Good quality, faster analysis. Suitable for 4-6 GB VRAM.",
        "recommended": False,
    },
    {
        "name": "qwen3-vl:4b",
        "label": "Qwen 3 VL 4B",
        "size": "~3 GB",
        "quality": "Good",
        "speed": "Fast",
        "desc": "Newer architecture. Good quality with improved reasoning. 4+ GB VRAM.",
        "recommended": False,
    },
    {
        "name": "moondream:latest",
        "label": "Moondream 2",
        "size": "1.8 GB",
        "quality": "Basic",
        "speed": "Very fast",
        "desc": "Smallest option. Basic visual understanding. For very low VRAM (2 GB).",
        "recommended": False,
    },
]


class ModelSelectionDialog:
    """Tkinter modal dialog for choosing an AI model during first-time setup."""

    def __init__(self, parent, already_installed: bool = False):
        self.result: str | None = None
        self.already_installed = already_installed

        self.top = tk.Toplevel(parent)
        self.top.title("Select AI Model")
        self.top.geometry("520x480")
        self.top.configure(bg=BG)
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._on_skip)

        self._center(parent)

        heading = "AI Model Already Installed" if already_installed else "Choose an AI Model"
        tk.Label(self.top, text=heading, font=FONT_TITLE, bg=BG, fg=FG).pack(pady=(18, 2))

        sub = "A vision model was found. You can switch or keep the current one."
        if not already_installed:
            sub = "Select a model to download. Larger models produce better results."
        tk.Label(self.top, text=sub, font=("Segoe UI", 9), bg=BG, fg="#aaaaaa").pack(pady=(0, 10))

        self._var = tk.StringVar(value="qwen2.5vl:7b")

        container = tk.Frame(self.top, bg=BG)
        container.pack(fill="x", padx=30, pady=(0, 6))

        for m in MODEL_CATALOG:
            self._add_option(container, m)

        btn_frame = tk.Frame(self.top, bg=BG)
        btn_frame.pack(pady=(8, 16))

        if already_installed:
            tk.Button(btn_frame, text="Keep Current", font=("Segoe UI", 10),
                      bg="#333333", fg=FG, relief="flat", padx=14, pady=4,
                      cursor="hand2", command=self._on_skip).pack(side="left", padx=(0, 10))

        tk.Button(btn_frame, text="Download" if not already_installed else "Switch Model",
                  font=("Segoe UI", 10, "bold"), bg=ACCENT, fg="white",
                  relief="flat", padx=14, pady=4, cursor="hand2",
                  command=self._on_confirm).pack(side="left")

    def _add_option(self, parent, m):
        row = tk.Frame(parent, bg=BAR_BG, highlightbackground="#444444",
                       highlightthickness=1, cursor="hand2")
        row.pack(fill="x", pady=3)

        rb = tk.Radiobutton(row, variable=self._var, value=m["name"],
                            bg=BAR_BG, fg=FG, selectcolor=BG,
                            activebackground=BAR_BG, activeforeground=FG,
                            indicatoron=False, width=2, anchor="w")
        rb.pack(side="left", padx=(6, 0), pady=6)

        info = tk.Frame(row, bg=BAR_BG)
        info.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)

        badge = f"  \u2605 Recommended" if m["recommended"] else ""
        quality_color = GREEN if m["quality"] == "Best" else ACCENT if m["quality"] == "Good" else "#aaaaaa"

        header_text = f'{m["label"]}  ({m["size"]})'
        tk.Label(info, text=header_text, font=FONT_BOLD, bg=BAR_BG, fg=FG,
                 anchor="w").pack(fill="x")
        tk.Label(info, text=m["desc"], font=("Segoe UI", 8), bg=BAR_BG,
                 fg="#aaaaaa", anchor="w", wraplength=380, justify="left").pack(fill="x")

        tags = tk.Frame(info, bg=BAR_BG)
        tags.pack(fill="x", pady=(2, 0))
        for tag_text, color in [("Quality: " + m["quality"], quality_color),
                                ("Speed: " + m["speed"], "#aaaaaa")]:
            tk.Label(tags, text=tag_text, font=("Segoe UI", 8, "bold"),
                     bg=BAR_BG, fg=color, anchor="w").pack(side="left", padx=(0, 12))
        if badge:
            tk.Label(tags, text=badge, font=("Segoe UI", 8, "bold"),
                     bg=BAR_BG, fg="#f59e0b", anchor="w").pack(side="left")

        for w in (row, info, tags):
            for child in w.winfo_children():
                child.bind("<Button-1>", lambda e, v=m["name"]: self._var.set(v))

    def _center(self, parent):
        self.top.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.top.winfo_width()
        h = self.top.winfo_height()
        self.top.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _on_confirm(self):
        self.result = self._var.get()
        self.top.destroy()

    def _on_skip(self):
        self.result = None
        self.top.destroy()


def main():
    _log(f"main() argv={sys.argv} frozen={getattr(sys, 'frozen', False)}")

    if "--streamlit-server" in sys.argv:
        if "--check-only" in sys.argv:
            import importlib.metadata
            importlib.metadata.version("streamlit")
            sys.exit(0)

        _log(f"APP_PATH={APP_PATH} exists={APP_PATH.exists()}")
        os.environ["STREAMLIT_CONFIG_PATH"] = str(BASE_DIR / ".streamlit" / "config.toml")
        sys.argv = [
            "streamlit",
            "run",
            str(APP_PATH),
            "--server.port=8501",
            "--server.headless=true",
            "--browser.serverAddress=",
            "--global.developmentMode=false",
            "--browser.gatherUsageStats=false",
        ]
        _log(f"argv set to {sys.argv}")
        _log(f"STREAMLIT_CONFIG_PATH={os.environ.get('STREAMLIT_CONFIG_PATH')}")
        from streamlit.runtime.scriptrunner import magic_funcs  # noqa: F401
        from streamlit.web.cli import main as stcli_main
        _log("calling stcli.main()")
        stcli_main()
        _log("stcli.main() returned")
        return

    if "--no-gui" in sys.argv:
        class _StubWin:
            def set_step(self, *a): pass
            def set_progress(self, *a): pass
            def set_info(self, *a): pass
            def update(self): pass
            def close(self): pass
        _launch_app(_StubWin())
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
            _install_exiftool(win)
            _add_to_user_path(BIN_DIR)
        win.update()

        # ---- Step 2: FFmpeg ----
        if _resolve_binary_path("ffmpeg"):
            win.set_step(2, "\u2713 Checking FFmpeg... found")
            win.set_progress(100)
            win.set_info("")
        else:
            _install_ffmpeg(win)
            _add_to_user_path(BIN_DIR)
        win.update()

        # ---- Step 3: Ollama ----
        def _ollama_binary():
            """Locate the ollama executable, including the default install path
            that a just-finished silent installer won't expose via PATH yet."""
            found = shutil.which("ollama")
            if found:
                return found
            default_path = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                            / "Programs" / "Ollama" / "ollama.exe")
            if default_path.exists():
                return str(default_path)
            return None

        ollama_binary = _ollama_binary()
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
            ollama_binary = _ollama_binary()

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
        selected_model = "qwen2.5vl:7b"

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

        already_installed = _vision_model_installed()

        if already_installed:
            win.set_step(4, "\u2713 AI model found")
            win.set_progress(100)
            win.set_info("")
            win.update()

            dlg = ModelSelectionDialog(win.root, already_installed=True)
            win.root.wait_window(dlg.top)

            if dlg.result:
                selected_model = dlg.result
                _log(f"User chose to switch to model: {selected_model}")
                _stream_model_with_progress(win, 4,
                                            f"Downloading {selected_model}...",
                                            selected_model)
            else:
                _log("User kept current model")
        else:
            dlg = ModelSelectionDialog(win.root, already_installed=False)
            win.root.wait_window(dlg.top)

            selected_model = dlg.result or "qwen2.5vl:7b"
            _log(f"User selected model: {selected_model}")
            _stream_model_with_progress(win, 4,
                                        f"Downloading {selected_model}...",
                                        selected_model)

        os.environ["SELECTED_MODEL"] = selected_model
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


def _kill_stale_server():
    """Kill any process still listening on port 8501 from a previous session."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            if ":8501" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                _log(f"killing stale server PID={pid}")
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        _log(f"_kill_stale_server: {e}")


def _launch_app(win):
    win.set_step(6, "\u2713 Starting app...")
    win.set_progress(100)
    win.set_info("Starting Streamlit server...")
    win.update()

    _kill_stale_server()

    _log(f"launch_app: spawning subprocess {sys.executable} --streamlit-server")
    log_path = CACHE_DIR / "server.log"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "--streamlit-server"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=log_fh,
        stderr=log_fh,
    )
    _log(f"launch_app: child PID={proc.pid}")

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
                _log("health check: OK (200)")
                break
        except Exception as e:
            _log(f"health check: {e}")
        time.sleep(0.5)

    if not ready:
        _log("health check: FAILED after 30s")
        # Dump child process stderr
        log_fh.close()
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                _log(f"child stdout/stderr:\n{f.read()}")
        except Exception:
            pass
        win.set_info("App taking longer than expected — opening browser...")
        win.update()
    else:
        win.set_info("Opening app window...")
        win.update()

    # Also dump server log for success case
    log_fh.close()
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            server_out = f.read().strip()
            if server_out:
                _log(f"child server output:\n{server_out}")
    except Exception:
        pass

    win.close()

    # Try pywebview native window; fall back to browser
    try:
        import webview
        _icon = str(BASE_DIR / "icon.ico")
        webview.create_window("AI Media Renamer", "http://localhost:8501",
                              width=1280, height=800, resizable=True)
        webview.start(private_mode=True, gui="edgechromium", icon=_icon)
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
