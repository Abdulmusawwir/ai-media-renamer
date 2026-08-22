import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from pathlib import Path

if getattr(sys, "frozen", False) and sys.stdin is None:
    sys.stdin = open(os.devnull)
if getattr(sys, "frozen", False) and sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if getattr(sys, "frozen", False) and sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import requests

from engine import (
    LLAMACPP_GGUF_CATALOG,
    SETUP_DEPENDENCIES,
    SETUP_USE_CASES,
    VERSION,
    _llamacpp_gguf_paths,
    _llamacpp_runtime_digests,
    _llamacpp_runtime_urls,
    _llamacpp_server_running,
    _resolve_binary_path,
    check_for_updates,
    config,
    configure_llamacpp_install,
    download_file,
    ensure_llamacpp_server,
    get_provider,
    load_setup_profile,
    pre_download_whisper,
    recommended_llamacpp_models,
    recommended_models,
    save_setup_profile,
    use_cases_needs,
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
INSTALLER_CACHE = CACHE_DIR / "cache"
LLAMACPP_ZIP_CACHE = CACHE_DIR / "cache" / "llamacpp.zip"
LLAMACPP_EXE = BIN_DIR / "llama-server.exe"

# ---------- theme colors (modern dark) ----------
BG = "#14161c"
PANEL = "#1f232c"
PANEL_HOVER = "#272c37"
BORDER = "#333a47"
FG = "#e8eaf0"
MUTED = "#9aa3b2"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#3a74e8"
GREEN = "#34d399"
RED = "#f87171"
AMBER = "#fbbf24"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SEMI = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_MUTED = ("Segoe UI", 9)
BAR_BG = PANEL  # kept as alias for any remaining callers


def _hover_btn(parent, text, command, *, bg=None, fg="white", font=None,
               padx=20, pady=6, width=None, disabled=False, cursor="hand2"):
    """Modern flat button with hover states."""
    bg = bg or ACCENT
    font = font or ("Segoe UI", 10, "bold")
    btn = tk.Button(parent, text=text, font=font, bg=bg, fg=fg, relief="flat",
                    padx=padx, pady=pady, cursor=cursor, command=command,
                    activebackground=bg, activeforeground=fg, bd=0,
                    highlightthickness=0, disabledforeground="#8a93a3")
    if width:
        btn.config(width=width)
    if disabled:
        btn.config(state="disabled")

    def _on_enter(_e):
        if str(btn.cget("state")) == "normal":
            btn.config(bg=ACCENT_HOVER if bg == ACCENT else PANEL_HOVER)

    def _on_leave(_e):
        if str(btn.cget("state")) == "normal":
            btn.config(bg=bg)

    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn


def _hover_row(row, normal_bg=PANEL, hover_bg=PANEL_HOVER,
               border=BORDER, border_hover=ACCENT):
    """Add hover feedback to a clickable row (binds all children too)."""

    def _set(bg, bord, *_):
        for w in (row, *row.winfo_children()):
            try:
                if str(w.cget("bg")) != "systemTransparent":
                    w.config(bg=bg)
            except tk.TclError:
                pass
        try:
            row.config(highlightbackground=bord)
        except tk.TclError:
            pass

    row.bind("<Enter>", lambda e: _set(hover_bg, border_hover))
    row.bind("<Leave>", lambda e: _set(normal_bg, border))
    for child in row.winfo_children():
        child.bind("<Enter>", lambda e: _set(hover_bg, border_hover))
        child.bind("<Leave>", lambda e: _set(normal_bg, border))


def _bind_wheel(widget):
    """Wire mouse-wheel scrolling onto a widget and all its children."""
    widget.bind_all("<MouseWheel>",
                    lambda e: widget.yview_scroll(int(-e.delta / 120), "units")
                    if widget.winfo_exists() else None)
    widget.bind_all("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
    widget.bind_all("<Button-5>", lambda e: widget.yview_scroll(1, "units"))


def _show_modal(win, dlg):
    """Run a modal Toplevel without nesting an event loop.

    A plain update() loop is immune to the Windows tkinter hang that occurs
    when a grab-holding Toplevel is destroyed inside wait_window()'s nested
    loop, so closing a dialog can never freeze the wizard.
    """
    while True:
        try:
            if not dlg.top.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            win.root.update()
        except tk.TclError:
            return
        time.sleep(0.005)


def _close_dialog(dlg):
    """Destroy a dialog safely: release any grab, then destroy."""
    dlg._closed = True
    try:
        dlg.top.grab_release()
    except tk.TclError:
        pass
    try:
        dlg.top.destroy()
    except tk.TclError:
        pass


class SetupWindow:
    def __init__(self):
        self.root = tk.Tk() if tk else None
        if not self.root:
            print("tkinter not available — running in headless mode.")
            return
        self.root.title("AI Media Renamer — Setup")
        self.root.geometry("560x380")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.root.iconbitmap(str(BASE_DIR / "icon.ico"))
        except Exception:
            pass

        # Modern progress-bar style (accent fill, rounded, dark track)
        try:
            style = ttk.Style(self.root)
            style.theme_use("clam")
            style.configure(
                "dark.Horizontal.TProgressbar", troughcolor="#262b35",
                background=ACCENT, bordercolor=BG, lightcolor=ACCENT,
                darkcolor=ACCENT, thickness=8)
        except Exception:
            pass

        self._center_window()

        # Title + accent rule
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=40, pady=(24, 0))
        tk.Label(header, text="AI Media Renamer", font=("Segoe UI", 17, "bold"),
                 bg=BG, fg=FG).pack(anchor="w")
        tk.Label(header, text="Setting up your local AI workspace…",
                 font=FONT_MUTED, bg=BG, fg=MUTED, anchor="w").pack(fill="x", pady=(2, 0))
        tk.Frame(header, bg=ACCENT, height=2).pack(fill="x", pady=(12, 0))

        # Status step label
        self.step_label = tk.Label(self.root, text="", font=FONT_BOLD,
                                   bg=BG, fg=FG, anchor="w")
        self.step_label.pack(fill="x", padx=40, pady=(16, 4))

        # Progress bar
        self.progress = ttk.Progressbar(self.root, length=480, mode="determinate",
                                         style="dark.Horizontal.TProgressbar")
        self.progress.pack(padx=40, pady=(0, 6))

        # Info text
        self.info_label = tk.Label(self.root, text="", font=FONT_MUTED,
                                   bg=BG, fg=MUTED, anchor="w")
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

        self.dl_btn = _hover_btn(btn_frame, "Download Update",
                                 self._on_download_update, bg=ACCENT, fg="white",
                                 font=("Segoe UI", 10), padx=16, pady=5)
        self.dl_btn.pack(side="left", padx=(0, 12))

        self.cont_btn = _hover_btn(btn_frame, "Continue to App",
                                   self._on_continue, bg=PANEL, fg=FG,
                                   font=("Segoe UI", 10), padx=16, pady=5)
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


def _exiftool_expected_sha256(url: str) -> str | None:
    """Return the published SHA-256 digest for an ExifTool zip URL, or None.

    The digest is read from exiftool.org's ``checksums-<ver>.txt`` file, which
    lists ``SHA2-256(exiftool-<ver>_64.zip)= <hex>``. The version is derived
    from the zip filename embedded in the SourceForge URL. Returns None when
    the version cannot be derived or the checksum file is unavailable.
    """
    match = re.search(r"exiftool-(\d+\.\d+)_64\.zip", url)
    if not match:
        return None
    ver = match.group(1)
    try:
        resp = requests.get(f"https://exiftool.org/checksums-{ver}.txt", timeout=10)
        checksum_line = next(
            (
                line for line in resp.text.splitlines()
                if f"SHA2-256(exiftool-{ver}_64.zip)=" in line
            ),
            "",
        )
        if not checksum_line:
            return None
        digest = checksum_line.split("=", 1)[1].strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            return digest
    except Exception:
        pass
    return None


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
            expected_sha256 = _exiftool_expected_sha256(url)
            if not expected_sha256:
                raise RuntimeError(
                    "no published SHA-256 checksum available for this build")
            zip_dest.unlink(missing_ok=True)
            download_file(url, zip_dest,
                          progress_callback=lambda d, t: _progress_callback(d, t, win, "ExifTool"),
                          expected_sha256=expected_sha256)
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
        resp = requests.get(
            "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
            timeout=10,
        )
        resp.raise_for_status()
        match = re.search(r"[0-9a-f]{64}", resp.text.strip())
        if not match:
            raise RuntimeError("could not read published SHA-256 checksum from gyan.dev")
        expected_sha256 = match.group(0)

        download_file("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
                      zip_dest,
                      progress_callback=lambda d, t: _progress_callback(d, t, win, "FFmpeg"),
                      expected_sha256=expected_sha256)
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


def _install_llamacpp_runtime(win, step: int) -> None:
    """Download and install the llama.cpp ``llama-server`` binary (Windows CPU).

    The runtime zip is a small (~18 MB) CPU build that bundles the server
    executable; it is the default (and only) local AI runtime.
    """
    win.set_step(step, "\u27f3 Downloading llama.cpp runtime...")
    win.set_progress(0)
    win.set_info("Downloading...")
    win.update()

    last_err = None
    digests = _llamacpp_runtime_digests()
    for url in _llamacpp_runtime_urls():
        try:
            expected_sha256 = digests.get(url, "").strip().lower()
            if not expected_sha256:
                raise RuntimeError(
                    "no published SHA-256 checksum available for this runtime build")
            LLAMACPP_ZIP_CACHE.unlink(missing_ok=True)
            download_file(url, LLAMACPP_ZIP_CACHE,
                          progress_callback=lambda d, t: _progress_callback(d, t, win, "llama.cpp"),
                          expected_sha256=expected_sha256)
            if not _is_valid_zip(LLAMACPP_ZIP_CACHE):
                raise RuntimeError("downloaded file is not a valid ZIP archive")
            extract_dir = CACHE_DIR / "llamacpp_extracted"
            shutil.rmtree(extract_dir, ignore_errors=True)
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(LLAMACPP_ZIP_CACHE, "r") as zf:
                zf.extractall(extract_dir)

            exe_src = next((f for f in extract_dir.rglob("llama-server.exe")), None)
            if exe_src is None:
                raise RuntimeError("llama-server.exe not found inside archive")
            BIN_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(exe_src, LLAMACPP_EXE)
            shutil.rmtree(extract_dir, ignore_errors=True)
            LLAMACPP_ZIP_CACHE.unlink(missing_ok=True)
            _add_to_user_path(BIN_DIR)
            win.set_step(step, "\u2713 Checking llama.cpp... ready")
            win.set_progress(100)
            win.set_info("")
            win.update()
            return
        except Exception as exc:
            last_err = exc
            continue

    win.set_step(step, "\u2716 llama.cpp download failed")
    win.set_progress(0)
    win.set_info(f"Automatic download failed: {last_err}. "
                 "Install llama-server manually and retry.")
    win.update()
    import time
    time.sleep(5)


def _download_hf_with_mirror(url: str, dest: Path, win, label: str,
                             expected_sha256: str | None = None) -> None:
    """Download a HuggingFace file, falling back to the hf-mirror.com host.

    Args:
        url: HTTPS HuggingFace resolve URL.
        dest: Destination file path.
        win: Wizard window (for progress updates).
        label: Human-readable download label.
        expected_sha256: Published SHA-256 digest to verify against. When set,
            a mismatching download is rejected (the mirror is only retried for
            transport failures, never for checksum mismatches).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err = None
    for host in ("huggingface.co", "hf-mirror.com"):
        if host == "hf-mirror.com":
            candidate = url.replace("huggingface.co", "hf-mirror.com")
        else:
            candidate = url
        if candidate == url and host == "hf-mirror.com":
            continue
        try:
            dest.unlink(missing_ok=True)
            download_file(candidate, dest,
                          progress_callback=lambda d, t: _progress_callback(d, t, win, label),
                          expected_sha256=expected_sha256)
            return
        except Exception as exc:
            if expected_sha256 and "SHA-256 mismatch" in str(exc):
                raise RuntimeError(
                    f"Checksum verification failed for {label}: {exc}")
            last_err = exc
            continue
    raise RuntimeError(f"Download failed for {label}: {last_err}")


def _pick_llamacpp_model(kind: str, rec: dict[str, str]) -> dict:
    """Select a GGUF catalog entry for a kind, honouring the recommendation."""
    rec_name = rec.get(kind, "")
    for m in LLAMACPP_GGUF_CATALOG:
        if m["kind"] == kind and m["name"] == rec_name:
            return m
    return next((m for m in LLAMACPP_GGUF_CATALOG if m["kind"] == kind), None)


def _install_llamacpp_models(win, step: int, needs: set[str],
                             rec: dict[str, str]) -> None:
    """Download the GGUF models the profile needs and record them in config.

    A vision GGUF (with mmproj) also serves text-only prompts, so a profile
    needing both vision and text only downloads the vision model; text-only
    profiles download the small text GGUF instead.
    """
    needs_vision = "vision_model" in needs
    needs_text = "text_model" in needs

    if needs_vision:
        model = _pick_llamacpp_model("vision", rec)
    elif needs_text:
        model = _pick_llamacpp_model("text", rec)
    else:
        return

    gguf_path, mmproj_path = _llamacpp_gguf_paths(model["name"])
    if gguf_path.exists():
        win.set_step(step, f"\u2713 {model['label']} \u2014 already installed")
        win.set_progress(100)
        win.set_info("")
    else:
        win.set_step(step, f"\u27f3 Downloading {model['label']}...")
        win.set_progress(0)
        win.set_info("This is a large model \u2014 please wait.")
        win.update()
        _download_hf_with_mirror(model["url"], gguf_path, win, model["label"],
                                 expected_sha256=model.get("sha256", ""))
        win.set_progress(100)
        win.set_info("")

    mmproj = model.get("mmproj_url", "")
    if needs_vision and mmproj and not mmproj_path.exists():
        win.set_step(step, "\u27f3 Downloading vision projector (mmproj)...")
        win.set_progress(0)
        win.set_info("Smaller companion file for image understanding.")
        win.update()
        _download_hf_with_mirror(mmproj, mmproj_path, win, "Vision projector",
                                 expected_sha256=model.get("mmproj_sha256", ""))
        win.set_progress(100)
        win.set_info("")

    configure_llamacpp_install(model["name"], gguf_path,
                               mmproj_path if needs_vision else None,
                               make_default=True)

    win.set_step(step, f"\u2713 {model['label']} \u2014 ready")
    win.set_progress(100)
    win.set_info("")
    win.update()


def _start_llamacpp_server(win) -> bool:
    """Launch the installed llama.cpp server (idempotent) and wait for it."""
    win.set_step(0, "\u27f3 Starting llama.cpp server...")
    win.set_progress(50)
    win.set_info("Launching local AI server in background...")
    win.update()
    ok = ensure_llamacpp_server(timeout=40)
    win.set_progress(100)
    win.set_info("")
    win.update()
    return ok


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


class UseCaseDialog:
    """First-run questionnaire: multi-select what the user plans to rename."""

    def __init__(self, parent):
        self.result: list[str] | None = None
        self._closed = False

        self.top = tk.Toplevel(parent)
        self.top.title("What will you rename?")
        sw = self.top.winfo_screenheight()
        height = min(560, max(420, sw - 160))
        self.top.geometry(f"600x{height}")
        self.top.minsize(520, 400)
        self.top.configure(bg=BG)
        self.top.resizable(True, True)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._on_skip)

        self._center(parent)

        # Header
        header = tk.Frame(self.top, bg=BG)
        header.pack(fill="x", padx=28, pady=(22, 0))
        tk.Label(header, text="What do you plan to rename?", font=FONT_TITLE,
                 bg=BG, fg=FG).pack(anchor="w")
        tk.Label(header, text="Select all that apply. This decides what gets "
                              "downloaded once to get you started.",
                 font=FONT_MUTED, bg=BG, fg=MUTED, anchor="w").pack(fill="x", pady=(4, 0))
        tk.Frame(header, bg=ACCENT, height=2).pack(fill="x", pady=(12, 0))

        # Row actions (Select all / Clear)
        actions = tk.Frame(header, bg=BG)
        actions.pack(fill="x", pady=(12, 4))
        tk.Label(actions, text="", bg=BG).pack(side="left", expand=True)
        for text, cmd, primary in (("Select all", self._select_all, False),
                                   ("Clear", self._clear_all, False)):
            _hover_btn(actions, text, cmd, bg=PANEL, fg=FG, font=FONT_SEMI,
                       padx=12, pady=3).pack(side="left", padx=(8, 0))

        # Scrollable body so every option stays reachable on short screens
        body = tk.Frame(self.top, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=(4, 0))
        self._canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=self._canvas.yview,
                              bg=BORDER, troughcolor=BG, bd=0,
                              highlightthickness=0, width=12)
        self._inner = tk.Frame(self._canvas, bg=BG)
        self._inner_id = self._canvas.create_window((0, 0), window=self._inner,
                                                    anchor="nw")
        self._canvas.configure(yscrollcommand=scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._inner_id, width=e.width))
        self.top.bind(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._vars: dict[str, tk.BooleanVar] = {}
        for key, use in SETUP_USE_CASES.items():
            var = tk.BooleanVar(value=False)
            self._vars[key] = var
            row = tk.Frame(self._inner, bg=PANEL, highlightbackground=BORDER,
                           highlightthickness=1, cursor="hand2")
            row.pack(fill="x", pady=4)
            cb = tk.Checkbutton(row, variable=var, bg=PANEL, fg=FG,
                                activebackground=PANEL, activeforeground=FG,
                                selectcolor="#2d3a4f", highlightthickness=0,
                                bd=0, cursor="hand2")
            cb.pack(side="left", padx=(10, 6), pady=10)
            info = tk.Frame(row, bg=PANEL)
            info.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=8)
            tk.Label(info, text=use["label"], font=FONT_BOLD, bg=PANEL, fg=FG,
                     anchor="w").pack(fill="x")
            tk.Label(info, text=use["desc"], font=FONT_MUTED, bg=PANEL,
                     fg=MUTED, anchor="w", wraplength=470, justify="left").pack(fill="x", pady=(1, 0))

            _hover_row(row)
            for w in (row, cb, info, *info.winfo_children()):
                w.bind("<Button-1>",
                       lambda _e, v=var: (v.set(not v.get())))

        # Footer buttons (pinned, always visible)
        footer = tk.Frame(self.top, bg=BG)
        footer.pack(fill="x", padx=28, pady=(10, 16))
        self.cont_btn = _hover_btn(footer, "Continue", self._on_continue,
                                   bg=ACCENT, fg="white", padx=26, pady=7,
                                   disabled=True)
        self.cont_btn.pack(side="left")
        _hover_btn(footer, "Cancel for now", self._on_skip, bg=PANEL, fg=FG,
                   padx=16, pady=7).pack(side="left", padx=(10, 0))
        self.top.bind("<Return>", lambda e: self._on_continue())
        self.top.bind("<Escape>", lambda e: self._on_skip())

        for var in self._vars.values():
            var.trace_add("write", self._update_continue)
        self._update_continue()

    def _select_all(self):
        for var in self._vars.values():
            var.set(True)

    def _clear_all(self):
        for var in self._vars.values():
            var.set(False)

    def _update_continue(self, *_):
        state = "normal" if any(v.get() for v in self._vars.values()) else "disabled"
        self.cont_btn.config(state=state)

    def _on_continue(self):
        chosen = [k for k, v in self._vars.items() if v.get()]
        if not chosen:
            return
        self.result = chosen
        _close_dialog(self)

    def _on_skip(self):
        self.result = None
        _close_dialog(self)

    def _center(self, parent):
        self.top.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.top.winfo_width()
        h = self.top.winfo_height()
        self.top.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.top.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")


def _plan_sizes(rec_models: dict[str, str]) -> dict[str, str]:
    """Approximate one-time download size per dependency for the plan summary.

    Model rows show the full size range across the catalog alternatives,
    because the exact size depends on which model the user picks next.
    """
    sizes = {"llamacpp": "~18 MB",
             "ffmpeg": "~109 MB", "exiftool": "~10 MB",
             "whisper": "~74 MB"}
    for kind in ("vision", "text"):
        cands = [m["size_gb"] for m in LLAMACPP_GGUF_CATALOG if m["kind"] == kind]
        if cands:
            lo, hi = min(cands), max(cands)
            sizes[f"{kind}_gguf"] = (f"{lo:.1f} GB" if abs(hi - lo) < 0.01
                                     else f"{lo:.1f}\u2013{hi:.1f} GB")
        else:
            sizes[f"{kind}_gguf"] = "?"
    return sizes


def _build_plan(profile: list[str], needs: set[str], rec_models: dict[str, str]) -> list[dict]:
    """Build the 'you will download once' plan for the chosen use cases.

    The local AI runtime is the small (~18 MB) llama.cpp ``llama-server`` that
    runs the GGUF models locally; it is the default (and only) runtime.
    """
    sizes = _plan_sizes(rec_models)
    runtime = "llamacpp"
    plan: list[dict] = []

    exe = LLAMACPP_EXE if LLAMACPP_EXE.exists() else _resolve_binary_path("llama-server")
    plan.append({"label": "llama.cpp runtime (AI server)", "size": sizes["llamacpp"],
                 "desc": "Runs your AI models locally \u2014 the default for new setups.",
                 "status": "ready" if exe else "download"})
    for key in ("exiftool", "ffmpeg"):
        if key in needs:
            status = "ready" if _resolve_binary_path(key) else "download"
            plan.append({"label": SETUP_DEPENDENCIES[key]["label"], "size": sizes[key],
                         "desc": SETUP_DEPENDENCIES[key]["desc"], "status": status})
    for key in ("vision_model", "text_model"):
        if key not in needs:
            continue
        kind = key.replace("_model", "")
        rec_name = rec_models.get(kind, "")
        gguf_path, _ = _llamacpp_gguf_paths(rec_name)
        status = "installed" if gguf_path.exists() else "download"
        size = sizes.get(f"{kind}_gguf", "?")
        plan.append({"label": SETUP_DEPENDENCIES[key]["label"], "size": size,
                     "desc": SETUP_DEPENDENCIES[key]["desc"], "status": status})
    if runtime == "llamacpp" and "vision_model" in needs and "text_model" in needs:
        plan.append({"label": "Text analysis (vision model handles it)", "size": "",
                     "desc": "No extra download \u2014 the vision GGUF also answers "
                             "text-only prompts.",
                     "status": "included"})
    if "whisper" in needs:
        plan.append({"label": SETUP_DEPENDENCIES["whisper"]["label"], "size": sizes["whisper"],
                     "desc": SETUP_DEPENDENCIES["whisper"]["desc"], "status": "download"})
    return plan


class PlanConfirmDialog:
    """Confirmation dialog listing what the setup will download once."""

    def __init__(self, parent, plan: list[dict]):
        self.result = False
        self._closed = False
        self.top = tk.Toplevel(parent)
        self.top.title("One-time setup")
        sw = self.top.winfo_screenheight()
        height = min(460, max(320, sw - 200))
        self.top.geometry(f"600x{height}")
        self.top.minsize(520, 320)
        self.top.configure(bg=BG)
        self.top.resizable(True, True)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._on_back)

        self._center(parent)

        header = tk.Frame(self.top, bg=BG)
        header.pack(fill="x", padx=30, pady=(22, 0))
        tk.Label(header, text="You'll download this once", font=FONT_TITLE,
                 bg=BG, fg=FG).pack(anchor="w")
        tk.Label(header, text="Everything below is installed locally and needed "
                              "for the use cases you picked.",
                 font=FONT_MUTED, bg=BG, fg=MUTED, anchor="w").pack(fill="x", pady=(4, 0))
        tk.Frame(header, bg=ACCENT, height=2).pack(fill="x", pady=(12, 0))

        # Scrollable body so long plans never push the buttons off-screen
        body = tk.Frame(self.top, bg=BG)
        body.pack(fill="both", expand=True, padx=30, pady=(14, 0))
        self._canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=self._canvas.yview,
                              bg=BORDER, troughcolor=BG, bd=0,
                              highlightthickness=0, width=12)
        self._inner = tk.Frame(self._canvas, bg=BG)
        self._inner_id = self._canvas.create_window((0, 0), window=self._inner,
                                                    anchor="nw")
        self._canvas.configure(yscrollcommand=scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._inner_id, width=e.width))
        self.top.bind(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-e.delta / 120), "units"))

        for item in plan:
            row = tk.Frame(self._inner, bg=PANEL, highlightbackground=BORDER,
                           highlightthickness=1)
            row.pack(fill="x", pady=3)
            status_color = GREEN if item["status"] in ("ready", "installed", "included") else AMBER
            badge = {"ready": "Found", "installed": "Installed",
                     "included": "Included", "download": "To download"}[item["status"]]
            tk.Label(row, text=item["label"], font=FONT_BOLD, bg=PANEL, fg=FG,
                     anchor="w", width=24).pack(side="left", padx=(12, 6), pady=8)
            tk.Label(row, text=item["size"], font=FONT_MUTED, bg=PANEL,
                     fg=MUTED, anchor="e", width=12).pack(side="left", padx=(0, 6))
            tk.Label(row, text=badge, font=("Segoe UI", 8, "bold"), bg=PANEL,
                     fg=status_color, anchor="e", width=12).pack(side="right", padx=(0, 12))

        sizes = [i["size"] for i in plan if i["status"] == "download"]
        total = tk.Label(self._inner, text="", font=FONT_SEMI, bg=BG, fg=FG, anchor="w")
        total.pack(fill="x", pady=(12, 0))
        total.config(text=(f"New downloads: {', '.join(sizes)}"
                           if sizes else "Nothing to download — everything is already found"))

        # Footer buttons (pinned, always visible)
        footer = tk.Frame(self.top, bg=BG)
        footer.pack(fill="x", padx=30, pady=(8, 16))
        _hover_btn(footer, "Start setup", self._on_start, bg=ACCENT, fg="white",
                   padx=26, pady=7).pack(side="left")
        _hover_btn(footer, "Back", self._on_back, bg=PANEL, fg=FG,
                   padx=16, pady=7).pack(side="left", padx=(10, 0))
        self.top.bind("<Return>", lambda e: self._on_start())
        self.top.bind("<Escape>", lambda e: self._on_back())

    def _on_start(self):
        self.result = True
        _close_dialog(self)

    def _on_back(self):
        self.result = False
        _close_dialog(self)

    def _center(self, parent):
        self.top.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.top.winfo_width()
        h = self.top.winfo_height()
        self.top.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")


def _installed_models() -> set[str]:
    """Return the set of model names the running llama.cpp server exposes."""
    if not _llamacpp_server_running():
        return set()
    try:
        provider = get_provider("llamacpp")
        return set(provider.available_models())
    except Exception:
        return set()


class ModelRecommendationDialog:
    """Choose vision and/or text models for the onboarding profile.

    The model list lives in a scrollable, resizable panel so every option and
    the footer buttons are always reachable. Registry validation runs in a
    background thread but results are applied through a main-thread queue
    poll, so closing the dialog can never touch Tk from another thread or
    block the wizard.
    """

    def __init__(self, parent, needs: set[str], installed: set[str],
                 recommended: dict[str, str]):
        self.result: dict[str, str | None] = {"vision": None, "text": None}
        self.installed = installed
        self.recommended = recommended
        self._closed = False
        self._row_status: dict[str, tk.Widget] = {}

        self.top = tk.Toplevel(parent)
        self.top.title("Choose AI Models")
        sw = self.top.winfo_screenheight()
        height = min(680, max(420, sw - 180))
        self.top.geometry(f"600x{height}")
        self.top.minsize(520, 380)
        self.top.configure(bg=BG)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._on_skip)

        self._center(parent)

        # Header (fixed)
        header = tk.Frame(self.top, bg=BG)
        header.pack(fill="x", padx=28, pady=(20, 0))
        tk.Label(header, text="Choose AI models", font=FONT_TITLE,
                 bg=BG, fg=FG).pack(anchor="w")
        tk.Label(header, text="Recommended for your hardware — you can pick any "
                              "installed or available alternative.",
                 font=FONT_MUTED, bg=BG, fg=MUTED, anchor="w").pack(fill="x", pady=(4, 0))
        tk.Frame(header, bg=ACCENT, height=2).pack(fill="x", pady=(12, 0))

        # Scrollable body
        body = tk.Frame(self.top, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=(12, 0))
        self._canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=self._canvas.yview,
                              bg=BORDER, troughcolor=BG, bd=0,
                              highlightthickness=0, width=12)
        self._inner = tk.Frame(self._canvas, bg=BG)
        self._inner_id = self._canvas.create_window((0, 0), window=self._inner,
                                                    anchor="nw")
        self._canvas.configure(yscrollcommand=scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._inner_id, width=e.width))
        self.top.bind(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._vars: dict[str, tk.StringVar] = {}
        kind_labels = {"vision": "Vision model (analyzes frames & photos)",
                       "text": "Text model (documents, spreadsheets, transcripts)"}
        for kind in ("vision", "text"):
            if f"{kind}_model" not in needs:
                continue
            tk.Label(self._inner, text=kind_labels[kind], font=FONT_SEMI, bg=BG,
                     fg=ACCENT, anchor="w").pack(fill="x", pady=(10, 4))
            self._vars[kind] = tk.StringVar(value=self.recommended.get(kind, ""))
            for m in LLAMACPP_GGUF_CATALOG:
                if m["kind"] != kind:
                    continue
                self._add_row(m, kind)

        # Footer (fixed)
        footer = tk.Frame(self.top, bg=BG)
        footer.pack(fill="x", padx=28, pady=(10, 16))
        note = tk.Label(footer, text="", font=FONT_MUTED, bg=BG, fg=MUTED, anchor="w")
        note.pack(fill="x", pady=(0, 8))
        note.config(text="Pick the model that best fits your hardware and use case.")
        self.dl_btn = _hover_btn(footer, "Continue", self._on_confirm, bg=ACCENT,
                                 fg="white", padx=26, pady=7)
        self.dl_btn.pack(side="left")
        _hover_btn(footer, "Skip", self._on_skip, bg=PANEL, fg=FG,
                   padx=16, pady=7).pack(side="left", padx=(10, 0))

    def _add_row(self, m, kind):
        row = tk.Frame(self._inner, bg=PANEL, highlightbackground=BORDER,
                       highlightthickness=1, cursor="hand2")
        row.pack(fill="x", pady=4)
        rb = tk.Radiobutton(row, variable=self._vars[kind], value=m["name"],
                            bg=PANEL, fg=FG, selectcolor="#2d3a4f",
                            activebackground=PANEL, activeforeground=FG,
                            highlightthickness=0, bd=0, cursor="hand2")
        rb.pack(side="left", padx=(12, 4), pady=12)

        info = tk.Frame(row, bg=PANEL)
        info.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)

        installed = m["name"] in self.installed
        rec = (self.recommended.get(kind) == m["name"])
        quality_color = GREEN if m["quality"] == "Best" else ACCENT if m["quality"] == "Good" else MUTED
        header_text = f'{m["label"]}   ({m["size"]})'
        tk.Label(info, text=header_text, font=FONT_BOLD, bg=PANEL, fg=FG,
                 anchor="w").pack(fill="x")
        tk.Label(info, text=m["desc"], font=FONT_MUTED, bg=PANEL,
                 fg=MUTED, anchor="w", wraplength=470, justify="left").pack(fill="x", pady=(1, 0))

        tags = tk.Frame(info, bg=PANEL)
        tags.pack(fill="x", pady=(4, 0))
        for tag_text, color in [("Quality: " + m["quality"], quality_color),
                                ("Speed: " + m["speed"], MUTED)]:
            tk.Label(tags, text=tag_text, font=("Segoe UI", 8, "bold"),
                     bg=PANEL, fg=color, anchor="w").pack(side="left", padx=(0, 12))
        badge_txt = ("  \u2713 Installed" if installed else
                     "  \u2605 Recommended" if rec else "")
        status = tk.Label(tags, text=badge_txt, font=("Segoe UI", 8, "bold"),
                          bg=PANEL, fg=GREEN if installed else AMBER, anchor="w")
        status.pack(side="left")
        self._row_status[m["name"]] = status

        _hover_row(row)
        for w in (row, info, tags, *tags.winfo_children(), *info.winfo_children()):
            w.bind("<Button-1>", lambda e, v=m["name"], k=kind: self._vars[k].set(v))

    def _on_confirm(self):
        self.result = {k: v.get() or None for k, v in self._vars.items()}
        _close_dialog(self)

    def _on_skip(self):
        self.result = {"vision": None, "text": None}
        _close_dialog(self)

    def _center(self, parent):
        self.top.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.top.winfo_width()
        h = self.top.winfo_height()
        self.top.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")


def main():
    _log(f"main() argv={sys.argv} frozen={getattr(sys, 'frozen', False)}")

    if "--streamlit-server" in sys.argv:
        if "--check-only" in sys.argv:
            import importlib.metadata
            importlib.metadata.version("streamlit")
            sys.exit(0)

        _log(f"APP_PATH={APP_PATH} exists={APP_PATH.exists()}")
        os.environ["STREAMLIT_CONFIG_PATH"] = str(BASE_DIR / ".streamlit" / "config.toml")
        # Bind to loopback by default; opt into LAN exposure via
        # config.json server.lan_expose = true (see AGENTS.md / 20.3).
        lan_expose = bool(config.get("server", {}).get("lan_expose", False))
        server_address = "0.0.0.0" if lan_expose else "127.0.0.1"
        sys.argv = [
            "streamlit",
            "run",
            str(APP_PATH),
            "--server.port=8501",
            "--server.headless=true",
            f"--server.address={server_address}",
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

    force_setup = "--setup" in sys.argv

    try:
        # ---- Onboarding questionnaire (first run, or explicit --setup) ----
        profile_data = load_setup_profile()
        onboarded = profile_data.get("onboarded", False)
        profile = profile_data.get("profile", [])

        if not onboarded or force_setup:
            dlg = UseCaseDialog(win.root)
            _show_modal(win, dlg)
            if dlg.result is None:
                profile = []
                save_setup_profile(profile=[], onboarded=True)
            else:
                profile = dlg.result

        needs = use_cases_needs(profile) if profile else {"ffmpeg", "exiftool"}
        rec_models = recommended_models(profile) if profile else {}
        do_installs = bool(profile)

        # Skipped onboarding (empty profile): don't force any downloads —
        # launch the app; env checks + in-app download buttons cover the rest.
        if not do_installs:
            _launch_app(win)
            return

        # Confirm the one-time download plan when onboarding / re-running setup
        if do_installs and (not onboarded or force_setup):
            dlg = PlanConfirmDialog(win.root, _build_plan(profile, needs, rec_models))
            _show_modal(win, dlg)
            if not dlg.result:
                save_setup_profile(profile=profile, onboarded=True)
                _launch_app(win)
                return

        step = 1

        # ---- Step: Local AI runtime (llama.cpp) ----
        runtime = "llamacpp"
        llm_exe = LLAMACPP_EXE if LLAMACPP_EXE.exists() else _resolve_binary_path("llama-server")
        if not llm_exe:
            _install_llamacpp_runtime(win, step)
        if _llamacpp_server_running():
            win.set_step(step, "\u2713 Checking llama.cpp... running")
            win.set_progress(100)
            win.set_info("")
        elif not _start_llamacpp_server(win):
            win.set_step(step, "\u26a0 llama.cpp server did not start")
            win.set_progress(100)
            win.set_info("Please start llama-server manually and restart this app.")
            win.wait_for_user()
            win.close()
            return
        win.update()
        step += 1

        # ---- Step: ExifTool (only when the profile needs it) ----
        if "exiftool" in needs:
            if _resolve_binary_path("exiftool"):
                win.set_step(step, "\u2713 Checking ExifTool... found")
                win.set_progress(100)
                win.set_info("")
            else:
                _install_exiftool(win)
                _add_to_user_path(BIN_DIR)
            win.update()
            step += 1

        # ---- Step: FFmpeg (only when the profile needs it) ----
        if "ffmpeg" in needs:
            if _resolve_binary_path("ffmpeg"):
                win.set_step(step, "\u2713 Checking FFmpeg... found")
                win.set_progress(100)
                win.set_info("")
            else:
                _install_ffmpeg(win)
                _add_to_user_path(BIN_DIR)
            win.update()
            step += 1

        # ---- Step: AI models (vision and/or text for the profile) ----
        needs_vision = "vision_model" in needs
        needs_text = "text_model" in needs

        if needs_vision or needs_text:
            rec_llamacpp = recommended_llamacpp_models(profile)
            _install_llamacpp_models(win, step, needs, rec_llamacpp)
            step += 1
        win.update()

        # ---- Step: Whisper (speech-to-text, when the profile needs it) ----
        if "whisper" in needs:
            win.set_step(step, "\u27f3 Preparing Whisper (speech-to-text)...")
            win.set_progress(50)
            win.set_info("Downloading speech-to-text model (~74 MB)...")
            win.update()
            pre_download_whisper("base")
            win.set_step(step, "\u2713 Whisper \u2014 ready")
            win.set_progress(100)
            win.set_info("")
            win.update()
            step += 1

        # ---- Persist the onboarding profile ----
        if not onboarded or force_setup:
            save_setup_profile(profile=profile, onboarded=True, runtime=runtime)

        # ---- Step: Update check ----
        update_info = check_for_updates()
        if update_info.get("ok") and update_info.get("update_available"):
            win.set_step(step, "\u26a0 Update available")
            win.set_progress(100)
            win.set_info("")
            win.show_update(update_info)
            win.update()
            win.wait_for_user()
        else:
            win.set_step(step, "\u2713 Checking for updates... up to date")
            win.set_progress(100)
            win.set_info("")
        win.update()

        # ---- Step: Launch ----
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
            with open(log_path, encoding="utf-8", errors="replace") as f:
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
        with open(log_path, encoding="utf-8", errors="replace") as f:
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
        ("llama.cpp server", _llamacpp_server_running()),
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
