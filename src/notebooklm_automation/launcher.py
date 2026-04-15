#!/usr/bin/env python3
"""
Study Hub — Full Pipeline Launcher
────────────────────────────────────
Place next to build_study_hub.py and tutor_server.py.

Windows (dev)  : python launcher.py
Windows (exe)  : rename to launcher.pyw and double-click
                 OR: pyinstaller --onefile --windowed launcher.py
"""

from __future__ import annotations

import json
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Callable

from notebooklm_automation.config import normalize_notebook_id, parse_source_ids

# ── Platform ──────────────────────────────────────────────────────────────────
IS_MAC = platform.system() == "Darwin"
IS_WIN = platform.system() == "Windows"

# ── Resolve the real executable directory (works both frozen and plain Python)
# When PyInstaller builds --onefile, sys.executable is the .exe itself.
# __file__ would be a temp _MEI path — never use it for user-facing files.
if getattr(sys, "frozen", False):
    # Running as a PyInstaller bundle
    EXE_DIR = Path(sys.executable).parent.resolve()
else:
    # Running as a plain .py script
    EXE_DIR = Path(__file__).parent.resolve()

# ── Persisted settings file lives next to the exe, survives relaunches ────────
SETTINGS_FILE = EXE_DIR / "launcher_settings.json"
PROFILE_DIR = EXE_DIR / "launcher_profiles"

# ── Colours ───────────────────────────────────────────────────────────────────
BG = "#0d1117"
SURFACE = "#161b22"
SURFACE2 = "#21262d"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
GREEN_L = "#2ea043"
RED = "#da3633"
YELLOW = "#d29922"
BLUE = "#1f6feb"
BLUE_L = "#388bfd"
PURPLE = "#6e40c9"

# ── Fonts ─────────────────────────────────────────────────────────────────────
if IS_MAC:
    F_UI = ("SF Pro Text", 11)
    F_UI_B = ("SF Pro Text", 11, "bold")
    F_H = ("SF Pro Display", 13, "bold")
    F_MONO = ("SF Mono", 10)
elif IS_WIN:
    F_UI = ("Segoe UI", 10)
    F_UI_B = ("Segoe UI", 10, "bold")
    F_H = ("Segoe UI", 12, "bold")
    F_MONO = ("Consolas", 9)
else:
    F_UI = ("DejaVu Sans", 10)
    F_UI_B = ("DejaVu Sans", 10, "bold")
    F_H = ("DejaVu Sans", 12, "bold")
    F_MONO = ("Monospace", 9)


# ── Helpers ────────────────────────────────────────────────────────────────────
def run_ollama_check() -> bool:
    try:
        import urllib.request

        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def open_path(p: str) -> None:
    if IS_MAC:
        subprocess.Popen(["open", p])
    elif IS_WIN:
        os.startfile(p)
    else:
        subprocess.Popen(["xdg-open", p])


