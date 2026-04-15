#!/usr/bin/env python3
"""
Build a static HTML study hub from Markdown files, with an optional
AI tutor sidebar powered by a local Ollama model.

Usage:
    python build_study_hub.py
    python build_study_hub.py --input output --site-dir output
    python build_study_hub.py --title "My Study Hub" --tutor-port 8000
    python build_study_hub.py --no-tutor          # skip AI sidebar

Tutor setup (separate terminal):
    pip install fastapi uvicorn httpx
    ollama serve && ollama pull deepseek-r1:8b
    uvicorn tutor_server:app --reload --port 8000
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path


def strip_source_references(text: str) -> str:
    """Remove bracketed source citations like [1], [2, 3], [1-5] from text."""
    return re.sub(r"\s*\[[\d,\s\-]+\]", "", text)


def format_section_labels(text: str) -> str:
    """Detect plain-text label lines and wrap them in ** so the parser treats them as headings."""
    lines = text.split("\n")
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip lines that are already formatted, empty, or clearly not labels
        if (
            not stripped
            or stripped == "---"
            or stripped.startswith("#")
            or stripped.startswith("**")
            or re.match(r"^[-*·]\s", stripped)
            or re.match(r"^\d+\.\s", stripped)
            or stripped.startswith("```")
            or stripped.endswith(".")
            or stripped.endswith(":")
            or not stripped[0].isupper()
        ):
            result.append(line)
            continue

        # Look ahead for a non-blank line (label must have content after it)
        next_stripped = ""
        for j in range(i + 1, len(lines)):
            if lines[j].strip():
                next_stripped = lines[j].strip()
                break

        if next_stripped and len(stripped) < 120:
            result.append(f"**{stripped}**")
        else:
            result.append(line)

    return "\n".join(result)


# ── Ordering ───────────────────────────────────────────────────────────────────
ordered_concepts: list[str] = [
    # "your_file_stem_here",
    "software_development_lifecycle_sdlc",
    "predictive_development_models",
    "adaptive_development_models",
    "spiral_model",
    "secure_sdlc_ssdlc_and_shift_left",
    "threat_modeling",
    "verification",
    "validation",
    "functional_testing",
    "security_testing",
    "static_application_security_testing_sast",
    "dynamic_application_security_testing_dast",
    "software_composition_analysis_sca",
]


# ══════════════════════════════════════════════════════════════════════════════
#  TUTOR ASSETS  (written as tutor.css / tutor.js into the site directory)
# ══════════════════════════════════════════════════════════════════════════════

TUTOR_CSS = r"""
/* ── Tutor Sidebar ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* Toggle pill – sticks to right edge */
#tutor-toggle-btn {
    position: fixed;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    z-index: 9990;
    background: linear-gradient(160deg, #2563eb, #7c3aed);
    color: #fff;
    border: none;
    border-radius: 10px 0 0 10px;
    padding: 18px 9px;
    font-size: 1.2rem;
    line-height: 1;
    cursor: pointer;
    box-shadow: -3px 0 18px rgba(37,99,235,.45);
    transition: padding .2s, box-shadow .2s;
    writing-mode: vertical-rl;
    letter-spacing: .08em;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: .7rem;
    font-weight: 600;
    text-transform: uppercase;
}
#tutor-toggle-btn:hover {
    padding-left: 14px;
    box-shadow: -5px 0 26px rgba(37,99,235,.6);
}

/* Sidebar panel */
#tutor-sidebar {
    position: fixed;
    top: 0;
    right: -420px;
    width: 400px;
    height: 100vh;
    z-index: 9991;
    display: flex;
    flex-direction: column;
    background: #0d1117;
    border-left: 1px solid rgba(255,255,255,.07);
    box-shadow: -8px 0 40px rgba(0,0,0,.5);
    transition: right .32s cubic-bezier(.4,0,.2,1);
    font-family: 'IBM Plex Sans', ui-sans-serif, sans-serif;
    color: #e6edf3;
    overflow: hidden;
}
#tutor-sidebar.open { right: 0; }
#tutor-sidebar.minimized {
    right: -400px;
}

/* Push main content left when sidebar opens */
body.tutor-open .wrap {
    margin-right: 410px;
    transition: margin-right .32s cubic-bezier(.4,0,.2,1);
}

/* ── Header ─────────────────────────────────────────────────────────────────── */
#tutor-header {
    flex-shrink: 0;
    padding: 14px 16px 12px;
    background: #161b22;
    border-bottom: 1px solid rgba(255,255,255,.07);
}
#tutor-header-expandable {
    max-height: 0;
    overflow: hidden;
    transition: max-height .25s ease, opacity .25s ease;
    opacity: 0;
}
#tutor-header:hover #tutor-header-expandable,
#tutor-header:hover + #tutor-modes {
    max-height: 300px;
    opacity: 1;
}
#tutor-header-wrap:hover #tutor-header-expandable,
#tutor-header-wrap:hover #tutor-modes {
    max-height: 300px;
    opacity: 1;
    overflow: visible;
}
#tutor-title-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
#tutor-brand {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    font-size: .92rem;
    letter-spacing: -.01em;
}
#tutor-brand-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #22d3ee;
    box-shadow: 0 0 8px #22d3ee;
    animation: pulse-dot 2s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%,100% { opacity: 1; transform: scale(1); }
    50%      { opacity: .5; transform: scale(.7); }
}
#tutor-header-btns { display: flex; gap: 5px; }
#tutor-header-btns button {
    width: 24px; height: 24px;
    border-radius: 6px;
    border: 1px solid rgba(255,255,255,.1);
    background: rgba(255,255,255,.05);
    color: #8b949e;
    font-size: .95rem;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: background .15s, color .15s;
}
#tutor-header-btns button:hover { background: rgba(255,255,255,.12); color: #e6edf3; }

