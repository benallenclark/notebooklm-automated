# notebooklm-automation

Batch prompt runner for NotebookLM study workflows.

notebooklm login --storage "$env:NOTEBOOKLM_HOME\storage_state.json"

Notebooklm-py file was modified to increase timeout ceiling:
1. Go to your virtual environment
2. then find Lib/site-packages/notebooklm/_core.py
  - Edit the timeout to match this
  ```
  timeout = httpx.Timeout(
                connect=10.0,
                read=None,
                write=120.0,
                pool=120.0,
            )
  ```


### For testing one concept
nlm-auto --limit-concepts 1 --limit-prompts 9 --overwrite 

### for all concepts
nlm-auto --overwrite 

---
# Quick Start

## 1. Ollama
ollama serve
ollama pull deepseek-r1:8b
ollama pull deepseek-r1:1.5b

## 2. Tutor server
pip install fastapi uvicorn httpx
uvicorn tutor_server:app --reload --port 8000

## 3. Build & open
python scripts/build_study_hub.py
open study_hub/index.html

---

What's in each file
tutor_server.py — FastAPI backend:

POST /chat — SSE streaming through Ollama. Builds a mode-specific system prompt grounded in the page's section content and the student's mastery history
GET/POST /mastery/{id} — tracks mastery score per concept using exponential moving average (recent quiz results weighted more)
GET /library — returns all tracked concepts for cross-concept mode
SQLite database (tutor_state.db) auto-created on first run

build_study_hub.py — adds two generated files to your site:

tutor.css / tutor.js — written once into the site dir, referenced by every concept page
Each concept page gets window.TUTOR_CONCEPT_ID and window.TUTOR_CONCEPT_TITLE injected so the sidebar knows what it's reading

Sidebar features

5 modes: Professor (plain explanations), Socratic (no direct answers), Quiz (scored, auto-updates mastery), Boundary (edge cases/misconceptions), Diagnose (gap-finding with a RECOMMENDATION at the end)
deepseek-r1 <think> tags rendered as a collapsible "Reasoning trace" block — useful to actually see the model work through a concept
Mastery bar per concept — turns red/amber/green based on quiz performance
Cross-concept toggle — off by default (page-local); when enabled, fetches your full library and includes it as context
--no-tutor flag if you want to build without the sidebar