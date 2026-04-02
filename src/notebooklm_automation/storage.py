# -----------------------------
# Imports
# -----------------------------
from datetime import datetime
import json
import re
from pathlib import Path

from notebooklm_automation.models import Concept, PromptTemplate


# -----------------------------
# Naming helpers
# -----------------------------
def slugify(value: str) -> str:
    """
    Convert a concept name into a filesystem-safe file/folder name.
    """
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def build_concept_output_path(output_dir: Path, concept: Concept, position: int = 0) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{position:02d}_" if position > 0 else ""
    return output_dir / f"{prefix}{slugify(concept.name)}.md"


# -----------------------------
# File writing helpers
# -----------------------------
def initialize_concept_file(output_path: Path, concept: Concept) -> None:
    """
    Create or reset the concept output file with a top-level header.
    """
    timestamp = datetime.now().isoformat(timespec="seconds")

    content = f"""# {concept.name}

**Generated:** {timestamp}

---

"""
    output_path.write_text(content, encoding="utf-8")


def append_prompt_section(
    output_path: Path,
    prompt: PromptTemplate,
    rendered_prompt: str,
    answer: str,
) -> None:
    """
    Append one clean answer section to the concept markdown file.
    """
    section = f"""## {prompt.title}

{answer}

---

"""
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(section)


def append_manifest(
    output_dir: Path,
    concept: Concept,
    prompt: PromptTemplate,
    status: str,
    output_path: Path | None,
    error: str | None = None,
) -> None:
    """
    Append one JSON object per line to a manifest file for traceability.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.jsonl"

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "concept": concept.name,
        "prompt_key": prompt.key,
        "prompt_file": prompt.filename,
        "status": status,
        "output_path": str(output_path) if output_path else None,
        "error": error,
    }

    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