#tutor-concept-label {
    font-size: .78rem;
    color: #8b949e;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 10px;
    padding-left: 2px;
}

/* Mastery row */
#mastery-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: .75rem;
    color: #8b949e;
    font-family: 'IBM Plex Mono', monospace;
}
#mastery-track {
    flex: 1;
    height: 5px;
    background: rgba(255,255,255,.07);
    border-radius: 999px;
    overflow: hidden;
}
#mastery-fill {
    height: 100%;
    width: 50%;
    border-radius: 999px;
    background: #f59e0b;
    transition: width .5s ease, background .5s ease;
}

/* ── Tutor Stats ─────────────────────────────────────────────────────────────── */
#tutor-stats {
    font-family: 'IBM Plex Mono', monospace;
    font-size: .68rem;
    color: #6e7681;
    margin-bottom: 8px;
    letter-spacing: .02em;
    min-height: .85rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* ── Speed selector ──────────────────────────────────────────────────────────── */
#tutor-speed-row {
    display: flex; gap: 5px; margin-top: 8px;
}
.speed-btn {
    flex: 1; padding: 4px 8px; border-radius: 6px;
    border: 1px solid rgba(255,255,255,.1);
    background: rgba(255,255,255,.04); color: #8b949e;
    font-family: 'IBM Plex Sans', sans-serif; font-size: .7rem;
    font-weight: 600; cursor: pointer; text-transform: uppercase;
    letter-spacing: .04em; transition: all .15s;
}
.speed-btn.active {
    background: linear-gradient(135deg, #2563eb, #7c3aed);
    border-color: transparent; color: #fff;
}

/* ── Mode selector ──────────────────────────────────────────────────────────── */
#tutor-modes {
    max-height: 0;
    overflow: hidden;
    transition: max-height .25s ease, opacity .25s ease;
    opacity: 0;
    flex-shrink: 0;
    border-bottom: 1px solid rgba(255,255,255,.07);
    background: #0d1117;
}

#mode-select {
    position: relative;
    cursor: pointer;
    user-select: none;
    outline: none;
}
#mode-current {
    display: flex;
    align-items: baseline;
    gap: 7px;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,.1);
    background: rgba(255,255,255,.04);
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: .82rem;
    font-weight: 600;
    color: #e6edf3;
    transition: border-color .15s;
}
#mode-select:focus #mode-current,
#mode-current:hover { border-color: #2563eb; }
#mode-chevron {
    margin-left: auto;
    font-size: .7rem;
    color: #8b949e;
    transition: transform .15s;
}
#mode-options {
    display: none;
    position: absolute;
    top: calc(100% + 4px);
    left: 14px;
    right: 14px;
    background: #161b22;
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 10px;
    overflow: hidden;
    z-index: 100;
    box-shadow: 0 8px 24px rgba(0,0,0,.4);
}
#mode-options.open { display: block; }
.mode-option {
    padding: 9px 13px;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: .82rem;
    font-weight: 600;
    color: #c9d1d9;
    cursor: pointer;
    transition: background .12s;
    display: flex;
    align-items: baseline;
    gap: 7px;
}
.mode-option:hover    { background: rgba(255,255,255,.06); color: #e6edf3; }
.mode-option.active   { color: #a5b4fc; }
.mode-desc {
    font-weight: 400;
    font-size: .75rem;
    color: #6e7681;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* ── Think Streaming─────────────────────────────────────────────────────────── */
.think-streaming {
    background: rgba(0,0,0,.2);
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 7px;
    margin-bottom: 8px;
}
.think-streaming-label {
    padding: 5px 10px;
    font-size: .73rem;
    color: #8b949e;
    font-family: 'IBM Plex Mono', monospace;
    text-transform: uppercase;
    letter-spacing: .06em;
    border-bottom: 1px solid rgba(255,255,255,.05);
}

/* ── Messages ───────────────────────────────────────────────────────────────── */
#tutor-messages {
    flex: 1;
    overflow-y: auto;
    padding: 14px 14px 8px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    scroll-behavior: smooth;
}
#tutor-messages::-webkit-scrollbar { width: 3px; }
#tutor-messages::-webkit-scrollbar-track { background: transparent; }
#tutor-messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,.1); border-radius: 2px; }

.tutor-msg {
    max-width: 96%;
    padding: 10px 13px;
    border-radius: 12px;
    font-size: .84rem;
    line-height: 1.6;
    word-break: break-word;
    animation: msg-in .18s ease;
}
@keyframes msg-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0);   }
}
.tutor-msg-user {
    background: linear-gradient(135deg, #1d4ed8, #6d28d9);
    color: #fff;
    align-self: flex-end;
    border-radius: 12px 12px 4px 12px;
}
.tutor-msg-ai {
    background: #161b22;
    border: 1px solid rgba(255,255,255,.08);
    color: #c9d1d9;
    align-self: flex-start;
    border-radius: 12px 12px 12px 4px;
}
.tutor-msg strong { color: #e6edf3; }
.tutor-msg em     { color: #a5b4fc; font-style: italic; }
.tutor-msg code {
    font-family: 'IBM Plex Mono', monospace;
    font-size: .82em;
    background: rgba(0,0,0,.4);
    border: 1px solid rgba(255,255,255,.1);
    padding: 1px 5px;
    border-radius: 4px;
    color: #79c0ff;
}

/* Thinking block (deepseek-r1 <think> tags) */
.think-block {
    margin-bottom: 8px;
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 7px;
    overflow: hidden;
}
.think-block summary {
    padding: 5px 10px;
    font-size: .73rem;
    color: #8b949e;
    background: rgba(255,255,255,.03);
    cursor: pointer;
    user-select: none;
    font-family: 'IBM Plex Mono', monospace;
    text-transform: uppercase;
    letter-spacing: .06em;
}
.think-block summary:hover { color: #c9d1d9; }
.think-content {
    padding: 8px 10px;
    font-size: .78rem;
    color: #6e7681;
    white-space: pre-wrap;
    font-family: 'IBM Plex Mono', monospace;
    max-height: 160px;
    overflow-y: auto;
    line-height: 1.5;
}

/* Streaming states */
.thinking-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #8b949e;
    font-size: .78rem;
    font-family: 'IBM Plex Mono', monospace;
}
.thinking-indicator::before {
    content: '';
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #22d3ee;
    animation: pulse-dot 1s ease-in-out infinite;
}
.cursor-blink { animation: blink .6s step-end infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

.tutor-error { color: #f87171; font-size: .82rem; }

/* ── Footer (cross-concept + input) ────────────────────────────────────────── */
#tutor-footer {
    flex-shrink: 0;
    border-top: 1px solid rgba(255,255,255,.07);
    background: #161b22;
}
#tutor-cross-row {
    padding: 7px 14px;
    border-bottom: 1px solid rgba(255,255,255,.05);
}
#tutor-cross-row label {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: .73rem;
    color: #8b949e;
    cursor: pointer;
    user-select: none;
}
#tutor-cross-row label:hover { color: #c9d1d9; }
#cross-toggle {
    width: 13px; height: 13px;
    accent-color: #7c3aed;
    cursor: pointer;
}
#tutor-input-row {
    display: flex;
    gap: 8px;
    align-items: flex-end;
    padding: 10px 12px 12px;
}
#tutor-input {
    flex: 1;
    background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 10px;
    color: #e6edf3;
    padding: 8px 12px;
    font-size: .84rem;
    font-family: 'IBM Plex Sans', sans-serif;
    resize: none;
    outline: none;
    line-height: 1.45;
    max-height: 110px;
    overflow-y: auto;
    transition: border-color .15s;
}
#tutor-input:focus  { border-color: #2563eb; }
#tutor-input::placeholder { color: rgba(139,148,158,.5); }
#tutor-send {
    width: 36px; height: 36px;
    border-radius: 9px;
    background: linear-gradient(135deg, #2563eb, #7c3aed);
    border: none;
    color: #fff;
    font-size: 1rem;
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity .15s, transform .1s;
    display: flex; align-items: center; justify-content: center;
}
#tutor-send:hover    { transform: scale(1.05); }
#tutor-send:disabled { opacity: .4; cursor: not-allowed; transform: none; }

