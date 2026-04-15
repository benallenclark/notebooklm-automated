# -----------------------------
# Imports
# -----------------------------
from dataclasses import dataclass
from pathlib import Path
import os
import re
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class AppConfig:
    default_notebook_id: str | None
    source_ids: list[str]
    auth_storage_path: Path
    concepts_csv: Path
    prompts_dir: Path
    output_dir: Path
    logs_dir: Path
    retries: int
    delay_seconds: float


def _resolve_path(raw_value: str, default_value: str) -> Path:
    raw = raw_value.strip() if raw_value else default_value
    path = Path(raw)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def parse_source_ids(raw_value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, (list, tuple)):
        return [str(value).strip() for value in raw_value if str(value).strip()]

    normalized = raw_value.replace("\r", "\n")
    for separator in (",", ";"):
        normalized = normalized.replace(separator, "\n")

    return [line.strip() for line in normalized.split("\n") if line.strip()]


def normalize_notebook_id(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None

    raw = raw_value.strip()
    if not raw:
        return None

    uuid_match = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        raw,
    )
    if uuid_match:
        return uuid_match.group(0)

    if "://" in raw:
        parsed = urlparse(raw)
        query = parse_qs(parsed.query)
        for key in ("notebookId", "notebook_id", "id"):
            values = query.get(key)
            if values and values[0].strip():
                return values[0].strip()

        path_parts = [part for part in parsed.path.split("/") if part]
        if path_parts:
            return path_parts[-1]

    return raw


def load_config(
    *,
    notebook_id: str | None = None,
    source_ids: str | list[str] | tuple[str, ...] | None = None,
    prompts_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    concepts_csv: str | Path | None = None,
) -> AppConfig:
    notebook_id_raw = normalize_notebook_id(notebook_id) if isinstance(notebook_id, str) else notebook_id
    source_ids_raw = source_ids if source_ids is not None else os.getenv("SOURCE_IDS", "")
    prompts_dir_raw = str(prompts_dir).strip() if prompts_dir else os.getenv("PROMPTS_DIR", "")
    output_dir_raw = str(output_dir).strip() if output_dir else os.getenv("OUTPUT_DIR", "")
    concepts_csv_raw = (
        str(concepts_csv).strip() if concepts_csv is not None else os.getenv("CONCEPTS_CSV", "")
    )
    parsed_source_ids = parse_source_ids(source_ids_raw)
    output_dir_path = _resolve_path(output_dir_raw, "output")
    concepts_csv_path = (
        _resolve_path(concepts_csv_raw, "output/concepts.csv")
        if concepts_csv_raw
        else output_dir_path / "concepts.csv"
    )

    return AppConfig(
        default_notebook_id=notebook_id_raw or normalize_notebook_id(os.getenv("DEFAULT_NOTEBOOK_ID")) or None,
        source_ids=parsed_source_ids,
        auth_storage_path=_resolve_path(
            os.getenv("AUTH_STORAGE_PATH", ""),
            ".notebooklm_state/storage_state.json",
        ),
        concepts_csv=concepts_csv_path,
        prompts_dir=_resolve_path(prompts_dir_raw, "prompts/default"),
        output_dir=output_dir_path,
        logs_dir=_resolve_path(os.getenv("LOGS_DIR", ""), "logs"),
        retries=int(os.getenv("RETRIES", "1")),
        delay_seconds=float(os.getenv("DELAY_SECONDS", "2.0")),
    )
