# -----------------------------
# Imports
# -----------------------------
from pathlib import Path

from notebooklm_automation.template_loader import load_concepts, load_prompt_templates


# -----------------------------
# Tests
# -----------------------------
def test_prompt_templates_require_concept_placeholder(tmp_path: Path) -> None:
    prompt_file = tmp_path / "01_test.txt"
    prompt_file.write_text("Hello {concept}", encoding="utf-8")

    templates = load_prompt_templates(tmp_path)

    assert len(templates) == 1
    assert templates[0].render("CIA triad") == "Hello CIA triad"


def test_load_concepts_reads_optional_notebook_id_and_source_ids(tmp_path: Path) -> None:
    csv_path = tmp_path / "concepts.csv"
    csv_path.write_text(
        "concept,notebook_id,source_ids\n"
        'Threat Modeling,nb-123,"src-1, src-2"\n',
        encoding="utf-8",
    )

    concepts = load_concepts(csv_path)

    assert len(concepts) == 1
    assert concepts[0].notebook_id == "nb-123"
    assert concepts[0].source_ids == ["src-1", "src-2"]
