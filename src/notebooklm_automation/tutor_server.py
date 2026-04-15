#!/usr/bin/env python3
"""
Study Hub AI Tutor Server
─────────────────────────
Backend for the local AI-powered study hub tutor sidebar.

Setup:
    pip install fastapi uvicorn httpx

    # In a separate terminal:
    ollama serve
    ollama pull deepseek-r1:8b

Run:
    uvicorn tutor_server:app --reload --port 8000

The server exposes:
    POST /chat             → SSE streaming chat with Ollama
    GET  /mastery/{id}     → Mastery data for a concept
    POST /mastery/update   → Record quiz result or confusion
    POST /quiz/record      → Log a quiz exchange
    GET  /library          → All tracked concepts + mastery
    GET  /health           → Liveness check
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Config ─────────────────────────────────────────────────────────────────────
FAST_MODEL = "deepseek-r1:1.5b"
ACCURATE_MODEL = "deepseek-r1:8b"
OLLAMA_URL = "http://localhost:11434/api/chat"
DB_PATH = Path("tutor_state.db")
TIMEOUT = 180.0  # seconds; long chains of thought need time
CONTEXT_WINDOWS = {
    "deepseek-r1:1.5b": 131072,
    "deepseek-r1:8b": 131072,
}

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Study Hub AI Tutor", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Database ───────────────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mastery (
            concept_id       TEXT PRIMARY KEY,
            concept_title    TEXT NOT NULL,
            mastery_score    REAL    DEFAULT 0.5,
            times_studied    INTEGER DEFAULT 0,
            times_quizzed    INTEGER DEFAULT 0,
            times_correct    INTEGER DEFAULT 0,
            last_reviewed    TEXT,
            confusion_topics TEXT    DEFAULT '[]',
            notes            TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS quiz_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_id   TEXT    NOT NULL,
            question     TEXT    NOT NULL,
            user_answer  TEXT    NOT NULL,
            was_correct  INTEGER NOT NULL,
            ai_feedback  TEXT,
            mode         TEXT    DEFAULT 'quiz',
            timestamp    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_id   TEXT NOT NULL,
            mode         TEXT NOT NULL,
            user_msg     TEXT NOT NULL,
            ai_msg       TEXT NOT NULL,
            timestamp    TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


@app.on_event("startup")
async def startup() -> None:
    init_db()


# ── Pydantic models ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
    concept_id: str
    concept_title: str
    mode: str = "professor"
    page_sections: dict[str, str] = {}
    cross_concept: bool = False
    library_context: str = ""
    model: str = FAST_MODEL


class MasteryUpdate(BaseModel):
    concept_id: str
    concept_title: str
    correct: bool | None = None
    confusion_topic: str | None = None
    mode: str = "study"


class QuizRecord(BaseModel):
    concept_id: str
    question: str
    user_answer: str
    was_correct: bool
    ai_feedback: str
    mode: str = "quiz"


# ── Mode instruction strings ───────────────────────────────────────────────────
MODE_INSTRUCTIONS: dict[str, str] = {
    "professor": (
        "You are a patient, expert professor. Make the concept crystal clear.\n"
        "Use analogies, concrete examples, and plain language. Break down jargon.\n"
        "Reference specific sections from the page content when relevant.\n"
        "Be encouraging but precise. Use short paragraphs. Avoid walls of text."
    ),
    "socratic": (
        "You are a Socratic tutor. NEVER give direct answers.\n"
        "Guide the student to discover answers through carefully chosen questions.\n"
        "If they're stuck after 2 exchanges, give a small hint — then ask again.\n"
        "When they get it right, celebrate briefly and ask the next probing question.\n"
        "End each response with exactly one question."
    ),
    "quiz": (
        "You are a quiz master testing the student's knowledge.\n"
        "Ask ONE focused question at a time. Wait for their answer.\n"
        "After each answer: say CORRECT ✓ or INCORRECT ✗ clearly, then explain.\n"
        "Report running score as: Score: N/M.\n"
        "Vary types: definition → application → comparison → edge-case → synthesis.\n"
        "After 5 questions, give a brief summary of strengths and gaps."
    ),
    "boundary": (
        "You are stress-testing the student's mental model.\n"
        "Focus exclusively on: misconceptions, edge cases, where the concept breaks down,\n"
        "how it differs from similar concepts, and what happens at the limits.\n"
        "Ask 'what if', 'what about', 'does this still hold when...' questions.\n"
        "Correct precisely when their model is wrong. Be challenging but fair."
    ),
    "diagnose": (
        "You are diagnosing knowledge gaps systematically.\n"
        "Start broad, then drill into specific weak areas based on each answer.\n"
        "Name the gap precisely when you find it (e.g. 'You understand X but not Y').\n"
        "Probe deeper into every hesitation or partial answer.\n"
        "End your response with: RECOMMENDATION: [one specific next action]."
    ),
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_mastery_row(concept_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM mastery WHERE concept_id = ?", (concept_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def touch_mastery(concept_id: str, concept_title: str, conn: sqlite3.Connection) -> None:
    """Ensure row exists and bump times_studied."""
    conn.execute(
        "INSERT OR IGNORE INTO mastery (concept_id, concept_title, last_reviewed) VALUES (?,?,?)",
        (concept_id, concept_title, now_iso()),
    )
    conn.execute(
        "UPDATE mastery SET times_studied = times_studied + 1, last_reviewed = ? WHERE concept_id = ?",
        (now_iso(), concept_id),
    )


def build_system_prompt(
    mode: str,
    concept_title: str,
    page_sections: dict[str, str],
    mastery: dict | None,
    library_context: str = "",
) -> str:
    # Page sections (capped per section to stay within context)
    sections_block = ""
    if page_sections:
        for section, content in page_sections.items():
            trimmed = content.strip()[:700]
            if trimmed:
                sections_block += f"\n### {section}\n{trimmed}\n"

    # Student profile
    profile_block = ""
    if mastery:
        score = mastery.get("mastery_score", 0.5)
        correct = mastery.get("times_correct", 0)
        quizzed = mastery.get("times_quizzed", 0)
        confuse = json.loads(mastery.get("confusion_topics", "[]"))
        profile_block = (
            f"\nStudent profile for '{concept_title}':\n"
            f"  Mastery score : {score:.0%}\n"
            f"  Quiz record   : {correct}/{quizzed} correct\n"
            f"  Known confusions: {', '.join(confuse) if confuse else 'none yet'}\n"
        )

    cross_block = f"\n\nRelated library context:\n{library_context}" if library_context else ""

    return (
        f'You are an AI tutor. The student is studying: "{concept_title}"\n\n'
        f"{MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS['professor'])}\n"
        f"{profile_block}"
        f"\nPage content (by section):{sections_block}"
        f"{cross_block}\n\n"
        "Rules: Stay grounded in the provided page content. Do not invent facts not present "
        "in the material. Keep responses focused and appropriately concise."
    )


def serialize_mastery(row: dict) -> dict:
    return {**row, "confusion_topics": json.loads(row.get("confusion_topics", "[]"))}


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    mastery = get_mastery_row(req.concept_id)
    system_prompt = build_system_prompt(
        mode=req.mode,
        concept_title=req.concept_title,
        page_sections=req.page_sections,
        mastery=mastery,
        library_context=req.library_context,
    )
    ollama_messages = [{"role": "system", "content": system_prompt}, *req.messages]

    async def stream() -> ...:
        full_response = ""
        thinking_started = False
        thinking_closed = False
        prompt_chars = len(json.dumps(ollama_messages))

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    OLLAMA_URL,
                    json={
                        "model": req.model,
                        "messages": ollama_messages,
                        "stream": True,
                        "think": True,
                    },
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        yield f"data: {json.dumps({'error': f'Ollama {response.status_code}: {body.decode()[:200]}'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if chunk.get("done"):
                            prompt_tokens = chunk.get("prompt_eval_count", "?")
                            response_tokens = chunk.get("eval_count", "?")
                            total = (
                                prompt_tokens + response_tokens
                                if isinstance(prompt_tokens, int)
                                and isinstance(response_tokens, int)
                                else "?"
                            )
                            ctx_size = CONTEXT_WINDOWS.get(req.model, 131072)
                            used_pct = (
                                f"{round(total / ctx_size * 100, 1)}% of {ctx_size // 1024}k"
                                if isinstance(total, int)
                                else "?"
                            )
                            yield f"data: {json.dumps({'stats': {'prompt_chars': prompt_chars, 'ctx': used_pct}})}\n\n"
                            break

                        thinking_chunk = chunk.get("message", {}).get("thinking", "")
                        content_chunk = chunk.get("message", {}).get("content", "")

                        if thinking_chunk:
                            if not thinking_started:
                                thinking_started = True
                                full_response += "<think>"
                                yield f"data: {json.dumps({'content': '<think>'})}\n\n"
                            full_response += thinking_chunk
                            yield f"data: {json.dumps({'content': thinking_chunk})}\n\n"

                        if content_chunk:
                            if thinking_started and not thinking_closed:
                                thinking_closed = True
                                full_response += "</think>"
                                yield f"data: {json.dumps({'content': '</think>'})}\n\n"
                            full_response += content_chunk
                            yield f"data: {json.dumps({'content': content_chunk})}\n\n"

        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': 'Cannot reach Ollama. Run: ollama serve'})}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        # Persist interaction + update mastery
        if full_response and req.messages:
            user_msg = req.messages[-1].get("content", "")
            conn = get_db()
            conn.execute(
                "INSERT INTO interactions (concept_id,mode,user_msg,ai_msg,timestamp) VALUES (?,?,?,?,?)",
                (req.concept_id, req.mode, user_msg, full_response, now_iso()),
            )
            touch_mastery(req.concept_id, req.concept_title, conn)
            conn.commit()
            conn.close()

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/mastery/{concept_id}")
async def get_mastery(concept_id: str) -> dict:
    row = get_mastery_row(concept_id)
    if row is None:
        return {
            "concept_id": concept_id,
            "mastery_score": 0.5,
            "times_studied": 0,
            "times_quizzed": 0,
            "times_correct": 0,
            "confusion_topics": [],
        }
    return serialize_mastery(row)


@app.post("/mastery/update")
async def update_mastery(update: MasteryUpdate) -> dict:
    conn = get_db()
    touch_mastery(update.concept_id, update.concept_title, conn)

    if update.correct is not None:
        row = conn.execute(
            "SELECT mastery_score, times_quizzed, times_correct FROM mastery WHERE concept_id=?",
            (update.concept_id,),
        ).fetchone()
        if row:
            # Exponential moving average: weight recent results more
            old = row["mastery_score"]
            result = 1.0 if update.correct else 0.0
            new = round(old * 0.75 + result * 0.25, 4)
            conn.execute(
                """UPDATE mastery
                   SET mastery_score=?, times_quizzed=times_quizzed+1,
                       times_correct=times_correct+?, last_reviewed=?
                   WHERE concept_id=?""",
                (new, 1 if update.correct else 0, now_iso(), update.concept_id),
            )

    if update.confusion_topic:
        row = conn.execute(
            "SELECT confusion_topics FROM mastery WHERE concept_id=?", (update.concept_id,)
        ).fetchone()
        if row:
            topics = json.loads(row["confusion_topics"] or "[]")
            if update.confusion_topic not in topics:
                topics.append(update.confusion_topic)
            conn.execute(
                "UPDATE mastery SET confusion_topics=? WHERE concept_id=?",
                (json.dumps(topics[-10:]), update.concept_id),
            )

    conn.commit()
    result = conn.execute(
        "SELECT * FROM mastery WHERE concept_id=?", (update.concept_id,)
    ).fetchone()
    conn.close()
    return serialize_mastery(dict(result))


@app.post("/quiz/record")
async def record_quiz(rec: QuizRecord) -> dict:
    conn = get_db()
    conn.execute(
        "INSERT INTO quiz_history (concept_id,question,user_answer,was_correct,ai_feedback,mode,timestamp) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            rec.concept_id,
            rec.question,
            rec.user_answer,
            int(rec.was_correct),
            rec.ai_feedback,
            rec.mode,
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()
    return {"recorded": True}


@app.get("/library")
async def get_library() -> dict:
    conn = get_db()
    rows = conn.execute("SELECT * FROM mastery ORDER BY last_reviewed DESC").fetchall()
    conn.close()
    return {"concepts": [serialize_mastery(dict(r)) for r in rows]}


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "models": "dynamic",
        "db": str(DB_PATH),
    }


# ── Entrypoint ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tutor_server:app", host="127.0.0.1", port=8000, reload=True)
