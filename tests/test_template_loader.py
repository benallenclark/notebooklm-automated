# -----------------------------
# Imports
# -----------------------------
from pathlib import Path

from notebooklm_automation.template_loader import load_prompt_templates


# -----------------------------
# Tests
# -----------------------------
def test_prompt_templates_require_concept_placeholder(tmp_path: Path) -> None:
    prompt_file = tmp_path / "01_test.txt"
    prompt_file.write_text("Hello {concept}", encoding="utf-8")

    templates = load_prompt_templates(tmp_path)

    assert len(templates) == 1
    assert templates[0].render("CIA triad") == "Hello CIA triad"