/* Responsive */
@media (max-width: 700px) {
    #tutor-sidebar { width: 100vw; right: -100vw; }
    body.tutor-open .wrap { margin-right: 0; }
}
"""

# ─────────────────────────────────────────────────────────────────────────────

TUTOR_JS = r"""
// tutor.js — Study Hub AI Tutor sidebar
// Pairs with tutor_server.py (FastAPI + Ollama deepseek-r1:8b)
(function () {
    'use strict';

    const API         = 'http://localhost:' + (window.TUTOR_PORT || 8000);
    const CONCEPT_ID  = window.TUTOR_CONCEPT_ID    || 'unknown';
    const CONCEPT_TTL = window.TUTOR_CONCEPT_TITLE || document.title;

    let history         = [];   // [{role, content}]
    let mode            = 'professor';
    let crossEnabled    = false;
    let streaming       = false;
    let mastery         = null;
    let speed = 'fast';   // 'fast' | 'accurate'
    let wasMinimized = false;

    const MODELS = { fast: 'deepseek-r1:1.5b', accurate: 'deepseek-r1:8b' };

    const MODES = {
        professor : { label: '🎓 Professor', desc: 'when you know what needs clarifying' },
        socratic  : { label: '🤔 Socratic',  desc: 'when you want to answer first' },
        quiz      : { label: '📝 Quiz',       desc: 'when you want a quick check' },
        boundary  : { label: '🔲 Boundary',   desc: 'when concepts feel too similar' },
        diagnose  : { label: '🩺 Diagnose',   desc: "when you're confused but not sure why" },
    };

    const MODE_GREET = {
        professor : 'Professor mode — ask me to explain any section, term, or idea.',
        socratic  : 'Socratic mode — I\'ll guide you with questions instead of answers.',
        quiz      : 'Quiz mode — say "start" and I\'ll test you. I track your score.',
        boundary  : 'Boundary mode — I\'ll challenge your assumptions and find the edges of your model.',
        diagnose  : 'Diagnosis mode — I\'ll find your exact gaps. Ready when you are.',
    };

    // ── Page content extraction ─────────────────────────────────────────────
    function extractPage() {
        const panel = document.querySelector('.panel');
        if (!panel) return { sections: {}, fullText: '' };

        const sections = {};
        let current = 'Overview';

        Array.from(panel.children).forEach(el => {
            const tag = el.tagName;
            if (tag === 'H1' || tag === 'H2' || tag === 'H3') {
                current = el.textContent.trim();
                if (!sections[current]) sections[current] = '';
            } else {
                if (!sections[current]) sections[current] = '';
                sections[current] += el.textContent.trim() + '\n';
            }
        });

        // Cap each section to avoid blowing context
        Object.keys(sections).forEach(k => {
            sections[k] = sections[k].slice(0, 30000);
        });

        return { sections, fullText: panel.innerText.slice(0, 300000) };
    }

    // ── Rendering helpers ───────────────────────────────────────────────────
    function esc(t) {
        return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function md(text) {
        // Minimal markdown → HTML (bold, italic, code, line breaks)
        return esc(text)
            .replace(/\*\*(.+?)\*\*/g,  '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g,       '<em>$1</em>')
            .replace(/`([^`\n]+)`/g,     '<code>$1</code>')
            .replace(/^#{1,4}\s+(.+)$/gm,'<strong>$1</strong>')
            .replace(/^[-•]\s+(.+)$/gm,  '&bull; $1')
            .replace(/\n{2,}/g,          '<br><br>')
            .replace(/\n/g,              '<br>');
    }

    // During streaming, deepseek-r1 emits <think>...</think> first.
    // We show a compact "reasoning" indicator while inside the block,
    // then a collapsed details element once it closes.
    function renderStreaming(raw) {
        const closeIdx = raw.indexOf('</think>');
        if (raw.startsWith('<think>')) {
            if (closeIdx === -1) {
                // Still inside think block — plain div, always visible
                const thinking = raw.slice(7);
                return (
                    '<div class="think-streaming">' +
                    '<div class="think-streaming-label">🧠 Thinking…</div>' +
                    '<div class="think-content">' + esc(thinking) + '</div>' +
                    '</div>'
                );
            }
            // Think block finished — show open details + response so far
            const thinking = raw.slice(7, closeIdx);
            const response = raw.slice(closeIdx + 8).trim();
            return (
                '<details class="think-block" open>' +
                '<summary>🧠 Reasoning trace</summary>' +
                '<div class="think-content">' + esc(thinking) + '</div>' +
                '</details>' +
                md(response) + '<span class="cursor-blink">▌</span>'
            );
        }
        return md(raw) + '<span class="cursor-blink">▌</span>';
    }

    function renderFinal(raw) {
        const closeIdx = raw.indexOf('</think>');
        if (raw.startsWith('<think>') && closeIdx !== -1) {
            const thinking = raw.slice(7, closeIdx);
            const response = raw.slice(closeIdx + 8).trim();
            return (
                '<details class="think-block" open>' +   // ← add open here too
                '<summary>🧠 Reasoning trace</summary>' +
                '<div class="think-content">' + esc(thinking) + '</div>' +
                '</details>' +
                md(response)
            );
        }
        return md(raw.replace(/<think>[\s\S]*?<\/think>/g, '').trim());
    }

    function thinkHtml(thinking) {
        return (
            '<details class="think-block">' +
            '<summary>🧠 Reasoning trace</summary>' +
            '<div class="think-content">' + esc(thinking) + '</div>' +
            '</details>'
        );
    }

    // ── DOM building ────────────────────────────────────────────────────────
    function buildSidebar() {
        // Toggle pill
        const pill = document.createElement('button');
        pill.id = 'tutor-toggle-btn';
        pill.textContent = 'AI Tutor';
        pill.title = 'Open AI Tutor';
        document.body.appendChild(pill);

        // Sidebar
        const sb = document.createElement('div');
        sb.id = 'tutor-sidebar';
        sb.innerHTML =
            '<div id="tutor-header-wrap">' +
                '<div id="tutor-header">' +
                    '<div id="tutor-title-bar">' +
                        '<div id="tutor-brand"><div id="tutor-brand-dot"></div>AI Tutor</div>' +
                        '<div id="tutor-header-btns">' +
                            '<button id="btn-min" title="Minimise">−</button>' +
                            '<button id="btn-cls" title="Close">×</button>' +
                        '</div>' +
                    '</div>' +
                    '<div id="tutor-header-expandable">' +
                        '<div id="tutor-stats"></div>' +
                        '<div id="tutor-concept-label">' + esc(CONCEPT_TTL) + '</div>' +
                        '<div id="mastery-row">' +
                            '<span id="mastery-lbl">mastery</span>' +
                            '<div id="mastery-track"><div id="mastery-fill"></div></div>' +
                            '<span id="mastery-pct">—</span>' +
                        '</div>' +
                        '<div id="tutor-speed-row">' +
                            '<button class="speed-btn active" id="speed-fast" data-speed="fast">⚡ Fast</button>' +
                            '<button class="speed-btn" id="speed-slow" data-speed="accurate">🧠 Accurate</button>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                '<div id="tutor-modes">' +
                    '<div id="mode-select" tabindex="0">' +
                        '<div id="mode-current">' +
                            '<span id="mode-current-label">🎓 Professor</span>' +
                            '<span class="mode-desc">when you know what needs clarifying</span>' +
                            '<span id="mode-chevron">▾</span>' +
                        '</div>' +
                        '<div id="mode-options">' +
                            Object.entries(MODES).map(([k, v]) =>
                                `<div class="mode-option${k === 'professor' ? ' active' : ''}" data-mode="${k}">` +
                                `${v.label}<span class="mode-desc">${v.desc}</span></div>`
                            ).join('') +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div id="tutor-messages"></div>' +
            '<div id="tutor-footer">' +
                '<div id="tutor-cross-row">' +
                    '<label>' +
                        '<input type="checkbox" id="cross-toggle">' +
                        '🔬 Cross-concept library search' +
                    '</label>' +
                '</div>' +
                '<div id="tutor-input-row">' +
                    '<textarea id="tutor-input" placeholder="Ask anything… or say \'start\' in Quiz mode" rows="2"></textarea>' +
                    '<button id="tutor-send">↑</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(sb);
    }

    // ── Message helpers ─────────────────────────────────────────────────────
    function appendMsg(role, html_content, id) {
        const wrap = document.getElementById('tutor-messages');
        const div  = document.createElement('div');
        div.className = `tutor-msg tutor-msg-${role}`;
        if (id) div.id = id;
        div.innerHTML = html_content;
        wrap.appendChild(div);
        wrap.scrollTop = wrap.scrollHeight;
        return div;
    }

    function scrollMessages() {
        const w = document.getElementById('tutor-messages');
        if (w) w.scrollTop = w.scrollHeight;
    }

    // ── Mastery ─────────────────────────────────────────────────────────────
    async function loadMastery() {
        try {
            const r = await fetch(`${API}/mastery/${CONCEPT_ID}`);
            mastery = await r.json();
            renderMastery();
        } catch { /* server not running yet */ }
    }

    function renderMastery() {
        if (!mastery) return;
        const score = mastery.mastery_score ?? 0.5;
        const pct   = Math.round(score * 100);
        const fill  = document.getElementById('mastery-fill');
        const label = document.getElementById('mastery-pct');
        if (!fill || !label) return;
        fill.style.width      = pct + '%';
        fill.style.background = score < 0.4 ? '#ef4444' : score < 0.7 ? '#f59e0b' : '#22c55e';
        label.textContent     = pct + '%';
    }

    async function patchMastery(correct) {
        try {
            await fetch(`${API}/mastery/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    concept_id: CONCEPT_ID, concept_title: CONCEPT_TTL,
                    correct, mode,
                }),
            });
            await loadMastery();
        } catch {}
    }

    // ── Send / stream ───────────────────────────────────────────────────────
    async function send(userText) {
        userText = userText.trim();
        if (!userText || streaming) return;
        streaming = true;
        document.getElementById('tutor-send').disabled = true;
        document.getElementById('tutor-input').value = '';

        appendMsg('user', md(userText));
        history.push({ role: 'user', content: userText });

        const placeholder = appendMsg('ai', '<span class="thinking-indicator">Thinking…</span>', 'stream-bubble');

        // Build library context if cross-concept enabled
        let libraryCtx = '';
        if (crossEnabled) {
            try {
                const lr  = await fetch(`${API}/library`);
                const ld  = await lr.json();
                libraryCtx = ld.concepts
                    .map(c => `- ${c.concept_title} (mastery ${Math.round((c.mastery_score||0.5)*100)}%)`)
                    .join('\n');
            } catch {}
        }

        const page = extractPage();
        const payload = {
            messages       : history.slice(-14),
            concept_id     : CONCEPT_ID,
            concept_title  : CONCEPT_TTL,
            mode,
            page_sections  : page.sections,
            cross_concept  : crossEnabled,
            library_context: libraryCtx,
            model: MODELS[speed],
        };

        let full = '';

        try {
            const res = await fetch(`${API}/chat`, {
                method : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify(payload),
            });

            if (!res.ok) throw new Error(`Server ${res.status}`);

            const reader  = res.body.getReader();
            const decoder = new TextDecoder();
            let   buf     = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop();

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const payload = line.slice(6);
                    if (payload === '[DONE]') break;
                    try {
                        const chunk = JSON.parse(payload);
                        if (chunk.error) {
                            placeholder.innerHTML = `<span class="tutor-error">⚠ ${esc(chunk.error)}</span>`;
                            streaming = false;
                            document.getElementById('tutor-send').disabled = false;
                            return;
                        }
                        if (chunk.stats) {
                            const s = chunk.stats;
                            document.getElementById('tutor-stats').textContent =
                                `${MODELS[speed]} · ${s.prompt_chars.toLocaleString()} chars · ctx ${s.ctx}`;
                        }
                        if (chunk.content) {
                            full += chunk.content;
                            console.log('[stream chunk]', JSON.stringify(full.slice(0, 80)));
                            placeholder.innerHTML = renderStreaming(full);
                            const tc = placeholder.querySelector('.think-content');
                            if (tc) tc.scrollTop = tc.scrollHeight;
                            scrollMessages();
                        }
                    } catch {}
                }
            }

        } catch (err) {
            placeholder.innerHTML =
                `<span class="tutor-error">⚠ ${esc(err.message)}<br>` +
                `Is tutor_server.py running on port ${window.TUTOR_PORT || 8000}?</span>`;
            streaming = false;
            document.getElementById('tutor-send').disabled = false;
            return;
        }

        // Finalise bubble
        placeholder.removeAttribute('id');
        placeholder.innerHTML = renderFinal(full);
        history.push({ role: 'assistant', content: full });
        scrollMessages();

        // Auto-detect quiz result
        if (mode === 'quiz') {
            const lo = full.toLowerCase();
            if      (lo.includes('correct ✓') || lo.includes('correct!'))   patchMastery(true);
            else if (lo.includes('incorrect ✗') || lo.includes('incorrect.')) patchMastery(false);
        }

        streaming = false;
        document.getElementById('tutor-send').disabled = false;
    }

    // ── Event wiring ────────────────────────────────────────────────────────
    function wire() {
        const sb = document.getElementById('tutor-sidebar');
        const modeSelect  = document.getElementById('mode-select');
        const modeOptions = document.getElementById('mode-options');
        
        document.querySelectorAll('.speed-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                speed = btn.dataset.speed;
            });
        });

        document.getElementById('tutor-toggle-btn').addEventListener('click', () => {
            sb.classList.toggle('open');
            document.body.classList.toggle('tutor-open');
            if (sb.classList.contains('open') && !history.length && !wasMinimized) {
                greet();
            }
            if (sb.classList.contains('open')) {
                wasMinimized = false;   // reset after reopening
            }
        });

        document.getElementById('btn-cls').addEventListener('click', () => {
            wasMinimized = false;
            sb.classList.remove('open');
            document.body.classList.remove('tutor-open');
            // Clear chat state
            history = [];
            document.getElementById('tutor-messages').innerHTML = '';
        });

        document.getElementById('btn-min').addEventListener('click', () => {
            wasMinimized = true;
            sb.classList.remove('open', 'minimized');
            document.body.classList.remove('tutor-open');
        });

        modeSelect.addEventListener('click', e => {
            const opt = e.target.closest('.mode-option');
            if (opt) {
                // Option chosen
                mode = opt.dataset.mode;
                document.getElementById('mode-current-label').textContent = MODES[mode].label;
                document.querySelector('#mode-current .mode-desc').textContent = MODES[mode].desc;
                document.querySelectorAll('.mode-option').forEach(o => o.classList.remove('active'));
                opt.classList.add('active');
                modeOptions.classList.remove('open');
                document.getElementById('mode-chevron').textContent = '▾';
                appendMsg('ai', md(MODE_GREET[mode] || 'Mode switched.'));
            } else {
                // Toggle open/close
                const isOpen = modeOptions.classList.toggle('open');
                document.getElementById('mode-chevron').textContent = isOpen ? '▴' : '▾';
            }
        });

        // Close if clicking outside
        document.addEventListener('click', e => {
            if (!modeSelect.contains(e.target)) {
                modeOptions.classList.remove('open');
                document.getElementById('mode-chevron').textContent = '▾';
            }
        });

        document.getElementById('tutor-send').addEventListener('click', () => {
            send(document.getElementById('tutor-input').value);
        });

        document.getElementById('tutor-input').addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send(document.getElementById('tutor-input').value);
            }
        });

        document.getElementById('cross-toggle').addEventListener('change', e => {
            crossEnabled = e.target.checked;
            appendMsg('ai', crossEnabled
                ? md('🔬 Cross-concept mode **on** — I can now reference your full concept library.')
                : md('Cross-concept mode off — focusing on this page only.'));
        });
    }

    // ── Greeting ────────────────────────────────────────────────────────────
    function greet() {
        const page     = extractPage();
        const sections = Object.keys(page.sections).filter(s => s !== 'Overview');
        const count    = sections.length;

        appendMsg('ai', md(
            `I'm reading **${CONCEPT_TTL}** with you.\n\n` +
            `I can see ${count - 1} section${count !== 1 ? 's' : ''} on this page.\n\n` +
            `Pick a mode above or just ask — I can explain sections, quiz you, ` +
            `stress-test your understanding, or diagnose what to study next.`
        ));
    }

    // ── Boot ─────────────────────────────────────────────────────────────────
    function init() {
        buildSidebar();
        wire();
        loadMastery();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
"""


# ══════════════════════════════════════════════════════════════════════════════
#  EXISTING HELPERS  (unchanged)
# ══════════════════════════════════════════════════════════════════════════════


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    return slug.strip("-") or "document"


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    return escaped


def markdown_to_html(md_text: str) -> str:
    lines = md_text.splitlines()
    parts: list[str] = []
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []
    ol_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            text = " ".join(item.strip() for item in paragraph_buffer if item.strip())
            if text:
                parts.append(f"<p>{inline_markdown(text)}</p>")
            paragraph_buffer.clear()

    def flush_list() -> None:
        if list_buffer:
            items = "\n".join(f"<li>{inline_markdown(item)}</li>" for item in list_buffer)
            parts.append(f"<ul>\n{items}\n</ul>")
            list_buffer.clear()

    def flush_ol() -> None:
        if not ol_buffer:
            return
        if len(ol_buffer) == 1:
            # Single numbered line = bold heading
            num, text = ol_buffer[0]
            parts.append(
                f'<p class="section-label"><strong>{num}. {inline_markdown(text)}</strong></p>'
            )
        else:
            # Consecutive numbered lines = ordered list
            start = ol_buffer[0][0]
            items = "\n".join(f"<li>{inline_markdown(text)}</li>" for _, text in ol_buffer)
            parts.append(f'<ol start="{start}">\n{items}\n</ol>')
        ol_buffer.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_ol()
            continue
        if stripped == "---":
            flush_paragraph()
            flush_list()
            flush_ol()
            parts.append("<hr>")
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            flush_ol()
            parts.append(f"<h3>{inline_markdown(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            flush_ol()
            parts.append(f"<h2>{inline_markdown(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            flush_ol()
            parts.append(f"<h1>{inline_markdown(stripped[2:])}</h1>")
            continue

        list_match = re.match(r"^[-*·]\s+(.*)$", stripped)
        if list_match:
            flush_paragraph()
            flush_ol()
            list_buffer.append(list_match.group(1))
            continue

        bold_heading = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
        if bold_heading:
            flush_paragraph()
            flush_list()
            flush_ol()
            parts.append(
                f'<p class="section-label"><strong>{inline_markdown(bold_heading.group(1))}</strong></p>'
            )
            continue

        ol_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if ol_match:
            flush_paragraph()
            flush_list()
            ol_buffer.append((ol_match.group(1), ol_match.group(2)))
            continue

        flush_list()
        flush_ol()
        paragraph_buffer.append(stripped)

    flush_paragraph()
    flush_list()
    flush_ol()
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDERS
# ══════════════════════════════════════════════════════════════════════════════


def base_html(title: str, body: str, extra_head: str = "") -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0b1020;
      --surface: #121a31;
      --surface-2: #1b2647;
      --text: #eef2ff;
      --muted: #b6c2e2;
      --border: #31406d;
      --link: #9ec5ff;
      --accent: #6aa6ff;
      --accent-2: #84b8ff;
      --heading: #6aa6ff;
      --bold: #e2b86b;
      --shadow: 0 10px 30px rgba(0,0,0,.25);
      --done-bg: #0e2a1a;
      --done-border: #1e5c35;
      --done-text: #6ee8a0;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f6f8fc; --surface: #ffffff; --surface-2: #f0f4fb;
        --text: #18243d; --muted: #53627f; --border: #dbe4f3;
        --link: #0b61ff; --accent: #0b61ff; --accent-2: #2a73ff;
        --shadow: 0 12px 28px rgba(19,35,68,.08);
        --done-bg: #edfbf3; --done-border: #6ee8a0; --done-text: #1a6b3a;
        --heading: #0b61ff;
        --bold: #8a6115;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.65;
    }}
    .wrap {{ max-width: 1000px; margin: 0 auto; padding: 32px 20px 56px; }}
    .panel {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 18px; padding: 28px; box-shadow: var(--shadow);
    }}
    .topbar {{
      display: flex; justify-content: space-between; align-items: center;
      gap: 12px; margin-bottom: 20px; flex-wrap: wrap;
    }}
    .home-btn, .raw-btn {{
      display: inline-block; text-decoration: none; color: white;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      padding: 10px 14px; border-radius: 12px; font-weight: 600; border: none;
    }}
    .raw-btn {{ color: var(--text); background: var(--surface-2); border: 1px solid var(--border); }}
    .meta {{ color: var(--muted); font-size: .95rem; margin-bottom: 18px; }}
    h1, h2, h3 {{ line-height: 1.2; margin-top: 1.4em; margin-bottom: .6em; }}
    h1 {{ font-size: 2rem; margin-top: 0; color: var(--heading); }}
    h2 {{ font-size: 1.35rem; padding-top: .35rem; border-top: 1px solid var(--border); color: var(--heading); }}
    h3 {{ font-size: 1.05rem; color: var(--heading); text-transform: uppercase; letter-spacing: .04em; opacity: .8; }}
    strong {{ color: var(--bold); }}
    .section-label {{ margin-bottom: .2em; }}
    .section-label strong {{ color: var(--heading); font-size: 1.05em; }}
    p, ul {{ margin: .8em 0; }} ul {{ padding-left: 1.35rem; }} li {{ margin: .35em 0; }}
    hr {{ border: 0; border-top: 1px solid var(--border); margin: 1.5rem 0; }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: var(--surface-2); padding: .15em .4em; border-radius: 6px;
      border: 1px solid var(--border); font-size: .95em;
    }}
    a {{ color: var(--link); }}
    .hub-list {{ list-style: none; padding: 0; margin: 1.25rem 0 0; display: grid; gap: 14px; }}
    .hub-item {{ display: flex; align-items: center; gap: 14px; }}
    .concept-checkbox {{
      appearance: none; -webkit-appearance: none; flex-shrink: 0;
      width: 22px; height: 22px; border: 2px solid var(--border);
      border-radius: 7px; background: var(--surface-2); cursor: pointer;
      position: relative; transition: background .15s, border-color .15s;
    }}
    .concept-checkbox:checked {{ background: linear-gradient(135deg,#22c55e,#16a34a); border-color: #16a34a; }}
    .concept-checkbox:checked::after {{
      content: ""; position: absolute; left: 5px; top: 2px;
      width: 7px; height: 11px; border: 2.5px solid #fff;
      border-top: none; border-left: none; transform: rotate(45deg);
    }}
    .concept-checkbox:hover {{ border-color: var(--accent); }}
    .hub-card {{
      display: block; flex: 1; text-decoration: none; color: inherit;
      background: var(--surface-2); border: 1px solid var(--border);
      border-radius: 16px; padding: 18px; transition: transform .12s, border-color .12s;
    }}
    .hub-card:hover {{ transform: translateY(-1px); border-color: var(--accent); }}
    .hub-item.is-done .hub-card {{ background: var(--done-bg); border-color: var(--done-border); }}
    .hub-item.is-done .hub-title {{ color: var(--done-text); text-decoration: line-through; }}
    .hub-item.is-done .hub-sub {{ opacity: .55; }}
    .hub-title {{ font-size: 1.05rem; font-weight: 700; margin-bottom: 6px; }}
    .hub-sub {{ color: var(--muted); font-size: .95rem; }}
    .progress-wrap {{ margin-bottom: 22px; }}
    .progress-label {{
      display: flex; justify-content: space-between;
      font-size: .9rem; color: var(--muted); margin-bottom: 6px;
    }}
    .progress-bar-bg {{
      background: var(--surface-2); border: 1px solid var(--border);
      border-radius: 999px; height: 10px; overflow: hidden;
    }}
    .progress-bar-fill {{
      height: 100%; background: linear-gradient(90deg,#22c55e,#16a34a);
      border-radius: 999px; transition: width .3s ease;
    }}
  </style>
  {extra_head}
</head>
<body>
  <div class="wrap">
    <div class="panel">
      {body}
    </div>
  </div>
</body>
</html>
"""


def build_index_page(title: str, entries: list[dict[str, str]]) -> str:
    cards = []
    for entry in entries:
        key = html.escape(entry["storage_key"])
        cards.append(f"""
<li class="hub-item" id="item-{key}">
  <input type="checkbox" class="concept-checkbox" id="chk-{key}"
         data-key="{key}" aria-label="Mark {html.escape(entry["title"])} as read">
  <a class="hub-card" href="{html.escape(entry["html_filename"])}">
    <div class="hub-title">{html.escape(entry["title"])}</div>
    <div class="hub-sub">{html.escape(entry["md_filename"])}</div>
  </a>
</li>
""")

    total = len(entries)
    body = f"""
<div class="topbar">
  <div>
    <h1 style="margin:0;">{html.escape(title)}</h1>
    <div class="meta">Click a concept to open it. Check the box to mark it as read.</div>
  </div>
</div>
<div class="progress-wrap">
  <div class="progress-label">
    <span>Progress</span>
    <span id="progress-text">0 / {total} completed</span>
  </div>
  <div class="progress-bar-bg">
    <div class="progress-bar-fill" id="progress-fill" style="width:0%"></div>
  </div>
</div>
<ul class="hub-list">
  {"".join(cards)}
</ul>
<script>
(function(){{
  const PREFIX = "studyhub_read__";
  const total  = {total};
  function key(k) {{ return PREFIX + k; }}
  function update() {{
    const n   = document.querySelectorAll(".concept-checkbox:checked").length;
    const pct = total ? Math.round(n/total*100) : 0;
    document.getElementById("progress-text").textContent = n+" / "+total+" completed";
    document.getElementById("progress-fill").style.width  = pct+"%";
  }}
  function setDone(k, done) {{
    const item = document.getElementById("item-"+k);
    if (!item) return;
    item.classList.toggle("is-done", done);
  }}
  document.querySelectorAll(".concept-checkbox").forEach(chk => {{
    const k = chk.dataset.key;
    if (localStorage.getItem(key(k)) === "1") {{ chk.checked = true; setDone(k, true); }}
  }});
  update();
  document.querySelectorAll(".concept-checkbox").forEach(chk => {{
    chk.addEventListener("change", () => {{
      localStorage.setItem(key(chk.dataset.key), chk.checked ? "1" : "0");
      setDone(chk.dataset.key, chk.checked);
      update();
    }});
  }});
}})();
</script>
"""
    return base_html(title, body)


def build_concept_page(
    hub_title: str,
    entry_title: str,
    raw_md_filename: str,
    content_html: str,
    storage_key: str = "",
    tutor_enabled: bool = False,
    tutor_port: int = 8000,
) -> str:
    # Tutor injection — small inline script sets window vars, then loads assets
    tutor_injection = ""
    if tutor_enabled and storage_key:
        safe_title = html.escape(entry_title, quote=True).replace("'", "\\'")
        tutor_injection = (
            f"<script>"
            f'window.TUTOR_CONCEPT_ID="{storage_key}";'
            f'window.TUTOR_CONCEPT_TITLE="{safe_title}";'
            f"window.TUTOR_PORT={tutor_port};"
            f"</script>"
            f'<link rel="stylesheet" href="tutor.css">'
            f'<script src="tutor.js" defer></script>'
        )

    body = f"""
<div class="topbar">
  <a class="home-btn" href="index.html">← Home</a>
  <a class="raw-btn" href="raw/{html.escape(raw_md_filename)}">Open raw markdown</a>
</div>
<div class="meta">{html.escape(hub_title)}</div>
{content_html}
"""
    return base_html(entry_title, body, extra_head=tutor_injection)


# ── Ordering ───────────────────────────────────────────────────────────────────


def sort_entries(entries: list[dict[str, str]], order: list[str]) -> list[dict[str, str]]:
    """Sort by numeric filename prefix (01_, 02_ …) if present, else alphabetically."""

    def sort_key(e: dict) -> tuple:
        stem = e["stem"]
        # Extract leading digits before first underscore
        part = stem.split("_")[0]
        if part.isdigit():
            return (0, int(part), stem)
        return (1, 0, stem)  # no prefix → sort alphabetically after prefixed entries

    return sorted(entries, key=sort_key)


# ── Main build ─────────────────────────────────────────────────────────────────


def build_site(
    input_dir: Path,
    site_dir: Path,
    title: str,
    tutor_enabled: bool = True,
    tutor_port: int = 8000,
) -> None:
    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found in: {input_dir}")

    site_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = site_dir / "raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for html_file in site_dir.glob("*.html"):
        html_file.unlink()

    # Write tutor assets once
    if tutor_enabled:
        (site_dir / "tutor.css").write_text(TUTOR_CSS, encoding="utf-8")
        (site_dir / "tutor.js").write_text(TUTOR_JS, encoding="utf-8")
    else:
        for asset_name in ("tutor.css", "tutor.js"):
            asset_path = site_dir / asset_name
            if asset_path.exists():
                asset_path.unlink()

    entries: list[dict[str, str]] = []

    for md_path in md_files:
        raw_text = md_path.read_text(encoding="utf-8")
        stem = md_path.stem
        html_filename = f"{slugify(stem)}.html"

        title_match = re.search(r"^#\s+(.+)$", raw_text, flags=re.MULTILINE)
        entry_title = (
            title_match.group(1).strip() if title_match else stem.replace("_", " ").title()
        )

        shutil.copy2(md_path, raw_dir / md_path.name)

        concept_html = markdown_to_html(format_section_labels(strip_source_references(raw_text)))
        concept_page = build_concept_page(
            hub_title=title,
            entry_title=entry_title,
            raw_md_filename=md_path.name,
            content_html=concept_html,
            storage_key=slugify(stem),
            tutor_enabled=tutor_enabled,
            tutor_port=tutor_port,
        )
        (site_dir / html_filename).write_text(concept_page, encoding="utf-8")

        entries.append(
            {
                "stem": stem,
                "title": entry_title,
                "html_filename": html_filename,
                "md_filename": md_path.name,
                "storage_key": slugify(stem),
            }
        )

    entries = sort_entries(entries, [])
    index_html = build_index_page(title, entries)
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")


# ── CLI ────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build an HTML study hub from Markdown files.")
    p.add_argument("--input", default="output", help="Directory of .md files")
    p.add_argument(
        "--site-dir",
        default=None,
        help="Output directory. Defaults to the input directory when omitted.",
    )
    p.add_argument("--title", default="NotebookLM Study Hub", help="Hub page title")
    p.add_argument("--tutor-port", default=8000, type=int, help="tutor_server.py port")
    p.add_argument("--no-tutor", action="store_true", help="Disable AI tutor sidebar")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input).resolve()
    site_dir = Path(args.site_dir).resolve() if args.site_dir else input_dir
    build_site(
        input_dir=input_dir,
        site_dir=site_dir,
        title=args.title,
        tutor_enabled=not args.no_tutor,
        tutor_port=args.tutor_port,
    )
    suffix = f" (AI tutor on port {args.tutor_port})" if not args.no_tutor else " (no tutor)"
    print(f"Study hub built: {site_dir / 'index.html'}{suffix}")


if __name__ == "__main__":
    main()