def dot_color(ok: bool | None) -> str:
    if ok is None:
        return YELLOW
    return GREEN_L if ok else RED


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def sanitize_folder_name(raw_name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw_name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def build_profile_path(profile_name: str) -> Path:
    safe_name = sanitize_folder_name(profile_name)
    return PROFILE_DIR / f"{safe_name}.json"


def list_profile_paths() -> list[Path]:
    if not PROFILE_DIR.exists():
        return []

    return sorted(PROFILE_DIR.glob("*.json"), key=lambda path: path.stem.lower())


def infer_subfolder_name(root: Path, parent_name: str, target_dir: str) -> str:
    try:
        relative = Path(target_dir).resolve().relative_to((root / parent_name).resolve())
    except Exception:
        return ""

    return relative.parts[0] if len(relative.parts) == 1 else ""


def infer_collection_name(root: Path, output_dir: str) -> str:
    return infer_subfolder_name(root, "output", output_dir)


def infer_prompt_set_name(root: Path, prompts_dir: str) -> str:
    prompt_set_name = infer_subfolder_name(root, "prompts", prompts_dir)
    return "" if prompt_set_name == "default" else prompt_set_name


def build_pipeline_dirs(root: Path, collection_name: str) -> tuple[Path, Path, str]:
    folder_name = sanitize_folder_name(collection_name)
    if not folder_name:
        return root / "output", root / "output", ""

    notebook_dir = root / "output" / folder_name
    return notebook_dir, notebook_dir, folder_name


def build_site_dir_from_output(root: Path, output_dir: str | Path) -> Path:
    return Path(output_dir)


def build_prompts_dir(root: Path, prompt_set_name: str) -> tuple[Path, str]:
    folder_name = sanitize_folder_name(prompt_set_name)
    if not folder_name:
        return root / "prompts" / "default", ""

    return root / "prompts" / folder_name, folder_name


# ── Reusable widgets ───────────────────────────────────────────────────────────


class LogBox(tk.Frame):
    TAGS = {
        "ok": GREEN_L,
        "err": "#f85149",
        "warn": "#e3b341",
        "info": BLUE_L,
        "dim": MUTED,
        "hi": "#79c0ff",
    }

    def __init__(self, parent: tk.Widget, height: int = 14, **kw) -> None:
        super().__init__(parent, bg=BG, **kw)
        self._q: queue.Queue[tuple[str, str]] = queue.Queue()
        self._text = scrolledtext.ScrolledText(
            self,
            bg="#010409",
            fg=TEXT,
            font=F_MONO,
            height=height,
            relief="flat",
            bd=0,
            wrap="word",
            state="disabled",
            cursor="arrow",
        )
        self._text.pack(fill="both", expand=True)
        for tag, colour in self.TAGS.items():
            self._text.tag_config(tag, foreground=colour)
        self._poll()

    def log(self, msg: str, tag: str = "") -> None:
        self._q.put((msg, tag))

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                msg, tag = self._q.get_nowait()
                ts = time.strftime("%H:%M:%S")
                self._text.configure(state="normal")
                self._text.insert("end", f"[{ts}] {msg}\n", tag)
                self._text.see("end")
                self._text.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(80, self._poll)


class Field(tk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        var: tk.Variable,
        browse: bool = False,
        browse_start: str | Path | None | Callable[[], str | Path | None] = None,
        prefer_browse_start: bool = False,
        width: int = 36,
        on_select: Callable[[str], None] | None = None,
        **kw,
    ) -> None:
        super().__init__(parent, bg=BG, **kw)
        tk.Label(self, text=label, bg=BG, fg=MUTED, font=F_UI, width=26, anchor="w").pack(
            side="left"
        )
        tk.Entry(
            self,
            textvariable=var,
            bg=SURFACE2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=4,
            font=F_MONO,
            width=width,
        ).pack(side="left", padx=(0, 4))
        if browse:
            tk.Button(
                self,
                text="...",
                bg=SURFACE2,
                fg=TEXT,
                activebackground=BORDER,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=6,
                cursor="hand2",
                font=F_UI,
                command=lambda: self._browse_directory(var, browse_start, prefer_browse_start, on_select),
            ).pack(side="left")

    def _browse_directory(
        self,
        var: tk.Variable,
        browse_start: str | Path | None | Callable[[], str | Path | None],
        prefer_browse_start: bool,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        initial_dir = None

        if browse_start is not None:
            candidate = browse_start() if callable(browse_start) else browse_start
            if candidate:
                candidate_path = Path(candidate)
                if candidate_path.exists():
                    initial_dir = candidate_path if candidate_path.is_dir() else candidate_path.parent

        if prefer_browse_start and initial_dir is not None:
            selected = filedialog.askdirectory(initialdir=str(initial_dir))
            if selected:
                var.set(selected)
                if on_select:
                    on_select(selected)
            return

        current_value = str(var.get()).strip()
        if current_value:
            current_path = Path(current_value)
            if current_path.exists():
                initial_dir = current_path if current_path.is_dir() else current_path.parent

        selected = filedialog.askdirectory(initialdir=str(initial_dir) if initial_dir else None)
        if selected:
            var.set(selected)
            if on_select:
                on_select(selected)


class ActionBtn(tk.Button):
    def __init__(self, parent, text, colour, command, **kw):
        super().__init__(
            parent,
            text=text,
            bg=colour,
            fg="white",
            activebackground=colour,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            font=F_UI_B,
            command=command,
            **kw,
        )


def build_scrolling_listbox(
    parent: tk.Widget,
    *,
    height: int,
) -> tk.Listbox:
    container = tk.Frame(parent, bg=BG)
    container.pack(fill="both", expand=True)

    listbox = tk.Listbox(
        container,
        bg="#010409",
        fg=TEXT,
        selectbackground=BLUE,
        selectforeground="white",
        font=F_MONO,
        height=height,
        relief="flat",
        bd=0,
    )
    scrollbar = tk.Scrollbar(
        container,
        orient="vertical",
        command=listbox.yview,
        bg=SURFACE2,
        activebackground=BORDER,
        troughcolor=BG,
        relief="flat",
        bd=0,
    )
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return listbox


class StatusBar(tk.Frame):
    def __init__(self, parent: tk.Widget, items: list[str], **kw) -> None:
        super().__init__(parent, bg=SURFACE, pady=8, **kw)
        self._dots: dict[str, tk.Label] = {}
        for name in items:
            f = tk.Frame(self, bg=SURFACE)
            f.pack(side="left", padx=12)
            dot = tk.Label(f, text="●", fg=YELLOW, bg=SURFACE, font=("Arial", 13))
            dot.pack(side="left", padx=(0, 4))
            tk.Label(f, text=name, fg=MUTED, bg=SURFACE, font=F_UI).pack(side="left")
            self._dots[name] = dot

    def set(self, name: str, ok: bool | None) -> None:
        if name in self._dots:
            self._dots[name].config(fg=dot_color(ok))


# ── Main App ───────────────────────────────────────────────────────────────────


class SetupWizard(tk.Toplevel):
    """
    Modal dialog shown on first launch or when critical settings are missing.
    Guides the user through: venv python, project root, .env check.
    """

    def __init__(self, parent: tk.Tk, settings: dict) -> None:
        super().__init__(parent)
        self.title("Study Hub — First-Time Setup")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()  # modal
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._cancelled = False
        self._python = tk.StringVar(value=settings.get("venv_python", ""))
        self._root = tk.StringVar(value=settings.get("nlm_root", ""))

        self._build()
        self.geometry("640x480")
        # Centre on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=SURFACE, pady=14)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text="Welcome — Let's set up the launcher", bg=SURFACE, fg=TEXT, font=F_H
        ).pack()
        tk.Label(
            hdr,
            text="These two paths are required before anything will work.",
            bg=SURFACE,
            fg=MUTED,
            font=F_UI,
        ).pack()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Step 1: Python
        tk.Label(
            body, text="1  PYTHON / VIRTUAL ENVIRONMENT", bg=BG, fg=MUTED, font=F_UI, anchor="w"
        ).pack(fill="x", pady=(0, 2))
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))
        tk.Label(
            body,
            text=(
                "Point to the python.exe inside your virtual environment.\n"
                "Example: C:\\...\\notebooklm-automated\\.venv\\Scripts\\python.exe"
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        py_row = tk.Frame(body, bg=BG)
        py_row.pack(fill="x", pady=(0, 4))
        tk.Entry(
            py_row,
            textvariable=self._python,
            bg=SURFACE2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=4,
            font=F_MONO,
            width=52,
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            py_row,
            text="Browse...",
            bg=SURFACE2,
            fg=TEXT,
            activebackground=BORDER,
            relief="flat",
            bd=0,
            padx=8,
            cursor="hand2",
            font=F_UI,
            command=self._browse_python,
        ).pack(side="left")

        self._py_status = tk.Label(body, text="", bg=BG, font=F_UI)
        self._py_status.pack(anchor="w", pady=(0, 12))
        self._python.trace_add("write", lambda *_: self._check_python())
        self._check_python()

        # ── Step 2: Project root
        tk.Label(body, text="2  PROJECT ROOT FOLDER", bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
            fill="x", pady=(0, 2)
        )
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))
        tk.Label(
            body,
            text=(
                "The root of your notebooklm-automated project.\n"
                "Example: C:\\Users\\vytal\\Dev\\...\\notebooklm-automated"
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        root_row = tk.Frame(body, bg=BG)
        root_row.pack(fill="x", pady=(0, 4))
        tk.Entry(
            root_row,
            textvariable=self._root,
            bg=SURFACE2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=4,
            font=F_MONO,
            width=52,
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            root_row,
            text="Browse...",
            bg=SURFACE2,
            fg=TEXT,
            activebackground=BORDER,
            relief="flat",
            bd=0,
            padx=8,
            cursor="hand2",
            font=F_UI,
            command=lambda: self._root.set(
                filedialog.askdirectory(title="Select project root") or self._root.get()
            ),
        ).pack(side="left")

        self._root_status = tk.Label(body, text="", bg=BG, font=F_UI)
        self._root_status.pack(anchor="w", pady=(0, 4))
        self._root.trace_add("write", lambda *_: self._check_root())
        self._check_root()

        # ── Buttons
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=24, pady=(0, 16))
        tk.Button(
            btn_row,
            text="Cancel — exit launcher",
            bg=SURFACE2,
            fg=MUTED,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            cursor="hand2",
            font=F_UI,
            command=self._cancel,
        ).pack(side="left")
        self._save_btn = tk.Button(
            btn_row,
            text="Save & Continue  →",
            bg=GREEN_L,
            fg="white",
            activebackground=GREEN_L,
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            font=F_UI_B,
            command=self._save,
        )
        self._save_btn.pack(side="right")

    def _browse_python(self) -> None:
        path = filedialog.askopenfilename(
            title="Select python.exe",
            filetypes=[
                ("Python executable", "python.exe python python3 python3.*"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._python.set(path)

    def _check_python(self) -> None:
        p = self._python.get().strip()
        if p and Path(p).exists():
            self._py_status.config(text="✔  Found", fg=GREEN_L)
        elif p:
            self._py_status.config(text="✘  Not found at that path", fg="#f85149")
        else:
            self._py_status.config(text="Not set", fg=YELLOW)

    def _check_root(self) -> None:
        r = self._root.get().strip()
        if not r:
            self._root_status.config(text="Not set", fg=YELLOW)
            return
        rp = Path(r)
        if not rp.exists():
            self._root_status.config(text="✘  Folder not found", fg="#f85149")
            return
        env = rp / ".env"
        cli = rp / "src" / "notebooklm_automation" / "cli.py"
        notes = []
        if env.exists():
            notes.append(".env found")
        else:
            notes.append(".env missing (will be created on first open)")
        if cli.exists():
            notes.append("cli.py found")
        else:
            notes.append("cli.py not found — check this is the right folder")
        self._root_status.config(text="✔  " + " · ".join(notes), fg=GREEN_L)

    def _save(self) -> None:
        python = self._python.get().strip()
        root = self._root.get().strip()
        errors = []
        if not python:
            errors.append("Python path is required.")
        elif not Path(python).exists():
            errors.append(f"Python not found: {python}")
        if not root:
            errors.append("Project root is required.")
        elif not Path(root).exists():
            errors.append(f"Project root folder not found: {root}")
        if errors:
            messagebox.showerror("Fix these before continuing", "\n".join(errors), parent=self)
            return
        self.result = {"venv_python": python, "nlm_root": root}
        self.destroy()

    def _cancel(self) -> None:
        self._cancelled = True
        self.result = None
        self.destroy()


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Study Hub - Pipeline Launcher")
        self.configure(bg=BG)
        self.resizable(True, True)

        # Load only machine-level persisted settings (path config, not profile data)
        saved = load_settings()

        # ── Show setup wizard if critical settings are missing ─────────────────────
        needs_setup = (
            not saved.get("venv_python")
            or not Path(saved.get("venv_python", "")).exists()
            or not saved.get("nlm_root")
            or not Path(saved.get("nlm_root", "")).exists()
        )
        if needs_setup:
            self.withdraw()
            wizard = SetupWizard(self, saved)
            self.wait_window(wizard)
            if wizard._cancelled or wizard.result is None:
                self.destroy()
                return
            saved.update(wizard.result)
            save_settings(saved)
            self.deiconify()

        initial_root = Path(saved.get("nlm_root", str(EXE_DIR)))
        initial_prompts_dir = initial_root / "prompts" / "default"
        initial_output_dir = str(initial_root / "output")

        self._nlm_root = tk.StringVar(value=str(initial_root))
        self._notebook_id = tk.StringVar(value="")
        self._notebook_catalog: list[dict[str, str]] = []
        self._notebook_list: tk.Listbox | None = None
        self._notebook_rows: list[dict[str, str]] = []
        self._prompt_set_name = tk.StringVar(value="default")
        self._prompts_dir = tk.StringVar(value=str(initial_prompts_dir))
        self._collection_name = tk.StringVar(value="")
        self._output_dir = tk.StringVar(value=initial_output_dir)
        self._site_dir = tk.StringVar(value=initial_output_dir)
        self._source_ids_text = ""
        self._source_ids_editor: scrolledtext.ScrolledText | None = None
        self._source_catalog: list[dict[str, str]] = []
        self._source_catalog_notebook_id = ""
        self._available_source_list: tk.Listbox | None = None
        self._selected_source_list: tk.Listbox | None = None
        self._available_source_rows: list[dict[str, str]] = []
        self._selected_source_rows: list[dict[str, str]] = []
        self._last_listed_source_ids: list[str] = []
        self._notebook_locked = tk.BooleanVar(value=False)
        self._sources_locked = tk.BooleanVar(value=False)
        self._notebook_lock_btn: tk.Button | None = None
        self._sources_lock_btn: tk.Button | None = None
        self._concepts_text: tk.Text | None = None
        self._concepts_loaded_path: Path | None = None
        self._concepts_tab_index: int | None = None
        self._hub_title = tk.StringVar(value="NotebookLM Study Hub")
        self._port = tk.IntVar(value=8000)
        self._venv_python = tk.StringVar(
            value=saved.get(
                "venv_python", sys.executable if not getattr(sys, "frozen", False) else ""
            )
        )
        self._active_profile_path: Path | None = None
        self._active_profile_name = tk.StringVar(value="Session only")
        self._venv_python.trace_add("write", lambda *_: self._persist_settings())
        self._limit_c = tk.StringVar(value="")
        self._limit_p = tk.StringVar(value="")
        self._overwrite = tk.BooleanVar(value=False)
        self._dry_run = tk.BooleanVar(value=False)

        # Trace any settings variable change → auto-save
        for var in (
            self._nlm_root,
            self._notebook_id,
            self._prompt_set_name,
            self._prompts_dir,
            self._collection_name,
            self._output_dir,
            self._site_dir,
            self._hub_title,
            self._port,
        ):
            var.trace_add("write", lambda *_: self._persist_settings())

        # Process handles
        self._server_proc: subprocess.Popen | None = None
        self._nlm_proc: subprocess.Popen | None = None
        self._server_running = False
        self._profile_menu_after_id: str | None = None
        self._syncing_site_dir = False

        self._output_dir.trace_add("write", lambda *_: self._sync_site_dir_from_output())
        self._nlm_root.trace_add("write", lambda *_: self._sync_site_dir_from_output())
        self._notebook_id.trace_add("write", lambda *_: self._on_notebook_id_changed())

        self._build_ui()
        self._poll_status()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(860, max(720, screen_width - 80))
        height = min(880, max(560, screen_height - 80))
        self.geometry(f"{width}x{height}")
        self.minsize(700, 500)

    # ── Persist ────────────────────────────────────────────────────────────────

    def _persist_settings(self) -> None:
        save_settings(
            {
                "nlm_root": self._nlm_root.get(),
                "prompt_set_name": self._prompt_set_name.get(),
                "prompts_dir": self._prompts_dir.get(),
                "collection_name": self._collection_name.get(),
                "output_dir": self._output_dir.get(),
                "site_dir": self._site_dir.get(),
                "hub_title": self._hub_title.get(),
                "port": self._port.get(),
                "venv_python": self._venv_python.get(),
                "active_profile": str(self._active_profile_path) if self._active_profile_path else "",
                "notebook_id": self._notebook_id.get(),
                "notebook_catalog": self._notebook_catalog,
                "source_ids_text": self._get_source_ids_text(),
                "source_catalog": self._source_catalog,
                "source_catalog_notebook_id": self._source_catalog_notebook_id,
                "notebook_locked": self._notebook_locked.get(),
                "sources_locked": self._sources_locked.get(),
            }
        )

    # ── Python helper ──────────────────────────────────────────────────────────

    def _get_python(self) -> str:
        """Return the python executable for subprocess calls."""
        venv = self._venv_python.get().strip()
        if venv and Path(venv).exists():
            return venv
        if not getattr(sys, "frozen", False):
            return sys.executable
        return "python"  # last resort: PATH

    def _update_python_label(self) -> None:
        p = self._venv_python.get().strip()
        if p and Path(p).exists():
            self._python_status.config(text=f"Found: {p}", fg=GREEN_L)
        elif p:
            self._python_status.config(text=f"Not found: {p}", fg="#f85149")
        else:
            self._python_status.config(text="Not set — will use system Python", fg=YELLOW)

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        hdr = tk.Frame(self, bg=SURFACE, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Study Hub - Pipeline Launcher", bg=SURFACE, fg=TEXT, font=F_H).pack()
        tk.Label(
            hdr,
            text="NotebookLM automation  ->  Site build  ->  AI tutor",
            bg=SURFACE,
            fg=MUTED,
            font=F_UI,
        ).pack()
        self._profile_lbl = tk.Label(
            hdr,
            text="",
            bg=SURFACE,
            fg=MUTED,
            font=F_UI,
        )
        self._profile_lbl.pack()
        self._update_profile_label()

        self._status = StatusBar(self, ["Ollama", "Tutor Server", "Auth Saved", "Site Built"])
        self._status.pack(fill="x")

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=[14, 6], font=F_UI
        )
        style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", TEXT)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self._notebook = nb
        self._menu_tab_index = 0
        self._last_real_tab_index = 1

        menu_tab = tk.Frame(nb, bg=BG)
        nb.add(menu_tab, text="  ☰  ")

        for label, builder in [
            ("  NotebookLM  ", self._build_nlm_tab),
            ("  Build Hub  ", self._build_hub_tab),
            ("  Concepts  ", self._build_concepts_tab),
            ("  AI Tutor  ", self._build_tutor_tab),
            ("  Settings  ", self._build_settings_tab),
        ]:
            f = tk.Frame(nb, bg=BG)
            nb.add(f, text=label)
            if label.strip() == "Concepts":
                self._concepts_tab_index = nb.index("end") - 1
            builder(self._make_scrollable_tab(f))

        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        nb.select(self._last_real_tab_index)

    def _make_scrollable_tab(self, parent: tk.Widget) -> tk.Frame:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_canvas_resize(event) -> None:
            canvas.itemconfig(inner_id, width=event.width)

        def on_frame_resize(_event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _find_scrollable(widget: tk.Misc) -> tk.Misc:
            """Walk up the widget tree to find the first scrollable widget."""
            w: tk.Misc | None = widget
            while w is not None:
                if isinstance(w, (tk.Listbox, tk.Text, tk.Canvas)):
                    return w
                w = getattr(w, "master", None)
            return canvas

        def on_mousewheel(event: tk.Event) -> None:  # type: ignore[type-arg]
            target = self.winfo_containing(event.x_root, event.y_root)  # type: ignore[arg-type]
            scrollable = _find_scrollable(target) if target is not None else canvas
            delta: int = getattr(event, "delta", 0) or 0
            if delta:
                scrollable.yview_scroll(int(-1 * (delta / 120)), "units")  # type: ignore[attr-defined]
            elif getattr(event, "num", None) == 4:
                scrollable.yview_scroll(-1, "units")  # type: ignore[attr-defined]
            elif getattr(event, "num", None) == 5:
                scrollable.yview_scroll(1, "units")  # type: ignore[attr-defined]

        def bind_mousewheel(_event) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", on_mousewheel)
            canvas.bind_all("<Button-5>", on_mousewheel)

        def unbind_mousewheel(_event) -> None:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Configure>", on_canvas_resize)
        inner.bind("<Configure>", on_frame_resize)
        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)

        return inner

    def _section(self, parent: tk.Widget, title: str) -> tk.Frame:
        tk.Label(parent, text=title, bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
            fill="x", padx=16, pady=(12, 2)
        )
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))
        inner = tk.Frame(parent, bg=BG)
        inner.pack(fill="x", padx=16)
        return inner

    def _update_profile_label(self) -> None:
        text = (
            f"Profile: {self._active_profile_name.get()}"
            if self._active_profile_path
            else "Profile: Session only"
        )
        self._profile_lbl.config(text=text)

    def _set_active_profile(self, profile_path: Path | None) -> None:
        self._active_profile_path = profile_path
        self._active_profile_name.set(profile_path.stem if profile_path else "Session only")
        self._update_profile_label()
        self._persist_settings()

    def _profile_payload(self) -> dict:
        return {
            "version": 1,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "settings": {
                "nlm_root": self._nlm_root.get(),
                "notebook_id": self._notebook_id.get(),
                "notebook_catalog": self._notebook_catalog,
                "prompt_set_name": self._prompt_set_name.get(),
                "prompts_dir": self._prompts_dir.get(),
                "source_ids_text": self._get_source_ids_text(),
                "source_catalog": self._source_catalog,
                "source_catalog_notebook_id": self._source_catalog_notebook_id,
                "collection_name": self._collection_name.get(),
                "output_dir": self._output_dir.get(),
                "site_dir": self._site_dir.get(),
                "hub_title": self._hub_title.get(),
                "port": self._port.get(),
                "venv_python": self._venv_python.get(),
                "limit_concepts": self._limit_c.get(),
                "limit_prompts": self._limit_p.get(),
                "overwrite": self._overwrite.get(),
                "dry_run": self._dry_run.get(),
                "notebook_locked": self._notebook_locked.get(),
                "sources_locked": self._sources_locked.get(),
            },
        }

    def _get_source_ids_text(self) -> str:
        if self._source_ids_editor is not None:
            return self._source_ids_editor.get("1.0", "end-1c")
        return self._source_ids_text

    def _set_source_ids_text(self, value: str) -> None:
        self._source_ids_text = value
        if self._source_ids_editor is not None:
            self._source_ids_editor.delete("1.0", "end")
            self._source_ids_editor.insert("1.0", value)
            self._source_ids_editor.edit_modified(False)
        self._refresh_source_lists()

    def _on_source_ids_modified(self, _event=None) -> None:
        if self._source_ids_editor is None or not self._source_ids_editor.edit_modified():
            return

        self._source_ids_text = self._source_ids_editor.get("1.0", "end-1c")
        self._source_ids_editor.edit_modified(False)
        self._refresh_source_lists()
        self._persist_settings()

    def _toggle_notebook_lock(self) -> None:
        self._notebook_locked.set(not self._notebook_locked.get())
        self._update_lock_buttons()
        self._persist_settings()

    def _toggle_sources_lock(self) -> None:
        self._sources_locked.set(not self._sources_locked.get())
        self._update_lock_buttons()
        self._persist_settings()

    def _update_lock_buttons(self) -> None:
        if self._notebook_lock_btn is not None:
            self._notebook_lock_btn.config(
                text="🔒" if self._notebook_locked.get() else "🔓"
            )
        if self._sources_lock_btn is not None:
            self._sources_lock_btn.config(
                text="🔒" if self._sources_locked.get() else "🔓"
            )

    def _format_source_row(self, source: dict[str, str]) -> str:
        title = source.get("title") or "(Untitled source)"
        kind = source.get("kind") or "unknown"
        return f"{title} [{kind}] | {source.get('id', '')}"

    def _format_notebook_row(self, notebook: dict[str, str]) -> str:
        title = notebook.get("title") or "(Untitled notebook)"
        return f"{title} | {notebook.get('id', '')}"

    def _on_notebook_id_changed(self) -> None:
        current_id = normalize_notebook_id(self._notebook_id.get())
        catalog_notebook_id = normalize_notebook_id(self._source_catalog_notebook_id)
        if not current_id or current_id != catalog_notebook_id:
            self._last_listed_source_ids = []
        else:
            self._last_listed_source_ids = [
                source["id"] for source in self._source_catalog if source.get("id")
            ]

        self._refresh_notebook_list()
        self._refresh_source_lists()

    def _refresh_notebook_list(self) -> None:
        if self._notebook_list is None:
            return

        self._notebook_rows = [row for row in self._notebook_catalog if row.get("id")]
        self._notebook_list.delete(0, "end")
        for notebook in self._notebook_rows:
            self._notebook_list.insert("end", self._format_notebook_row(notebook))

        current_id = normalize_notebook_id(self._notebook_id.get())
        if not current_id:
            return

        for index, notebook in enumerate(self._notebook_rows):
            if normalize_notebook_id(notebook.get("id")) == current_id:
                self._notebook_list.selection_clear(0, "end")
                self._notebook_list.selection_set(index)
                self._notebook_list.see(index)
                break

    def _current_selected_source_ids(self) -> list[str]:
        return parse_source_ids(self._get_source_ids_text())

    def _refresh_source_lists(self) -> None:
        if self._available_source_list is None or self._selected_source_list is None:
            return

        selected_ids = self._current_selected_source_ids()
        selected_set = set(selected_ids)
        current_notebook_id = normalize_notebook_id(self._notebook_id.get())
        catalog_notebook_id = normalize_notebook_id(self._source_catalog_notebook_id)
        matching_catalog = (
            self._source_catalog
            if current_notebook_id and catalog_notebook_id == current_notebook_id
            else []
        )
        catalog_by_id = {source["id"]: source for source in matching_catalog if source.get("id")}

        self._selected_source_rows = []
        for source_id in selected_ids:
            source = catalog_by_id.get(
                source_id,
                {"id": source_id, "title": "(Saved source)", "kind": "unknown"},
            )
            self._selected_source_rows.append(source)

        self._available_source_rows = [
            source for source in matching_catalog if source.get("id") not in selected_set
        ]

        self._available_source_list.delete(0, "end")
        for source in self._available_source_rows:
            self._available_source_list.insert("end", self._format_source_row(source))

        self._selected_source_list.delete(0, "end")
        for source in self._selected_source_rows:
            self._selected_source_list.insert("end", self._format_source_row(source))

    def _add_source_from_available(self, _event=None) -> None:
        if self._sources_locked.get():
            return
        if self._available_source_list is None:
            return

        selection = self._available_source_list.curselection()
        if not selection:
            return

        source = self._available_source_rows[selection[0]]
        selected_ids = self._current_selected_source_ids()
        if source["id"] not in selected_ids:
            selected_ids.append(source["id"])
            self._set_source_ids_text("\n".join(selected_ids))
            self._persist_settings()
        self._available_source_list.selection_clear(0, "end")

    def _remove_source_from_selected(self, _event=None) -> None:
        if self._sources_locked.get():
            return
        if self._selected_source_list is None:
            return

        selection = self._selected_source_list.curselection()
        if not selection:
            return

        source = self._selected_source_rows[selection[0]]
        selected_ids = [value for value in self._current_selected_source_ids() if value != source["id"]]
        self._set_source_ids_text("\n".join(selected_ids))
        self._persist_settings()
        self._selected_source_list.selection_clear(0, "end")

    def _apply_profile_payload(self, payload: dict) -> None:
        settings = payload.get("settings", payload)
        self._nlm_root.set(settings.get("nlm_root", self._nlm_root.get()))
        self._notebook_id.set(settings.get("notebook_id", self._notebook_id.get()))
        self._notebook_catalog = settings.get("notebook_catalog", self._notebook_catalog)
        self._prompt_set_name.set(settings.get("prompt_set_name", self._prompt_set_name.get()))
        self._prompts_dir.set(settings.get("prompts_dir", self._prompts_dir.get()))
        self._source_catalog = settings.get("source_catalog", self._source_catalog)
        self._source_catalog_notebook_id = settings.get(
            "source_catalog_notebook_id",
            self._source_catalog_notebook_id,
        )
        self._set_source_ids_text(settings.get("source_ids_text", self._get_source_ids_text()))
        self._collection_name.set(settings.get("collection_name", self._collection_name.get()))
        self._output_dir.set(settings.get("output_dir", self._output_dir.get()))
        self._sync_site_dir_from_output()
        self._hub_title.set(settings.get("hub_title", self._hub_title.get()))
        self._port.set(int(settings.get("port", self._port.get())))
        self._venv_python.set(settings.get("venv_python", self._venv_python.get()))
        self._limit_c.set(settings.get("limit_concepts", self._limit_c.get()))
        self._limit_p.set(settings.get("limit_prompts", self._limit_p.get()))
        self._overwrite.set(bool(settings.get("overwrite", self._overwrite.get())))
        self._dry_run.set(bool(settings.get("dry_run", self._dry_run.get())))
        self._notebook_locked.set(bool(settings.get("notebook_locked", self._notebook_locked.get())))
        self._sources_locked.set(bool(settings.get("sources_locked", self._sources_locked.get())))
        self._update_lock_buttons()
        self._ensure_concepts_tab_current(force=True)
        self._refresh_notebook_list()
        self._refresh_source_lists()

    def _show_profile_menu(self) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Save",
            command=self._save_profile,
            state="normal" if self._active_profile_path else "disabled",
        )
        menu.add_command(label="Save As...", command=self._save_profile_as)

        load_menu = tk.Menu(menu, tearoff=0)
        profile_paths = list_profile_paths()
        if profile_paths:
            for path in profile_paths:
                load_menu.add_command(
                    label=path.stem,
                    command=lambda selected_path=path: self._load_profile(selected_path),
                )
        else:
            load_menu.add_command(label="No saved configs", state="disabled")

        menu.add_cascade(label="Load", menu=load_menu)

        try:
            x, y, width, height = self._notebook.bbox(self._menu_tab_index)
            popup_x = self._notebook.winfo_rootx() + x + 10
            popup_y = self._notebook.winfo_rooty() + y + height + 8
            menu.tk_popup(
                popup_x,
                popup_y,
            )
        finally:
            menu.grab_release()

    def _on_tab_changed(self, _event=None) -> None:
        current_index = self._notebook.index(self._notebook.select())
        if current_index == self._menu_tab_index:
            if self._profile_menu_after_id:
                self.after_cancel(self._profile_menu_after_id)
            self._profile_menu_after_id = self.after(150, self._open_profile_menu_after_click)
            self.after_idle(lambda: self._notebook.select(self._last_real_tab_index))
            return

        self._last_real_tab_index = current_index
        if self._concepts_tab_index is not None and current_index == self._concepts_tab_index:
            self._ensure_concepts_tab_current()

    def _open_profile_menu_after_click(self) -> None:
        self._profile_menu_after_id = None
        self._show_profile_menu()

    def _save_profile(self) -> None:
        if not self._active_profile_path:
            self._save_profile_as()
            return

        self._write_profile(self._active_profile_path)

    def _save_profile_as(self) -> None:
        profile_name = simpledialog.askstring(
            "Save Config As",
            "Enter a config name:",
            initialvalue=self._active_profile_name.get() if self._active_profile_path else "",
            parent=self,
        )
        if profile_name is None:
            return

        safe_name = sanitize_folder_name(profile_name)
        if not safe_name:
            messagebox.showerror("Invalid name", "Please enter a valid config name.", parent=self)
            return

        profile_path = build_profile_path(safe_name)
        if profile_path.exists() and not messagebox.askyesno(
            "Overwrite config?",
            f"A config named '{safe_name}' already exists.\nOverwrite it?",
            parent=self,
        ):
            return

        self._write_profile(profile_path)

    def _write_profile(self, profile_path: Path) -> None:
        try:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            profile_path.write_text(
                json.dumps(self._profile_payload(), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror("Save failed", f"Could not save config:\n{exc}", parent=self)
            return

        self._set_active_profile(profile_path)
        log_box = getattr(self, "_nlm_log", None)
        if log_box is not None:
            log_box.log(f"Saved config profile: {profile_path}", "ok")

    def _load_profile(self, profile_path: Path) -> None:
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("Load failed", f"Could not load config:\n{exc}", parent=self)
            return

        self._apply_profile_payload(payload)
        self._set_active_profile(profile_path)
        log_box = getattr(self, "_nlm_log", None)
        if log_box is not None:
            log_box.log(f"Loaded config profile: {profile_path}", "ok")

    def _find_script(self, name: str) -> Path | None:
        """Search for a companion script in order of likely locations."""
        candidates = [
            EXE_DIR / name,  # dist/
            Path(self._nlm_root.get())
            / "src"
            / "notebooklm_automation"
            / name,  # src/notebooklm_automation/
            Path(self._nlm_root.get()) / "scripts" / name,  # scripts/
            Path(self._nlm_root.get()) / name,  # project root
            EXE_DIR.parent / name,  # one level above dist/
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    # ── Tab: NotebookLM ────────────────────────────────────────────────────────

    def _build_nlm_tab(self, tab: tk.Frame) -> None:
        auth = self._section(tab, "STEP 1 - LOGIN & SAVE AUTH STATE")
        tk.Label(
            auth,
            text=(
                "Opens a browser so you can log into NotebookLM.\n"
                "After logging in, close the browser — the session is saved automatically."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        row1 = tk.Frame(auth, bg=BG)
        row1.pack(anchor="w", pady=(0, 4))
        ActionBtn(row1, "Login to NotebookLM", BLUE, self._nlm_login).pack(side="left", padx=(0, 8))
        ActionBtn(row1, "Check Auth State", SURFACE2, self._nlm_check_auth).pack(side="left")

        self._auth_lbl = tk.Label(auth, text="", bg=BG, fg=MUTED, font=F_UI)
        self._auth_lbl.pack(anchor="w", pady=(4, 0))

        notebook_sec = self._section(tab, "STEP 1.5 - NOTEBOOK DETAILS")
        tk.Label(
            notebook_sec,
            text=(
                "Each saved launcher profile can carry its own NotebookLM notebook ID and source IDs.\n"
                "Click 'List Notebooks' to discover your notebooks from saved auth, then click one to set its ID."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        Field(notebook_sec, "Notebook ID:", self._notebook_id, width=44).pack(anchor="w", pady=2)

        notebook_btn_row = tk.Frame(notebook_sec, bg=BG)
        notebook_btn_row.pack(anchor="w", pady=(6, 8))
        ActionBtn(
            notebook_btn_row,
            "List Notebooks",
            SURFACE2,
            self._list_notebooks,
        ).pack(side="left", padx=(0, 8))
        ActionBtn(
            notebook_btn_row,
            "List Sources",
            SURFACE2,
            self._list_sources_for_notebook,
        ).pack(side="left", padx=(0, 8))
        ActionBtn(
            notebook_btn_row,
            "Use All Listed IDs",
            SURFACE2,
            self._use_last_listed_source_ids,
        ).pack(side="left")

        notebook_list_frame = tk.Frame(notebook_sec, bg=BG)
        notebook_list_frame.pack(fill="both", pady=(0, 10))
        notebook_list_hdr = tk.Frame(notebook_list_frame, bg=BG)
        notebook_list_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(
            notebook_list_hdr,
            text="Available Notebooks",
            bg=BG,
            fg=MUTED,
            font=F_UI,
            anchor="w",
        ).pack(side="left")
        self._notebook_lock_btn = tk.Button(
            notebook_list_hdr,
            text="🔒" if self._notebook_locked.get() else "🔓",
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=F_UI,
            command=self._toggle_notebook_lock,
        )
        self._notebook_lock_btn.pack(side="right")
        notebook_list = build_scrolling_listbox(notebook_list_frame, height=6)
        notebook_list.bind("<ButtonRelease-1>", self._select_notebook_from_list)
        self._notebook_list = notebook_list
        self._refresh_notebook_list()

        lists = tk.Frame(notebook_sec, bg=BG)
        lists.pack(fill="x", pady=(4, 6))

        available_frame = tk.Frame(lists, bg=BG)
        available_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))
        sources_hdr = tk.Frame(available_frame, bg=BG)
        sources_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(
            sources_hdr,
            text="Not Added",
            bg=BG,
            fg=MUTED,
            font=F_UI,
            anchor="w",
        ).pack(side="left")
        self._sources_lock_btn = tk.Button(
            sources_hdr,
            text="🔒" if self._sources_locked.get() else "🔓",
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=F_UI,
            command=self._toggle_sources_lock,
        )
        self._sources_lock_btn.pack(side="right")
        available_list = build_scrolling_listbox(available_frame, height=8)
        available_list.bind("<ButtonRelease-1>", self._add_source_from_available)
        self._available_source_list = available_list

        added_frame = tk.Frame(lists, bg=BG)
        added_frame.pack(side="left", fill="both", expand=True)
        tk.Label(
            added_frame,
            text="Added",
            bg=BG,
            fg=MUTED,
            font=F_UI,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        selected_list = build_scrolling_listbox(added_frame, height=8)
        selected_list.bind("<ButtonRelease-1>", self._remove_source_from_selected)
        self._selected_source_list = selected_list
        self._refresh_source_lists()

        run_sec = self._section(
            tab,
            "STEP 2 - RUN AUTOMATION  (concepts.csv x prompts -> chosen markdown folder)",
        )
        Field(run_sec, "Limit concepts (blank = all):", self._limit_c, width=8).pack(
            anchor="w", pady=2
        )
        Field(run_sec, "Limit prompts  (blank = all):", self._limit_p, width=8).pack(
            anchor="w", pady=2
        )
        tk.Label(
            run_sec,
            text=(
                "Optional: set a prompt set name to route this run into project-root/prompts/<name>.\n"
                "Leave it blank to use project-root/prompts/default/."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(4, 6))
        Field(run_sec, "Prompt set name:", self._prompt_set_name, width=24).pack(anchor="w", pady=2)
        row_prompt_paths = tk.Frame(run_sec, bg=BG)
        row_prompt_paths.pack(anchor="w", pady=(2, 6))
        ActionBtn(
            row_prompt_paths,
            "Use/Create Prompt Folder",
            SURFACE2,
            self._apply_prompt_folder,
        ).pack(side="left", padx=(0, 8))
        Field(
            run_sec,
            "Prompt input folder:",
            self._prompts_dir,
            browse=True,
            browse_start=lambda: self._nlm_root_path() / "prompts",
            prefer_browse_start=True,
            on_select=lambda p: print(f"success: prompt input folder changed to {p}"),
        ).pack(anchor="w", pady=2)
        tk.Label(
            run_sec,
            text=(
                "Optional: set a course / collection name to route this run into\n"
                "project-root/output/<name>, where both the markdown and HTML files will live."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(4, 6))
        Field(run_sec, "Course / collection name:", self._collection_name, width=24).pack(
            anchor="w", pady=2
        )
        row_paths = tk.Frame(run_sec, bg=BG)
        row_paths.pack(anchor="w", pady=(2, 6))
        ActionBtn(
            row_paths,
            "Use/Create Course Folder",
            SURFACE2,
            self._apply_collection_folder,
        ).pack(side="left", padx=(0, 8))
        Field(
            run_sec,
            "Markdown output folder:",
            self._output_dir,
            browse=True,
            browse_start=lambda: self._nlm_root_path() / "output",
            prefer_browse_start=True,
            on_select=lambda p: print(f"success: markdown output folder changed to {p}"),
        ).pack(anchor="w", pady=2)

        flags = tk.Frame(run_sec, bg=BG)
        flags.pack(anchor="w", pady=6)
        for text, var in [
            ("Overwrite existing files", self._overwrite),
            ("Dry run (preview only)", self._dry_run),
        ]:
            tk.Checkbutton(
                flags,
                text=text,
                variable=var,
                bg=BG,
                fg=TEXT,
                selectcolor=SURFACE2,
                activebackground=BG,
                font=F_UI,
            ).pack(side="left", padx=(0, 20))

        row2 = tk.Frame(run_sec, bg=BG)
        row2.pack(anchor="w", pady=(0, 8))
        ActionBtn(row2, "Run Automation", GREEN_L, self._nlm_run).pack(side="left", padx=(0, 8))
        ActionBtn(row2, "Stop", RED, self._nlm_stop).pack(side="left", padx=(0, 8))
        ActionBtn(row2, "Open Prompt Folder", SURFACE2, self._open_prompts).pack(
            side="left", padx=(0, 8)
        )
        ActionBtn(row2, "Open Output Folder", SURFACE2, self._open_output).pack(side="left")

        tk.Label(tab, text="  AUTOMATION LOG", bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
            fill="x", padx=16, pady=(10, 2)
        )
        self._nlm_log = LogBox(tab, height=22)
        self._nlm_log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    # ── Tab: Build Hub ─────────────────────────────────────────────────────────

    def _build_hub_tab(self, tab: tk.Frame) -> None:
        sec = self._section(tab, "STEP 3 - BUILD HTML STUDY HUB")
        tk.Label(
            sec,
            text=(
                "Converts markdown files from the selected folder into a browseable HTML hub.\n"
                "The HTML files are written into that same output folder so each notebook stays self-contained."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        Field(
            sec,
            "Markdown input folder:",
            self._output_dir,
            browse=True,
            browse_start=lambda: self._nlm_root_path() / "output",
            prefer_browse_start=True,
        ).pack(anchor="w", pady=2)
        Field(
            sec,
            "HTML site output folder:",
            self._site_dir,
            browse=True,
            browse_start=lambda: self._nlm_root_path() / "output",
            prefer_browse_start=True,
        ).pack(anchor="w", pady=2)
        Field(sec, "Hub page title:", self._hub_title, width=36).pack(anchor="w", pady=2)
        Field(sec, "Tutor server port:", self._port, width=8).pack(anchor="w", pady=2)

        row = tk.Frame(sec, bg=BG)
        row.pack(anchor="w", pady=(10, 0))
        ActionBtn(row, "Build Site", BLUE, self._build_site).pack(side="left", padx=(0, 8))
        ActionBtn(row, "Open Hub", PURPLE, self._open_hub).pack(side="left", padx=(0, 8))
        ActionBtn(row, "Open Site Folder", SURFACE2, self._open_site_folder).pack(side="left")

        tk.Label(tab, text="  BUILD LOG", bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
            fill="x", padx=16, pady=(14, 2)
        )
        self._build_log = LogBox(tab, height=18)
        self._build_log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    # ── Tab: Concepts CSV ──────────────────────────────────────────────────────

    def _build_concepts_tab(self, tab: tk.Frame) -> None:
        sec = self._section(tab, "CONCEPTS  (current notebook folder/concepts.csv)")
        tk.Label(
            sec,
            text=(
                "Each notebook folder keeps its own concepts.csv beside its markdown and HTML files.\n"
                "Edit here and click Save, or use Open in Editor for a full CSV editor."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        btn_row = tk.Frame(sec, bg=BG)
        btn_row.pack(anchor="w", pady=(0, 8))
        ActionBtn(btn_row, "Reload", SURFACE2, self._concepts_reload).pack(side="left", padx=(0, 8))
        ActionBtn(btn_row, "Save", GREEN_L, self._concepts_save).pack(side="left", padx=(0, 8))
        ActionBtn(btn_row, "Open in Editor", SURFACE2, self._concepts_open_editor).pack(side="left")

        self._concepts_status = tk.Label(sec, text="", bg=BG, fg=MUTED, font=F_UI)
        self._concepts_status.pack(anchor="w", pady=(0, 4))

        # Header row label
        tk.Label(tab, text="  concept", bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
            fill="x", padx=16, pady=(4, 0)
        )

        # Editable text area
        editor_frame = tk.Frame(tab, bg=BORDER, padx=1, pady=1)
        editor_frame.pack(fill="both", expand=True, padx=16, pady=(2, 12))

        self._concepts_text = tk.Text(
            editor_frame,
            bg="#010409",
            fg=TEXT,
            insertbackground=TEXT,
            font=F_MONO,
            relief="flat",
            bd=0,
            wrap="none",
            undo=True,
        )
        scroll_y = tk.Scrollbar(editor_frame, orient="vertical", command=self._concepts_text.yview)
        scroll_x = tk.Scrollbar(
            editor_frame, orient="horizontal", command=self._concepts_text.xview
        )
        self._concepts_text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self._concepts_text.pack(fill="both", expand=True)

        # Load on first show
        self._concepts_reload()

    def _concepts_csv_path(self) -> Path:
        return self._current_concepts_csv_path()

    def _write_concepts_to_path(self, path: Path) -> tuple[int, str]:
        content = self._concepts_text.get("1.0", "end-1c") if self._concepts_text else "concept\n"
        if not content.startswith("concept"):
            content = "concept\n" + content
            if self._concepts_text is not None:
                self._concepts_text.delete("1.0", "end")
                self._concepts_text.insert("1.0", content)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        if self._concepts_text is not None:
            self._concepts_text.edit_modified(False)

        lines = [
            line for line in content.splitlines() if line.strip() and line.strip() != "concept"
        ]
        self._concepts_loaded_path = path
        return len(lines), content

    def _ensure_concepts_tab_current(self, force: bool = False) -> None:
        if self._concepts_text is None:
            return

        target_path = self._concepts_csv_path()
        if not force and self._concepts_loaded_path == target_path:
            return

        if (
            self._concepts_loaded_path is not None
            and self._concepts_loaded_path != target_path
            and self._concepts_text.edit_modified()
        ):
            try:
                count, _ = self._write_concepts_to_path(self._concepts_loaded_path)
                self._concepts_status.config(
                    text=f"Auto-saved {count} concepts to {self._concepts_loaded_path}",
                    fg=GREEN_L,
                )
            except Exception as exc:
                self._concepts_status.config(
                    text=f"Auto-save failed before switching notebooks: {exc}",
                    fg="#f85149",
                )
                return

        self._concepts_reload()

    def _concepts_reload(self) -> None:
        path = self._concepts_csv_path()
        self._concepts_text.delete("1.0", "end")
        if path.exists():
            self._concepts_text.insert("1.0", path.read_text(encoding="utf-8"))
            self._concepts_status.config(text=f"Loaded: {path}", fg=GREEN_L)
        else:
            # Show a starter template
            self._concepts_text.insert("1.0", "concept\n")
            self._concepts_status.config(
                text=f"File not found — will be created on Save: {path}", fg=YELLOW
            )
        self._concepts_loaded_path = path
        self._concepts_text.edit_modified(False)

    def _concepts_save(self) -> None:
        path = self._concepts_csv_path()
        try:
            concept_count, _ = self._write_concepts_to_path(path)
            self._concepts_status.config(
                text=f"Saved {concept_count} concepts to {path}",
                fg=GREEN_L,
            )
        except Exception as exc:
            self._concepts_status.config(text=f"Save failed: {exc}", fg="#f85149")

    def _concepts_open_editor(self) -> None:
        self._ensure_concepts_tab_current()
        path = self._concepts_csv_path()
        if not path.exists():
            self._concepts_save()

        if IS_WIN:
            # Try Notepad++ first, fall back to plain Notepad
            notepadpp_candidates = [
                Path(os.environ.get("ProgramFiles", "C:/Program Files"))
                / "Notepad++"
                / "notepad++.exe",
                Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
                / "Notepad++"
                / "notepad++.exe",
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "Programs"
                / "Notepad++"
                / "notepad++.exe",
            ]
            editor = next((str(p) for p in notepadpp_candidates if p.exists()), "notepad.exe")
            subprocess.Popen([editor, str(path)])
        else:
            open_path(str(path))  # uses xdg-open / open on Linux/Mac

    # ── Tab: AI Tutor ──────────────────────────────────────────────────────────

    def _build_tutor_tab(self, tab: tk.Frame) -> None:
        oll = self._section(tab, "OLLAMA")
        row1 = tk.Frame(oll, bg=BG)
        row1.pack(anchor="w", pady=(0, 6))
        ActionBtn(row1, "Start Ollama", SURFACE2, self._start_ollama).pack(side="left", padx=(0, 6))
        ActionBtn(
            row1, "Pull deepseek-r1:1.5b", SURFACE2, lambda: self._pull_model("deepseek-r1:1.5b")
        ).pack(side="left", padx=(0, 6))
        ActionBtn(
            row1, "Pull deepseek-r1:8b", SURFACE2, lambda: self._pull_model("deepseek-r1:8b")
        ).pack(side="left")

        srv = self._section(tab, "TUTOR SERVER  (tutor_server.py via uvicorn)")
        row2 = tk.Frame(srv, bg=BG)
        row2.pack(anchor="w", pady=(0, 6))
        ActionBtn(row2, "Start Server", GREEN_L, self._start_server).pack(side="left", padx=(0, 8))
        ActionBtn(row2, "Stop Server", RED, self._stop_server).pack(side="left")

        tk.Label(tab, text="  SERVER / OLLAMA LOG", bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
            fill="x", padx=16, pady=(14, 2)
        )
        self._tutor_log = LogBox(tab, height=22)
        self._tutor_log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    # ── Tab: Settings ──────────────────────────────────────────────────────────

    def _build_settings_tab(self, tab: tk.Frame) -> None:
        # Launcher settings info
        info = self._section(tab, "LAUNCHER SETTINGS")
        tk.Label(
            info,
            text=f"Settings are auto-saved to:\n{SETTINGS_FILE}",
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        # Python / venv
        python_sec = self._section(tab, "PYTHON / VIRTUAL ENVIRONMENT")
        tk.Label(
            python_sec,
            text=(
                "Point this to the python.exe inside your virtual environment.\n"
                "This is the Python that will run the automation, tutor server, and login."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        python_row = tk.Frame(python_sec, bg=BG)
        python_row.pack(anchor="w", pady=(0, 4))
        tk.Label(
            python_row, text="Python executable:", bg=BG, fg=MUTED, font=F_UI, width=26, anchor="w"
        ).pack(side="left")
        tk.Entry(
            python_row,
            textvariable=self._venv_python,
            bg=SURFACE2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=4,
            font=F_MONO,
            width=44,
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            python_row,
            text="Browse...",
            bg=SURFACE2,
            fg=TEXT,
            activebackground=BORDER,
            relief="flat",
            bd=0,
            padx=6,
            cursor="hand2",
            font=F_UI,
            command=lambda: self._venv_python.set(
                filedialog.askopenfilename(
                    title="Select python.exe",
                    filetypes=[
                        ("Python executable", "python.exe python python3 python3.*"),
                        ("All files", "*.*"),
                    ],
                )
                or self._venv_python.get()
            ),
        ).pack(side="left")

        self._python_status = tk.Label(python_sec, text="", bg=BG, fg=MUTED, font=F_MONO)
        self._python_status.pack(anchor="w", pady=(4, 0))
        self._venv_python.trace_add("write", lambda *_: self._update_python_label())
        self._update_python_label()

        notebook_cfg = self._section(tab, "NOTEBOOK CONFIG")
        tk.Label(
            notebook_cfg,
            text=(
                "These values are saved with your launcher profile so each NotebookLM notebook\n"
                "can keep its own notebook ID and source set."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        Field(notebook_cfg, "Notebook ID:", self._notebook_id, width=44).pack(anchor="w", pady=3)

        # Project paths
        paths = self._section(tab, "PROJECT PATHS")
        Field(
            paths, "Project root (notebooklm-automated):", self._nlm_root, browse=True, width=44
        ).pack(anchor="w", pady=3)
        tk.Label(
            paths,
            text=(
                "Optional: keep prompt variations in subfolders under prompts/.\n"
                "This lets each run choose a different input prompt set."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(4, 6))
        Field(paths, "Prompt set name:", self._prompt_set_name, width=44).pack(anchor="w", pady=3)
        ActionBtn(paths, "Use/Create Prompt Folder", SURFACE2, self._apply_prompt_folder).pack(
            anchor="w", pady=(2, 8)
        )
        Field(
            paths,
            "Prompt input folder:",
            self._prompts_dir,
            browse=True,
            browse_start=lambda: self._nlm_root_path() / "prompts",
            prefer_browse_start=True,
            width=44,
        ).pack(
            anchor="w", pady=3
        )
        tk.Label(
            paths,
            text=(
                "Optional: keep each class or program in its own subfolder.\n"
                "This will set the notebook's working folder where markdown and HTML files both live."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(4, 6))
        Field(paths, "Course / collection name:", self._collection_name, width=44).pack(
            anchor="w", pady=3
        )
        ActionBtn(paths, "Use/Create Course Folder", SURFACE2, self._apply_collection_folder).pack(
            anchor="w", pady=(2, 8)
        )
        Field(
            paths,
            "Markdown output folder:",
            self._output_dir,
            browse=True,
            browse_start=lambda: self._nlm_root_path() / "output",
            prefer_browse_start=True,
            width=44,
        ).pack(
            anchor="w", pady=3
        )
        Field(
            paths,
            "HTML site folder:",
            self._site_dir,
            browse=True,
            browse_start=lambda: self._nlm_root_path() / "output",
            prefer_browse_start=True,
            width=44,
        ).pack(
            anchor="w", pady=3
        )

        # .env
        env_sec = self._section(tab, ".ENV FILE")
        tk.Label(
            env_sec,
            text=(
                "The automation reads DEFAULT_NOTEBOOK_ID, SOURCE_IDS, AUTH_STORAGE_PATH etc.\n"
                "from the .env file in your project root folder."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        self._env_path_lbl = tk.Label(env_sec, text="", bg=BG, fg=MUTED, font=F_MONO)
        self._env_path_lbl.pack(anchor="w", pady=(0, 6))
        self._update_env_label()
        self._nlm_root.trace_add("write", lambda *_: self._update_env_label())
        ActionBtn(env_sec, "Open .env", SURFACE2, self._open_env).pack(anchor="w")

        # Build command
        dep_sec = self._section(tab, "BUILD COMMAND  (run inside your virtual environment)")
        tk.Label(
            dep_sec,
            text=(
                "Activate your venv first, then build. The exe packages the launcher UI only.\n"
                "Your venv Python (set above) handles the automation and server at runtime."
            ),
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        for cmd in [
            "# From your project root, with venv active:",
            "pip install pyinstaller",
            "pyinstaller --onefile --windowed"
            ' --add-data "src/notebooklm_automation/build_study_hub.py;."'
            ' --add-data "src/notebooklm_automation/tutor_server.py;."'
            ' --add-data "scripts/list_sources.py;."'
            ' --add-data "scripts/list_notebooks.py;."'
            " src/notebooklm_automation/launcher.py",
            "# Then set Python executable in Settings to your venv python.exe",
        ]:
            tk.Label(
                dep_sec,
                text=f"   {cmd}",
                bg=SURFACE2,
                fg="#79c0ff",
                font=F_MONO,
                anchor="w",
                pady=3,
            ).pack(fill="x", pady=2)

        # Bottom padding so last item isn't flush against the edge
        tk.Frame(tab, bg=BG, height=20).pack()

    def _update_env_label(self) -> None:
        env = Path(self._nlm_root.get()) / ".env"
        exists = "exists" if env.exists() else "not found"
        self._env_path_lbl.config(
            text=str(env) + f"  [{exists}]",
            fg=GREEN_L if env.exists() else "#e3b341",
        )

    # ── Status polling ─────────────────────────────────────────────────────────

    def _poll_status(self) -> None:
        def loop() -> None:
            while True:
                ollama_ok = run_ollama_check()
                server_ok = (
                    self._server_running
                    and self._server_proc is not None
                    and self._server_proc.poll() is None
                )
                auth_path = self._current_auth_storage_path()
                auth_ok = auth_path.exists()
                site_ok = (self._current_site_dir() / "index.html").exists()
                self.after(0, self._apply_status, ollama_ok, server_ok, auth_ok, site_ok)
                time.sleep(4)

        threading.Thread(target=loop, daemon=True).start()

    def _apply_status(self, ollama: bool, server: bool, auth: bool, site: bool) -> None:
        self._status.set("Ollama", ollama)
        self._status.set("Tutor Server", server)
        self._status.set("Auth Saved", auth)
        self._status.set("Site Built", site)
        self._server_running = server

    # ── NotebookLM actions ─────────────────────────────────────────────────────

    def _nlm_root_path(self) -> Path:
        return Path(self._nlm_root.get())

    def _current_auth_storage_path(self) -> Path:
        return self._nlm_root_path() / ".notebooklm_state" / "storage_state.json"

    def _current_prompts_dir(self) -> Path:
        raw = self._prompts_dir.get().strip()
        return Path(raw) if raw else self._nlm_root_path() / "prompts" / "default"

    def _current_output_dir(self) -> Path:
        raw = self._output_dir.get().strip()
        return Path(raw) if raw else self._nlm_root_path() / "output"

    def _current_concepts_csv_path(self) -> Path:
        return self._current_output_dir() / "concepts.csv"

    def _current_site_dir(self) -> Path:
        raw = self._site_dir.get().strip()
        return Path(raw) if raw else build_site_dir_from_output(
            self._nlm_root_path(),
            self._current_output_dir(),
        )

    def _sync_site_dir_from_output(self) -> None:
        if self._syncing_site_dir:
            return

        self._syncing_site_dir = True
        try:
            derived_site_dir = build_site_dir_from_output(
                self._nlm_root_path(),
                self._current_output_dir(),
            )
            if self._site_dir.get().strip() != str(derived_site_dir):
                self._site_dir.set(str(derived_site_dir))
        finally:
            self._syncing_site_dir = False

    def _subprocess_run_options(self) -> dict:
        options = {
            "capture_output": True,
            "text": True,
        }
        if IS_WIN and hasattr(subprocess, "CREATE_NO_WINDOW"):
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        return options

    def _log_process_output(self, output: str, tag: str = "err") -> None:
        for line in output.splitlines():
            if line.strip():
                self._nlm_log.log(line, tag)

    def _apply_prompt_folder(self) -> None:
        root = self._nlm_root_path()
        if not root.exists():
            messagebox.showerror(
                "Project root not found",
                "Set the correct project root in Settings before choosing a prompt folder.",
            )
            return

        raw_name = self._prompt_set_name.get().strip()
        prompts_dir, folder_name = build_prompts_dir(root, raw_name)
        created = not prompts_dir.exists()
        prompts_dir.mkdir(parents=True, exist_ok=True)

        if raw_name and folder_name != raw_name:
            self._prompt_set_name.set(folder_name)

        self._prompts_dir.set(str(prompts_dir))

        if folder_name:
            message = f"Using prompt folder '{folder_name}' -> prompts: {prompts_dir}"
        else:
            message = f"Using default prompt folder -> prompts: {prompts_dir}"

        if created:
            message += " (created; add .txt prompt files before running)"

        log_box = getattr(self, "_nlm_log", None)
        if log_box is not None:
            log_box.log(message, "info")

    def _apply_collection_folder(self) -> None:
        root = self._nlm_root_path()
        if not root.exists():
            messagebox.showerror(
                "Project root not found",
                "Set the correct project root in Settings before creating a course folder.",
            )
            return

        raw_name = self._collection_name.get().strip()
        output_dir, site_dir, folder_name = build_pipeline_dirs(root, raw_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        site_dir.mkdir(parents=True, exist_ok=True)

        if raw_name and folder_name != raw_name:
            self._collection_name.set(folder_name)

        self._output_dir.set(str(output_dir))
        self._site_dir.set(str(site_dir))
        self._ensure_concepts_tab_current(force=True)

        if folder_name:
            message = (
                f"Using course folder '{folder_name}' -> notebook folder: {output_dir}"
            )
        else:
            message = f"Using shared notebook folder: {output_dir}"

        for attr_name, tag in (("_nlm_log", "ok"), ("_build_log", "info")):
            log_box = getattr(self, attr_name, None)
            if log_box is not None:
                log_box.log(message, tag)

    def _nlm_check_auth(self) -> None:
        auth = self._current_auth_storage_path()
        if not auth.exists():
            self._auth_lbl.config(text=f"Not found: {auth}", fg="#f85149")
            self._nlm_log.log(f"Auth file missing: {auth}", "err")
            self._nlm_log.log(
                "Run 'Login to NotebookLM' first, or check that Project Root is set correctly in Settings.",
                "warn",
            )
            return

        script = self._find_script("list_notebooks.py")
        if not script:
            self._auth_lbl.config(text=f"Auth file found: {auth}", fg=YELLOW)
            self._nlm_log.log(f"Auth state file exists at {auth}", "warn")
            self._nlm_log.log(
                "Could not validate auth because list_notebooks.py was not found.",
                "warn",
            )
            return

        self._auth_lbl.config(text="Checking NotebookLM auth...", fg=YELLOW)
        self._nlm_log.log("Validating NotebookLM auth against the API...", "info")
        cmd = [self._get_python(), str(script), "--json"]

        def run() -> None:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(self._nlm_root_path()),
                    **self._subprocess_run_options(),
                )
            except Exception as exc:
                message = f"Auth validation could not start: {exc}"
                self.after(
                    0,
                    lambda: (
                        self._auth_lbl.config(text="Auth check failed to run", fg="#f85149"),
                        self._nlm_log.log(message, "err"),
                    ),
                )
                return

            def apply_failure() -> None:
                self._auth_lbl.config(text="Auth invalid or expired", fg="#f85149")
                self._log_process_output(result.stdout + result.stderr, "err")
                self._nlm_log.log("NotebookLM auth is invalid or expired.", "err")
                self._nlm_log.log("Run 'Login to NotebookLM' again to refresh the session.", "warn")

            if result.returncode != 0:
                self.after(0, apply_failure)
                return

            try:
                notebooks = json.loads(result.stdout or "[]")
            except json.JSONDecodeError as exc:
                message = f"NotebookLM auth worked, but JSON parsing failed: {exc}"
                self.after(
                    0,
                    lambda: (
                        self._auth_lbl.config(text="Auth validated, but response parsing failed", fg=YELLOW),
                        self._nlm_log.log(message, "warn"),
                    ),
                )
                return

            def apply_success() -> None:
                self._auth_lbl.config(text=f"Auth valid: {auth}", fg=GREEN_L)
                self._notebook_catalog = notebooks
                self._refresh_notebook_list()
                self._persist_settings()
                self._nlm_log.log(
                    f"NotebookLM auth is valid. {len(notebooks)} notebooks are available.",
                    "ok",
                )

            self.after(0, apply_success)

        threading.Thread(target=run, daemon=True).start()

    def _select_notebook_from_list(self, _event=None) -> None:
        if self._notebook_locked.get():
            return
        if self._notebook_list is None:
            return

        selection = self._notebook_list.curselection()
        if not selection:
            return

        notebook = self._notebook_rows[selection[0]]
        notebook_id = normalize_notebook_id(notebook.get("id"))
        if not notebook_id:
            return

        self._notebook_id.set(notebook_id)
        self._refresh_source_lists()
        self._persist_settings()
        self._nlm_log.log(
            f"Selected notebook: {notebook.get('title') or '(Untitled notebook)'} ({notebook_id})",
            "ok",
        )
        self._notebook_list.selection_clear(0, "end")
        self._refresh_notebook_list()

    def _list_notebooks(self) -> None:
        script = self._find_script("list_notebooks.py")
        if not script:
            self._nlm_log.log(
                "list_notebooks.py not found. Checked: dist/, scripts/, src/notebooklm_automation/, project root.",
                "err",
            )
            return

        self._nlm_log.log("Listing NotebookLM notebooks from saved auth...", "info")
        cmd = [self._get_python(), str(script), "--json"]

        def run() -> None:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(self._nlm_root_path()),
                    **self._subprocess_run_options(),
                )
            except Exception as exc:
                message = f"Notebook listing could not start: {exc}"
                self.after(0, lambda: self._nlm_log.log(message, "err"))
                return

            if result.returncode != 0:
                def apply_failure() -> None:
                    self._log_process_output(result.stdout + result.stderr, "err")
                    self._nlm_log.log(f"Notebook listing failed (exit {result.returncode}).", "err")

                self.after(0, apply_failure)
                return

            try:
                notebooks = json.loads(result.stdout or "[]")
            except json.JSONDecodeError as exc:
                message = f"Could not parse notebook listing output: {exc}"
                self.after(
                    0,
                    lambda: self._nlm_log.log(message, "err"),
                )
                return

            def apply_results() -> None:
                self._notebook_catalog = notebooks
                self._refresh_notebook_list()
                self._persist_settings()

                if notebooks:
                    self._nlm_log.log(
                        f"Loaded {len(notebooks)} notebooks. Click one to set its notebook ID.",
                        "ok",
                    )
                else:
                    self._nlm_log.log("No notebooks were returned for this account.", "warn")

            self.after(0, apply_results)

        threading.Thread(target=run, daemon=True).start()

    def _list_sources_for_notebook(self) -> None:
        notebook_id = normalize_notebook_id(self._notebook_id.get())
        if not notebook_id:
            self._nlm_log.log("Notebook ID is required before listing sources.", "err")
            return
        self._notebook_id.set(notebook_id)

        script = self._find_script("list_sources.py")
        if not script:
            self._nlm_log.log(
                "list_sources.py not found. Checked: dist/, scripts/, src/notebooklm_automation/, project root.",
                "err",
            )
            return

        self._nlm_log.log(f"Listing sources for notebook: {notebook_id}", "info")
        cmd = [self._get_python(), str(script), "--notebook-id", notebook_id, "--json"]

        def run() -> None:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(self._nlm_root_path()),
                    **self._subprocess_run_options(),
                )
            except Exception as exc:
                message = f"Source listing could not start: {exc}"
                self.after(0, lambda: self._nlm_log.log(message, "err"))
                return

            if result.returncode != 0:
                def apply_failure() -> None:
                    self._log_process_output(result.stdout + result.stderr, "err")
                    self._nlm_log.log(f"Source listing failed (exit {result.returncode}).", "err")

                self.after(0, apply_failure)
                return

            try:
                sources = json.loads(result.stdout or "[]")
            except json.JSONDecodeError as exc:
                message = f"Could not parse source listing output: {exc}"
                self.after(
                    0,
                    lambda: self._nlm_log.log(message, "err"),
                )
                return

            def apply_results() -> None:
                self._source_catalog = sources
                self._source_catalog_notebook_id = notebook_id
                self._last_listed_source_ids = [source["id"] for source in sources if source.get("id")]
                self._refresh_source_lists()
                self._persist_settings()

                if sources:
                    self._nlm_log.log(
                        f"Loaded {len(sources)} sources. Click an item in 'Not Added' to include it in this notebook config.",
                        "ok",
                    )
                else:
                    self._nlm_log.log("No sources were returned for this notebook.", "warn")

            self.after(0, apply_results)

        threading.Thread(target=run, daemon=True).start()

    def _use_last_listed_source_ids(self) -> None:
        if not self._last_listed_source_ids:
            self._nlm_log.log("No listed sources available yet. Run 'List Sources' first.", "warn")
            return

        self._set_source_ids_text("\n".join(self._last_listed_source_ids))
        self._persist_settings()
        self._nlm_log.log(
            f"Loaded {len(self._last_listed_source_ids)} source IDs into this notebook config.",
            "ok",
        )

    def _nlm_login(self) -> None:
        root = self._nlm_root_path()
        if not root.exists():
            self._nlm_log.log(f"Project root not found: {root}", "err")
            self._nlm_log.log("Set the correct path in Settings first.", "warn")
            return

        python = self._get_python()
        auth_storage = self._current_auth_storage_path()
        auth_storage.parent.mkdir(parents=True, exist_ok=True)
        self._nlm_log.log(f"Project root: {root}", "dim")
        self._nlm_log.log(f"Auth will be saved to: {auth_storage}", "dim")
        self._nlm_log.log("Opening a terminal window for NotebookLM login...", "info")
        self._nlm_log.log("Complete the login in the terminal, then press ENTER there.", "dim")

        def run() -> None:
            try:
                if IS_WIN:
                    python_win = str(Path(python).resolve())  # normalize to backslashes
                    auth_win = str(auth_storage.resolve())
                    # cmd /k requires outer quotes wrapping the whole command when the path has inner quotes
                    inner = f'"{python_win}" -m notebooklm login --storage "{auth_win}"'
                    subprocess.Popen(
                        f'start "NotebookLM Login" cmd /k "{inner}"',
                        shell=True,
                        cwd=str(root),
                    )
                elif IS_MAC:
                    script = (
                        f'cd "{root}" && "{python}" -m notebooklm login'
                        f' --storage "{auth_storage}"'
                    )
                    subprocess.Popen(
                        ["osascript", "-e", f'tell app "Terminal" to do script "{script}"']
                    )
                else:
                    subprocess.Popen(
                        [
                            "x-terminal-emulator",
                            "-e",
                            (
                                f'bash -c \'cd "{root}" && "{python}" -m notebooklm login'
                                f' --storage "{auth_storage}"; read -p "Press ENTER to close"\' '
                            ),
                        ]
                    )
                self._nlm_log.log(
                    "Terminal opened. Complete login there, then click 'Check Auth State'.", "ok"
                )
            except Exception as exc:
                self._nlm_log.log(f"Could not open terminal: {exc}", "err")

        threading.Thread(target=run, daemon=True).start()

    def _nlm_run(self) -> None:
        if self._nlm_proc and self._nlm_proc.poll() is None:
            self._nlm_log.log("Automation is already running.", "warn")
            return

        root = self._nlm_root_path()
        cli = root / "src" / "notebooklm_automation" / "cli.py"
        if not cli.exists():
            cli = root / "cli.py"
        if not cli.exists():
            self._nlm_log.log(f"cli.py not found under {root}", "err")
            self._nlm_log.log("Check the Project Root path in Settings.", "warn")
            return

        prompts_dir = self._current_prompts_dir()
        if not prompts_dir.exists():
            self._nlm_log.log(f"Prompt folder not found: {prompts_dir}", "err")
            self._nlm_log.log(
                "Choose a valid prompt folder or use 'Use/Create Prompt Folder' first.",
                "warn",
            )
            return
        if not list(prompts_dir.glob("*.txt")):
            self._nlm_log.log(f"No .txt prompt files found in: {prompts_dir}", "err")
            self._nlm_log.log("Add prompt templates to that folder before running.", "warn")
            return

        output_dir = self._current_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        concepts_csv = self._concepts_csv_path()
        if self._concepts_text is not None and self._concepts_text.edit_modified():
            try:
                concept_count, _ = self._write_concepts_to_path(concepts_csv)
                self._concepts_status.config(
                    text=f"Auto-saved {concept_count} concepts to {concepts_csv}",
                    fg=GREEN_L,
                )
                self._nlm_log.log(f"Auto-saved concepts to {concepts_csv}", "info")
            except Exception as exc:
                self._nlm_log.log(f"Could not save concepts before running: {exc}", "err")
                return
        notebook_id = normalize_notebook_id(self._notebook_id.get())
        if notebook_id:
            self._notebook_id.set(notebook_id)
        source_ids = parse_source_ids(self._get_source_ids_text())

        cmd = [
            self._get_python(),
            str(cli),
            "--prompts-dir",
            str(prompts_dir),
            "--output-dir",
            str(output_dir),
            "--concepts-csv",
            str(concepts_csv),
        ]
        if notebook_id:
            cmd += ["--notebook-id", notebook_id]
        for source_id in source_ids:
            cmd += ["--source-id", source_id]
        lc = self._limit_c.get().strip()
        lp = self._limit_p.get().strip()
        if lc.isdigit():
            cmd += ["--limit-concepts", lc]
        if lp.isdigit():
            cmd += ["--limit-prompts", lp]
        if self._overwrite.get():
            cmd += ["--overwrite"]
        if self._dry_run.get():
            cmd += ["--dry-run"]

        self._nlm_log.clear()
        self._nlm_log.log("Command: " + " ".join(cmd), "dim")
        self._nlm_log.log("-" * 60, "dim")

        try:
            self._nlm_proc = subprocess.Popen(
                cmd,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WIN else 0,
            )
        except Exception as exc:
            self._nlm_log.log(f"Failed to start: {exc}", "err")
            return

        threading.Thread(target=self._tail_nlm, daemon=True).start()

    def _tail_nlm(self) -> None:
        if not self._nlm_proc:
            return
        for raw in self._nlm_proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            lo = line.lower()
            tag = (
                "ok"
                if "success" in lo
                else "err"
                if any(w in lo for w in ("error", "fail", "exception"))
                else "warn"
                if any(w in lo for w in ("skip", "warn"))
                else "hi"
                if ("concept" in lo and "/" in lo)
                else ""
            )
            self._nlm_log.log(line, tag)

        rc = self._nlm_proc.wait()
        self._nlm_log.log("-" * 60, "dim")
        if rc == 0:
            self._nlm_log.log("Automation finished successfully.", "ok")
        else:
            self._nlm_log.log(f"Automation exited with code {rc}.", "err")

    def _nlm_stop(self) -> None:
        if self._nlm_proc and self._nlm_proc.poll() is None:
            self._nlm_proc.terminate()
            self._nlm_log.log("Automation stopped.", "warn")
        else:
            self._nlm_log.log("Nothing running.", "dim")

    def _open_output(self) -> None:
        output_dir = self._current_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        open_path(str(output_dir))

    def _open_prompts(self) -> None:
        prompts_dir = self._current_prompts_dir()
        prompts_dir.mkdir(parents=True, exist_ok=True)
        open_path(str(prompts_dir))

    # ── Build Hub actions ──────────────────────────────────────────────────────

    def _build_site(self) -> None:
        self._sync_site_dir_from_output()
        s = self._find_script("build_study_hub.py")
        if not s:
            self._build_log.log(
                "build_study_hub.py not found. Checked: dist/, src/notebooklm_automation/, project root.",
                "err",
            )
            return
        self._build_log.clear()
        self._build_log.log("Building study hub...", "info")
        cmd = [
            self._get_python(),
            str(s),
            "--input",
            str(self._current_output_dir()),
            "--site-dir",
            str(self._current_site_dir()),
            "--title",
            self._hub_title.get(),
            "--tutor-port",
            str(self._port.get()),
        ]

        def run() -> None:
            result = subprocess.run(cmd, capture_output=True, text=True)
            for line in (result.stdout + result.stderr).splitlines():
                tag = "ok" if "built" in line.lower() else "err" if "error" in line.lower() else ""
                self._build_log.log(line, tag)
            self._build_log.log(
                "Site built successfully."
                if result.returncode == 0
                else f"Build failed (exit {result.returncode}).",
                "ok" if result.returncode == 0 else "err",
            )

        threading.Thread(target=run, daemon=True).start()

    def _open_hub(self) -> None:
        self._sync_site_dir_from_output()
        index = self._current_site_dir() / "index.html"
        if not index.exists():
            self._build_log.log("index.html not found — build the site first.", "warn")
            return
        open_path(str(index))
        self._build_log.log(f"Opened {index}", "ok")

    def _open_site_folder(self) -> None:
        self._sync_site_dir_from_output()
        site_dir = self._current_site_dir()
        site_dir.mkdir(parents=True, exist_ok=True)
        open_path(str(site_dir))

    # ── Tutor server actions ───────────────────────────────────────────────────

    def _start_server(self) -> None:
        if self._server_running:
            self._tutor_log.log("Server already running.", "warn")
            return
        s = self._find_script("tutor_server.py")
        if not s:
            self._tutor_log.log(
                "tutor_server.py not found. Checked: dist/, src/notebooklm_automation/, project root.",
                "err",
            )
            return
        port = self._port.get()
        self._tutor_log.log(f"Starting tutor server on port {port}...", "info")
        cmd = [
            self._get_python(),
            "-m",
            "uvicorn",
            "tutor_server:app",
            "--port",
            str(port),
            "--reload",
        ]
        try:
            self._server_proc = subprocess.Popen(
                cmd,
                cwd=str(s.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WIN else 0,
            )
            self._server_running = True
            self._tutor_log.log(f"Server started (pid {self._server_proc.pid})", "ok")
            threading.Thread(target=self._tail_server, daemon=True).start()
        except FileNotFoundError:
            self._tutor_log.log("uvicorn not found — run: pip install uvicorn fastapi httpx", "err")
        except Exception as exc:
            self._tutor_log.log(f"Error: {exc}", "err")

    def _tail_server(self) -> None:
        if not self._server_proc:
            return
        for raw in self._server_proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            lo = line.lower()
            tag = "err" if "error" in lo else "ok" if "started" in lo or "running" in lo else "dim"
            self._tutor_log.log(line, tag)
        self._server_running = False
        self._tutor_log.log("Server process ended.", "warn")

    def _stop_server(self) -> None:
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
            self._server_proc = None
            self._server_running = False
            self._tutor_log.log("Tutor server stopped.", "warn")
        else:
            self._tutor_log.log("No server running.", "dim")

    def _start_ollama(self) -> None:
        self._tutor_log.log("Starting Ollama in background...", "info")
        try:
            flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if IS_WIN else 0
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
            self._tutor_log.log("Ollama started silently in background.", "ok")
            self._launch_ollama_tray()
        except FileNotFoundError:
            self._tutor_log.log("Ollama not found. Download from https://ollama.com", "err")

    def _launch_ollama_tray(self) -> None:
        """Show a system tray icon for Ollama with a Stop option."""
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            self._tutor_log.log(
                "pystray/pillow not installed — no tray icon. Run: pip install pystray pillow",
                "warn",
            )
            return

        # Draw a simple coloured circle icon (32x32)
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, 30, 30], fill="#f59e0b")  # amber circle
        draw.ellipse([8, 8, 24, 24], fill="#0d1117")  # dark centre dot

        def stop_ollama(icon, item) -> None:
            icon.stop()
            if IS_WIN:
                subprocess.Popen(
                    ["taskkill", "/F", "/IM", "ollama.exe"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(["pkill", "-f", "ollama serve"])
            self._tutor_log.log("Ollama stopped via tray.", "warn")

        def open_launcher(icon, item) -> None:
            self.lift()
            self.focus_force()

        icon = pystray.Icon(
            "ollama",
            img,
            "Ollama (Study Hub)",
            menu=pystray.Menu(
                pystray.MenuItem("Study Hub Launcher", open_launcher, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Stop Ollama", stop_ollama),
            ),
        )

        # Run the tray icon in its own daemon thread so it doesn't block the UI
        threading.Thread(target=icon.run, daemon=True).start()
        self._tutor_log.log("Ollama tray icon active — right-click it to stop Ollama.", "ok")

    def _pull_model(self, model: str) -> None:
        self._tutor_log.log(f"Pulling {model} — this may take a while...", "info")

        def run() -> None:
            try:
                proc = subprocess.Popen(
                    ["ollama", "pull", model],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                for raw in proc.stdout:
                    line = raw.rstrip()
                    if line:
                        self._tutor_log.log(f"[ollama] {line}")
                proc.wait()
                self._tutor_log.log(
                    f"Pull complete: {model}" if proc.returncode == 0 else f"Pull failed: {model}",
                    "ok" if proc.returncode == 0 else "err",
                )
            except FileNotFoundError:
                self._tutor_log.log("Ollama not found in PATH.", "err")

        threading.Thread(target=run, daemon=True).start()

    # ── Settings actions ───────────────────────────────────────────────────────

    def _open_env(self) -> None:
        env = self._nlm_root_path() / ".env"
        if not env.exists():
            try:
                env.parent.mkdir(parents=True, exist_ok=True)
                env.write_text(
                    "DEFAULT_NOTEBOOK_ID=\n"
                    "SOURCE_IDS=\n"
                    "AUTH_STORAGE_PATH=.notebooklm_state/storage_state.json\n"
                    "CONCEPTS_CSV=output/concepts.csv\n"
                    "PROMPTS_DIR=prompts/default\n"
                    "OUTPUT_DIR=output\n"
                    "LOGS_DIR=logs\n"
                    "RETRIES=1\n"
                    "DELAY_SECONDS=2.0\n",
                    encoding="utf-8",
                )
                messagebox.showinfo(".env created", f"A template .env was created at:\n{env}")
            except Exception as exc:
                messagebox.showerror(
                    "Error",
                    f"Could not create .env:\n{exc}\n\n"
                    "Check that the Project Root path in Settings is correct.",
                )
                return
        self._update_env_label()
        open_path(str(env))

    # ── Quit ───────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        active = []
        if self._server_running:
            active.append("Tutor Server")
        if self._nlm_proc and self._nlm_proc.poll() is None:
            active.append("NotebookLM Automation")
        if active and not messagebox.askyesno(
            "Quit", f"{', '.join(active)} is still running.\nStop and quit?"
        ):
            return
        self._stop_server()
        self._nlm_stop()
        self.destroy()


# ── Entry ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = Launcher()
    app.protocol("WM_DELETE_WINDOW", app._on_close)
    app.mainloop()
