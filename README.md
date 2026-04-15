# notebooklm-automation

A complete local study workflow: batch-generate concept notes from NotebookLM, build a browseable HTML study hub, and study interactively with a local AI tutor powered by DeepSeek-R1 via Ollama.

---

## Table of Contents

1. [What This Project Does](#what-this-project-does)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Critical Library Fix — Increase Timeout](#critical-library-fix--increase-timeout)
5. [Environment Configuration](#environment-configuration)
6. [Running the GUI Launcher](#running-the-gui-launcher)
7. [Running From the Command Line](#running-from-the-command-line)
8. [Project Structure](#project-structure)
9. [How Each Component Works](#how-each-component-works)
10. [AI Tutor Sidebar Modes](#ai-tutor-sidebar-modes)
11. [Building a Stand-Alone Executable](#building-a-stand-alone-executable)
12. [Troubleshooting](#troubleshooting)

---

## What This Project Does

This project automates your entire study pipeline in three stages:

```
concepts.csv  →  NotebookLM (9 prompts each)  →  01_concept.md … 13_concept.md
                                                         ↓
                                               build_study_hub.py
                                                         ↓
                                               output/<notebook>/index.html
                                               + AI tutor sidebar (DeepSeek-R1)
```

1. **NotebookLM automation** — reads the active notebook folder's `concepts.csv`, runs a selected set of structured prompts against each concept in your NotebookLM notebook, and saves one numbered Markdown file per concept to that same notebook folder (by default `output/`, or a course folder such as `output/csci 372/`).
2. **Study hub builder** — converts those Markdown files into a polished HTML site with checkboxes, a progress bar, and per-concept pages.
3. **AI tutor** — a local FastAPI server + sidebar injected into every concept page, backed by DeepSeek-R1 running in Ollama. Supports Professor, Socratic, Quiz, Boundary, and Diagnose modes with per-concept mastery tracking.

---

## Prerequisites

Install the following before continuing:

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 or 3.12 | 3.13 is supported but less tested |
| [Ollama](https://ollama.com) | Latest | Runs DeepSeek-R1 locally |
| [Notepad++](https://notepad-plus-plus.org) | Any | Optional but recommended for editing CSV/config files |
| Git | Any | For cloning the repo |

> **Windows note:** Make sure Python is added to your PATH during installation. Check "Add Python to PATH" on the installer screen.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/notebooklm-automation.git
cd notebooklm-automation
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat

# Mac / Linux
source .venv/bin/activate
```

### 3. Install all dependencies

This project uses a `pyproject.toml`. Install the package and all development dependencies in one command:

```bash
pip install -e ".[dev]"
```

This installs the main package in editable mode along with all extras declared under `[dev]` in `pyproject.toml`, including `playwright`, `fastapi`, `uvicorn`, `httpx`, `pystray`, `pillow`, and `pyinstaller`.

### 4. Install Playwright's browser

After pip finishes, Playwright needs to download Chromium once:

```bash
playwright install chromium
```

### 5. Pull the Ollama models

Make sure Ollama is running first (`ollama serve` in a separate terminal or via the GUI launcher), then pull both models:

```bash
ollama pull deepseek-r1:1.5b
ollama pull deepseek-r1:8b
```

The 1.5b model is used by default (fast). The 8b model is available via the speed toggle in the tutor sidebar.

---

## Critical Library Fix — Increase Timeout

NotebookLM responses can be slow. The default `notebooklm-py` timeout is too short and causes frequent timeout errors on longer prompts. You must patch one file after installing dependencies.

### Steps

1. Open your virtual environment folder and navigate to:
   ```
   .venv/Lib/site-packages/notebooklm/_core.py
   ```

2. Find the `timeout` assignment (there is only one). Replace whatever values are there with:

   ```python
   timeout = httpx.Timeout(
       connect=10.0,
       read=None,
       write=120.0,
       pool=120.0,
   )
   ```

   Setting `read=None` removes the read timeout entirely, which is the main cause of failures on long NotebookLM responses. The `write` and `pool` values of 120 seconds give ample headroom for slow connections.

3. Save the file.

> **Important:** This change is made directly to the installed library file. If you ever reinstall or upgrade `notebooklm-py` (e.g. via `pip install --upgrade notebooklm-py`), this fix will be overwritten and you will need to reapply it.

---

## Environment Configuration

The automation reads configuration from a `.env` file in the project root. Create one by copying the template:

```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Then open `.env` and fill in your values:

```env
# Your NotebookLM notebook ID
# Found in the URL: notebooklm.google.com/notebooklm#?authuser=0&source=...
DEFAULT_NOTEBOOK_ID=your-notebook-id-here

# Optional default source IDs (comma or newline separated)
SOURCE_IDS=

# Path where Playwright saves your login session (do not change unless necessary)
AUTH_STORAGE_PATH=.notebooklm_state/storage_state.json

# Path to your concepts CSV file
CONCEPTS_CSV=output/concepts.csv

# Path to your prompt templates folder
PROMPTS_DIR=prompts/default

# Where generated Markdown files are saved
OUTPUT_DIR=output

# Where automation logs are saved
LOGS_DIR=logs

# How many times to retry a failed prompt before giving up
RETRIES=4

# Seconds to wait between prompts (be polite to NotebookLM)
DELAY_SECONDS=2.0
```

### concepts.csv format

Each notebook folder keeps its own `concepts.csv`. By default that means `output/concepts.csv`, and if you use a course folder such as `output/csci 372/`, the concepts file becomes `output/csci 372/concepts.csv`.

Your `concepts.csv` file must have a `concept` header column. One concept per row:

```csv
concept
Software Development Lifecycle
Predictive Development Models
Adaptive Development Models
...
```

The concepts are processed in the order they appear in this file. Output files are named with a numeric prefix matching their position: `01_software_development_lifecycle.md`, `02_predictive_development_models.md`, etc. The study hub uses these prefixes to display concepts in the correct order automatically.

---

## Running the GUI Launcher

The launcher (`launcher.py`) is the easiest way to use this project. It covers the full pipeline from a single window without touching the command line.

### First launch

```bash
python src/notebooklm_automation/launcher.py
```

A **setup wizard** appears on first launch (or whenever the venv path or project root cannot be found). Set:

- **Python executable** — point this to `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (Mac/Linux) inside this project
- **Project root** — the root folder of this repository

These settings are saved to `launcher_settings.json` next to the launcher and are remembered on every subsequent launch.

### Saved configs

The launcher now includes a leftmost `☰` tab before **NotebookLM**. Click it to open config actions:

- **Save** overwrites the currently loaded named config
- **Save As...** asks for a new config name and saves the current launcher state as a new profile
- **Load** shows your saved profiles and restores the selected one

These named configs capture the launcher state together, including notebook ID, source IDs, prompt input folder, output folder, prompt-set name, collection name, Python path, and the current run flags. Profiles are stored locally in `launcher_profiles/` next to the launcher.

### Workflow tabs

| Tab | What to do |
|---|---|
| **NotebookLM** | 1. Click **Login to NotebookLM** — a terminal opens. Sign in with Google, then press ENTER in that terminal. 2. Click **Check Auth State** to confirm the session was saved. 3. Click **Run Automation** to generate your Markdown files. |
| **Build Hub** | Click **Build Site** to convert Markdown files into HTML. Click **Open Hub** to open the result in your browser. |
| **Concepts** | Edit the current notebook folder's `concepts.csv` directly inside the launcher. Click **Save** when done. |
| **AI Tutor** | Click **Start Ollama** (runs silently with a system tray icon), then **Start Server** to launch the tutor backend. |
| **Settings** | Set paths, Python executable, and open your `.env` file for editing. |

### Course / collection folders

If you want separate study libraries for different classes or programs, use the launcher's **Course / collection name** field and click **Use/Create Course Folder**.

- A name like `csci 372` maps the markdown output to `output/csci 372/`
- That folder stays self-contained: `concepts.csv` lives there, markdown files go there, the study hub is built there, and `index.html` opens from there
- The Build Hub step inherits the markdown output folder as both its markdown input and HTML output

### Prompt set folders

If you want different prompt packs for different workflows, use the launcher's **Prompt set name** field and click **Use/Create Prompt Folder**.

- A name like `midterm-review` maps the prompt input to `prompts/midterm-review/`
- Leave it blank to use the default `prompts/default/` folder
- The launcher passes that selected prompt folder into the automation run, so the GUI prompt choice and the actual run stay in sync
- New prompt folders are created for you, but they need `.txt` prompt files before a run will start

### Notebook-specific setup

For each NotebookLM notebook, the launcher can now save all of these together in one profile:

- Notebook ID
- Source IDs
- Prompt input folder
- Notebook output folder

Use **List Notebooks** to fetch your notebooks from saved NotebookLM auth, then click the notebook row you want to use. After that, click **List Sources** to fetch that notebook's sources. Click a row in **Not Added** to add that source to the notebook config, and click a row in **Added** to remove it.

### Ollama system tray

When you click **Start Ollama** from the AI Tutor tab, Ollama runs silently in the background and an amber dot icon appears in the Windows system tray. Right-click it to **Stop Ollama** or bring the launcher window back to front.

---

## Running From the Command Line

If you prefer the CLI over the GUI launcher, all components can be run manually.

### Login to NotebookLM

```powershell
# Windows PowerShell
notebooklm login --storage "$env:NOTEBOOKLM_HOME\storage_state.json"

# Or using the module directly
python -m notebooklm login
```

### Run the automation

```bash
# Test with 1 concept and 2 prompts
nlm-auto --limit-concepts 1 --limit-prompts 2 --overwrite

# Test one concept with all prompts
nlm-auto --limit-concepts 1 --limit-prompts 9 --overwrite

# Run all concepts with all prompts
nlm-auto --overwrite

# Run with a specific prompt set and output folder
nlm-auto --prompts-dir "prompts/midterm-review" --output-dir "output/csci 372" --overwrite

# Run with a notebook-specific ID and sources
nlm-auto --notebook-id "your-notebook-id" --source-id "src-1" --source-id "src-2" --prompts-dir "prompts/midterm-review" --output-dir "output/csci 372" --overwrite

# Run a specific course/program into its own folder
nlm-auto --output-dir "output/csci 372" --overwrite

# Preview what would run without calling NotebookLM
nlm-auto --dry-run
```

### Build the study hub

```bash
python src/notebooklm_automation/build_study_hub.py \
  --input "output/csci 372" \
  --site-dir "output/csci 372" \
  --title "My Study Hub" \
  --tutor-port 8000
```

Add `--no-tutor` to build without the AI sidebar.

### Start the AI tutor server

```bash
# Make sure Ollama is running first
ollama serve

# Then start the FastAPI backend
uvicorn tutor_server:app --reload --port 8000
```

### Open the hub

```bash
# Windows
start output\\csci 372\\index.html

# Mac
open output/csci\ 372/index.html
```

---

## Project Structure

```
notebooklm-automation/
├── .env                          # Your configuration (not committed)
├── .env.example                  # Template — copy to .env and fill in
├── pyproject.toml                # Package definition and dependencies
├── prompts/
│   ├── default/
│   │   ├── 01_why_it_matters.txt # Default prompt templates
│   │   ├── 02_core_identity.txt
│   │   └── ...
│   ├── midterm-review/
│   │   ├── 01_why_it_matters.txt
│   │   └── ...
│   └── ...
├── output/                       # Generated Markdown files (gitignored)
│   ├── csci 372/
│   │   ├── concepts.csv
│   │   ├── 01_software_development_lifecycle_sdlc.md
│   │   ├── index.html
│   │   ├── tutor.css
│   │   ├── tutor.js
│   │   └── ...
│   └── berkeley msse/
├── logs/                         # Automation run logs (gitignored)
├── src/
│   └── notebooklm_automation/
│       ├── launcher.py           # GUI launcher (all-in-one)
│       ├── build_study_hub.py    # HTML site builder
│       ├── tutor_server.py       # AI tutor FastAPI backend
│       ├── cli.py                # CLI entry point (nlm-auto)
│       ├── runner.py             # Batch orchestration logic
│       ├── config.py             # .env loader
│       ├── models.py             # Data models
│       ├── storage.py            # File writing helpers
│       ├── template_loader.py    # CSV and prompt file loaders
│       ├── notebooklm_service.py # notebooklm-py wrapper
│       └── source_config.py      # Fallback NotebookLM source IDs
└── .notebooklm_state/
    └── storage_state.json        # Saved login session (gitignored)
```

---

## How Each Component Works

### `tutor_server.py` — AI tutor backend

A FastAPI server that acts as the bridge between the study hub and your local Ollama instance.

| Endpoint | Purpose |
|---|---|
| `POST /chat` | SSE streaming chat. Builds a mode-specific system prompt from the current page's section content and the student's mastery history, then streams DeepSeek-R1's response token by token. |
| `GET /mastery/{id}` | Returns mastery data for a concept: score, quiz history, known confusions. |
| `POST /mastery/update` | Records a quiz result or confusion topic. Updates the mastery score using an exponential moving average so recent performance matters more than old results. |
| `GET /library` | Returns all tracked concepts and their mastery scores — used for cross-concept mode. |

A SQLite database (`tutor_state.db`) is created automatically on first run and stores all mastery and interaction history.

### `build_study_hub.py` — HTML site builder

Converts your numbered Markdown files into a static HTML site in the same notebook output folder. Concepts are ordered by their numeric prefix (`01_`, `02_`, etc.) automatically — no manual ordering list required.

The builder injects two files into the site:

- `tutor.css` — sidebar styles
- `tutor.js` — sidebar logic, streaming renderer, mastery tracking

Each concept page receives `window.TUTOR_CONCEPT_ID` and `window.TUTOR_CONCEPT_TITLE` so the sidebar always knows which concept it is reading.

### `runner.py` — batch orchestration

For each concept in your CSV, the runner:

1. Builds the output path with the concept's position prefix (`01_`, `02_`, etc.)
2. Runs each prompt template in order against NotebookLM
3. Appends each answer as a `## Section` in the Markdown file
4. Retries failed prompts up to `RETRIES` times with `DELAY_SECONDS` between attempts
5. Writes a `manifest.jsonl` entry for every prompt attempt (success or failure)

---

## AI Tutor Sidebar Modes

Open any concept page and click the **AI Tutor** pill on the right edge of the screen to open the sidebar.

| Mode | Best used when… |
|---|---|
| **Professor** | You want a section explained in plain language |
| **Socratic** | You want to reason through it yourself with guided questions |
| **Quiz** | You want a quick scored check of what you know |
| **Boundary** | Two concepts feel too similar and you need to stress-test the difference |
| **Diagnose** | You feel confused but can't identify exactly why |

**Speed toggle** — ⚡ Fast uses `deepseek-r1:1.5b` (quick responses). 🧠 Accurate uses `deepseek-r1:8b` (deeper reasoning, slower). The model's thinking process is shown live in an expandable reasoning trace before the final answer appears.

**Cross-concept mode** — disabled by default (the tutor only reads the current page). Enable it to allow the tutor to reference your full concept library when answering comparison or prerequisite questions.

**Mastery tracking** — the tutor automatically detects correct and incorrect answers in Quiz mode and updates a per-concept mastery score (shown as a coloured bar: red < 40%, amber 40–70%, green > 70%).

---

## Building a Stand-Alone Executable

To share the launcher as a double-clickable `.exe` with no Python installation required on the target machine:

```bash
# Activate your venv, then run from the project root:
# pyinstaller --onefile --windowed \
#   --add-data "src/notebooklm_automation/build_study_hub.py;." \
#   --add-data "src/notebooklm_automation/tutor_server.py;." \
#   --add-data "scripts/list_sources.py;." \
#   --add-data "scripts/list_notebooks.py;." \
#   src/notebooklm_automation/launcher.py

pyinstaller --onefile --windowed --add-data "src/notebooklm_automation/build_study_hub.py;." --add-data "src/notebooklm_automation/tutor_server.py;." --add-data "scripts/list_sources.py;." --add-data "scripts/list_notebooks.py;." src/notebooklm_automation/launcher.py

```

The output is at `dist/launcher.exe`. The `--add-data` flags copy `build_study_hub.py`, `tutor_server.py`, `list_sources.py`, and `list_notebooks.py` into the same folder as the exe automatically.

> **Important:** The exe packages the launcher UI only. The automation, tutor server, and login still require Python at runtime. After running the exe for the first time, go to **Settings → Python executable** and point it to your `.venv/Scripts/python.exe`. This setting is saved and remembered permanently.

---

## Troubleshooting

**`No module named notebooklm`**
Your venv Python is not set correctly in the launcher. Go to Settings → Python executable and browse to `.venv/Scripts/python.exe` inside this project folder.

**`Login command exited 1` / `Aborted!`**
The login command is interactive and needs a real terminal. The launcher opens one automatically — complete the Google login there and press ENTER in that terminal window.

**`Chromium pre-flight check failed`**
Playwright's Chromium is not installed. Run:
```bash
playwright install chromium
```

**Frequent timeout errors during automation**
Apply the [library timeout fix](#critical-library-fix--increase-timeout). Also try increasing `RETRIES` in your `.env` (e.g. `RETRIES=4`).

**`Could not import module "tutor_server"`**
uvicorn is looking in the wrong directory. Make sure the launcher's `_start_server` uses `cwd=str(s.parent)` where `s` is the resolved path to `tutor_server.py`.

**`No .txt prompt files found in: ...`**
The selected prompt folder exists, but it does not contain any prompt templates yet. Add your `.txt` prompt files there, or switch back to the base `prompts/` folder or another prompt-set folder that already has templates.

**`No .md files found in: ...\dist\output`**
The markdown folder is pointing to `dist/output` instead of your project's real study set folder. Go to **NotebookLM** or **Settings**, set the correct markdown output folder, or use **Course / collection name** to recreate the right `output/<name>` path.

**Ollama not found**
Download and install Ollama from [ollama.com](https://ollama.com), then restart the launcher. Ollama must be on your system PATH.

**Study hub not showing concepts in the right order**
The hub orders concepts by numeric filename prefix (`01_`, `02_`, etc.). If your files do not have this prefix, re-run the automation — `runner.py` now automatically adds the position prefix based on the order in `concepts.csv`.
