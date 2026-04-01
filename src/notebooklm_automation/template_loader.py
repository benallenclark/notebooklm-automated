import csv
from pathlib import Path

from notebooklm_automation.models import Concept, PromptTemplate


def load_concepts(csv_path: Path) -> list[Concept]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Concept CSV not found: {csv_path}")

    concepts: list[Concept] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)

        if "concept" not in (reader.fieldnames or []):
            raise ValueError("Concept CSV must contain a 'concept' column.")

        for row in reader:
            concept_name = (row.get("concept") or "").strip()

            if not concept_name:
                continue

            concepts.append(Concept(name=concept_name))

    if not concepts:
        raise ValueError("No concepts were loaded from the CSV file.")

    return concepts


def _make_title_from_stem(stem: str) -> str:
    """
    Convert a filename stem like:
        01_core_idea
    into:
        Core Idea
    """
    parts = stem.split("_")

    # Remove leading numeric prefix if present
    if parts and parts[0].isdigit():
        parts = parts[1:]

    return " ".join(word.capitalize() for word in parts)


def load_prompt_templates(prompts_dir: Path) -> list[PromptTemplate]:
    if not prompts_dir.exists():
        raise FileNotFoundError(f"Prompts directory not found: {prompts_dir}")

    prompt_files = sorted(prompts_dir.glob("*.txt"))

    if not prompt_files:
        raise ValueError(f"No prompt template files found in: {prompts_dir}")

    templates: list[PromptTemplate] = []

    for file_path in prompt_files:
        raw_text = file_path.read_text(encoding="utf-8").strip()

        if not raw_text:
            raise ValueError(f"Prompt file is empty: {file_path.name}")

        if "{concept}" not in raw_text and "[Concept Name]" not in raw_text:
            raise ValueError(
                f"Prompt file '{file_path.name}' must contain either '{{concept}}' or '[Concept Name]'."
            )

        stem = file_path.stem

        templates.append(
            PromptTemplate(
                key=stem,
                title=_make_title_from_stem(stem),
                filename=file_path.name,
                raw_text=raw_text,
            )
        )

    return templates
