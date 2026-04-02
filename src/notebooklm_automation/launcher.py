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
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

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
        width: int = 36,
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
                command=lambda: var.set(filedialog.askdirectory() or var.get()),
            ).pack(side="left")


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

        # Load persisted settings, fall back to sensible defaults
        saved = load_settings()

        # ── Show setup wizard if critical settings are missing ─────────────────────
        needs_setup = (
            not saved.get("venv_python")
            or not Path(saved.get("venv_python", "")).exists()
            or not saved.get("nlm_root")
            or not Path(saved.get("nlm_root", "")).exists()
        )
        if needs_setup:
            # Temporarily show the root window so the wizard has a parent
            self.withdraw()
            wizard = SetupWizard(self, saved)
            self.wait_window(wizard)
            if wizard._cancelled or wizard.result is None:
                self.destroy()
                return
            # Merge wizard results into saved so the StringVars below pick them up
            saved.update(wizard.result)
            save_settings(saved)
            self.deiconify()

        self._nlm_root = tk.StringVar(value=saved.get("nlm_root", str(EXE_DIR)))
        self._output_dir = tk.StringVar(
            value=saved.get("output_dir", str(Path(saved.get("nlm_root", str(EXE_DIR))) / "output"))
        )
        self._site_dir = tk.StringVar(
            value=saved.get(
                "site_dir", str(Path(saved.get("nlm_root", str(EXE_DIR))) / "study_hub")
            )
        )
        self._hub_title = tk.StringVar(value=saved.get("hub_title", "NotebookLM Study Hub"))
        self._port = tk.IntVar(value=saved.get("port", 8000))
        self._venv_python = tk.StringVar(
            value=saved.get(
                "venv_python", sys.executable if not getattr(sys, "frozen", False) else ""
            )
        )
        self._venv_python.trace_add("write", lambda *_: self._persist_settings())
        self._limit_c = tk.StringVar(value="")
        self._limit_p = tk.StringVar(value="")
        self._overwrite = tk.BooleanVar(value=False)
        self._dry_run = tk.BooleanVar(value=False)

        # Trace any settings variable change → auto-save
        for var in (self._nlm_root, self._output_dir, self._site_dir, self._hub_title, self._port):
            var.trace_add("write", lambda *_: self._persist_settings())

        # Process handles
        self._server_proc: subprocess.Popen | None = None
        self._nlm_proc: subprocess.Popen | None = None
        self._server_running = False

        self._build_ui()
        self._poll_status()
        self.geometry("860x880")
        self.minsize(700, 620)

    # ── Persist ────────────────────────────────────────────────────────────────

    def _persist_settings(self) -> None:
        save_settings(
            {
                "nlm_root": self._nlm_root.get(),
                "output_dir": self._output_dir.get(),
                "site_dir": self._site_dir.get(),
                "hub_title": self._hub_title.get(),
                "port": self._port.get(),
                "venv_python": self._venv_python.get(),
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

        for label, builder in [
            ("  NotebookLM  ", self._build_nlm_tab),
            ("  Build Hub  ", self._build_hub_tab),
            ("  Concepts  ", self._build_concepts_tab),
            ("  AI Tutor  ", self._build_tutor_tab),
            ("  Settings  ", self._build_settings_tab),
        ]:
            f = tk.Frame(nb, bg=BG)
            nb.add(f, text=label)
            builder(f)

    def _section(self, parent: tk.Widget, title: str) -> tk.Frame:
        tk.Label(parent, text=title, bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
            fill="x", padx=16, pady=(12, 2)
        )
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))
        inner = tk.Frame(parent, bg=BG)
        inner.pack(fill="x", padx=16)
        return inner

    def _find_script(self, name: str) -> Path | None:
        """Search for a companion script in order of likely locations."""
        candidates = [
            EXE_DIR / name,  # dist/
            Path(self._nlm_root.get())
            / "src"
            / "notebooklm_automation"
            / name,  # src/notebooklm_automation/
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

        run_sec = self._section(tab, "STEP 2 - RUN AUTOMATION  (concepts.csv x prompts -> output/)")
        Field(run_sec, "Limit concepts (blank = all):", self._limit_c, width=8).pack(
            anchor="w", pady=2
        )
        Field(run_sec, "Limit prompts  (blank = all):", self._limit_p, width=8).pack(
            anchor="w", pady=2
        )

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
            text="Converts markdown files from the output folder into a browseable HTML hub.",
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        Field(sec, "Markdown input folder:", self._output_dir, browse=True).pack(anchor="w", pady=2)
        Field(sec, "HTML site output folder:", self._site_dir, browse=True).pack(anchor="w", pady=2)
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
        sec = self._section(tab, "CONCEPTS  (data/concepts.csv)")
        tk.Label(
            sec,
            text=(
                "One concept per line. The 'concept' column is used by the automation.\n"
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
        return Path(self._nlm_root.get()) / "data" / "concepts.csv"

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

    def _concepts_save(self) -> None:
        path = self._concepts_csv_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            content = self._concepts_text.get("1.0", "end-1c")
            # Ensure header row exists
            if not content.startswith("concept"):
                content = "concept\n" + content
                self._concepts_text.delete("1.0", "end")
                self._concepts_text.insert("1.0", content)
            path.write_text(content, encoding="utf-8")
            lines = [l for l in content.splitlines() if l.strip() and l.strip() != "concept"]
            self._concepts_status.config(text=f"Saved {len(lines)} concepts to {path}", fg=GREEN_L)
        except Exception as exc:
            self._concepts_status.config(text=f"Save failed: {exc}", fg="#f85149")

    def _concepts_open_editor(self) -> None:
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
        # ── Scrollable wrapper ─────────────────────────────────────────────────
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_resize(event):
            canvas.itemconfig(inner_id, width=event.width)

        canvas.bind("<Configure>", on_resize)

        def on_frame_resize(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", on_frame_resize)

        # Mousewheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # ── All content goes into `inner` instead of `tab` ────────────────────
        def section(title: str) -> tk.Frame:
            tk.Label(inner, text=title, bg=BG, fg=MUTED, font=F_UI, anchor="w").pack(
                fill="x", padx=16, pady=(12, 2)
            )
            tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))
            f = tk.Frame(inner, bg=BG)
            f.pack(fill="x", padx=16)
            return f

        # Launcher settings info
        info = section("LAUNCHER SETTINGS")
        tk.Label(
            info,
            text=f"Settings are auto-saved to:\n{SETTINGS_FILE}",
            bg=BG,
            fg=MUTED,
            font=F_UI,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        # Python / venv
        python_sec = section("PYTHON / VIRTUAL ENVIRONMENT")
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

        # Project paths
        paths = section("PROJECT PATHS")
        Field(
            paths, "Project root (notebooklm-automated):", self._nlm_root, browse=True, width=44
        ).pack(anchor="w", pady=3)
        Field(paths, "Markdown output folder:", self._output_dir, browse=True, width=44).pack(
            anchor="w", pady=3
        )
        Field(paths, "HTML site folder:", self._site_dir, browse=True, width=44).pack(
            anchor="w", pady=3
        )

        # .env
        env_sec = section(".ENV FILE")
        tk.Label(
            env_sec,
            text=(
                "The automation reads DEFAULT_NOTEBOOK_ID, AUTH_STORAGE_PATH etc.\n"
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
        dep_sec = section("BUILD COMMAND  (run inside your virtual environment)")
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
        tk.Frame(inner, bg=BG, height=20).pack()

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
                auth_path = Path(self._nlm_root.get()) / ".notebooklm_state" / "storage_state.json"
                auth_ok = auth_path.exists()
                site_ok = (Path(self._site_dir.get()) / "index.html").exists()
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

    def _nlm_check_auth(self) -> None:
        auth = self._nlm_root_path() / ".notebooklm_state" / "storage_state.json"
        if auth.exists():
            self._auth_lbl.config(text=f"Auth found: {auth}", fg=GREEN_L)
            self._nlm_log.log(f"Auth state exists at {auth}", "ok")
        else:
            self._auth_lbl.config(text=f"Not found: {auth}", fg="#f85149")
            self._nlm_log.log(f"Auth file missing: {auth}", "err")
            self._nlm_log.log(
                "Run 'Login to NotebookLM' first, or check that Project Root is set correctly in Settings.",
                "warn",
            )

    def _nlm_login(self) -> None:
        root = self._nlm_root_path()
        if not root.exists():
            self._nlm_log.log(f"Project root not found: {root}", "err")
            self._nlm_log.log("Set the correct path in Settings first.", "warn")
            return

        python = self._get_python()
        self._nlm_log.log(f"Project root: {root}", "dim")
        self._nlm_log.log("Opening a terminal window for NotebookLM login...", "info")
        self._nlm_log.log("Complete the login in the terminal, then press ENTER there.", "dim")

        def run() -> None:
            try:
                if IS_WIN:
                    python_win = str(Path(python).resolve())  # normalize to backslashes
                    # cmd /k requires outer quotes wrapping the whole command when the path has inner quotes
                    inner = f'"{python_win}" -m notebooklm login'
                    subprocess.Popen(
                        f'start "NotebookLM Login" cmd /k "{inner}"',
                        shell=True,
                        cwd=str(root),
                    )
                elif IS_MAC:
                    script = f'cd "{root}" && "{python}" -m notebooklm login'
                    subprocess.Popen(
                        ["osascript", "-e", f'tell app "Terminal" to do script "{script}"']
                    )
                else:
                    subprocess.Popen(
                        [
                            "x-terminal-emulator",
                            "-e",
                            f'bash -c \'cd "{root}" && "{python}" -m notebooklm login; read -p "Press ENTER to close"\' ',
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

        cmd = [self._get_python(), str(cli)]
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
        p = self._output_dir.get()
        Path(p).mkdir(parents=True, exist_ok=True)
        open_path(p)

    # ── Build Hub actions ──────────────────────────────────────────────────────

    def _build_site(self) -> None:
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
            self._output_dir.get(),
            "--site-dir",
            self._site_dir.get(),
            "--title",
            self._hub_title.get(),
            "--tutor-port",
            str(self._port.get()),
            "--concepts-csv",
            str(Path(self._nlm_root.get()) / "data" / "concepts.csv"),
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
        index = Path(self._site_dir.get()) / "index.html"
        if not index.exists():
            self._build_log.log("index.html not found — build the site first.", "warn")
            return
        open_path(str(index))
        self._build_log.log(f"Opened {index}", "ok")

    def _open_site_folder(self) -> None:
        p = self._site_dir.get()
        Path(p).mkdir(parents=True, exist_ok=True)
        open_path(p)

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
                    "AUTH_STORAGE_PATH=.notebooklm_state/storage_state.json\n"
                    "CONCEPTS_CSV=data/concepts.csv\n"
                    "PROMPTS_DIR=prompts\n"
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
