from pathlib import Path

from notebooklm_automation.config import (
    PROJECT_ROOT,
    load_config,
    normalize_notebook_id,
    parse_source_ids,
)
from notebooklm_automation.launcher import build_profile_path, build_site_dir_from_output


def test_load_config_defaults_to_default_prompts_folder() -> None:
    config = load_config()

    assert config.prompts_dir == PROJECT_ROOT / "prompts" / "default"


def test_load_config_accepts_notebook_id_and_source_ids_overrides() -> None:
    config = load_config(
        notebook_id="notebook-123",
        source_ids=["src-1", "src-2"],
    )

    assert config.default_notebook_id == "notebook-123"
    assert config.source_ids == ["src-1", "src-2"]


def test_load_config_uses_relative_output_override() -> None:
    config = load_config(output_dir="output/csci 372")

    assert config.output_dir == PROJECT_ROOT / "output" / "csci 372"
    assert config.concepts_csv == PROJECT_ROOT / "output" / "csci 372" / "concepts.csv"


def test_load_config_uses_relative_prompts_override() -> None:
    config = load_config(prompts_dir="prompts/msse")

    assert config.prompts_dir == PROJECT_ROOT / "prompts" / "msse"


def test_load_config_uses_absolute_output_override(tmp_path: Path) -> None:
    target = tmp_path / "berkeley msse"

    config = load_config(output_dir=target)

    assert config.output_dir == target
    assert config.concepts_csv == target / "concepts.csv"


def test_load_config_uses_absolute_prompts_override(tmp_path: Path) -> None:
    target = tmp_path / "csci-372-prompts"

    config = load_config(prompts_dir=target)

    assert config.prompts_dir == target


def test_load_config_accepts_explicit_concepts_csv_override(tmp_path: Path) -> None:
    concepts_csv = tmp_path / "custom" / "concepts.csv"

    config = load_config(
        output_dir=tmp_path / "berkeley msse",
        concepts_csv=concepts_csv,
    )

    assert config.concepts_csv == concepts_csv


def test_build_profile_path_sanitizes_the_profile_name() -> None:
    profile_path = build_profile_path('csci:372/final?review')

    assert profile_path.name == "csci_372_final_review.json"


def test_parse_source_ids_supports_newlines_and_commas() -> None:
    source_ids = parse_source_ids("aaa,\nbbb\nccc ; ddd")

    assert source_ids == ["aaa", "bbb", "ccc", "ddd"]


def test_normalize_notebook_id_extracts_uuid_from_url() -> None:
    notebook_id = normalize_notebook_id(
        "https://notebooklm.google.com/notebook/123e4567-e89b-12d3-a456-426614174000"
    )

    assert notebook_id == "123e4567-e89b-12d3-a456-426614174000"


def test_build_site_dir_from_output_maps_output_subfolder_to_itself() -> None:
    root = PROJECT_ROOT

    site_dir = build_site_dir_from_output(root, root / "output" / "csci 372")

    assert site_dir == root / "output" / "csci 372"


def test_build_site_dir_from_output_maps_root_output_to_itself() -> None:
    root = PROJECT_ROOT

    site_dir = build_site_dir_from_output(root, root / "output")

    assert site_dir == root / "output"
